"""
Pydantic models for data pipeline module.
Extends broker models with storage-specific fields.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DataSource(str, Enum):
    """Source of market data."""

    HISTORICAL = "historical"  # Batch download from API
    REALTIME = "realtime"  # WebSocket streaming
    BACKFILL = "backfill"  # Gap filling


class OHLCBar(BaseModel):
    """
    Extended OHLC candle model for storage.
    Compatible with broker.models.OHLCCandle but adds storage metadata.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
    epic: str  # XAUUSD, BTCUSD, US500
    timeframe: str  # 1min, 5min, 15min, 1h, 4h, 1d
    source: DataSource = DataSource.HISTORICAL

    model_config = ConfigDict(use_enum_values=True)


class DataQualityReport(BaseModel):
    """Report of data quality checks."""

    epic: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    total_candles: int
    gaps_found: int
    outliers_found: int
    validation_errors: list[str] = Field(default_factory=list)
    passed: bool
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GapInfo(BaseModel):
    """Information about a detected gap in time-series data."""

    epic: str
    timeframe: str
    gap_start: datetime
    gap_end: datetime
    expected_candles: int
    is_market_closed: bool = False  # Weekend/holiday gap


class DownloadProgress(BaseModel):
    """Progress tracking for historical data download."""

    epic: str
    timeframe: str
    total_days: int
    downloaded_days: int
    total_candles: int
    downloaded_candles: int
    start_time: datetime
    estimated_completion: datetime | None = None
    status: str = "in_progress"  # in_progress, completed, failed
    error_message: str | None = None

    @property
    def progress_percentage(self) -> float:
        """Calculate download progress percentage."""
        if self.total_days == 0:
            return 0.0
        return (self.downloaded_days / self.total_days) * 100

    @property
    def candles_per_second(self) -> float:
        """Calculate download speed in candles/sec."""
        elapsed = (datetime.now(UTC) - self.start_time).total_seconds()
        if elapsed == 0:
            return 0.0
        return self.downloaded_candles / elapsed


class ParquetMetadata(BaseModel):
    """Metadata about a Parquet file."""

    epic: str
    timeframe: str
    file_path: str
    month: str  # YYYY-MM
    num_rows: int
    file_size_bytes: int
    compression: str  # snappy, gzip, zstd, etc.
    created_at: datetime
    last_updated: datetime
    min_timestamp: datetime
    max_timestamp: datetime

    @property
    def file_size_mb(self) -> float:
        """File size in MB."""
        return self.file_size_bytes / (1024 * 1024)


class DataStorageStats(BaseModel):
    """Statistics about stored data."""

    total_assets: int
    total_timeframes: int
    total_candles: int
    total_files: int
    total_size_bytes: int
    earliest_data: datetime | None = None
    latest_data: datetime | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_size_mb(self) -> float:
        """Total storage size in MB."""
        return self.total_size_bytes / (1024 * 1024)

    @property
    def total_size_gb(self) -> float:
        """Total storage size in GB."""
        return self.total_size_bytes / (1024 * 1024 * 1024)
