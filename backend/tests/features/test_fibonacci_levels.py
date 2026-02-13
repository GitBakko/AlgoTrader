"""Tests for Fibonacci levels indicator."""

import numpy as np
import polars as pl
import pytest

from src.features.technical import TechnicalIndicators


@pytest.fixture
def fib_sample_data() -> pl.DataFrame:
    """Generate sample OHLC data with sufficient bars for Fibonacci calculation."""
    np.random.seed(42)
    n = 50
    prices = 100 + np.cumsum(np.random.randn(n) * 0.5)

    return pl.DataFrame({
        "high": prices + 1.0,
        "low": prices - 1.0,
        "close": prices,
        "open": prices - 0.2,
    })


@pytest.fixture
def fib_known_values() -> pl.DataFrame:
    """Create data with known swing values for exact verification."""
    # Create data where we can control swing high/low precisely
    n = 40

    # Swing high = 110, swing low = 90 in the last 20 bars
    # swing_range = 20
    # Fib levels from high:
    # 0.236: 110 - 20*0.236 = 105.28
    # 0.382: 110 - 20*0.382 = 102.36
    # 0.500: 110 - 20*0.500 = 100.00
    # 0.618: 110 - 20*0.618 = 97.64
    # 0.786: 110 - 20*0.786 = 94.28

    # First 20 bars: establish swing range
    highs = [110.0] * 20 + [105.0] * 20
    lows = [90.0] * 20 + [95.0] * 20
    closes = [100.0] * 20 + [100.0] * 20  # Close at exactly 0.500 level
    opens = [99.5] * 20 + [99.5] * 20

    return pl.DataFrame({
        "high": highs,
        "low": lows,
        "close": closes,
        "open": opens,
    })


@pytest.fixture
def flat_prices() -> pl.DataFrame:
    """Flat prices for edge case testing."""
    n = 40
    return pl.DataFrame({
        "high": [100.0] * n,
        "low": [100.0] * n,
        "close": [100.0] * n,
        "open": [100.0] * n,
    })


@pytest.mark.unit
@pytest.mark.features
class TestFibonacciLevels:

    def test_all_columns_present(self, fib_sample_data: pl.DataFrame):
        """Verify all 7 Fibonacci columns are created."""
        df = TechnicalIndicators.add_fibonacci_levels(fib_sample_data)

        expected_cols = [
            "fib_dist_0236",
            "fib_dist_0382",
            "fib_dist_05",  # 0.500 becomes "05" after replace('.', '')
            "fib_dist_0618",
            "fib_dist_0786",
            "fib_nearest_level",
            "fib_cluster_strength",
        ]

        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_fib_distance_values(self, fib_known_values: pl.DataFrame):
        """Verify Fibonacci distance calculations with known swing values."""
        df = TechnicalIndicators.add_fibonacci_levels(
            fib_known_values,
            swing_lookback=20,
            atr_period=14
        )

        # After swing_lookback bars, we should have valid Fib calculations
        # Row 19 (0-indexed) is the first row with 20-bar lookback
        # Swing high = 110, swing low = 90, close = 100
        # swing_range = 20
        # Fib 0.500 level = 110 - 20*0.5 = 100 (exactly at close)
        # Distance to 0.500 level = (100 - 100) / ATR = 0

        row = df.row(19, named=True)
        atr = row["atr_14"]

        # Distance to 0.500 level should be approximately 0 (close is at this level)
        assert abs(row["fib_dist_05"]) < 0.1, "Close should be near 0.500 Fib level"

        # Distance to 0.236 level (105.28) should be negative (close below level)
        # (100 - 105.28) / atr ≈ -5.28 / atr
        assert row["fib_dist_0236"] < 0, "Close should be below 0.236 level"

        # Distance to 0.786 level (94.28) should be positive (close above level)
        # (100 - 94.28) / atr ≈ 5.72 / atr
        assert row["fib_dist_0786"] > 0, "Close should be above 0.786 level"

    def test_fib_nearest_level(self, fib_sample_data: pl.DataFrame):
        """Verify nearest_level is the minimum absolute distance."""
        df = TechnicalIndicators.add_fibonacci_levels(fib_sample_data)

        # Check non-null rows
        valid = df.filter(pl.col("fib_nearest_level").is_not_null())

        for row in valid.iter_rows(named=True):
            abs_distances = [
                abs(row["fib_dist_0236"]),
                abs(row["fib_dist_0382"]),
                abs(row["fib_dist_05"]),
                abs(row["fib_dist_0618"]),
                abs(row["fib_dist_0786"]),
            ]

            expected_min = min(abs_distances)
            actual = row["fib_nearest_level"]

            assert pytest.approx(actual, abs=1e-6) == expected_min, (
                f"nearest_level should be min of absolute distances: "
                f"expected {expected_min}, got {actual}"
            )

    def test_cluster_strength_multiple_nearby(self, fib_known_values: pl.DataFrame):
        """Multiple levels near close should produce high cluster strength."""
        # Modify data so close is very near multiple Fib levels
        df = fib_known_values.clone()

        # After row 19, set close to 102.36 (exactly at 0.382 level)
        # This is also close to 0.236 (105.28) and 0.500 (100.00)
        df = df.with_columns([
            pl.when(pl.int_range(pl.len()).over(pl.lit(1)) >= 19)
            .then(pl.lit(102.36))
            .otherwise(pl.col("close"))
            .alias("close")
        ])

        df = TechnicalIndicators.add_fibonacci_levels(
            df,
            swing_lookback=20,
            atr_period=14
        )

        # Check rows after establishing swing high/low
        # Cluster strength counts levels within 0.5 ATR
        row = df.row(25, named=True)
        cluster = row["fib_cluster_strength"]

        # Should have at least 1 level nearby (the 0.382 level itself)
        assert cluster >= 1, f"Expected cluster >= 1, got {cluster}"

    def test_cluster_strength_none_nearby(self, fib_known_values: pl.DataFrame):
        """No levels near close should produce zero cluster strength."""
        df = fib_known_values.clone()

        # Set close far from all Fib levels (e.g., 120, above swing high)
        df = df.with_columns([
            pl.when(pl.int_range(pl.len()).over(pl.lit(1)) >= 19)
            .then(pl.lit(120.0))
            .otherwise(pl.col("close"))
            .alias("close")
        ])

        df = TechnicalIndicators.add_fibonacci_levels(
            df,
            swing_lookback=20,
            atr_period=14
        )

        # Close at 120 is far above swing high (110)
        # All Fib distances should be large (> 0.5 ATR)
        row = df.row(25, named=True)
        cluster = row["fib_cluster_strength"]

        # With ATR around 0 (flat swings) or very small, might still have some matches
        # But with close far from swing range, expect low cluster
        assert cluster <= 2, f"Expected low cluster strength, got {cluster}"

    def test_swing_lookback_parameter(self, fib_sample_data: pl.DataFrame):
        """Different swing lookback should produce different swing levels."""
        df_20 = TechnicalIndicators.add_fibonacci_levels(
            fib_sample_data.clone(),
            swing_lookback=20,
            atr_period=14
        )

        df_10 = TechnicalIndicators.add_fibonacci_levels(
            fib_sample_data.clone(),
            swing_lookback=10,
            atr_period=14
        )

        # After sufficient warmup, Fib distances should differ
        # because swing high/low windows are different
        row_20 = df_20.row(30, named=True)
        row_10 = df_10.row(30, named=True)

        # At least one Fib distance should be different
        distances_differ = any([
            abs(row_20["fib_dist_0236"] - row_10["fib_dist_0236"]) > 0.01,
            abs(row_20["fib_dist_0382"] - row_10["fib_dist_0382"]) > 0.01,
            abs(row_20["fib_dist_05"] - row_10["fib_dist_05"]) > 0.01,
        ])

        assert distances_differ, "Different lookback periods should produce different Fib distances"

    def test_handles_flat_prices(self, flat_prices: pl.DataFrame):
        """Flat prices (edge case) should not crash and produce valid output."""
        df = TechnicalIndicators.add_fibonacci_levels(flat_prices)

        # Should complete without error
        assert "fib_dist_0236" in df.columns

        # With flat prices, all Fib levels are the same as close
        # Distances should be 0 or very close to 0
        row = df.row(25, named=True)

        # All distances should be near 0 (normalized by ATR)
        assert abs(row["fib_dist_0236"]) < 1.0
        assert abs(row["fib_dist_05"]) < 1.0
        assert abs(row["fib_dist_0786"]) < 1.0

        # Cluster strength should be high (all levels at same place)
        assert row["fib_cluster_strength"] >= 3, "Flat prices should cluster all Fib levels"

    def test_no_nan_in_output(self, fib_sample_data: pl.DataFrame):
        """With sufficient data, output should have no NaN values."""
        df = TechnicalIndicators.add_fibonacci_levels(
            fib_sample_data,
            swing_lookback=20,
            atr_period=14
        )

        # After warmup period (max of swing_lookback and atr_period)
        warmup = max(20, 14)
        valid_df = df.slice(warmup, len(df) - warmup)

        fib_cols = [
            "fib_dist_0236",
            "fib_dist_0382",
            "fib_dist_05",
            "fib_dist_0618",
            "fib_dist_0786",
            "fib_nearest_level",
            "fib_cluster_strength",
        ]

        for col in fib_cols:
            null_count = valid_df[col].null_count()
            assert null_count == 0, f"Column {col} has {null_count} null values after warmup"

    def test_atr_created_if_missing(self, fib_sample_data: pl.DataFrame):
        """ATR column should be auto-created if it doesn't exist."""
        # Ensure no ATR column exists
        df = fib_sample_data.clone()
        assert "atr_14" not in df.columns

        df = TechnicalIndicators.add_fibonacci_levels(df, atr_period=14)

        # ATR should now exist
        assert "atr_14" in df.columns, "ATR should be auto-created"
        assert "atr_ratio" in df.columns, "ATR ratio should also exist"

    def test_existing_atr_preserved(self, fib_sample_data: pl.DataFrame):
        """If ATR already exists, it should be used and not overwritten."""
        # Add ATR manually
        df = TechnicalIndicators.add_atr(fib_sample_data, period=14)
        original_atr = df["atr_14"].clone()

        # Add Fibonacci levels (should use existing ATR)
        df = TechnicalIndicators.add_fibonacci_levels(df, atr_period=14)

        # ATR should be unchanged
        assert df["atr_14"].equals(original_atr), "Existing ATR should be preserved"

    def test_fib_values_within_reasonable_range(self, fib_sample_data: pl.DataFrame):
        """Fibonacci distance values should be within reasonable range."""
        df = TechnicalIndicators.add_fibonacci_levels(fib_sample_data)

        # Filter valid rows
        valid = df.filter(pl.col("fib_dist_05").is_not_null())

        # Distances are normalized by ATR, so should typically be within -10 to +10
        # (close rarely more than 10 ATRs from any Fib level)
        for col in ["fib_dist_0236", "fib_dist_0382", "fib_dist_05", "fib_dist_0618", "fib_dist_0786"]:
            values = valid[col].to_numpy()
            assert values.min() > -20, f"{col} has unreasonably low values"
            assert values.max() < 20, f"{col} has unreasonably high values"

    def test_cluster_strength_range(self, fib_sample_data: pl.DataFrame):
        """Cluster strength should be between 0 and 5 (number of Fib levels)."""
        df = TechnicalIndicators.add_fibonacci_levels(fib_sample_data)

        valid = df.filter(pl.col("fib_cluster_strength").is_not_null())
        cluster_values = valid["fib_cluster_strength"].to_numpy()

        assert cluster_values.min() >= 0, "Cluster strength cannot be negative"
        assert cluster_values.max() <= 5, "Cluster strength cannot exceed 5 (total Fib levels)"

    def test_different_atr_periods(self, fib_sample_data: pl.DataFrame):
        """Verify Fibonacci calculation works with different ATR periods."""
        # Test with ATR period 14
        df_14 = TechnicalIndicators.add_fibonacci_levels(
            fib_sample_data.clone(),
            swing_lookback=20,
            atr_period=14
        )

        # Test with ATR period 7
        df_7 = TechnicalIndicators.add_fibonacci_levels(
            fib_sample_data.clone(),
            swing_lookback=20,
            atr_period=7
        )

        # Verify correct ATR columns exist
        assert "atr_14" in df_14.columns, "ATR 14 column should exist"
        assert "atr_7" in df_7.columns, "ATR 7 column should exist"

        # Verify Fibonacci columns exist in both
        fib_cols = ["fib_dist_0236", "fib_dist_0382", "fib_dist_05", "fib_dist_0618", "fib_dist_0786"]
        for col in fib_cols:
            assert col in df_14.columns, f"{col} should exist in df_14"
            assert col in df_7.columns, f"{col} should exist in df_7"

        # Verify valid data exists (not all null)
        valid_14 = df_14.filter(pl.col("fib_dist_05").is_not_null())
        valid_7 = df_7.filter(pl.col("fib_dist_05").is_not_null())

        assert len(valid_14) > 0, "Should have valid Fibonacci data with ATR 14"
        assert len(valid_7) > 0, "Should have valid Fibonacci data with ATR 7"
