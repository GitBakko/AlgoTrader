# MANTIS-EVOLUTION: RL Feature Pipeline
"""Feature normalization for RL observation vectors."""
from __future__ import annotations

import numpy as np
from loguru import logger

from src.agents.schemas import MarketContext


# Top features used for RL observation (subset of MANTIS 220+ features)
RL_FEATURE_KEYS = [
    "ema_9", "ema_21", "rsi_14", "adx_14", "macd_histogram",
    "bb_upper", "bb_lower", "bb_middle", "atr",
    "volume", "volume_sma", "vwap",
    "ema_spread",       # computed: (ema_9 - ema_21) / ema_21
    "rsi_normalized",   # computed: (rsi - 50) / 50
    "adx_normalized",   # computed: adx / 50
]


class RLFeaturePipeline:
    """
    Extracts and normalizes features for the RL observation vector.
    All features are prefixed with 'rl_' when stored (for distinction from
    XGBoost features).
    """

    def __init__(self, feature_keys: list[str] | None = None) -> None:
        self.feature_keys: list[str] = feature_keys or RL_FEATURE_KEYS

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def extract_features(self, context: MarketContext) -> np.ndarray:
        """
        Extract normalized feature vector from MarketContext.

        Returns array of shape (n_features,) with dtype float32.
        """
        features = context.features
        result: list[float] = []

        for key in self.feature_keys:
            if key == "ema_spread":
                ema_9 = self._safe_get(features, "ema_9")
                ema_21 = self._safe_get(features, "ema_21")
                val = (ema_9 - ema_21) / ema_21 if ema_21 != 0.0 else 0.0
            elif key == "rsi_normalized":
                rsi = self._safe_get(features, "rsi_14")
                val = (rsi - 50.0) / 50.0
            elif key == "adx_normalized":
                adx = self._safe_get(features, "adx_14")
                val = adx / 50.0
            else:
                val = self._safe_get(features, key)

            result.append(val)

        return np.array(result, dtype=np.float32)

    def normalize_rolling(
        self, features_2d: np.ndarray, window: int = 200
    ) -> np.ndarray:
        """
        Rolling z-score normalization on a 2D feature array.

        Used for training data preparation.  For each row i the z-score is
        computed over the preceding ``window`` rows (inclusive).
        """
        n_rows, n_cols = features_2d.shape
        normalized = np.zeros_like(features_2d)

        for i in range(n_rows):
            start = max(0, i - window + 1)
            window_data = features_2d[start : i + 1]
            mean = np.mean(window_data, axis=0)
            std = np.std(window_data, axis=0)
            std[std < 1e-8] = 1.0  # avoid division by zero
            normalized[i] = (features_2d[i] - mean) / std

        return normalized

    def add_lag_features(
        self,
        features_2d: np.ndarray,
        lags: list[int] | None = None,
    ) -> np.ndarray:
        """
        Add lag features (t-1, t-2, t-3 by default) for each column.

        Returns a wider array with shape (n_rows, n_cols * (1 + n_lags)).
        Rows without enough history are filled with zeros.
        """
        if lags is None:
            lags = [1, 2, 3]

        n_rows, _ = features_2d.shape
        all_features: list[np.ndarray] = [features_2d]

        for lag in lags:
            lagged = np.zeros_like(features_2d)
            if lag > 0 and lag < n_rows:
                lagged[lag:] = features_2d[:-lag]
            all_features.append(lagged)

        return np.hstack(all_features)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_get(features: dict, key: str, default: float = 0.0) -> float:
        """Safely get a float from a features dict; returns *default* on any error."""
        val = features.get(key, default)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
