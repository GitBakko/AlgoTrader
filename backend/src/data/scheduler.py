"""
Data pipeline scheduler.
Uses APScheduler to run periodic data collection, quality checks, and maintenance.
"""

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from src.broker.client import CapitalComClient
from src.data.data_access import DataAccessLayer
from src.data.historical_downloader import HistoricalDownloader
from src.data.models import OHLCBar
from src.data.quality_checks import DataQualityChecker
from src.data.storage import ParquetStorageManager
from src.utils.constants import TRADABLE_ASSETS


class DataScheduler:
    """
    Manages scheduled data pipeline tasks.

    Tasks:
    1. EOD data download - Daily at market close
    2. Quality checks - Daily after download
    3. Gap backfill - Weekly scan and fill
    4. Parquet optimization - Weekly compaction
    5. Weekly model retrain - After data optimization
    """

    def __init__(
        self,
        client: CapitalComClient,
        storage: ParquetStorageManager,
        data_access: DataAccessLayer,
        prediction_service=None,
    ):
        self.client = client
        self.storage = storage
        self.data_access = data_access
        self.prediction_service = prediction_service
        self.downloader = HistoricalDownloader(client, storage)
        self.quality_checker = DataQualityChecker()
        self.scheduler = AsyncIOScheduler()

        self._assets = list(TRADABLE_ASSETS)
        self._timeframes = ["1h", "4h", "1d"]

        # Include candle timeframe for scalp or MR primary mode
        from src.utils.config import get_settings

        settings = get_settings()
        self._scalp_mode = settings.scalp_mode_enabled
        self._mr_primary_mode = settings.mr_primary_enabled
        if self._scalp_mode or self._mr_primary_mode:
            scalp_tf = settings.scalp_candle_resolution  # e.g. "15min" or "4h"
            if scalp_tf not in self._timeframes:
                self._timeframes.insert(0, scalp_tf)
            self._scalp_timeframe = scalp_tf

    def setup(self) -> None:
        """Register all scheduled jobs."""

        # 0. Hourly candle refresh - every hour at :05 (for live trading)
        self.scheduler.add_job(
            self.job_hourly_refresh,
            CronTrigger(minute=5),
            id="hourly_refresh",
            name="Hourly candle refresh (1h)",
            replace_existing=True,
        )

        # 0b. Candle refresh for scalp/MR timeframe
        # Scalp mode: every 5 min. MR primary (4h): every hour at :10 (after 1h refresh at :05)
        if self._scalp_mode:
            self.scheduler.add_job(
                self.job_scalp_refresh,
                CronTrigger(minute="*/5"),
                id="scalp_refresh",
                name=f"Scalp candle refresh ({self._scalp_timeframe})",
                replace_existing=True,
            )
        elif self._mr_primary_mode:
            self.scheduler.add_job(
                self.job_scalp_refresh,
                CronTrigger(minute=10),
                id="mr_candle_refresh",
                name=f"MR candle refresh ({self._scalp_timeframe})",
                replace_existing=True,
            )

        # 1. EOD download - weekdays at 22:00 UTC (after most markets close)
        self.scheduler.add_job(
            self.job_eod_download,
            CronTrigger(hour=22, minute=0, day_of_week="mon-fri"),
            id="eod_download",
            name="End-of-day data download",
            replace_existing=True,
        )

        # 2. Quality checks - weekdays at 22:30 UTC (after EOD download)
        self.scheduler.add_job(
            self.job_quality_checks,
            CronTrigger(hour=22, minute=30, day_of_week="mon-fri"),
            id="quality_checks",
            name="Data quality checks",
            replace_existing=True,
        )

        # 3. Gap backfill - Sundays at 12:00 UTC
        self.scheduler.add_job(
            self.job_gap_backfill,
            CronTrigger(hour=12, day_of_week="sun"),
            id="gap_backfill",
            name="Weekly gap backfill",
            replace_existing=True,
        )

        # 4. Parquet optimization - Sundays at 14:00 UTC
        self.scheduler.add_job(
            self.job_optimize_storage,
            CronTrigger(hour=14, day_of_week="sun"),
            id="optimize_storage",
            name="Weekly Parquet optimization",
            replace_existing=True,
        )

        # 5. Weekly model retrain - Sundays at 16:00 UTC (after data optimization)
        self.scheduler.add_job(
            self.job_weekly_retrain,
            CronTrigger(hour=16, day_of_week="sun"),
            id="weekly_retrain",
            name="Weekly model retrain",
            replace_existing=True,
        )

        job_count = len(self.scheduler.get_jobs())
        logger.info(f"Data scheduler configured with {job_count} jobs")

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Data scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Data scheduler stopped")

    async def job_hourly_refresh(self) -> None:
        """
        Hourly candle refresh for live/demo trading.
        Downloads last 3 hours of 1h candles for all tradable assets,
        then invalidates the data access cache so the trading loop
        picks up fresh candles immediately.
        """
        logger.info("Running hourly candle refresh...")
        start_date = datetime.now(UTC) - timedelta(hours=3)
        downloaded = 0

        for epic in self._assets:
            try:
                result = await self.downloader.download(
                    epic=epic,
                    timeframe="1h",
                    start_date=start_date,
                )
                downloaded += result.downloaded_candles
            except Exception as e:
                logger.error(f"Hourly refresh failed for {epic}: {e}")

        # Invalidate cache so trading loop sees fresh data
        self.data_access.invalidate_cache()
        logger.info(
            f"Hourly refresh complete: {downloaded} candles across {len(self._assets)} assets"
        )

    async def job_scalp_refresh(self) -> None:
        """
        Scalp candle refresh for scalp mode trading.
        Downloads last 2 hours of scalp-timeframe candles for all tradable assets,
        then invalidates cache so the trading loop detects new candles.
        """
        logger.info(f"Running scalp candle refresh ({self._scalp_timeframe})...")
        start_date = datetime.now(UTC) - timedelta(hours=2)
        downloaded = 0

        for epic in self._assets:
            try:
                result = await self.downloader.download(
                    epic=epic,
                    timeframe=self._scalp_timeframe,
                    start_date=start_date,
                )
                downloaded += result.downloaded_candles
            except Exception as e:
                logger.error(f"Scalp refresh failed for {epic}: {e}")

        self.data_access.invalidate_cache()
        logger.info(
            f"Scalp refresh complete: {downloaded} candles across {len(self._assets)} assets"
        )

    async def job_eod_download(self) -> None:
        """
        End-of-day data download.
        Downloads last 2 days of data for all assets/timeframes.
        Uses append with deduplication to avoid duplicates.
        """
        logger.info("Running EOD download job...")
        start_date = datetime.now(UTC) - timedelta(days=2)

        for epic in self._assets:
            for timeframe in self._timeframes:
                try:
                    result = await self.downloader.download(
                        epic=epic,
                        timeframe=timeframe,
                        start_date=start_date,
                    )
                    logger.info(
                        f"EOD {epic}/{timeframe}: "
                        f"{result.downloaded_candles} candles downloaded"
                    )
                except Exception as e:
                    logger.error(f"EOD download failed for {epic}/{timeframe}: {e}")

        self.data_access.invalidate_cache()
        logger.info("EOD download job completed")

    async def job_quality_checks(self) -> None:
        """
        Run quality checks on recent data (last 7 days).
        """
        logger.info("Running quality checks job...")
        start_date = datetime.now(UTC) - timedelta(days=7)

        for epic in self._assets:
            for timeframe in self._timeframes:
                try:
                    df = self.data_access.get_candles(
                        epic=epic,
                        timeframe=timeframe,
                        start_date=start_date,
                    )
                    if len(df) == 0:
                        continue

                    report = self.quality_checker.run_all_checks(df, epic, timeframe)
                    if not report.passed:
                        logger.warning(
                            f"Quality check FAILED for {epic}/{timeframe}: "
                            f"{report.validation_errors}"
                        )
                except Exception as e:
                    logger.error(f"Quality check failed for {epic}/{timeframe}: {e}")

        logger.info("Quality checks job completed")

    async def job_gap_backfill(self) -> None:
        """
        Scan for gaps and download missing data.
        """
        logger.info("Running gap backfill job...")

        for epic in self._assets:
            for timeframe in self._timeframes:
                try:
                    df = self.data_access.get_candles(epic=epic, timeframe=timeframe)
                    if len(df) == 0:
                        continue

                    gaps = self.quality_checker.detect_gaps(df, epic, timeframe)
                    if not gaps:
                        continue

                    ranges = self.quality_checker.get_gap_fill_ranges(gaps)
                    logger.info(f"Found {len(ranges)} gaps for {epic}/{timeframe}, backfilling...")

                    for start, end in ranges:
                        await self.downloader.download(
                            epic=epic,
                            timeframe=timeframe,
                            start_date=start,
                            end_date=end,
                        )

                except Exception as e:
                    logger.error(f"Gap backfill failed for {epic}/{timeframe}: {e}")

        logger.info("Gap backfill job completed")

    async def job_weekly_retrain(self) -> None:
        """
        Weekly model retraining.
        Runs walk-forward training for all active assets and reloads models.
        """
        from src.models.auto_retrain import retrain_all_models

        logger.info("Running weekly model retrain job...")
        try:
            results = await retrain_all_models(
                prediction_service=self.prediction_service,
                timeframe="1h",
                horizon_bars=6,
            )
            successful = sum(1 for s in results.values() if s)
            logger.info(f"Weekly retrain complete: {successful}/{len(results)} models")
        except Exception as e:
            logger.error(f"Weekly retrain job failed: {e}", exc_info=True)

    async def job_optimize_storage(self) -> None:
        """
        Optimize Parquet files: re-sort, deduplicate, recompress.
        """
        logger.info("Running storage optimization job...")

        for epic in self._assets:
            for timeframe in self._timeframes:
                try:
                    df = self.storage.read_candles(epic=epic, timeframe=timeframe)
                    if len(df) == 0:
                        continue

                    original_count = len(df)
                    # Deduplicate and re-sort
                    df = df.sort("timestamp").unique(subset=["timestamp"], keep="first")
                    optimized_count = len(df)

                    if optimized_count < original_count:
                        # Convert back to OHLCBar list and rewrite
                        bars = [OHLCBar(**row) for row in df.iter_rows(named=True)]
                        self.storage.write_candles(bars, epic, timeframe)
                        logger.info(
                            f"Optimized {epic}/{timeframe}: "
                            f"{original_count} → {optimized_count} candles "
                            f"({original_count - optimized_count} duplicates removed)"
                        )

                except Exception as e:
                    logger.error(f"Optimization failed for {epic}/{timeframe}: {e}")

        logger.info("Storage optimization job completed")
