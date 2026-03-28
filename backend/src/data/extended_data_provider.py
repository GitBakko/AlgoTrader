"""Extended data provider: fetches historical OHLCV from yfinance and CryptoCompare.

Standard column schema (Polars):
    timestamp  : Datetime[us, UTC]
    open       : Float64
    high       : Float64
    low        : Float64
    close      : Float64
    volume     : Float64
    epic       : Utf8
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import polars as pl
import yfinance as yf
from loguru import logger

from src.data.ticker_mapping import TickerMapper

if TYPE_CHECKING:
    from src.data.storage import ParquetStorageManager

# CryptoCompare free-tier endpoint (no API key required, 2000 bars per request)
_CC_BASE = "https://min-api.cryptocompare.com/data/v2/histohour"

# Standard column order
_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "epic"]

# Empty DataFrame with the correct schema, used as a sentinel value
_EMPTY_SCHEMA: dict[str, type] = {
    "timestamp": pl.Datetime("us", "UTC"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "epic": pl.Utf8,
}


def _empty_df() -> pl.DataFrame:
    return pl.DataFrame(schema=_EMPTY_SCHEMA)


class ExtendedDataProvider:
    """Fetches and normalises historical OHLCV data for all 21 MANTIS AI assets."""

    # ------------------------------------------------------------------
    # Source routing
    # ------------------------------------------------------------------

    def get_best_source(self, epic: str) -> str:
        """Return 'cryptocompare' for crypto epics, 'yfinance' for everything else."""
        return "cryptocompare" if TickerMapper.is_crypto(epic) else "yfinance"

    # ------------------------------------------------------------------
    # yfinance
    # ------------------------------------------------------------------

    async def fetch_yfinance(
        self,
        epic: str,
        start: datetime,
        end: datetime,
        interval: str = "1h",
    ) -> pl.DataFrame:
        """Download OHLCV from yfinance, running the blocking call in a thread pool.

        Args:
            epic: Capital.com epic (e.g. "XAUUSD").
            start: Start datetime (timezone-aware, UTC).
            end: End datetime (timezone-aware, UTC).
            interval: yfinance interval string (default "1h").

        Returns:
            Polars DataFrame with standard OHLCV schema, or an empty DataFrame on error.
        """
        ticker_sym = TickerMapper.to_yfinance(epic)
        if ticker_sym is None:
            logger.warning("fetch_yfinance: no yfinance mapping for epic={}", epic)
            return _empty_df()

        def _blocking() -> pl.DataFrame:
            try:
                ticker = yf.Ticker(ticker_sym)
                df_pd = ticker.history(
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    interval=interval,
                    auto_adjust=True,
                )
                if df_pd is None or df_pd.empty:
                    logger.warning(
                        "fetch_yfinance: empty result for epic={} ticker={}", epic, ticker_sym
                    )
                    return _empty_df()
                return self._normalize_yfinance(df_pd, epic)
            except Exception as exc:  # noqa: BLE001
                logger.error("fetch_yfinance error for epic={}: {}", epic, exc)
                return _empty_df()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _blocking)

    def _normalize_yfinance(self, df_pd: Any, epic: str) -> pl.DataFrame:
        """Convert a yfinance pandas DataFrame to the standard Polars schema.

        Handles both flat and multi-level column headers (yfinance sometimes returns
        a MultiIndex when downloading multiple tickers).
        """
        import pandas as pd  # local import to keep module-level imports clean

        # Flatten multi-level columns if present
        if isinstance(df_pd.columns, pd.MultiIndex):
            df_pd = df_pd.copy()
            df_pd.columns = [c[0] if isinstance(c, tuple) else c for c in df_pd.columns]

        # Ensure the index is named and timezone-aware
        df_pd = df_pd.copy()
        df_pd.index.name = "timestamp"
        if df_pd.index.tz is None:
            df_pd.index = df_pd.index.tz_localize("UTC")
        else:
            df_pd.index = df_pd.index.tz_convert("UTC")

        df_pd = df_pd.reset_index()

        # Rename OHLCV columns to lowercase
        col_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        df_pd = df_pd.rename(columns=col_map)

        # Keep only the columns we need (in case yfinance adds extras)
        keep = ["timestamp", "open", "high", "low", "close", "volume"]
        df_pd = df_pd[[c for c in keep if c in df_pd.columns]]

        # Build Polars DataFrame
        pl_df = pl.from_pandas(df_pd)

        # Ensure timestamp is UTC datetime with microsecond precision
        if "timestamp" in pl_df.columns:
            ts_col = pl_df["timestamp"]
            if ts_col.dtype == pl.Utf8:
                ts_col = ts_col.str.to_datetime(time_zone="UTC")
            elif ts_col.dtype.base_type() == pl.Datetime:
                if ts_col.dtype.time_zone is None:  # type: ignore[union-attr]
                    ts_col = ts_col.dt.replace_time_zone("UTC")
                else:
                    ts_col = ts_col.dt.convert_time_zone("UTC")
            pl_df = pl_df.with_columns(ts_col.cast(pl.Datetime("us", "UTC")).alias("timestamp"))

        # Ensure float types for OHLCV
        float_cols = ["open", "high", "low", "close", "volume"]
        pl_df = pl_df.with_columns(
            [pl.col(c).cast(pl.Float64) for c in float_cols if c in pl_df.columns]
        )

        # Add epic column
        pl_df = pl_df.with_columns(pl.lit(epic).alias("epic"))

        # Return only standard columns
        available = [c for c in _COLUMNS if c in pl_df.columns]
        return pl_df.select(available)

    # ------------------------------------------------------------------
    # CryptoCompare
    # ------------------------------------------------------------------

    async def fetch_cryptocompare(
        self,
        epic: str,
        limit: int = 2000,
        to_ts: int | None = None,
    ) -> pl.DataFrame:
        """Download OHLCV from CryptoCompare free API (hourly bars).

        Args:
            epic: Capital.com epic (e.g. "BTCUSD").
            limit: Number of bars to fetch (max 2000 per request).
            to_ts: Unix timestamp for the last bar (None = most recent).

        Returns:
            Polars DataFrame with standard OHLCV schema, or an empty DataFrame on error.
        """
        mapping = TickerMapper.to_cryptocompare(epic)
        if mapping is None:
            logger.debug("fetch_cryptocompare: {} is not a crypto epic, skipping", epic)
            return _empty_df()

        fsym, tsym = mapping
        params: dict[str, Any] = {"fsym": fsym, "tsym": tsym, "limit": limit}
        if to_ts is not None:
            params["toTs"] = to_ts

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(_CC_BASE, params=params)
                resp.raise_for_status()
                raw = resp.json()
            return self._normalize_cryptocompare(raw, epic)
        except Exception as exc:  # noqa: BLE001
            logger.error("fetch_cryptocompare error for epic={}: {}", epic, exc)
            return _empty_df()

    def _normalize_cryptocompare(self, raw: dict, epic: str) -> pl.DataFrame:
        """Convert a CryptoCompare API response dict to the standard Polars schema.

        Expected structure::

            {
                "Response": "Success",
                "Data": {
                    "Data": [
                        {"time": 1704067200, "open": ..., "high": ..., "low": ...,
                         "close": ..., "volumefrom": ..., "volumeto": ...},
                        ...
                    ]
                }
            }
        """
        if raw.get("Response") != "Success":
            logger.warning("_normalize_cryptocompare: non-success response: {}", raw.get("Message"))
            return _empty_df()

        bars: list[dict] = raw.get("Data", {}).get("Data", [])
        if not bars:
            return _empty_df()

        timestamps = [datetime.fromtimestamp(b["time"], tz=UTC) for b in bars]

        pl_df = pl.DataFrame(
            {
                "timestamp": timestamps,
                "open": [float(b["open"]) for b in bars],
                "high": [float(b["high"]) for b in bars],
                "low": [float(b["low"]) for b in bars],
                "close": [float(b["close"]) for b in bars],
                "volume": [float(b["volumefrom"]) for b in bars],
                "epic": [epic] * len(bars),
            }
        ).with_columns(
            pl.col("timestamp").dt.replace_time_zone("UTC").cast(pl.Datetime("us", "UTC"))
        )

        return pl_df.select(_COLUMNS)

    # ------------------------------------------------------------------
    # Auto-routing entry point
    # ------------------------------------------------------------------

    async def fetch_extended(
        self,
        epic: str,
        start: datetime,
        end: datetime,
        interval: str = "1h",
    ) -> pl.DataFrame:
        """Fetch OHLCV data using the best available source for the given epic.

        Crypto epics → CryptoCompare; all others → yfinance.

        Args:
            epic: Capital.com epic (e.g. "BTCUSD", "XAUUSD").
            start: Start datetime (UTC).
            end: End datetime (UTC).
            interval: yfinance interval (only used for yfinance source).

        Returns:
            Polars DataFrame with standard OHLCV schema.
        """
        source = self.get_best_source(epic)
        logger.debug("fetch_extended: epic={} source={}", epic, source)

        if source == "cryptocompare":
            # CryptoCompare limit: approximate number of hours between start and end
            hours = max(1, int((end - start).total_seconds() / 3600))
            limit = min(hours, 2000)
            return await self.fetch_cryptocompare(epic, limit=limit)
        else:
            return await self.fetch_yfinance(epic, start, end, interval=interval)

    # ------------------------------------------------------------------
    # CryptoCompare paginated (multi-year)
    # ------------------------------------------------------------------

    async def fetch_cryptocompare_extended(
        self,
        epic: str,
        days_back: int = 730,
    ) -> pl.DataFrame | None:
        """Fetch multi-year hourly data from CryptoCompare via backward pagination.

        CryptoCompare free tier: max 2000 bars per request.
        For 2 years of hourly data = ~17,520 bars = ~9 requests.

        Args:
            epic: Capital.com epic (e.g. "BTCUSD").
            days_back: How many days of history to fetch (default 730 = ~2 years).

        Returns:
            Combined Polars DataFrame or None on total failure.
        """
        mapping = TickerMapper.to_cryptocompare(epic)
        if mapping is None:
            logger.debug("fetch_cryptocompare_extended: {} is not a crypto epic", epic)
            return None

        cutoff = datetime.now(UTC) - timedelta(days=days_back)
        cutoff_ts = int(cutoff.timestamp())

        all_pages: list[pl.DataFrame] = []
        to_ts: int | None = None
        max_pages = (days_back * 24 // 2000) + 2  # safety limit

        for page_num in range(max_pages):
            page = await self.fetch_cryptocompare(epic, limit=2000, to_ts=to_ts)
            if page.is_empty():
                logger.debug("fetch_cryptocompare_extended: empty page {} for {}", page_num, epic)
                break

            all_pages.append(page)

            # Earliest timestamp in this page becomes the upper bound for next request
            earliest_ts = page["timestamp"].min()
            if earliest_ts is None:
                break
            earliest_unix = int(earliest_ts.replace(tzinfo=UTC).timestamp())

            # Stop if we've reached far enough back
            if earliest_unix <= cutoff_ts:
                logger.debug("fetch_cryptocompare_extended: reached cutoff at page {}", page_num)
                break

            # Next page ends just before the earliest bar we got
            to_ts = earliest_unix - 1

        if not all_pages:
            return None

        combined = pl.concat(all_pages, how="diagonal")
        # Dedup and filter to requested range
        combined = combined.unique(subset=["timestamp"], keep="first")
        combined = combined.filter(pl.col("timestamp") >= cutoff)
        combined = combined.sort("timestamp")

        logger.info(
            "fetch_cryptocompare_extended: {} — {} bars over {} pages",
            epic,
            len(combined),
            len(all_pages),
        )
        return combined

    # ------------------------------------------------------------------
    # yfinance extended (auto-interval selection)
    # ------------------------------------------------------------------

    async def fetch_yfinance_extended(
        self,
        epic: str,
        days_back: int = 730,
    ) -> pl.DataFrame | None:
        """Fetch extended data from yfinance, auto-selecting best interval.

        yfinance limits hourly data to ~730 days. For longer periods this
        method fetches daily bars and returns them as-is (the caller can
        resample if needed).

        Args:
            epic: Capital.com epic (e.g. "XAUUSD").
            days_back: How many days of history to fetch.

        Returns:
            Polars DataFrame or None on failure.
        """
        ticker_sym = TickerMapper.to_yfinance(epic)
        if ticker_sym is None:
            logger.warning("fetch_yfinance_extended: no yfinance mapping for {}", epic)
            return None

        # yfinance hourly limit is ~730 days
        if days_back <= 730:
            interval = "1h"
        else:
            interval = "1d"

        end = datetime.now(UTC)
        start = end - timedelta(days=days_back)

        result = await self.fetch_yfinance(epic, start, end, interval=interval)
        if result.is_empty():
            return None

        logger.info(
            "fetch_yfinance_extended: {} — {} bars (interval={})",
            epic,
            len(result),
            interval,
        )
        return result

    # ------------------------------------------------------------------
    # Unified download + store
    # ------------------------------------------------------------------

    async def download_and_store(
        self,
        epic: str,
        days_back: int = 730,
        storage: ParquetStorageManager | None = None,
    ) -> dict:
        """Download extended data and optionally merge with Parquet storage.

        Args:
            epic: Capital.com epic.
            days_back: Days of history to fetch.
            storage: If provided, append fetched data to Parquet files.

        Returns:
            Dict with keys: epic, bars_fetched, bars_new, source.
        """
        source = self.get_best_source(epic)

        if source == "cryptocompare":
            df = await self.fetch_cryptocompare_extended(epic, days_back=days_back)
        else:
            df = await self.fetch_yfinance_extended(epic, days_back=days_back)

        bars_fetched = len(df) if df is not None else 0
        bars_new = 0

        if df is not None and not df.is_empty() and storage is not None:
            from src.data.models import DataSource, OHLCBar

            candles: list[OHLCBar] = []
            for row in df.iter_rows(named=True):
                ts = row["timestamp"]
                # Ensure timezone-aware
                if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                vol_raw = row.get("volume")
                vol = int(vol_raw) if vol_raw is not None and vol_raw == vol_raw else 0
                candles.append(
                    OHLCBar(
                        timestamp=ts,
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=vol,
                        epic=epic,
                        timeframe="1h",
                        source=DataSource.HISTORICAL,
                    )
                )
            bars_new = storage.append_candles(candles, epic, "1h")

        return {
            "epic": epic,
            "bars_fetched": bars_fetched,
            "bars_new": bars_new,
            "source": source,
        }

    # ------------------------------------------------------------------
    # Merge / dedup helper
    # ------------------------------------------------------------------

    def merge_with_existing(self, existing: pl.DataFrame, extended: pl.DataFrame) -> pl.DataFrame:
        """Concatenate two DataFrames, deduplicate on timestamp, and sort ascending.

        Both DataFrames must share the standard OHLCV schema.

        Args:
            existing: Existing data (may be empty).
            extended: Newly fetched data (may be empty).

        Returns:
            Combined, deduplicated, sorted Polars DataFrame.
        """
        if existing.is_empty():
            return extended.sort("timestamp")
        if extended.is_empty():
            return existing.sort("timestamp")

        combined = pl.concat([existing, extended], how="diagonal")
        deduped = combined.unique(subset=["timestamp"], keep="first")
        return deduped.sort("timestamp")
