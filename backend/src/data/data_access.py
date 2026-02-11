"""
Unified data access layer.
Single interface for querying historical + real-time OHLC data.
"""

import time
from datetime import datetime

import polars as pl

from src.data.storage import DuckDBInterface, ParquetStorageManager


class DataAccessLayer:
    """
    Unified data access layer for all OHLC market data.

    Provides a single interface that:
    - Queries Parquet files via ParquetStorageManager
    - Runs analytical queries via DuckDB
    - Merges historical + real-time data seamlessly
    - Caches recent queries to avoid redundant disk I/O
    """

    def __init__(
        self,
        storage: ParquetStorageManager | None = None,
        duckdb: DuckDBInterface | None = None,
        cache_ttl: float = 300.0,
    ):
        self.storage = storage or ParquetStorageManager()
        self.duckdb = duckdb or DuckDBInterface()
        self._views_created = False
        self._cache: dict[str, tuple[float, pl.DataFrame]] = {}
        self._cache_ttl = cache_ttl

    def get_candles(
        self,
        epic: str,
        timeframe: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int | None = None,
    ) -> pl.DataFrame:
        """
        Get OHLC candles for an asset/timeframe.

        Uses an in-memory TTL cache to avoid redundant Parquet reads.
        Cache stores full results (without limit), so different limit
        values still get cache hits.

        Args:
            epic: Asset epic (XAUUSD, BTCUSD, US500)
            timeframe: Timeframe (1min, 5min, 15min, 1h, 4h, 1d)
            start_date: Start date filter
            end_date: End date filter
            limit: Max number of candles (most recent)

        Returns:
            Polars DataFrame sorted by timestamp ascending
        """
        cache_key = f"{epic}|{timeframe}|{start_date}|{end_date}"
        now = time.monotonic()

        cached = self._cache.get(cache_key)
        if cached is not None:
            cached_time, cached_df = cached
            if now - cached_time < self._cache_ttl:
                df = cached_df
                if limit and len(df) > limit:
                    df = df.tail(limit)
                return df

        df = self.storage.read_candles(
            epic=epic,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        self._cache[cache_key] = (now, df)

        if limit and len(df) > limit:
            df = df.tail(limit)

        return df

    def invalidate_cache(self, epic: str | None = None) -> None:
        """
        Invalidate cached data.

        Args:
            epic: If specified, only invalidate cache for this asset.
                  If None, clear all cache.
        """
        if epic is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{epic}|")]
            for k in keys_to_remove:
                del self._cache[k]

    def get_latest_candles(
        self,
        epic: str,
        timeframe: str,
        count: int = 100,
    ) -> pl.DataFrame:
        """
        Get the N most recent candles.

        Args:
            epic: Asset epic
            timeframe: Timeframe
            count: Number of candles

        Returns:
            Polars DataFrame with most recent candles
        """
        df = self.storage.read_candles(epic=epic, timeframe=timeframe)

        if len(df) > count:
            df = df.tail(count)

        return df

    def get_latest_price(self, epic: str, timeframe: str = "1h") -> dict | None:
        """
        Get the latest price for an asset.

        Returns:
            Dict with timestamp, open, high, low, close or None if no data.
        """
        df = self.get_latest_candles(epic, timeframe, count=1)

        if len(df) == 0:
            return None

        row = df.row(0, named=True)
        return row

    def query(self, sql: str) -> pl.DataFrame:
        """
        Execute a raw DuckDB SQL query on all stored data.

        Views available:
        - ohlc_all: All data
        - ohlc_xauusd, ohlc_btcusd, ohlc_us500: Per-asset views
        - ohlc_latest: Latest timestamp per epic/timeframe

        Args:
            sql: SQL query string

        Returns:
            Polars DataFrame with results
        """
        if not self._views_created:
            self.duckdb.create_views()
            self._views_created = True
        return self.duckdb.execute_query(sql)

    def get_date_range(
        self,
        epic: str,
        timeframe: str,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Get the date range of available data.
        Uses Parquet metadata to avoid loading all data into memory.

        Returns:
            (earliest_timestamp, latest_timestamp) or (None, None) if no data.
        """
        from src.data.utils import list_parquet_files

        files = list_parquet_files(self.storage.data_dir, epic, timeframe)
        if not files:
            return None, None

        # Read only timestamp column from first and last files
        first_df = pl.read_parquet(files[0], columns=["timestamp"])
        last_df = pl.read_parquet(files[-1], columns=["timestamp"])

        return first_df["timestamp"].min(), last_df["timestamp"].max()

    def get_candle_count(self, epic: str, timeframe: str) -> int:
        """
        Get total number of candles for an asset/timeframe.
        Uses Parquet metadata to avoid loading all data into memory.
        """
        from src.data.utils import list_parquet_files
        import pyarrow.parquet as pq

        files = list_parquet_files(self.storage.data_dir, epic, timeframe)
        total = 0
        for f in files:
            total += pq.read_metadata(f).num_rows
        return total

    def list_available_data(self) -> dict[str, dict[str, list[str]]]:
        """
        List all available data.

        Returns:
            Nested dict: {epic: {timeframe: [months]}}
        """
        return self.storage.list_available_data()

    def close(self) -> None:
        """Close DuckDB connection."""
        self.duckdb.close()
        self._views_created = False
