"""Tests for multi-timeframe feature alignment module."""

import polars as pl
import pytest
from datetime import datetime

from src.features.alignment import TimeframeAligner


@pytest.fixture
def base_hourly_df() -> pl.DataFrame:
    """Base 1-hour OHLCV DataFrame with 8 bars."""
    return pl.DataFrame({
        "timestamp": [datetime(2024, 1, 1, h) for h in range(0, 8)],
        "open": [99.0] * 8,
        "high": [101.0] * 8,
        "low": [98.0] * 8,
        "close": [100.0 + i * 0.5 for i in range(8)],
        "volume": [1000] * 8,
    })


@pytest.fixture
def higher_tf_4h_with_features() -> pl.DataFrame:
    """4-hour DataFrame with feature columns (ema_50, rsi_14)."""
    return pl.DataFrame({
        "timestamp": [datetime(2024, 1, 1, 0), datetime(2024, 1, 1, 4)],
        "open": [99.0, 100.0],
        "high": [102.0, 103.0],
        "low": [97.0, 98.0],
        "close": [101.0, 102.0],
        "volume": [5000, 6000],
        "ema_50": [100.5, 101.2],
        "rsi_14": [55.0, 62.0],
    })


class TestTimeframeAlignerAlign:
    def test_basic_alignment_adds_prefixed_columns(
        self, base_hourly_df: pl.DataFrame, higher_tf_4h_with_features: pl.DataFrame
    ):
        """Aligned result should contain prefixed feature columns from higher TF."""
        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": higher_tf_4h_with_features},
            base_timeframe="1h",
        )

        assert "4h_ema_50" in result.columns
        assert "4h_rsi_14" in result.columns
        # Original columns still present
        assert "close" in result.columns
        assert "timestamp" in result.columns

    def test_backward_strategy_forward_fills_values(
        self, base_hourly_df: pl.DataFrame, higher_tf_4h_with_features: pl.DataFrame
    ):
        """Asof join with backward strategy should forward-fill higher TF values."""
        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": higher_tf_4h_with_features},
            base_timeframe="1h",
        )

        ema_values = result["4h_ema_50"].to_list()
        # Hours 0-3 should get the 00:00 value (100.5)
        assert ema_values[0] == 100.5
        assert ema_values[3] == 100.5
        # Hours 4-7 should get the 04:00 value (101.2)
        assert ema_values[4] == 101.2
        assert ema_values[7] == 101.2

    def test_skips_empty_dataframes(self, base_hourly_df: pl.DataFrame):
        """Empty higher TF DataFrames should be silently skipped."""
        empty_df = pl.DataFrame({
            "timestamp": pl.Series([], dtype=pl.Datetime),
            "close": pl.Series([], dtype=pl.Float64),
            "ema_50": pl.Series([], dtype=pl.Float64),
        })

        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": empty_df},
            base_timeframe="1h",
        )

        # Should return base_df unchanged (no new columns)
        assert set(result.columns) == set(base_hourly_df.columns)
        assert len(result) == len(base_hourly_df)

    def test_skips_dataframes_with_no_feature_columns(
        self, base_hourly_df: pl.DataFrame
    ):
        """DataFrames with only OHLCV/metadata columns (no features) should be skipped."""
        ohlcv_only_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1, 0), datetime(2024, 1, 1, 4)],
            "open": [99.0, 100.0],
            "high": [102.0, 103.0],
            "low": [97.0, 98.0],
            "close": [101.0, 102.0],
            "volume": [5000, 6000],
        })

        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": ohlcv_only_df},
            base_timeframe="1h",
        )

        # No new columns should be added
        assert set(result.columns) == set(base_hourly_df.columns)

    def test_multiple_higher_timeframes(self, base_hourly_df: pl.DataFrame):
        """Multiple higher timeframes should all be merged with correct prefixes."""
        tf_4h = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1, 0), datetime(2024, 1, 1, 4)],
            "close": [101.0, 102.0],
            "ema_20": [100.8, 101.5],
        })
        tf_1d = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1, 0)],
            "close": [100.0],
            "sma_50": [99.5],
        })

        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": tf_4h, "1d": tf_1d},
            base_timeframe="1h",
        )

        assert "4h_ema_20" in result.columns
        assert "1d_sma_50" in result.columns
        assert len(result) == len(base_hourly_df)

    def test_row_count_preserved(
        self, base_hourly_df: pl.DataFrame, higher_tf_4h_with_features: pl.DataFrame
    ):
        """Alignment should preserve the exact number of rows from the base DataFrame."""
        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": higher_tf_4h_with_features},
            base_timeframe="1h",
        )

        assert len(result) == len(base_hourly_df)


class TestTimeframeAlignerLookback:
    def test_basic_lookback_calculation(self):
        """4h indicator needing 50 bars requires 50*4+1 = 201 base 1h bars."""
        result = TimeframeAligner.get_required_lookback(
            base_timeframe_minutes=60,
            higher_timeframe_minutes=240,
            indicator_lookback_bars=50,
        )
        assert result == 201  # 50 * (240/60) + 1

    def test_daily_lookback_from_hourly(self):
        """Daily indicator needing 20 bars requires 20*24+1 = 481 base 1h bars."""
        result = TimeframeAligner.get_required_lookback(
            base_timeframe_minutes=60,
            higher_timeframe_minutes=1440,
            indicator_lookback_bars=20,
        )
        assert result == 481  # 20 * (1440/60) + 1

    def test_same_timeframe_lookback(self):
        """Same timeframe ratio=1, so lookback = bars + 1."""
        result = TimeframeAligner.get_required_lookback(
            base_timeframe_minutes=60,
            higher_timeframe_minutes=60,
            indicator_lookback_bars=50,
        )
        assert result == 51  # 50 * 1 + 1
