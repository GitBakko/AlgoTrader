"""Tests for multi-timeframe feature alignment module."""

from datetime import datetime

import polars as pl
import pytest

from src.features.alignment import TimeframeAligner


@pytest.fixture
def base_hourly_df() -> pl.DataFrame:
    """Base 1-hour OHLCV DataFrame with 8 bars."""
    return pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, h) for h in range(0, 8)],
            "open": [99.0] * 8,
            "high": [101.0] * 8,
            "low": [98.0] * 8,
            "close": [100.0 + i * 0.5 for i in range(8)],
            "volume": [1000] * 8,
        }
    )


@pytest.fixture
def higher_tf_4h_with_features() -> pl.DataFrame:
    """4-hour DataFrame with feature columns (ema_50, rsi_14)."""
    return pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, 0), datetime(2024, 1, 1, 4)],
            "open": [99.0, 100.0],
            "high": [102.0, 103.0],
            "low": [97.0, 98.0],
            "close": [101.0, 102.0],
            "volume": [5000, 6000],
            "ema_50": [100.5, 101.2],
            "rsi_14": [55.0, 62.0],
        }
    )


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

    def test_backward_strategy_uses_only_closed_htf_bars(
        self, base_hourly_df: pl.DataFrame, higher_tf_4h_with_features: pl.DataFrame
    ):
        """Asof join must forward-fill from the last CLOSED higher-TF bar only.

        Timestamps are bar OPENs: the 00:00 4h bar closes at 04:00, the 04:00 bar
        at 08:00. So base bars 00:00-03:00 have NO closed HTF bar yet, and bars
        04:00-07:00 see the 00:00 bar (closed at 04:00). Previously this asserted
        hours 0-3 already saw the 00:00 bar (value 100.5) and hours 4-7 saw the
        04:00 bar (101.2) — that was a ~4h look-ahead leak (fixed 2026-05-28).
        """
        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": higher_tf_4h_with_features},
            base_timeframe="1h",
        )

        ema_values = result["4h_ema_50"].to_list()
        # Hours 0-3: first HTF bar only closes at 04:00 -> no data yet.
        assert ema_values[0] is None
        assert ema_values[3] is None
        # Hours 4-7: see the 00:00 bar (closed at 04:00), NOT the still-forming 04:00 bar.
        assert ema_values[4] == 100.5
        assert ema_values[7] == 100.5

    def test_skips_empty_dataframes(self, base_hourly_df: pl.DataFrame):
        """Empty higher TF DataFrames should be silently skipped."""
        empty_df = pl.DataFrame(
            {
                "timestamp": pl.Series([], dtype=pl.Datetime),
                "close": pl.Series([], dtype=pl.Float64),
                "ema_50": pl.Series([], dtype=pl.Float64),
            }
        )

        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": empty_df},
            base_timeframe="1h",
        )

        # Should return base_df unchanged (no new columns)
        assert set(result.columns) == set(base_hourly_df.columns)
        assert len(result) == len(base_hourly_df)

    def test_skips_dataframes_with_no_feature_columns(self, base_hourly_df: pl.DataFrame):
        """DataFrames with only OHLCV/metadata columns (no features) should be skipped."""
        ohlcv_only_df = pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1, 0), datetime(2024, 1, 1, 4)],
                "open": [99.0, 100.0],
                "high": [102.0, 103.0],
                "low": [97.0, 98.0],
                "close": [101.0, 102.0],
                "volume": [5000, 6000],
            }
        )

        result = TimeframeAligner.align(
            base_df=base_hourly_df,
            higher_tf_dfs={"4h": ohlcv_only_df},
            base_timeframe="1h",
        )

        # No new columns should be added
        assert set(result.columns) == set(base_hourly_df.columns)

    def test_multiple_higher_timeframes(self, base_hourly_df: pl.DataFrame):
        """Multiple higher timeframes should all be merged with correct prefixes."""
        tf_4h = pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1, 0), datetime(2024, 1, 1, 4)],
                "close": [101.0, 102.0],
                "ema_20": [100.8, 101.5],
            }
        )
        tf_1d = pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1, 0)],
                "close": [100.0],
                "sma_50": [99.5],
            }
        )

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


class TestTimeframeAlignerNoLookahead:
    """Explicit look-ahead regression guard (2026-05-28 fix)."""

    @staticmethod
    def _aligned_4h_by_hour() -> dict[int, float | None]:
        base = pl.DataFrame({"timestamp": [datetime(2026, 1, 1, h) for h in range(12)]})
        # 4h bars open-stamped 00/04/08 -> close 04/08/12, each a distinct value.
        tf4 = pl.DataFrame(
            {
                "timestamp": [
                    datetime(2026, 1, 1, 0),
                    datetime(2026, 1, 1, 4),
                    datetime(2026, 1, 1, 8),
                ],
                "feat": [10.0, 20.0, 30.0],
            }
        )
        out = TimeframeAligner.align(base, {"4h": tf4}, base_timeframe="1h")
        return {int(r["timestamp"].hour): r["4h_feat"] for r in out.iter_rows(named=True)}

    def test_no_future_bar_attached(self):
        by_hour = self._aligned_4h_by_hour()
        # 1h@05 is inside the 04->08 bar (feat=20, closes 08:00=future):
        # must use last CLOSED bar = 00->04 (feat=10), never 20.
        assert by_hour[5] == 10.0
        assert by_hour[7] == 10.0
        # 1h@09 inside 08->12 bar (feat=30, closes 12:00): last closed = 04->08 (feat=20).
        assert by_hour[9] == 20.0

    def test_null_before_first_close(self):
        by_hour = self._aligned_4h_by_hour()
        assert by_hour[2] is None
        assert by_hour[3] is None

    def test_update_exactly_at_close_boundary(self):
        by_hour = self._aligned_4h_by_hour()
        assert by_hour[3] is None
        assert by_hour[4] == 10.0  # 00->04 bar available exactly at its 04:00 close
        assert by_hour[7] == 10.0
        assert by_hour[8] == 20.0  # 04->08 bar available exactly at its 08:00 close
