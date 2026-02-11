"""Tests for market regime detector."""

import numpy as np
import polars as pl
import pytest

from src.features.regime import RegimeDetector
from src.features.schemas import MarketRegime


@pytest.fixture
def trending_up_df() -> pl.DataFrame:
    """DataFrame with strong uptrend (high ADX, positive EMA slope)."""
    return pl.DataFrame({
        "adx": [30.0] * 20,
        "ema_50": list(np.linspace(100, 120, 20)),  # Rising EMA
    })


@pytest.fixture
def trending_down_df() -> pl.DataFrame:
    """DataFrame with strong downtrend."""
    return pl.DataFrame({
        "adx": [30.0] * 20,
        "ema_50": list(np.linspace(120, 100, 20)),  # Falling EMA
    })


@pytest.fixture
def ranging_df() -> pl.DataFrame:
    """DataFrame with low ADX (ranging market)."""
    return pl.DataFrame({
        "adx": [15.0] * 20,
        "ema_50": [100.0] * 20,  # Flat EMA
    })


class TestRegimeDetector:
    def test_trending_up(self, trending_up_df: pl.DataFrame):
        detector = RegimeDetector(slope_lookback=5)
        result = detector.detect(trending_up_df)
        assert "regime" in result.columns
        # Later rows should be trending up
        last_regime = result["regime"][-1]
        assert last_regime == MarketRegime.TRENDING_UP.value

    def test_trending_down(self, trending_down_df: pl.DataFrame):
        detector = RegimeDetector(slope_lookback=5)
        result = detector.detect(trending_down_df)
        last_regime = result["regime"][-1]
        assert last_regime == MarketRegime.TRENDING_DOWN.value

    def test_ranging(self, ranging_df: pl.DataFrame):
        detector = RegimeDetector()
        result = detector.detect(ranging_df)
        last_regime = result["regime"][-1]
        assert last_regime == MarketRegime.RANGING.value

    def test_missing_columns_raises(self):
        df = pl.DataFrame({"close": [100.0, 101.0]})
        detector = RegimeDetector()
        with pytest.raises(ValueError, match="adx"):
            detector.detect(df)

    def test_no_temp_columns(self, trending_up_df: pl.DataFrame):
        detector = RegimeDetector(slope_lookback=5)
        result = detector.detect(trending_up_df)
        temp_cols = [c for c in result.columns if c.startswith("_")]
        assert len(temp_cols) == 0
