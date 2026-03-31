"""HMM-based market regime detector with 4-state classification."""

import pickle
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

import numpy as np
import polars as pl
from hmmlearn import hmm
from loguru import logger


class MarketRegime(IntEnum):
    """Market regime classification."""

    TRENDING_UP = 0
    TRENDING_DOWN = 1
    MEAN_REVERTING = 2
    HIGH_VOLATILITY = 3


@dataclass
class RegimeState:
    """Current regime detection result."""

    regime: MarketRegime
    confidence: float  # 0-1
    regime_duration: int
    is_tradeable: bool
    state_probabilities: dict[MarketRegime, float]


class HMMRegimeDetector:
    """Gaussian HMM regime detector with 4 market states."""

    MIN_SAMPLES = 100

    def __init__(
        self,
        n_states: int = 4,
        confidence_threshold: float = 0.65,
        n_iter: int = 200,
    ):
        self.n_states = n_states
        self.confidence_threshold = confidence_threshold
        self.n_iter = n_iter
        self.model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=n_iter,
            random_state=42,
        )
        self.is_fitted = False
        self._state_mapping: dict[int, MarketRegime] = {}
        self._feature_mean: np.ndarray | None = None
        self._feature_std: np.ndarray | None = None

    def _extract_features(self, df: pl.DataFrame) -> np.ndarray:
        """Extract log returns, realized volatility, and volume ratio from OHLCV."""
        close = df["close"].to_numpy().astype(np.float64)

        # Log returns
        log_returns = np.diff(np.log(close))

        # Realized volatility: 20-bar rolling std of log returns
        vol = np.full_like(log_returns, np.nan)
        window = 20
        for i in range(window - 1, len(log_returns)):
            vol[i] = np.std(log_returns[i - window + 1 : i + 1])

        # Volume ratio: current / 20-bar rolling mean
        if "volume" in df.columns:
            volume = df["volume"].to_numpy().astype(np.float64)[1:]  # align with returns
            vol_ratio = np.full_like(volume, np.nan)
            for i in range(window - 1, len(volume)):
                mean_vol = np.mean(volume[i - window + 1 : i + 1])
                vol_ratio[i] = volume[i] / mean_vol if mean_vol > 0 else 1.0
        else:
            vol_ratio = np.ones_like(log_returns)

        # Stack and remove NaN rows
        features = np.column_stack([log_returns, vol, vol_ratio])
        valid_mask = ~np.isnan(features).any(axis=1)
        return features[valid_mask]

    def _normalize(self, features: np.ndarray, fit: bool = False) -> np.ndarray:
        """Z-score normalize features. If fit=True, compute and store stats."""
        if fit:
            self._feature_mean = features.mean(axis=0)
            self._feature_std = features.std(axis=0)
            self._feature_std[self._feature_std < 1e-10] = 1.0
        return (features - self._feature_mean) / self._feature_std

    def _label_states(self, features: np.ndarray, states: np.ndarray) -> dict[int, MarketRegime]:
        """Map HMM state indices to MarketRegime labels."""
        state_stats: dict[int, dict] = {}
        for s in range(self.n_states):
            mask = states == s
            if mask.sum() == 0:
                state_stats[s] = {"mean_return": 0.0, "mean_vol": float("inf")}
            else:
                state_stats[s] = {
                    "mean_return": float(np.mean(features[mask, 0])),
                    "mean_vol": float(np.mean(features[mask, 1])),
                }

        # Highest volatility -> HIGH_VOLATILITY
        sorted_by_vol = sorted(state_stats.items(), key=lambda x: x[1]["mean_vol"], reverse=True)
        high_vol_state = sorted_by_vol[0][0]

        # Remaining states sorted by mean return
        remaining = [s for s, _ in sorted_by_vol[1:]]
        remaining.sort(key=lambda s: state_stats[s]["mean_return"])

        mapping = {high_vol_state: MarketRegime.HIGH_VOLATILITY}
        if len(remaining) >= 3:
            mapping[remaining[0]] = MarketRegime.TRENDING_DOWN
            mapping[remaining[1]] = MarketRegime.MEAN_REVERTING
            mapping[remaining[2]] = MarketRegime.TRENDING_UP
        elif len(remaining) == 2:
            mapping[remaining[0]] = MarketRegime.TRENDING_DOWN
            mapping[remaining[1]] = MarketRegime.TRENDING_UP
        elif len(remaining) == 1:
            mapping[remaining[0]] = MarketRegime.MEAN_REVERTING

        return mapping

    def fit(self, df: pl.DataFrame) -> "HMMRegimeDetector":
        """Fit the HMM on OHLCV data."""
        if len(df) < self.MIN_SAMPLES:
            raise ValueError(f"Need at least {self.MIN_SAMPLES} samples, got {len(df)}")

        raw_features = self._extract_features(df)
        features = self._normalize(raw_features, fit=True)
        logger.info(f"Fitting HMM on {len(features)} feature rows")

        self.model.fit(features)
        states = self.model.predict(features)
        self._state_mapping = self._label_states(raw_features, states)
        self.is_fitted = True

        logger.info(f"HMM fitted. State mapping: {self._state_mapping}")
        return self

    def predict(self, df: pl.DataFrame) -> RegimeState:
        """Predict current regime from recent OHLCV data."""
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        raw_features = self._extract_features(df)
        features = self._normalize(raw_features, fit=False)

        # Get posterior probabilities for the last observation
        log_prob, posteriors = self.model.score_samples(features)
        last_posteriors = posteriors[-1]

        # Map HMM state probabilities to regime probabilities
        state_probs: dict[MarketRegime, float] = {}
        for hmm_state, regime in self._state_mapping.items():
            state_probs[regime] = float(last_posteriors[hmm_state])

        # Fill any missing regimes with 0
        for r in MarketRegime:
            if r not in state_probs:
                state_probs[r] = 0.0

        # Current regime = highest probability
        current_regime = max(state_probs, key=lambda r: state_probs[r])
        confidence = state_probs[current_regime]

        # Compute regime duration (consecutive same-state bars at the end)
        all_states = self.model.predict(features)
        mapped_states = [
            self._state_mapping.get(s, MarketRegime.MEAN_REVERTING) for s in all_states
        ]
        duration = 1
        for i in range(len(mapped_states) - 2, -1, -1):
            if mapped_states[i] == current_regime:
                duration += 1
            else:
                break

        is_tradeable = confidence >= self.confidence_threshold

        return RegimeState(
            regime=current_regime,
            confidence=confidence,
            regime_duration=duration,
            is_tradeable=is_tradeable,
            state_probabilities=state_probs,
        )

    def save(self, path: Path | str) -> None:
        """Persist detector to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "model": self.model,
            "state_mapping": self._state_mapping,
            "is_fitted": self.is_fitted,
            "n_states": self.n_states,
            "confidence_threshold": self.confidence_threshold,
            "n_iter": self.n_iter,
            "feature_mean": self._feature_mean,
            "feature_std": self._feature_std,
        }
        with open(path, "wb") as f:
            pickle.dump(state, f)
        logger.info(f"HMM detector saved to {path}")

    def load(self, path: Path | str) -> "HMMRegimeDetector":
        """Load detector from disk."""
        path = Path(path)
        with open(path, "rb") as f:
            state = pickle.load(f)  # noqa: S301
        self.model = state["model"]
        self._state_mapping = state["state_mapping"]
        self.is_fitted = state["is_fitted"]
        self.n_states = state["n_states"]
        self.confidence_threshold = state["confidence_threshold"]
        self.n_iter = state["n_iter"]
        self._feature_mean = state["feature_mean"]
        self._feature_std = state["feature_std"]
        logger.info(f"HMM detector loaded from {path}")
        return self
