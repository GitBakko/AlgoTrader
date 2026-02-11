"""
Utility functions for data pipeline module.
Handles timeframe conversions, path management, and helpers.
"""

from datetime import datetime
from pathlib import Path

from src.broker.models import Resolution


# ===== Timeframe Conversions =====

TIMEFRAME_TO_RESOLUTION = {
    "1min": Resolution.MINUTE,
    "5min": Resolution.MINUTE_5,
    "15min": Resolution.MINUTE_15,
    "30min": Resolution.MINUTE_30,
    "1h": Resolution.HOUR,
    "4h": Resolution.HOUR_4,
    "1d": Resolution.DAY,
    "1w": Resolution.WEEK,
}

RESOLUTION_TO_TIMEFRAME = {v: k for k, v in TIMEFRAME_TO_RESOLUTION.items()}

TIMEFRAME_TO_MINUTES = {
    "1min": 1,
    "5min": 5,
    "15min": 15,
    "30min": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}


def timeframe_to_resolution(timeframe: str) -> Resolution:
    """
    Convert timeframe string to broker Resolution enum.

    Args:
        timeframe: Timeframe string (e.g., "1min", "1h", "1d")

    Returns:
        Resolution enum

    Raises:
        ValueError: If timeframe is not recognized
    """
    if timeframe not in TIMEFRAME_TO_RESOLUTION:
        raise ValueError(
            f"Unknown timeframe: {timeframe}. "
            f"Valid options: {list(TIMEFRAME_TO_RESOLUTION.keys())}"
        )
    return TIMEFRAME_TO_RESOLUTION[timeframe]


def resolution_to_timeframe(resolution: Resolution) -> str:
    """
    Convert broker Resolution enum to timeframe string.

    Args:
        resolution: Resolution enum

    Returns:
        Timeframe string (e.g., "1min", "1h", "1d")

    Raises:
        ValueError: If resolution is not recognized
    """
    if resolution not in RESOLUTION_TO_TIMEFRAME:
        raise ValueError(f"Unknown resolution: {resolution}")
    return RESOLUTION_TO_TIMEFRAME[resolution]


def timeframe_to_minutes(timeframe: str) -> int:
    """
    Convert timeframe string to number of minutes.

    Args:
        timeframe: Timeframe string (e.g., "1min", "1h", "1d")

    Returns:
        Number of minutes

    Raises:
        ValueError: If timeframe is not recognized
    """
    if timeframe not in TIMEFRAME_TO_MINUTES:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    return TIMEFRAME_TO_MINUTES[timeframe]


def timeframe_to_interval(timeframe: str) -> str:
    """
    Convert timeframe to DuckDB INTERVAL string.

    Args:
        timeframe: Timeframe string (e.g., "1min", "1h", "1d")

    Returns:
        DuckDB INTERVAL string (e.g., "1 MINUTE", "1 HOUR", "1 DAY")
    """
    mapping = {
        "1min": "1 MINUTE",
        "5min": "5 MINUTES",
        "15min": "15 MINUTES",
        "30min": "30 MINUTES",
        "1h": "1 HOUR",
        "4h": "4 HOURS",
        "1d": "1 DAY",
        "1w": "1 WEEK",
    }
    if timeframe not in mapping:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    return mapping[timeframe]


# ===== Path Management =====


def get_parquet_directory(data_dir: str, epic: str, timeframe: str) -> Path:
    """
    Get directory path for Parquet files.

    Args:
        data_dir: Base data directory (e.g., "data/historical")
        epic: Asset epic (e.g., "XAUUSD")
        timeframe: Timeframe string (e.g., "1h")

    Returns:
        Path object for directory
    """
    return Path(data_dir) / epic / timeframe


def get_parquet_file_for_month(data_dir: str, epic: str, timeframe: str, date: datetime) -> Path:
    """
    Get Parquet file path for a specific month.

    Args:
        data_dir: Base data directory
        epic: Asset epic
        timeframe: Timeframe string
        date: Any datetime in the target month

    Returns:
        Path object for Parquet file (e.g., data/historical/XAUUSD/1h/2024-03.parquet)
    """
    directory = get_parquet_directory(data_dir, epic, timeframe)
    month_str = date.strftime("%Y-%m")
    return directory / f"{month_str}.parquet"


def list_parquet_files(data_dir: str, epic: str, timeframe: str) -> list[Path]:
    """
    List all existing Parquet files for an asset/timeframe.

    Args:
        data_dir: Base data directory
        epic: Asset epic
        timeframe: Timeframe string

    Returns:
        List of Path objects, sorted by month
    """
    directory = get_parquet_directory(data_dir, epic, timeframe)

    if not directory.exists():
        return []

    files = sorted(directory.glob("*.parquet"))
    return files


def get_month_from_filename(file_path: Path) -> str:
    """
    Extract month string from Parquet filename.

    Args:
        file_path: Path to Parquet file (e.g., "2024-03.parquet")

    Returns:
        Month string (e.g., "2024-03")
    """
    return file_path.stem  # Gets filename without extension


def ensure_directory_exists(path: Path) -> None:
    """
    Create directory if it doesn't exist.

    Args:
        path: Directory path to create
    """
    path.mkdir(parents=True, exist_ok=True)


# ===== Date/Time Helpers =====


def get_months_in_range(start_date: datetime, end_date: datetime) -> list[str]:
    """
    Get list of month strings (YYYY-MM) in date range.

    Args:
        start_date: Range start
        end_date: Range end

    Returns:
        List of month strings (e.g., ["2024-01", "2024-02", "2024-03"])
    """
    months = set()
    current = start_date

    while current <= end_date:
        months.add(current.strftime("%Y-%m"))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return sorted(months)


def is_market_hours(timestamp: datetime, epic: str) -> bool:
    """
    Check if timestamp is during market hours for the asset.

    Args:
        timestamp: Timestamp to check
        epic: Asset epic (XAUUSD, BTCUSD, US500)

    Returns:
        True if market is open, False if closed

    Note:
        This is a simplified check. For production, consider holidays and
        exact market hours per asset.
    """
    weekday = timestamp.weekday()

    # Bitcoin trades 24/7
    if epic == "BTCUSD":
        return True

    # Gold and S&P500: closed on weekends
    if weekday >= 5:  # Saturday = 5, Sunday = 6
        return False

    return True
