"""
Data quality checks for OHLC market data.
Detects gaps, outliers, and validates data integrity.
"""

from datetime import datetime, timedelta

import polars as pl
from loguru import logger

from src.data.models import DataQualityReport, GapInfo
from src.data.utils import is_market_hours, timeframe_to_minutes


class DataQualityChecker:
    """
    Performs quality checks on OHLC market data.

    Checks:
    - Gap detection: missing candles in time series
    - Outlier detection: price spikes beyond N standard deviations
    - OHLC validation: high >= low, volume >= 0, etc.
    - Duplicate detection: repeated timestamps
    """

    def __init__(self, outlier_std_threshold: float = 5.0):
        """
        Args:
            outlier_std_threshold: Number of standard deviations for outlier detection.
        """
        self.outlier_std_threshold = outlier_std_threshold

    def run_all_checks(
        self,
        df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> DataQualityReport:
        """
        Run all quality checks on a DataFrame and produce a report.

        Args:
            df: Polars DataFrame with OHLC data (must have timestamp, open, high, low, close columns).
            epic: Asset epic code.
            timeframe: Timeframe string.

        Returns:
            DataQualityReport with results.
        """
        if len(df) == 0:
            return DataQualityReport(
                epic=epic,
                timeframe=timeframe,
                start_date=datetime(2000, 1, 1),
                end_date=datetime(2000, 1, 1),
                total_candles=0,
                gaps_found=0,
                outliers_found=0,
                validation_errors=["No data to check"],
                passed=False,
            )

        errors: list[str] = []

        # 1. OHLC validation
        ohlc_errors = self.validate_ohlc(df)
        errors.extend(ohlc_errors)

        # 2. Duplicate detection
        dup_count = self.count_duplicates(df)
        if dup_count > 0:
            errors.append(f"Found {dup_count} duplicate timestamps")

        # 3. Gap detection
        gaps = self.detect_gaps(df, epic, timeframe)

        # 4. Outlier detection
        outliers = self.detect_outliers(df)

        # Determine pass/fail
        total_candles = len(df)
        gaps_found = len(gaps)
        outliers_found = len(outliers)

        # Fail if validation errors or too many gaps/outliers
        passed = (
            len(ohlc_errors) == 0
            and dup_count == 0
            and gaps_found <= total_candles * 0.01  # Max 1% gaps
            and outliers_found <= total_candles * 0.005  # Max 0.5% outliers
        )

        timestamps = df["timestamp"]
        report = DataQualityReport(
            epic=epic,
            timeframe=timeframe,
            start_date=timestamps.min(),
            end_date=timestamps.max(),
            total_candles=total_candles,
            gaps_found=gaps_found,
            outliers_found=outliers_found,
            validation_errors=errors,
            passed=passed,
        )

        log_fn = logger.info if passed else logger.warning
        log_fn(
            f"Quality check {epic}/{timeframe}: "
            f"{total_candles} candles, {gaps_found} gaps, "
            f"{outliers_found} outliers, passed={passed}"
        )

        return report

    def validate_ohlc(self, df: pl.DataFrame) -> list[str]:
        """
        Validate OHLC data integrity.

        Checks:
        - high >= open, close, low
        - low <= open, close, high
        - All prices > 0
        - Volume >= 0 (if present)

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        # High must be >= all other prices
        bad_high = df.filter(
            (pl.col("high") < pl.col("open"))
            | (pl.col("high") < pl.col("close"))
            | (pl.col("high") < pl.col("low"))
        )
        if len(bad_high) > 0:
            errors.append(f"Found {len(bad_high)} candles where high < open/close/low")

        # Low must be <= all other prices
        bad_low = df.filter(
            (pl.col("low") > pl.col("open"))
            | (pl.col("low") > pl.col("close"))
            | (pl.col("low") > pl.col("high"))
        )
        if len(bad_low) > 0:
            errors.append(f"Found {len(bad_low)} candles where low > open/close/high")

        # All prices must be positive
        bad_prices = df.filter(
            (pl.col("open") <= 0)
            | (pl.col("high") <= 0)
            | (pl.col("low") <= 0)
            | (pl.col("close") <= 0)
        )
        if len(bad_prices) > 0:
            errors.append(f"Found {len(bad_prices)} candles with non-positive prices")

        # Volume must be non-negative (if column exists and has non-null values)
        if "volume" in df.columns:
            bad_volume = df.filter(pl.col("volume").is_not_null() & (pl.col("volume") < 0))
            if len(bad_volume) > 0:
                errors.append(f"Found {len(bad_volume)} candles with negative volume")

        return errors

    def count_duplicates(self, df: pl.DataFrame) -> int:
        """
        Count duplicate timestamps.

        Returns:
            Number of duplicate timestamps.
        """
        total = len(df)
        unique = df["timestamp"].n_unique()
        return total - unique

    def detect_gaps(
        self,
        df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> list[GapInfo]:
        """
        Detect gaps (missing candles) in time series data.

        Compares consecutive timestamp differences against expected interval.
        Ignores gaps during market closed hours (weekends for non-crypto).

        Returns:
            List of GapInfo objects.
        """
        if len(df) < 2:
            return []

        expected_minutes = timeframe_to_minutes(timeframe)
        expected_delta = timedelta(minutes=expected_minutes)
        # Allow small tolerance (1.5x expected interval)
        max_delta = expected_delta * 1.5

        sorted_df = df.sort("timestamp")
        timestamps = sorted_df["timestamp"].to_list()

        gaps: list[GapInfo] = []

        for i in range(1, len(timestamps)):
            prev_ts = timestamps[i - 1]
            curr_ts = timestamps[i]
            delta = curr_ts - prev_ts

            if delta > max_delta:
                # Check if gap is during market closed hours
                is_closed = not is_market_hours(prev_ts, epic)

                # Calculate expected number of missing candles
                expected_candles = int(delta / expected_delta) - 1

                gaps.append(
                    GapInfo(
                        epic=epic,
                        timeframe=timeframe,
                        gap_start=prev_ts,
                        gap_end=curr_ts,
                        expected_candles=expected_candles,
                        is_market_closed=is_closed,
                    )
                )

        # Filter out market-closed gaps for non-crypto
        if epic != "BTCUSD":
            market_gaps = [g for g in gaps if not g.is_market_closed]
            logger.debug(
                f"Gaps for {epic}/{timeframe}: {len(gaps)} total, "
                f"{len(market_gaps)} during market hours"
            )
            return market_gaps

        return gaps

    def detect_outliers(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detect price outliers using standard deviation method.

        A candle is an outlier if any price (open/high/low/close) deviates
        more than N standard deviations from the rolling mean.

        Returns:
            DataFrame of outlier rows.
        """
        if len(df) < 20:
            return df.clear()

        # Use close price for outlier detection
        close = df["close"]
        mean = close.mean()
        std = close.std()

        if std == 0 or std is None or mean is None:
            return df.clear()

        threshold = self.outlier_std_threshold
        lower = mean - threshold * std
        upper = mean + threshold * std

        outliers = df.filter(
            (pl.col("close") < lower)
            | (pl.col("close") > upper)
            | (pl.col("high") < lower)
            | (pl.col("high") > upper)
            | (pl.col("low") < lower)
            | (pl.col("low") > upper)
        )

        if len(outliers) > 0:
            logger.debug(
                f"Found {len(outliers)} outliers "
                f"(threshold: {threshold}σ, range: [{lower:.2f}, {upper:.2f}])"
            )

        return outliers

    def get_gap_fill_ranges(
        self,
        gaps: list[GapInfo],
    ) -> list[tuple[datetime, datetime]]:
        """
        Convert gaps to date ranges for backfill.

        Returns:
            List of (start, end) tuples for data that needs downloading.
        """
        return [(gap.gap_start, gap.gap_end) for gap in gaps]
