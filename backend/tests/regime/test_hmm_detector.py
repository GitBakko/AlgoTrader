"""Tests for HMMRegimeDetector."""

import numpy as np
import polars as pl
import pytest

from src.regime.hmm_detector import HMMRegimeDetector, MarketRegime, RegimeState


def _make_trending_data(n: int = 500, direction: float = 1.0, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic trending OHLCV data via cumulative sum with drift."""
    rng = np.random.default_rng(seed)
    drift = direction * 0.002
    noise = rng.normal(0, 0.01, size=n)
    log_prices = np.cumsum(drift + noise)
    prices = 100.0 * np.exp(log_prices)

    high = prices * (1 + rng.uniform(0.001, 0.005, size=n))
    low = prices * (1 - rng.uniform(0.001, 0.005, size=n))
    open_ = prices * (1 + rng.normal(0, 0.001, size=n))
    volume = rng.integers(1000, 5000, size=n).astype(np.float64)

    return pl.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": prices,
            "volume": volume,
        }
    )


def _make_ranging_data(n: int = 500, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic ranging OHLCV data via sine wave + noise."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 8 * np.pi, n)
    prices = 100.0 + 2.0 * np.sin(t) + rng.normal(0, 0.3, size=n)

    high = prices + rng.uniform(0.1, 0.5, size=n)
    low = prices - rng.uniform(0.1, 0.5, size=n)
    open_ = prices + rng.normal(0, 0.1, size=n)
    volume = rng.integers(1000, 5000, size=n).astype(np.float64)

    return pl.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": prices,
            "volume": volume,
        }
    )


class TestHMMRegimeDetector:
    def test_fit_on_historical_data(self):
        """Fits without errors on 500 bars."""
        df = _make_trending_data(500)
        detector = HMMRegimeDetector()
        detector.fit(df)
        assert detector.is_fitted is True

    def test_predict_returns_regime_state(self):
        """Returns a valid RegimeState dataclass."""
        df = _make_trending_data(500)
        detector = HMMRegimeDetector()
        detector.fit(df)
        state = detector.predict(df)

        assert isinstance(state, RegimeState)
        assert isinstance(state.regime, MarketRegime)
        assert 0.0 <= state.confidence <= 1.0
        assert state.regime_duration >= 1
        assert isinstance(state.is_tradeable, bool)
        assert len(state.state_probabilities) == len(MarketRegime)
        assert abs(sum(state.state_probabilities.values()) - 1.0) < 1e-6

    def test_high_confidence_on_clear_trend(self):
        """Strong trend gives confidence > 0.5."""
        df = _make_trending_data(500, direction=1.0, seed=123)
        detector = HMMRegimeDetector()
        detector.fit(df)
        state = detector.predict(df)

        assert state.confidence > 0.5

    def test_tradeable_flag_respects_threshold(self):
        """is_tradeable=False when threshold exceeds any possible confidence."""
        df = _make_ranging_data(500)
        detector = HMMRegimeDetector(confidence_threshold=1.0)
        detector.fit(df)
        state = detector.predict(df)

        # Confidence is always < 1.0, so threshold=1.0 makes it untradeable
        assert state.confidence < 1.0
        assert state.is_tradeable is False

    def test_save_and_load(self, tmp_path):
        """Persist and reload, same predictions."""
        df = _make_trending_data(500)
        detector = HMMRegimeDetector()
        detector.fit(df)
        state_before = detector.predict(df)

        save_path = tmp_path / "hmm_model.pkl"
        detector.save(save_path)

        loaded = HMMRegimeDetector()
        loaded.load(save_path)
        state_after = loaded.predict(df)

        assert state_before.regime == state_after.regime
        assert abs(state_before.confidence - state_after.confidence) < 1e-6

    def test_predict_on_unfitted_raises(self):
        """Raises RuntimeError if not fitted."""
        df = _make_trending_data(500)
        detector = HMMRegimeDetector()

        with pytest.raises(RuntimeError, match="not fitted"):
            detector.predict(df)

    def test_minimum_data_required(self):
        """Raises ValueError on <100 samples."""
        df = _make_trending_data(50)
        detector = HMMRegimeDetector()

        with pytest.raises(ValueError, match="at least 100"):
            detector.fit(df)
