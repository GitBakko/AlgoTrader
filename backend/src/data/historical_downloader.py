"""
Historical data downloader for Capital.com API.
Downloads OHLC data in chunks with retry logic and progress tracking.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from loguru import logger

from src.broker.client import CapitalComClient
from src.broker.exceptions import CapitalComError, RateLimitError
from src.broker.models import OHLCCandle
from src.data.models import DataSource, DownloadProgress, OHLCBar
from src.data.storage import ParquetStorageManager
from src.data.utils import timeframe_to_resolution

# Capital.com API limits: max ~1000 candles per request
MAX_CANDLES_PER_REQUEST = 1000

# Chunk size in days per request, by timeframe
CHUNK_DAYS = {
    "1min": 1,  # ~390 candles/day (market hours)
    "5min": 3,  # ~78 candles/day → 234/chunk
    "15min": 10,  # ~26 candles/day → 260/chunk
    "30min": 20,  # ~13 candles/day → 260/chunk
    "1h": 30,  # ~8 candles/day → 240/chunk
    "4h": 90,  # ~2 candles/day → 180/chunk
    "1d": 365,  # 1 candle/day → 365/chunk
    "1w": 730,  # ~1 candle/week → 104/chunk
}

# Default retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds


def _broker_to_ohlc_bar(
    candle: OHLCCandle,
    epic: str,
    timeframe: str,
) -> OHLCBar:
    """Convert broker OHLCCandle to storage OHLCBar."""
    return OHLCBar(
        timestamp=candle.timestamp,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.last_traded_volume,
        epic=epic,
        timeframe=timeframe,
        source=DataSource.HISTORICAL,
    )


class HistoricalDownloader:
    """
    Downloads historical OHLC data from Capital.com API.

    Features:
    - Chunked downloads to respect API limits
    - Automatic retry with exponential backoff
    - Progress tracking
    - Resume from last downloaded timestamp
    """

    def __init__(
        self,
        client: CapitalComClient,
        storage: ParquetStorageManager,
        max_retries: int = MAX_RETRIES,
        retry_base_delay: float = RETRY_BASE_DELAY,
    ):
        self.client = client
        self.storage = storage
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

    async def download(
        self,
        epic: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime | None = None,
        on_progress: Callable | None = None,
    ) -> DownloadProgress:
        """
        Download historical data for an asset/timeframe.

        Args:
            epic: Asset epic code (e.g., "XAUUSD")
            timeframe: Timeframe string (e.g., "1h", "1d")
            start_date: Start date for download
            end_date: End date (defaults to now)
            on_progress: Optional callback(DownloadProgress) for progress updates

        Returns:
            DownloadProgress with final stats
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        resolution = timeframe_to_resolution(timeframe)
        chunk_days = CHUNK_DAYS.get(timeframe, 30)
        total_days = (end_date - start_date).days

        progress = DownloadProgress(
            epic=epic,
            timeframe=timeframe,
            total_days=max(total_days, 1),
            downloaded_days=0,
            total_candles=0,
            downloaded_candles=0,
            start_time=datetime.now(timezone.utc),
            status="in_progress",
        )

        logger.info(
            f"Starting download: {epic}/{timeframe} "
            f"from {start_date.date()} to {end_date.date()} "
            f"({total_days} days, chunk_size={chunk_days}d)"
        )

        current_start = start_date
        total_downloaded = 0

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=chunk_days), end_date)

            # Download chunk with retry
            candles = await self._download_chunk_with_retry(
                epic=epic,
                resolution=resolution,
                from_date=current_start,
                to_date=current_end,
            )

            if candles:
                # Convert to storage format
                bars = [_broker_to_ohlc_bar(c, epic, timeframe) for c in candles]

                # Append to storage (handles deduplication)
                new_count = self.storage.append_candles(bars, epic, timeframe)
                total_downloaded += new_count

                logger.debug(
                    f"Chunk {current_start.date()} → {current_end.date()}: "
                    f"{len(candles)} fetched, {new_count} new"
                )

            # Update progress
            days_done = (current_end - start_date).days
            progress.downloaded_days = min(days_done, total_days)
            progress.downloaded_candles = total_downloaded

            if on_progress:
                on_progress(progress)

            # Move to next chunk
            current_start = current_end

            # Small delay between chunks to be nice to the API
            await asyncio.sleep(0.2)

        progress.status = "completed"
        progress.downloaded_days = total_days
        progress.total_candles = total_downloaded
        progress.downloaded_candles = total_downloaded

        logger.info(
            f"Download complete: {epic}/{timeframe} - "
            f"{total_downloaded} candles in "
            f"{(datetime.now(timezone.utc) - progress.start_time).total_seconds():.1f}s"
        )

        return progress

    async def download_all_assets(
        self,
        assets: list[str] | None = None,
        timeframes: list[str] | None = None,
        days_back: int = 730,
        on_progress: Callable | None = None,
    ) -> list[DownloadProgress]:
        """
        Download historical data for multiple assets and timeframes.

        Args:
            assets: List of epics (defaults to XAUUSD, BTCUSD, US500)
            timeframes: List of timeframes (defaults to 1h, 4h, 1d)
            days_back: Number of days of historical data
            on_progress: Optional callback

        Returns:
            List of DownloadProgress results
        """
        if assets is None:
            assets = ["XAUUSD", "BTCUSD", "US500"]
        if timeframes is None:
            timeframes = ["1h", "4h", "1d"]

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        results = []

        for epic in assets:
            for timeframe in timeframes:
                logger.info(f"Downloading {epic}/{timeframe}...")
                try:
                    result = await self.download(
                        epic=epic,
                        timeframe=timeframe,
                        start_date=start_date,
                        end_date=end_date,
                        on_progress=on_progress,
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to download {epic}/{timeframe}: {e}")
                    results.append(
                        DownloadProgress(
                            epic=epic,
                            timeframe=timeframe,
                            total_days=(end_date - start_date).days,
                            downloaded_days=0,
                            total_candles=0,
                            downloaded_candles=0,
                            start_time=datetime.now(timezone.utc),
                            status="failed",
                            error_message=str(e),
                        )
                    )

        return results

    async def get_resume_date(
        self,
        epic: str,
        timeframe: str,
        default_start: datetime,
    ) -> datetime:
        """
        Get the date to resume downloading from.
        Reads existing data and returns the last timestamp + 1 interval.

        Args:
            epic: Asset epic
            timeframe: Timeframe
            default_start: Default start date if no data exists

        Returns:
            Date to resume from
        """
        df = self.storage.read_candles(epic=epic, timeframe=timeframe)

        if len(df) == 0:
            return default_start

        last_ts = df["timestamp"].max()
        logger.info(f"Resuming {epic}/{timeframe} from {last_ts}")
        return last_ts

    async def _download_chunk_with_retry(
        self,
        epic: str,
        resolution: "Resolution",
        from_date: datetime,
        to_date: datetime,
    ) -> list[OHLCCandle]:
        """
        Download a single chunk with retry logic.

        Returns:
            List of candles, empty list if all retries fail.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                candles = await self.client.get_historical_prices(
                    epic=epic,
                    resolution=resolution,
                    from_date=from_date,
                    to_date=to_date,
                    max_candles=MAX_CANDLES_PER_REQUEST,
                )
                return candles

            except RateLimitError:
                delay = self.retry_base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"Rate limited on {epic} "
                    f"({from_date.date()} → {to_date.date()}), "
                    f"retry {attempt}/{self.max_retries} in {delay:.0f}s"
                )
                await asyncio.sleep(delay)

            except CapitalComError as e:
                if attempt == self.max_retries:
                    logger.error(
                        f"Failed to download {epic} "
                        f"({from_date.date()} → {to_date.date()}) "
                        f"after {self.max_retries} retries: {e}"
                    )
                    return []
                delay = self.retry_base_delay * attempt
                logger.warning(
                    f"Error downloading {epic}: {e}, "
                    f"retry {attempt}/{self.max_retries} in {delay:.0f}s"
                )
                await asyncio.sleep(delay)

        return []
