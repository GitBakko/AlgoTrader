"""
Unit tests for data quality checks.
"""

from datetime import datetime, timedelta

import polars as pl
import pytest

from src.data.models import DataSource
from src.data.quality_checks import DataQualityChecker


def make_ohlc_df(
    num_candles: int = 100,
    start_date: datetime | None = None,
    epic: str = "XAUUSD",
    timeframe: str = "1h",
    base_price: float = 2000.0,
    interval_hours: float = 1.0,
) -> pl.DataFrame:
    """Create a valid OHLC DataFrame for testing."""
    if start_date is None:
        start_date = datetime(2024, 1, 1)

    rows = []
    for i in range(num_candles):
        price = base_price + (i % 50) * 0.5
        rows.append({
            "timestamp": start_date + timedelta(hours=interval_hours * i),
            "open": price,
            "high": price + 2.0,
            "low": price - 1.5,
            "close": price + 0.5,
            "volume": 1000 + i * 10,
            "epic": epic,
            "timeframe": timeframe,
            "source": DataSource.HISTORICAL,
        })

    return pl.DataFrame(rows)


@pytest.fixture
def checker():
    return DataQualityChecker(outlier_std_threshold=5.0)


@pytest.mark.unit
class TestValidateOHLC:
    """Test OHLC validation."""

    def test_valid_data_passes(self, checker):
        df = make_ohlc_df()
        errors = checker.validate_ohlc(df)
        assert errors == []

    def test_high_less_than_low(self, checker):
        df = make_ohlc_df(num_candles=10)
        # Inject bad candle: high < low
        df = df.with_columns(
            pl.when(pl.col("timestamp") == df["timestamp"][5])
            .then(pl.lit(1990.0))
            .otherwise(pl.col("high"))
            .alias("high")
        )
        errors = checker.validate_ohlc(df)
        assert any("high < open/close/low" in e for e in errors)

    def test_negative_price(self, checker):
        df = make_ohlc_df(num_candles=10)
        df = df.with_columns(
            pl.when(pl.col("timestamp") == df["timestamp"][3])
            .then(pl.lit(-1.0))
            .otherwise(pl.col("open"))
            .alias("open")
        )
        errors = checker.validate_ohlc(df)
        assert any("non-positive prices" in e for e in errors)

    def test_negative_volume(self, checker):
        df = make_ohlc_df(num_candles=10)
        df = df.with_columns(
            pl.when(pl.col("timestamp") == df["timestamp"][2])
            .then(pl.lit(-100))
            .otherwise(pl.col("volume"))
            .alias("volume")
        )
        errors = checker.validate_ohlc(df)
        assert any("negative volume" in e for e in errors)


@pytest.mark.unit
class TestDuplicateDetection:
    """Test duplicate timestamp detection."""

    def test_no_duplicates(self, checker):
        df = make_ohlc_df()
        assert checker.count_duplicates(df) == 0

    def test_with_duplicates(self, checker):
        df = make_ohlc_df(num_candles=10)
        # Duplicate first row
        dup = df.head(1)
        df = pl.concat([df, dup])
        assert checker.count_duplicates(df) == 1


@pytest.mark.unit
class TestGapDetection:
    """Test gap detection."""

    def test_no_gaps(self, checker):
        df = make_ohlc_df(num_candles=50)
        gaps = checker.detect_gaps(df, "XAUUSD", "1h")
        assert len(gaps) == 0

    def test_detects_gap(self, checker):
        # Create data with a 5-hour gap in the middle (Tuesday)
        df1 = make_ohlc_df(num_candles=20, start_date=datetime(2024, 1, 2))
        df2 = make_ohlc_df(
            num_candles=20,
            start_date=datetime(2024, 1, 3, 1),  # 5-hour gap after last candle of df1
        )
        df = pl.concat([df1, df2])
        gaps = checker.detect_gaps(df, "XAUUSD", "1h")
        assert len(gaps) > 0
        assert gaps[0].expected_candles >= 4

    def test_weekend_gap_ignored_for_forex(self, checker):
        # Create data ending Friday, resuming Monday
        friday = datetime(2024, 1, 5, 20)  # Friday evening
        monday = datetime(2024, 1, 8, 1)  # Monday morning
        df1 = make_ohlc_df(num_candles=5, start_date=friday)
        df2 = make_ohlc_df(num_candles=5, start_date=monday)
        df = pl.concat([df1, df2])
        gaps = checker.detect_gaps(df, "XAUUSD", "1h")
        # Weekend gap should be filtered out for non-crypto
        assert len(gaps) == 0

    def test_weekend_gap_counted_for_btc(self, checker):
        friday = datetime(2024, 1, 5, 20)
        monday = datetime(2024, 1, 8, 1)
        df1 = make_ohlc_df(num_candles=5, start_date=friday, epic="BTCUSD")
        df2 = make_ohlc_df(num_candles=5, start_date=monday, epic="BTCUSD")
        df = pl.concat([df1, df2])
        gaps = checker.detect_gaps(df, "BTCUSD", "1h")
        # BTC trades 24/7, so weekend gap should be detected
        assert len(gaps) > 0

    def test_single_candle_no_error(self, checker):
        df = make_ohlc_df(num_candles=1)
        gaps = checker.detect_gaps(df, "XAUUSD", "1h")
        assert len(gaps) == 0


@pytest.mark.unit
class TestOutlierDetection:
    """Test outlier detection."""

    def test_no_outliers_in_normal_data(self, checker):
        df = make_ohlc_df(num_candles=100)
        outliers = checker.detect_outliers(df)
        assert len(outliers) == 0

    def test_detects_extreme_outlier(self, checker):
        df = make_ohlc_df(num_candles=100, base_price=2000.0)
        # Inject extreme outlier
        df = df.with_columns(
            pl.when(pl.col("timestamp") == df["timestamp"][50])
            .then(pl.lit(9999.0))
            .otherwise(pl.col("close"))
            .alias("close")
        )
        df = df.with_columns(
            pl.when(pl.col("timestamp") == df["timestamp"][50])
            .then(pl.lit(9999.0))
            .otherwise(pl.col("high"))
            .alias("high")
        )
        outliers = checker.detect_outliers(df)
        assert len(outliers) >= 1

    def test_too_few_candles_no_outliers(self, checker):
        df = make_ohlc_df(num_candles=5)
        outliers = checker.detect_outliers(df)
        assert len(outliers) == 0


@pytest.mark.unit
class TestRunAllChecks:
    """Test run_all_checks integration."""

    def test_clean_data_passes(self, checker):
        df = make_ohlc_df(num_candles=100)
        report = checker.run_all_checks(df, "XAUUSD", "1h")
        assert report.passed is True
        assert report.total_candles == 100
        assert report.gaps_found == 0
        assert report.validation_errors == []

    def test_empty_data_fails(self, checker):
        df = make_ohlc_df(num_candles=0)
        report = checker.run_all_checks(df, "XAUUSD", "1h")
        assert report.passed is False
        assert report.total_candles == 0

    def test_bad_data_fails(self, checker):
        df = make_ohlc_df(num_candles=50)
        # Inject bad price
        df = df.with_columns(
            pl.when(pl.col("timestamp") == df["timestamp"][10])
            .then(pl.lit(-5.0))
            .otherwise(pl.col("open"))
            .alias("open")
        )
        report = checker.run_all_checks(df, "XAUUSD", "1h")
        assert report.passed is False
        assert len(report.validation_errors) > 0

    def test_gap_fill_ranges(self, checker):
        from src.data.models import GapInfo
        gaps = [
            GapInfo(
                epic="XAUUSD",
                timeframe="1h",
                gap_start=datetime(2024, 1, 1, 10),
                gap_end=datetime(2024, 1, 1, 15),
                expected_candles=4,
            ),
        ]
        ranges = checker.get_gap_fill_ranges(gaps)
        assert len(ranges) == 1
        assert ranges[0] == (datetime(2024, 1, 1, 10), datetime(2024, 1, 1, 15))
