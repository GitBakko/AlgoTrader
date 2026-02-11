"""Tests for target builder module."""

import numpy as np
import polars as pl
import pytest

from src.models.schemas import SignalClass
from src.models.target_builder import TargetBuilder


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """DataFrame with close and ATR columns."""
    n = 100
    close = [100.0 + i * 0.5 for i in range(n)]  # Steady uptrend
    atr = [2.0] * n  # Constant ATR

    return pl.DataFrame({
        "close": close,
        "atr_14": atr,
    })


class TestTargetBuilder:
    def test_creates_target_column(self, sample_df: pl.DataFrame):
        builder = TargetBuilder(horizon_bars=6)
        result = builder.build_targets(sample_df)
        assert "target" in result.columns

    def test_last_rows_are_null(self, sample_df: pl.DataFrame):
        builder = TargetBuilder(horizon_bars=6)
        result = builder.build_targets(sample_df)
        # Last 6 rows should have null target
        last_targets = result["target"].tail(6).to_list()
        assert all(t is None for t in last_targets)

    def test_non_null_count(self, sample_df: pl.DataFrame):
        builder = TargetBuilder(horizon_bars=6)
        result = builder.build_targets(sample_df)
        non_null = result.filter(pl.col("target").is_not_null())
        assert len(non_null) == len(sample_df) - 6

    def test_uptrend_produces_buy_signals(self):
        """Steady uptrend with small ATR should produce BUY."""
        n = 50
        # Each bar gains 2.0, ATR = 1.0, horizon = 5
        # Future change = 5 * 2.0 = 10.0, ATR-relative = 10.0 / 1.0 = 10.0
        # Should be BUY (>0.5)
        close = [100.0 + i * 2.0 for i in range(n)]
        atr = [1.0] * n

        df = pl.DataFrame({"close": close, "atr_14": atr})
        builder = TargetBuilder(horizon_bars=5)
        result = builder.build_targets(df)

        valid = result.filter(pl.col("target").is_not_null())
        buys = valid.filter(pl.col("target") == SignalClass.BUY)
        assert len(buys) > len(valid) * 0.8

    def test_flat_market_produces_hold(self):
        """Flat market should produce HOLD signals."""
        n = 50
        close = [100.0] * n
        atr = [2.0] * n

        df = pl.DataFrame({"close": close, "atr_14": atr})
        builder = TargetBuilder(horizon_bars=5)
        result = builder.build_targets(df)

        valid = result.filter(pl.col("target").is_not_null())
        holds = valid.filter(pl.col("target") == SignalClass.HOLD)
        assert len(holds) == len(valid)  # All should be HOLD

    def test_downtrend_produces_sell_signals(self):
        """Steady downtrend should produce SELL."""
        n = 50
        close = [200.0 - i * 2.0 for i in range(n)]
        atr = [1.0] * n

        df = pl.DataFrame({"close": close, "atr_14": atr})
        builder = TargetBuilder(horizon_bars=5)
        result = builder.build_targets(df)

        valid = result.filter(pl.col("target").is_not_null())
        sells = valid.filter(pl.col("target") == SignalClass.SELL)
        assert len(sells) > len(valid) * 0.8

    def test_missing_atr_raises(self):
        df = pl.DataFrame({"close": [100.0, 101.0]})
        builder = TargetBuilder()
        with pytest.raises(ValueError, match="atr_14"):
            builder.build_targets(df)

    def test_class_distribution(self, sample_df: pl.DataFrame):
        builder = TargetBuilder(horizon_bars=6)
        result = builder.build_targets(sample_df)
        dist = builder.get_class_distribution(result)
        assert isinstance(dist, dict)
        assert sum(dist.values()) == len(sample_df) - 6

    def test_three_classes_only(self, sample_df: pl.DataFrame):
        """Verify only 3 classes are produced (SELL=0, HOLD=1, BUY=2)."""
        builder = TargetBuilder(horizon_bars=6)
        result = builder.build_targets(sample_df)
        valid = result.filter(pl.col("target").is_not_null())
        unique_targets = set(valid["target"].unique().to_list())
        assert unique_targets.issubset({0, 1, 2})
