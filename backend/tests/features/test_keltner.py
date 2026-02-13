"""Tests for Keltner Channel indicator."""

import numpy as np
import polars as pl
import pytest

from src.features.keltner import KeltnerChannel
from src.features.technical import TechnicalIndicators


@pytest.fixture
def sample_ohlc() -> pl.DataFrame:
    """Generate synthetic OHLC data for testing."""
    np.random.seed(42)
    n = 100

    # Generate price data with some volatility
    base = 100.0
    close = base + np.random.normal(0, 2, n).cumsum()
    high = close + np.abs(np.random.normal(1, 0.5, n))
    low = close - np.abs(np.random.normal(1, 0.5, n))

    return pl.DataFrame({
        "timestamp": pl.datetime_range(
            pl.datetime(2024, 1, 1),
            pl.datetime(2024, 1, 1) + pl.duration(hours=n - 1),
            interval="1h",
            eager=True,
        ),
        "open": close + np.random.normal(0, 0.5, n),
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(np.int64),
    })


@pytest.fixture
def sample_squeeze_data() -> pl.DataFrame:
    """Generate data with a known squeeze pattern."""
    np.random.seed(123)
    n = 50

    # Create a ranging pattern followed by a breakout
    price = np.concatenate([
        np.full(20, 100.0) + np.random.normal(0, 0.5, 20),  # Tight range
        np.linspace(100, 110, 30) + np.random.normal(0, 1, 30),  # Breakout
    ])

    return pl.DataFrame({
        "timestamp": pl.datetime_range(
            pl.datetime(2024, 1, 1),
            pl.datetime(2024, 1, 1) + pl.duration(hours=n - 1),
            interval="1h",
            eager=True,
        ),
        "open": price + np.random.normal(0, 0.3, n),
        "high": price + np.abs(np.random.normal(0.5, 0.2, n)),
        "low": price - np.abs(np.random.normal(0.5, 0.2, n)),
        "close": price,
        "volume": np.random.randint(1000, 5000, n).astype(np.int64),
    })


@pytest.mark.unit
@pytest.mark.features
class TestKeltnerChannel:
    """Tests for Keltner Channel indicator calculations."""

    def test_keltner_columns_present(self, sample_ohlc: pl.DataFrame):
        """Verify that add_keltner adds the expected columns."""
        df = KeltnerChannel.add_keltner(sample_ohlc)

        assert "kc_upper" in df.columns
        assert "kc_middle" in df.columns
        assert "kc_lower" in df.columns

        # All columns should have same length as input
        assert len(df) == len(sample_ohlc)

    def test_kc_upper_above_middle(self, sample_ohlc: pl.DataFrame):
        """Verify that KC upper band is always above middle line."""
        df = KeltnerChannel.add_keltner(sample_ohlc)

        # Filter out initial NaN values
        valid_rows = df.filter(
            pl.col("kc_upper").is_not_null() & pl.col("kc_middle").is_not_null()
        )

        assert len(valid_rows) > 0
        assert (valid_rows["kc_upper"] > valid_rows["kc_middle"]).all()

    def test_kc_lower_below_middle(self, sample_ohlc: pl.DataFrame):
        """Verify that KC lower band is always below middle line."""
        df = KeltnerChannel.add_keltner(sample_ohlc)

        valid_rows = df.filter(
            pl.col("kc_lower").is_not_null() & pl.col("kc_middle").is_not_null()
        )

        assert len(valid_rows) > 0
        assert (valid_rows["kc_lower"] < valid_rows["kc_middle"]).all()

    def test_kc_multiplier_affects_width(self, sample_ohlc: pl.DataFrame):
        """Verify that larger multiplier creates wider channel."""
        df1 = KeltnerChannel.add_keltner(sample_ohlc.clone(), multiplier=1.0)
        df2 = KeltnerChannel.add_keltner(sample_ohlc.clone(), multiplier=2.0)

        # Calculate channel widths
        width1 = (df1["kc_upper"] - df1["kc_lower"]).tail(50).mean()
        width2 = (df2["kc_upper"] - df2["kc_lower"]).tail(50).mean()

        assert width2 > width1
        # Should be approximately 2x wider (allowing for EMA differences)
        assert width2 / width1 > 1.8

    def test_kc_middle_is_ema(self, sample_ohlc: pl.DataFrame):
        """Verify that KC middle line equals EMA of close."""
        ema_period = 20
        df = KeltnerChannel.add_keltner(sample_ohlc, ema_period=ema_period)

        # Calculate EMA manually for comparison
        df_with_ema = sample_ohlc.with_columns(
            pl.col("close").ewm_mean(span=ema_period, ignore_nulls=True).alias("expected_ema")
        )

        # Join with keltner results
        comparison = df_with_ema.join(
            df.select(["timestamp", "kc_middle"]),
            on="timestamp",
            how="inner",
        )

        # Filter valid rows and compare
        valid = comparison.filter(
            pl.col("kc_middle").is_not_null() & pl.col("expected_ema").is_not_null()
        )

        assert len(valid) > 0
        actual = valid["kc_middle"].to_numpy()
        expected = valid["expected_ema"].to_numpy()

        np.testing.assert_allclose(actual, expected, rtol=1e-10)


@pytest.mark.unit
@pytest.mark.features
class TestTrueSqueeze:
    """Tests for true squeeze detection functionality."""

    def test_true_squeeze_columns(self, sample_ohlc: pl.DataFrame):
        """Verify that add_true_squeeze adds the expected columns."""
        df = KeltnerChannel.add_true_squeeze(sample_ohlc)

        assert "squeeze_on" in df.columns
        assert "squeeze_off" in df.columns
        assert "squeeze_momentum" in df.columns

        # Should also have BB and KC columns
        assert "bb_upper" in df.columns
        assert "bb_lower" in df.columns
        assert "kc_upper" in df.columns
        assert "kc_lower" in df.columns

    def test_squeeze_on_detection(self, sample_squeeze_data: pl.DataFrame):
        """Verify that squeeze_on is 1 when BB is inside KC."""
        df = KeltnerChannel.add_true_squeeze(sample_squeeze_data)

        # Check squeeze_on values are binary
        assert df["squeeze_on"].is_in([0, 1]).all()

        # In squeeze: BB upper < KC upper AND BB lower > KC lower
        squeeze_rows = df.filter(pl.col("squeeze_on") == 1)
        if len(squeeze_rows) > 0:
            assert (squeeze_rows["bb_upper"] < squeeze_rows["kc_upper"]).all()
            assert (squeeze_rows["bb_lower"] > squeeze_rows["kc_lower"]).all()

        # Not in squeeze: opposite condition
        non_squeeze_rows = df.filter(pl.col("squeeze_on") == 0)
        if len(non_squeeze_rows) > 0:
            # At least one condition should be false
            condition_met = (
                (non_squeeze_rows["bb_upper"] >= non_squeeze_rows["kc_upper"])
                | (non_squeeze_rows["bb_lower"] <= non_squeeze_rows["kc_lower"])
            )
            assert condition_met.all()

    def test_squeeze_off_detection(self, sample_squeeze_data: pl.DataFrame):
        """Verify that squeeze_off detects transition from squeeze to non-squeeze."""
        df = KeltnerChannel.add_true_squeeze(sample_squeeze_data)

        # squeeze_off should be 1 only when: current squeeze_on=0 AND previous squeeze_on=1
        squeeze_off_rows = df.filter(pl.col("squeeze_off") == 1)

        for idx in squeeze_off_rows.select(pl.lit(range(len(df)))).to_series().to_list():
            actual_idx = df.filter(pl.col("squeeze_off") == 1).select(
                pl.lit(range(len(df)))
            ).to_series().to_list().index(idx)

            # Get the row indices in the filtered dataframe
            all_indices = list(range(len(df)))
            off_indices = [i for i, val in enumerate(df["squeeze_off"].to_list()) if val == 1]

            for off_idx in off_indices:
                if off_idx > 0:  # Can't check previous for first row
                    assert df["squeeze_on"][off_idx] == 0
                    assert df["squeeze_on"][off_idx - 1] == 1

    def test_squeeze_momentum_direction(self, sample_squeeze_data: pl.DataFrame):
        """Verify that squeeze_momentum reflects MACD direction at release."""
        # Add MACD first
        df = TechnicalIndicators.add_macd(sample_squeeze_data)
        df = KeltnerChannel.add_true_squeeze(df)

        # squeeze_momentum should be non-zero only when squeeze_off == 1
        momentum_nonzero = df.filter(pl.col("squeeze_momentum") != 0)
        if len(momentum_nonzero) > 0:
            assert (momentum_nonzero["squeeze_off"] == 1).all()

        # When squeeze_off == 1:
        # - squeeze_momentum should be 1 if macd_histogram > 0
        # - squeeze_momentum should be -1 if macd_histogram < 0
        squeeze_releases = df.filter(pl.col("squeeze_off") == 1)
        for row in squeeze_releases.iter_rows(named=True):
            macd_hist = row.get("macd_histogram", 0)
            momentum = row.get("squeeze_momentum", 0)

            if macd_hist > 0:
                assert momentum == 1, f"MACD > 0 but momentum = {momentum}"
            elif macd_hist < 0:
                assert momentum == -1, f"MACD < 0 but momentum = {momentum}"

    def test_squeeze_without_macd(self, sample_ohlc: pl.DataFrame):
        """Verify that squeeze detection works even without MACD (momentum = 0)."""
        # Don't add MACD - should still work
        df = KeltnerChannel.add_true_squeeze(sample_ohlc)

        assert "squeeze_momentum" in df.columns
        # Without MACD, momentum should always be 0
        assert (df["squeeze_momentum"] == 0).all()

    def test_keltner_idempotent(self, sample_ohlc: pl.DataFrame):
        """Verify that calling add_keltner twice doesn't duplicate or corrupt data."""
        df1 = KeltnerChannel.add_keltner(sample_ohlc.clone())
        df2 = KeltnerChannel.add_keltner(df1.clone())

        # Should have same values
        assert df1["kc_upper"].equals(df2["kc_upper"])
        assert df1["kc_middle"].equals(df2["kc_middle"])
        assert df1["kc_lower"].equals(df2["kc_lower"])
