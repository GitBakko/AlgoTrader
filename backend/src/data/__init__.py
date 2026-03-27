"""
Data pipeline module for AlgoTrader AI.
Handles OHLC data collection, storage, and access.
"""

from src.data.data_access import DataAccessLayer
from src.data.historical_downloader import HistoricalDownloader
from src.data.models import (
    DataQualityReport,
    DataSource,
    DataStorageStats,
    DownloadProgress,
    GapInfo,
    OHLCBar,
    ParquetMetadata,
)
from src.data.quality_checks import DataQualityChecker
from src.data.realtime_streamer import RealtimeStreamer
from src.data.scheduler import DataScheduler
from src.data.storage import DuckDBInterface, ParquetStorageManager
from src.data.utils import (
    ensure_directory_exists,
    get_months_in_range,
    get_parquet_directory,
    get_parquet_file_for_month,
    is_market_hours,
    list_parquet_files,
    resolution_to_timeframe,
    timeframe_to_interval,
    timeframe_to_minutes,
    timeframe_to_resolution,
)

__all__ = [
    # Models
    "OHLCBar",
    "DataSource",
    "DataQualityReport",
    "GapInfo",
    "DownloadProgress",
    "ParquetMetadata",
    "DataStorageStats",
    # Utils
    "timeframe_to_resolution",
    "resolution_to_timeframe",
    "timeframe_to_minutes",
    "timeframe_to_interval",
    "get_parquet_directory",
    "get_parquet_file_for_month",
    "list_parquet_files",
    "ensure_directory_exists",
    "get_months_in_range",
    "is_market_hours",
    # Storage
    "ParquetStorageManager",
    "DuckDBInterface",
    # Quality
    "DataQualityChecker",
    # Downloader
    "HistoricalDownloader",
    # Streamer
    "RealtimeStreamer",
    # Access
    "DataAccessLayer",
    # Scheduler
    "DataScheduler",
]
