"""Tests for VWAPBands feature engineering."""

import polars as pl
import pytest

from src.features.vwap_bands import VWAPBands


@pytest.fixture
def sample_ohlcv():
    """Create sample OHLCV data with ~50 rows."""
    n = 50
    from datetime import datetime, timedelta

    base_time = datetime(2024, 1, 1)
    timestamps = [base_time + timedelta(hours=i) for i in range(n)]

    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [2000.0 + i * 0.5 for i in range(n)],
            "high": [2005.0 + i * 0.5 for i in range(n)],
            "low": [1995.0 + i * 0.5 for i in range(n)],
            "close": [2000.0 + i * 0.6 for i in range(n)],
            "volume": [1000.0 + i * 10 for i in range(n)],
        }
    )


@pytest.mark.unit
@pytest.mark.features
class TestVWAPBands:
    """Tests for VWAPBands.add_vwap_bands()."""

    def test_vwap_bands_columns_present(self, sample_ohlcv):
        """All VWAP columns exist after processing."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv)

        expected_cols = [
            "vwap_rolling",
            "vwap_sd",
            "vwap_z_score",
            "vwap_upper_10",
            "vwap_lower_10",
            "vwap_upper_20",
            "vwap_lower_20",
            "vwap_upper_30",
            "vwap_lower_30",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_vwap_rolling_reasonable(self, sample_ohlcv):
        """VWAP is reasonably close to price range."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv)

        # VWAP should be reasonably close to price action
        # (cumulative VWAP can drift outside current bar's range, so we check it's not wildly off)
        vwap = result["vwap_rolling"]
        close = result["close"]
        low = result["low"]
        high = result["high"]

        # Check last 30 rows - VWAP should be within 10% of current close
        for i in range(20, len(result)):
            tolerance = close[i] * 0.10  # 10% tolerance
            assert (
                close[i] - tolerance <= vwap[i] <= close[i] + tolerance
            ), f"VWAP too far from close at row {i}"
            # Also verify VWAP is not null
            assert vwap[i] is not None

    def test_z_score_calculation(self, sample_ohlcv):
        """z_score = (close - vwap) / sd."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv, sd_period=20)

        # Check a sample row (row 30, after warmup)
        close = result["close"][30]
        vwap = result["vwap_rolling"][30]
        sd = result["vwap_sd"][30]
        z_score = result["vwap_z_score"][30]

        if sd > 0:
            expected_z = (close - vwap) / sd
            assert z_score == pytest.approx(expected_z, rel=1e-4)

    def test_upper_above_lower(self, sample_ohlcv):
        """Upper bands > lower bands."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv)

        # Check all SD levels
        for suffix in ["10", "20", "30"]:
            upper = result[f"vwap_upper_{suffix}"]
            lower = result[f"vwap_lower_{suffix}"]

            # Check last 30 rows
            for i in range(20, len(result)):
                assert upper[i] >= lower[i], f"Upper < lower at row {i}, suffix {suffix}"

    def test_wider_bands_with_more_sd(self, sample_ohlcv):
        """upper_30 > upper_20 > upper_10."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv)

        # Check last 30 rows (after warmup)
        for i in range(20, len(result)):
            upper_10 = result["vwap_upper_10"][i]
            upper_20 = result["vwap_upper_20"][i]
            upper_30 = result["vwap_upper_30"][i]

            assert upper_30 >= upper_20 >= upper_10, f"Band order wrong at row {i}"

            lower_10 = result["vwap_lower_10"][i]
            lower_20 = result["vwap_lower_20"][i]
            lower_30 = result["vwap_lower_30"][i]

            assert lower_10 >= lower_20 >= lower_30, f"Lower band order wrong at row {i}"

    def test_no_volume_returns_unchanged(self, sample_ohlcv):
        """No volume column → no change."""
        df_no_volume = sample_ohlcv.drop("volume")
        result = VWAPBands.add_vwap_bands(df_no_volume)

        # Should return unchanged
        assert "vwap_rolling" not in result.columns
        assert len(result.columns) == len(df_no_volume.columns)

    def test_custom_sd_levels(self, sample_ohlcv):
        """Different num_sd parameter."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv, num_sd=[0.5, 1.5, 2.5])

        # Check custom bands exist
        assert "vwap_upper_05" in result.columns
        assert "vwap_lower_05" in result.columns
        assert "vwap_upper_15" in result.columns
        assert "vwap_lower_15" in result.columns
        assert "vwap_upper_25" in result.columns
        assert "vwap_lower_25" in result.columns

        # Default bands should NOT exist
        assert "vwap_upper_10" not in result.columns
        assert "vwap_upper_20" not in result.columns
        assert "vwap_upper_30" not in result.columns

    def test_no_nan_with_sufficient_data(self, sample_ohlcv):
        """Enough rows → no NaN in final rows."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv, sd_period=20)

        # Check last 10 rows (well after warmup)
        last_10 = result.tail(10)

        assert last_10["vwap_rolling"].null_count() == 0
        assert last_10["vwap_sd"].null_count() == 0
        assert last_10["vwap_z_score"].null_count() == 0
        assert last_10["vwap_upper_10"].null_count() == 0
        assert last_10["vwap_lower_10"].null_count() == 0

    def test_zero_volume_returns_unchanged(self, sample_ohlcv):
        """All-zero volume → no change."""
        df_zero_vol = sample_ohlcv.with_columns(pl.lit(0.0).alias("volume"))
        result = VWAPBands.add_vwap_bands(df_zero_vol)

        # Should return unchanged (no volume data)
        assert "vwap_rolling" not in result.columns

    def test_vwap_symmetric_around_bands(self, sample_ohlcv):
        """VWAP should be equidistant from upper and lower bands."""
        result = VWAPBands.add_vwap_bands(sample_ohlcv)

        # Check symmetry for last 20 rows
        for i in range(30, len(result)):
            vwap = result["vwap_rolling"][i]
            upper_10 = result["vwap_upper_10"][i]
            lower_10 = result["vwap_lower_10"][i]

            # Distance to upper and lower should be equal (within floating point precision)
            dist_upper = upper_10 - vwap
            dist_lower = vwap - lower_10

            assert dist_upper == pytest.approx(dist_lower, rel=1e-4)
