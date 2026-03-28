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
from datetime import UTC, datetime
from typing import Any

import httpx
import polars as pl
import yfinance as yf
from loguru import logger

from src.data.ticker_mapping import TickerMapper

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
