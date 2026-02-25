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


class TestRegimeHysteresis:
    """Tests for hysteresis-based regime stabilization."""

    def _make_df(
        self,
        adx_values: list[float],
        ema_values: list[float],
    ) -> pl.DataFrame:
        """Helper to create a DataFrame with adx and ema_50 columns."""
        return pl.DataFrame({
            "adx": adx_values,
            "ema_50": ema_values,
        })

    def test_hysteresis_prevents_single_bar_whipsaw(self):
        """A single-bar dip to ranging should NOT change the regime."""
        # 10 bars of trending_up (ADX=30, rising EMA), then 1 bar of
        # ranging (ADX dips to 15), then 4 bars of trending_up again.
        # slope_lookback=1 so EMA slope is just the 1-bar difference.
        n_up1 = 10
        n_dip = 1
        n_up2 = 4
        total = n_up1 + n_dip + n_up2

        # ADX: high everywhere except the dip bar
        adx = [30.0] * n_up1 + [15.0] * n_dip + [30.0] * n_up2

        # EMA: steadily rising so slope is always positive
        ema = list(np.linspace(100, 100 + total, total))

        df = self._make_df(adx, ema)
        detector = RegimeDetector(
            slope_lookback=1,
            hysteresis_bars=3,
        )
        result = detector.detect(df)
        regimes = result["regime"].to_list()

        # The single ranging dip should be smoothed out.
        # After the initial null-slope bar (bar 0), bars 1-9 are trending_up,
        # bar 10 is raw-ranging (ADX dip), bars 11-14 are trending_up.
        # With hysteresis=3, the single ranging bar cannot flip the regime.
        # So from bar 1 onward (once trending_up is established) through
        # the end, regime should stay trending_up.
        # Bar 0 has null slope -> raw = ranging (initial regime).
        # Bars 1-2: raw = trending_up, streak building (1,2).
        # Bar 3: raw = trending_up, streak=3 -> regime switches to trending_up.
        # Bars 3-9: trending_up (stable).
        # Bar 10: raw = ranging (ADX dip), streak=1 for ranging.
        #   Only 1 bar of ranging < 3, so regime stays trending_up.
        # Bars 11-14: raw = trending_up, candidate resets to trending_up.
        #   Regime stays trending_up.
        assert regimes[-1] == MarketRegime.TRENDING_UP.value
        # Verify the dip bar (index 10) also stayed trending_up
        assert regimes[10] == MarketRegime.TRENDING_UP.value

    def test_hysteresis_prevents_two_bar_whipsaw(self):
        """Two consecutive bars of a new regime should NOT switch with hysteresis=3."""
        n_up1 = 10
        n_dip = 2  # Two bars of ranging
        n_up2 = 4
        total = n_up1 + n_dip + n_up2

        adx = [30.0] * n_up1 + [15.0] * n_dip + [30.0] * n_up2
        ema = list(np.linspace(100, 100 + total, total))

        df = self._make_df(adx, ema)
        detector = RegimeDetector(slope_lookback=1, hysteresis_bars=3)
        result = detector.detect(df)
        regimes = result["regime"].to_list()

        # 2 bars of ranging < hysteresis threshold of 3, regime stays trending_up
        assert regimes[10] == MarketRegime.TRENDING_UP.value
        assert regimes[11] == MarketRegime.TRENDING_UP.value
        assert regimes[-1] == MarketRegime.TRENDING_UP.value

    def test_hysteresis_allows_sustained_change(self):
        """Regime DOES change after N consecutive bars of a new regime."""
        # 10 bars of trending_up, then 5 bars of ranging (ADX drops).
        n_up = 10
        n_ranging = 5
        total = n_up + n_ranging

        adx = [30.0] * n_up + [15.0] * n_ranging
        ema = list(np.linspace(100, 100 + total, total))

        df = self._make_df(adx, ema)
        detector = RegimeDetector(slope_lookback=1, hysteresis_bars=3)
        result = detector.detect(df)
        regimes = result["regime"].to_list()

        # After 3 consecutive ranging bars the regime should have switched.
        # Bar 10: ranging streak=1, stays trending_up
        # Bar 11: ranging streak=2, stays trending_up
        # Bar 12: ranging streak=3, switches to ranging!
        # Bars 13-14: ranging (stays)
        assert regimes[10] == MarketRegime.TRENDING_UP.value
        assert regimes[11] == MarketRegime.TRENDING_UP.value
        assert regimes[12] == MarketRegime.RANGING.value
        assert regimes[13] == MarketRegime.RANGING.value
        assert regimes[14] == MarketRegime.RANGING.value

    def test_hysteresis_bars_one_is_immediate(self):
        """With hysteresis_bars=1, regime switches immediately (no smoothing)."""
        # 10 bars trending_up, 1 bar ranging, 4 bars trending_up
        n_up1 = 10
        n_dip = 1
        n_up2 = 4
        total = n_up1 + n_dip + n_up2

        adx = [30.0] * n_up1 + [15.0] * n_dip + [30.0] * n_up2
        ema = list(np.linspace(100, 100 + total, total))

        df = self._make_df(adx, ema)
        detector = RegimeDetector(slope_lookback=1, hysteresis_bars=1)
        result = detector.detect(df)
        regimes = result["regime"].to_list()

        # With hysteresis=1 (no smoothing), the dip bar should be ranging
        assert regimes[10] == MarketRegime.RANGING.value
        # And the bars after should return to trending_up
        assert regimes[11] == MarketRegime.TRENDING_UP.value

    def test_hysteresis_default_is_three(self):
        """Default hysteresis_bars parameter is 3."""
        detector = RegimeDetector()
        assert detector.hysteresis_bars == 3

    def test_hysteresis_zero_clamped_to_one(self):
        """hysteresis_bars=0 is clamped to 1 (no crash, acts like no hysteresis)."""
        detector = RegimeDetector(hysteresis_bars=0)
        assert detector.hysteresis_bars == 1

    def test_hysteresis_preserves_output_length(self, trending_up_df: pl.DataFrame):
        """Hysteresis does not change the number of rows."""
        detector = RegimeDetector(slope_lookback=5, hysteresis_bars=3)
        result = detector.detect(trending_up_df)
        assert len(result) == len(trending_up_df)

    def test_apply_hysteresis_empty_list(self):
        """_apply_hysteresis handles empty input gracefully."""
        detector = RegimeDetector(hysteresis_bars=3)
        assert detector._apply_hysteresis([]) == []

    def test_existing_tests_pass_with_default_hysteresis(
        self, trending_up_df: pl.DataFrame
    ):
        """Existing regime detection still works correctly with default hysteresis."""
        # The default hysteresis=3 should not break steady-state trending_up data
        # because all bars are consistently trending_up.
        detector = RegimeDetector(slope_lookback=5, hysteresis_bars=3)
        result = detector.detect(trending_up_df)
        last_regime = result["regime"][-1]
        assert last_regime == MarketRegime.TRENDING_UP.value
