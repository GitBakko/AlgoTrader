# MANTIS-EVOLUTION: RL Feature Pipeline Tests
"""Tests for RLFeaturePipeline — no external dependencies required."""
from __future__ import annotations

import numpy as np
import pytest

from src.agents.schemas import MarketContext


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_context(features: dict | None = None) -> MarketContext:
    """Build a MarketContext with the given features dict."""
    base_features = {
        "ema_9": 2000.0,
        "ema_21": 1990.0,
        "rsi_14": 70.0,
        "adx_14": 25.0,
        "macd_histogram": 1.2,
        "bb_upper": 2025.0,
        "bb_lower": 1975.0,
        "bb_middle": 2000.0,
        "atr": 8.0,
        "volume": 1500.0,
        "volume_sma": 1200.0,
        "vwap": 1998.5,
    }
    if features is not None:
        base_features.update(features)
    return MarketContext(epic="XAUUSD", current_price=2000.0, atr=8.0, features=base_features)


# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------

from src.rl.feature_pipeline import RLFeaturePipeline, RL_FEATURE_KEYS  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Basic extraction — returns array of correct length
# ---------------------------------------------------------------------------


def test_extract_features_basic():
    """extract_features() must return a float32 numpy array with len(RL_FEATURE_KEYS) elements."""
    pipeline = RLFeaturePipeline()
    ctx = make_context()
    result = pipeline.extract_features(ctx)

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert result.shape == (len(RL_FEATURE_KEYS),)


# ---------------------------------------------------------------------------
# 2. Missing keys → 0.0 default, no exception
# ---------------------------------------------------------------------------


def test_extract_features_missing_keys():
    """Missing feature keys must default to 0.0 without raising."""
    pipeline = RLFeaturePipeline()
    ctx = MarketContext(epic="XAUUSD", current_price=1800.0, atr=5.0, features={})
    result = pipeline.extract_features(ctx)

    assert result is not None
    assert result.shape == (len(RL_FEATURE_KEYS),)
    # All raw keys (not computed) should be 0.0; computed keys use 0 as well
    # ema_spread: ema_21=0 → denominator 0 → 0.0
    # rsi_normalized: (0-50)/50 = -1.0
    # adx_normalized: 0/50 = 0.0
    assert np.isfinite(result).all()


# ---------------------------------------------------------------------------
# 3. ema_spread computed correctly
# ---------------------------------------------------------------------------


def test_ema_spread_computed():
    """ema_spread = (ema_9 - ema_21) / ema_21."""
    pipeline = RLFeaturePipeline()
    ctx = make_context({"ema_9": 2010.0, "ema_21": 2000.0})
    result = pipeline.extract_features(ctx)

    idx = RL_FEATURE_KEYS.index("ema_spread")
    expected = (2010.0 - 2000.0) / 2000.0  # 0.005
    assert result[idx] == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# 4. rsi_normalized: rsi=70 → 0.4
# ---------------------------------------------------------------------------


def test_rsi_normalized():
    """rsi_normalized = (rsi - 50) / 50; rsi=70 → 0.4."""
    pipeline = RLFeaturePipeline()
    ctx = make_context({"rsi_14": 70.0})
    result = pipeline.extract_features(ctx)

    idx = RL_FEATURE_KEYS.index("rsi_normalized")
    expected = (70.0 - 50.0) / 50.0  # 0.4
    assert result[idx] == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# 5. adx_normalized: adx=25 → 0.5
# ---------------------------------------------------------------------------


def test_adx_normalized():
    """adx_normalized = adx / 50; adx=25 → 0.5."""
    pipeline = RLFeaturePipeline()
    ctx = make_context({"adx_14": 25.0})
    result = pipeline.extract_features(ctx)

    idx = RL_FEATURE_KEYS.index("adx_normalized")
    expected = 25.0 / 50.0  # 0.5
    assert result[idx] == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# 6. normalize_rolling — output shape equals input shape
# ---------------------------------------------------------------------------


def test_normalize_rolling_shape():
    """normalize_rolling() must return an array with the same shape as input."""
    pipeline = RLFeaturePipeline()
    rng = np.random.default_rng(42)
    data = rng.standard_normal((100, 12)).astype(np.float32)

    result = pipeline.normalize_rolling(data, window=50)

    assert result.shape == data.shape
    assert result.dtype == data.dtype or result.dtype in (np.float32, np.float64)


# ---------------------------------------------------------------------------
# 7. normalize_rolling — values roughly centered around 0
# ---------------------------------------------------------------------------


def test_normalize_rolling_centered():
    """After rolling z-score, the mean of later rows should be close to 0."""
    pipeline = RLFeaturePipeline()
    rng = np.random.default_rng(0)
    # Use data with large non-zero mean to verify normalization effect
    data = rng.standard_normal((300, 5)).astype(np.float32) + 100.0

    result = pipeline.normalize_rolling(data, window=100)

    # After 100 warm-up rows the values should be roughly centered
    tail_mean = np.mean(result[200:], axis=0)
    assert np.all(np.abs(tail_mean) < 1.0), f"Mean not near 0: {tail_mean}"


# ---------------------------------------------------------------------------
# 8. add_lag_features — output width = n_cols * (1 + n_lags)
# ---------------------------------------------------------------------------


def test_add_lag_features_width():
    """add_lag_features() must produce n_cols * (1 + n_lags) columns."""
    pipeline = RLFeaturePipeline()
    rng = np.random.default_rng(7)
    data = rng.standard_normal((50, 6)).astype(np.float32)

    lags = [1, 2, 3]
    result = pipeline.add_lag_features(data, lags=lags)

    expected_cols = 6 * (1 + len(lags))
    assert result.shape == (50, expected_cols)


# ---------------------------------------------------------------------------
# 9. add_lag_features — first row has zeros in lag columns
# ---------------------------------------------------------------------------


def test_add_lag_features_first_row_zeros():
    """The lag columns of the first row must be 0 (no prior data)."""
    pipeline = RLFeaturePipeline()
    data = np.ones((10, 3), dtype=np.float32)

    result = pipeline.add_lag_features(data, lags=[1])
    # Columns 3-5 are lag-1 columns; row 0 should be 0
    assert np.all(result[0, 3:] == 0.0)


# ---------------------------------------------------------------------------
# 10. _safe_get with None value → returns default
# ---------------------------------------------------------------------------


def test_safe_get_none_value():
    """_safe_get must return default when the value is None."""
    result = RLFeaturePipeline._safe_get({"key": None}, "key", default=99.0)
    assert result == 99.0


# ---------------------------------------------------------------------------
# 11. _safe_get with missing key → returns default
# ---------------------------------------------------------------------------


def test_safe_get_missing_key():
    """_safe_get must return default when the key is absent."""
    result = RLFeaturePipeline._safe_get({}, "nonexistent", default=42.0)
    assert result == 42.0


# ---------------------------------------------------------------------------
# 12. Custom feature_keys are respected
# ---------------------------------------------------------------------------


def test_custom_feature_keys():
    """Passing custom feature_keys must change the output length."""
    custom_keys = ["ema_9", "rsi_14", "adx_14"]
    pipeline = RLFeaturePipeline(feature_keys=custom_keys)
    ctx = make_context()
    result = pipeline.extract_features(ctx)

    assert result.shape == (3,)
    assert result[0] == pytest.approx(ctx.features["ema_9"], abs=1e-6)
