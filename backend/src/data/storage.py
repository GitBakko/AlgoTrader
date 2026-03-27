"""
Parquet storage manager and DuckDB interface for market data.
Handles write/read/append operations and analytical queries.
"""

from datetime import datetime
from pathlib import Path

import duckdb
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from src.data.models import DataStorageStats, OHLCBar, ParquetMetadata
from src.data.utils import (
    ensure_directory_exists,
    get_parquet_directory,
    get_parquet_file_for_month,
    list_parquet_files,
)
from src.utils.config import get_settings

# PyArrow schema for OHLC data
OHLC_SCHEMA = pa.schema(
    [
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.int64()),
        ("epic", pa.string()),
        ("timeframe", pa.string()),
        ("source", pa.string()),
    ]
)

# Polars schema for empty DataFrames (avoids PyArrow Field incompatibility)
EMPTY_DF_SCHEMA = {
    "timestamp": pl.Datetime("us", "UTC"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
    "epic": pl.Utf8,
    "timeframe": pl.Utf8,
    "source": pl.Utf8,
}


class ParquetStorageManager:
    """
    Manages Parquet file storage for OHLC data.
    Handles partitioning by asset/timeframe/month.
    """

    def __init__(self, data_dir: str | None = None, compression: str | None = None):
        """
        Initialize Parquet storage manager.

        Args:
            data_dir: Base data directory (defaults to settings.data_dir)
            compression: Compression algorithm (defaults to settings.parquet_compression)
        """
        settings = get_settings()
        self.data_dir = data_dir or settings.data_dir
        self.compression = compression or settings.parquet_compression

    def write_candles(
        self,
        candles: list[OHLCBar],
        epic: str,
        timeframe: str,
    ) -> int:
        """
        Write candles to Parquet file(s).
        Automatically partitions by month.

        Args:
            candles: List of OHLC candles to write
            epic: Asset epic
            timeframe: Timeframe string

        Returns:
            Number of candles written
        """
        if not candles:
            logger.warning(f"No candles to write for {epic}/{timeframe}")
            return 0

        # Group candles by month
        candles_by_month: dict[str, list[OHLCBar]] = {}
        for candle in candles:
            month_key = candle.timestamp.strftime("%Y-%m")
            if month_key not in candles_by_month:
                candles_by_month[month_key] = []
            candles_by_month[month_key].append(candle)

        total_written = 0

        # Write each month to separate file
        for _month, month_candles in candles_by_month.items():
            file_path = get_parquet_file_for_month(
                self.data_dir, epic, timeframe, month_candles[0].timestamp
            )

            # Ensure directory exists
            ensure_directory_exists(file_path.parent)

            # Convert to DataFrame
            df = pl.DataFrame([candle.model_dump() for candle in month_candles])

            # Write to Parquet
            df.write_parquet(file_path, compression=self.compression)

            total_written += len(month_candles)
            logger.info(
                f"Wrote {len(month_candles)} candles to {file_path} "
                f"({self._get_file_size(file_path):.2f} MB)"
            )

        return total_written

    def append_candles(
        self,
        candles: list[OHLCBar],
        epic: str,
        timeframe: str,
    ) -> int:
        """
        Append candles to existing Parquet files.
        Handles deduplication by timestamp.

        Args:
            candles: List of OHLC candles to append
            epic: Asset epic
            timeframe: Timeframe string

        Returns:
            Number of new candles added (after deduplication)
        """
        if not candles:
            return 0

        # Group by month
        candles_by_month: dict[str, list[OHLCBar]] = {}
        for candle in candles:
            month_key = candle.timestamp.strftime("%Y-%m")
            if month_key not in candles_by_month:
                candles_by_month[month_key] = []
            candles_by_month[month_key].append(candle)

        total_added = 0

        for _month, month_candles in candles_by_month.items():
            file_path = get_parquet_file_for_month(
                self.data_dir, epic, timeframe, month_candles[0].timestamp
            )

            ensure_directory_exists(file_path.parent)

            # Convert new candles to DataFrame
            df_new = pl.DataFrame([candle.model_dump() for candle in month_candles])

            if file_path.exists():
                # Load existing data
                df_existing = pl.read_parquet(file_path)

                # Combine with new data
                df_combined = pl.concat([df_existing, df_new])

                # Deduplicate by timestamp (keep 'historical' source over 'realtime')
                # Sort by timestamp DESC, then by source (alphabetical: 'historical' < 'realtime')
                df_deduplicated = df_combined.sort(["timestamp", "source"]).unique(
                    subset=["timestamp"], keep="first"
                )

                added = len(df_deduplicated) - len(df_existing)
                logger.info(
                    f"Appended {added} new candles to {file_path} "
                    f"({len(df_new)} provided, {len(df_new) - added} duplicates)"
                )
            else:
                # New file
                df_deduplicated = df_new
                added = len(df_new)
                logger.info(f"Created new file {file_path} with {added} candles")

            # Write back
            df_deduplicated.write_parquet(file_path, compression=self.compression)
            total_added += added

        return total_added

    def read_candles(
        self,
        epic: str,
        timeframe: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> pl.DataFrame:
        """
        Read candles from Parquet files.

        Args:
            epic: Asset epic
            timeframe: Timeframe string
            start_date: Filter start date (inclusive)
            end_date: Filter end date (inclusive)

        Returns:
            Polars DataFrame with candles
        """
        directory = get_parquet_directory(self.data_dir, epic, timeframe)

        if not directory.exists():
            logger.warning(f"No data directory found: {directory}")
            return pl.DataFrame(schema=EMPTY_DF_SCHEMA)

        files = list_parquet_files(self.data_dir, epic, timeframe)

        if not files:
            logger.warning(f"No Parquet files found for {epic}/{timeframe}")
            return pl.DataFrame(schema=EMPTY_DF_SCHEMA)

        # Month-based file pruning: only read files that overlap with date range
        if start_date or end_date:
            filtered_files = []
            for f in files:
                month_str = f.stem  # "2024-03"
                try:
                    file_year, file_month = month_str.split("-")
                    file_start = datetime(int(file_year), int(file_month), 1)
                    # Last day of month
                    if int(file_month) == 12:
                        file_end = datetime(int(file_year) + 1, 1, 1)
                    else:
                        file_end = datetime(int(file_year), int(file_month) + 1, 1)

                    # Skip if file is entirely outside requested range
                    if end_date and file_start > end_date:
                        continue
                    if start_date and file_end <= start_date:
                        continue
                    filtered_files.append(f)
                except ValueError:
                    # Filename doesn't match YYYY-MM format, include it
                    filtered_files.append(f)
            files = filtered_files

        if not files:
            return pl.DataFrame(schema=EMPTY_DF_SCHEMA)

        # Read only relevant files
        dfs = []
        for file_path in files:
            df = pl.read_parquet(file_path)
            dfs.append(df)

        # Concatenate
        df_all = pl.concat(dfs)

        # Apply date filters
        if start_date:
            df_all = df_all.filter(pl.col("timestamp") >= start_date)
        if end_date:
            df_all = df_all.filter(pl.col("timestamp") <= end_date)

        # Sort by timestamp
        df_all = df_all.sort("timestamp")

        return df_all

    def get_latest_timestamp(self, epic: str, timeframe: str) -> datetime | None:
        """
        Get the latest candle timestamp without reading full data.
        Reads only the timestamp column from the most recent Parquet file.

        Returns:
            Latest timestamp or None if no data exists
        """
        files = list_parquet_files(self.data_dir, epic, timeframe)
        if not files:
            return None

        # Files are sorted by month; last file is most recent
        last_file = files[-1]
        df = pl.read_parquet(last_file, columns=["timestamp"])
        if df.is_empty():
            return None

        return df["timestamp"].max()

    def get_bar_count(self, epic: str, timeframe: str) -> int:
        """Get total number of bars without reading full data."""
        files = list_parquet_files(self.data_dir, epic, timeframe)
        total = 0
        for f in files:
            total += pq.read_metadata(f).num_rows
        return total

    def list_available_data(self) -> dict[str, dict[str, list[str]]]:
        """
        List all available data organized by asset and timeframe.

        Returns:
            Nested dict: {epic: {timeframe: [month_strings]}}
        """
        data_path = Path(self.data_dir)

        if not data_path.exists():
            return {}

        result = {}

        # Iterate over epics (XAUUSD, BTCUSD, US500)
        for epic_dir in data_path.iterdir():
            if not epic_dir.is_dir():
                continue

            epic = epic_dir.name
            result[epic] = {}

            # Iterate over timeframes (1min, 5min, 1h, etc.)
            for timeframe_dir in epic_dir.iterdir():
                if not timeframe_dir.is_dir():
                    continue

                timeframe = timeframe_dir.name
                months = []

                # List Parquet files
                for parquet_file in timeframe_dir.glob("*.parquet"):
                    months.append(parquet_file.stem)  # Get YYYY-MM from filename

                result[epic][timeframe] = sorted(months)

        return result

    def get_metadata(self, file_path: Path) -> ParquetMetadata:
        """
        Get metadata about a Parquet file.

        Args:
            file_path: Path to Parquet file

        Returns:
            ParquetMetadata object
        """
        # Read parquet metadata
        parquet_file = pq.ParquetFile(file_path)
        metadata = parquet_file.metadata

        # Read data to get timestamp range
        df = pl.read_parquet(file_path, columns=["timestamp"])

        return ParquetMetadata(
            epic=file_path.parent.parent.name,
            timeframe=file_path.parent.name,
            file_path=str(file_path),
            month=file_path.stem,
            num_rows=metadata.num_rows,
            file_size_bytes=file_path.stat().st_size,
            compression=str(metadata.row_group(0).column(0).compression),
            created_at=datetime.fromtimestamp(file_path.stat().st_ctime),
            last_updated=datetime.fromtimestamp(file_path.stat().st_mtime),
            min_timestamp=df["timestamp"].min(),
            max_timestamp=df["timestamp"].max(),
        )

    def get_storage_stats(self) -> DataStorageStats:
        """
        Get statistics about stored data.

        Returns:
            DataStorageStats object
        """
        available_data = self.list_available_data()

        total_assets = len(available_data)
        total_timeframes = sum(len(timeframes) for timeframes in available_data.values())
        total_files = 0
        total_size_bytes = 0
        earliest_data = None
        latest_data = None
        total_candles = 0

        # Traverse all files
        data_path = Path(self.data_dir)
        for parquet_file in data_path.rglob("*.parquet"):
            total_files += 1
            total_size_bytes += parquet_file.stat().st_size

            # Get metadata
            metadata = self.get_metadata(parquet_file)
            total_candles += metadata.num_rows

            # Update earliest/latest timestamps
            if earliest_data is None or metadata.min_timestamp < earliest_data:
                earliest_data = metadata.min_timestamp
            if latest_data is None or metadata.max_timestamp > latest_data:
                latest_data = metadata.max_timestamp

        return DataStorageStats(
            total_assets=total_assets,
            total_timeframes=total_timeframes,
            total_candles=total_candles,
            total_files=total_files,
            total_size_bytes=total_size_bytes,
            earliest_data=earliest_data,
            latest_data=latest_data,
        )

    @staticmethod
    def _get_file_size(file_path: Path) -> float:
        """Get file size in MB."""
        return file_path.stat().st_size / (1024 * 1024)


class DuckDBInterface:
    """
    DuckDB interface for analytical queries on Parquet files.
    Reads Parquet on-the-fly without loading into memory.
    """

    def __init__(self, duckdb_path: str | None = None, data_dir: str | None = None):
        """
        Initialize DuckDB interface.

        Args:
            duckdb_path: Path to DuckDB database file (defaults to settings.duckdb_path)
            data_dir: Base data directory for Parquet files (defaults to settings.data_dir)
        """
        settings = get_settings()
        self.duckdb_path = duckdb_path or settings.duckdb_path
        self.data_dir = data_dir or settings.data_dir
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        """
        Get or create DuckDB connection.

        Returns:
            DuckDB connection
        """
        if self._conn is None:
            self._conn = duckdb.connect(self.duckdb_path)
            logger.info(f"Connected to DuckDB at {self.duckdb_path}")
        return self._conn

    def create_views(self) -> None:
        """
        Create DuckDB views for convenient querying.

        Views created:
        - ohlc_all: All OHLC data across all assets/timeframes
        - ohlc_{epic}: Per-asset views (e.g., ohlc_xauusd)
        - ohlc_latest: Latest timestamp per asset/timeframe
        """
        conn = self.connect()

        # View 1: All OHLC data (use forward slashes for DuckDB glob on all OSes)
        data_dir_posix = self.data_dir.replace("\\", "/")
        conn.execute(f"""
            CREATE OR REPLACE VIEW ohlc_all AS
            SELECT * FROM read_parquet('{data_dir_posix}/**/*.parquet')
        """)
        logger.info("Created view: ohlc_all")

        # View 2: Per-asset views (XAUUSD, BTCUSD, US500)
        for epic in ["XAUUSD", "BTCUSD", "US500"]:
            view_name = f"ohlc_{epic.lower()}"
            conn.execute(f"""
                CREATE OR REPLACE VIEW {view_name} AS
                SELECT * FROM ohlc_all WHERE epic = '{epic}'
            """)
            logger.info(f"Created view: {view_name}")

        # View 3: Latest timestamps
        conn.execute("""
            CREATE OR REPLACE VIEW ohlc_latest AS
            SELECT
                epic,
                timeframe,
                MAX(timestamp) as latest_timestamp,
                COUNT(*) as total_candles
            FROM ohlc_all
            GROUP BY epic, timeframe
        """)
        logger.info("Created view: ohlc_latest")

    def execute_query(self, sql: str) -> pl.DataFrame:
        """
        Execute SQL query and return results as Polars DataFrame.

        Args:
            sql: SQL query string

        Returns:
            Polars DataFrame with results
        """
        conn = self.connect()
        result = conn.execute(sql).pl()
        return result

    def close(self) -> None:
        """Close DuckDB connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("Closed DuckDB connection")
