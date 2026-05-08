"""Download 730 days of 1h history for Phase 12 expansion candidates.

Uses yfinance `period="730d"` so the request anchors to yfinance's
real wall-clock (the project simulation date 2026-05-08 is in
yfinance's future, so explicit start/end dates would be rejected).
Persists the result through `ParquetStorageManager.append_candles`
so trainers/backtests pick the new data up like any other asset.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import polars as pl
import yfinance as yf
from loguru import logger

from src.data.models import DataSource, OHLCBar
from src.data.storage import ParquetStorageManager
from src.data.ticker_mapping import TickerMapper

CANDIDATES: list[str] = [
    # Stocks
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "AMD",
    # Forex
    "USDCHF",
    "USDCAD",
]


def _yf_history(ticker: str) -> pl.DataFrame:
    """Hit yfinance with a 730d period (anchored to real wall-clock)."""
    df_pd = yf.Ticker(ticker).history(period="730d", interval="1h", auto_adjust=True)
    if df_pd is None or df_pd.empty:
        return pl.DataFrame()

    df_pd = df_pd.copy()
    df_pd.index.name = "timestamp"
    if df_pd.index.tz is None:
        df_pd.index = df_pd.index.tz_localize("UTC")
    else:
        df_pd.index = df_pd.index.tz_convert("UTC")
    df_pd = df_pd.reset_index()
    df_pd = df_pd.rename(
        columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    )
    keep = ["timestamp", "open", "high", "low", "close", "volume"]
    df_pd = df_pd[[c for c in keep if c in df_pd.columns]]
    pl_df = pl.from_pandas(df_pd)
    pl_df = pl_df.with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))
    pl_df = pl_df.with_columns(
        [pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close", "volume") if c in pl_df.columns]
    )
    return pl_df


async def main() -> None:
    storage = ParquetStorageManager()

    print(f"{'epic':<10} {'ticker':<8} {'fetched':>8} {'first':<20} {'last':<20}")
    print("-" * 70)

    for epic in CANDIDATES:
        ticker = TickerMapper.to_yfinance(epic)
        if ticker is None:
            print(f"{epic:<10} <no mapping>")
            continue

        try:
            df = _yf_history(ticker)
        except Exception as exc:
            logger.error(f"{epic}: yfinance error — {exc!r}")
            print(f"{epic:<10} {ticker:<8} ERROR")
            continue

        n = len(df)
        if n == 0:
            print(f"{epic:<10} {ticker:<8} 0 (empty)")
            continue

        first_ts = df["timestamp"][0]
        last_ts = df["timestamp"][-1]

        # Persist via OHLCBar list (matches existing storage contract).
        bars: list[OHLCBar] = []
        for row in df.iter_rows(named=True):
            ts = row["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            bars.append(
                OHLCBar(
                    epic=epic,
                    timeframe="1h",
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"] or 0),
                    source=DataSource.HISTORICAL,
                )
            )
        storage.append_candles(bars, epic, "1h")

        print(f"{epic:<10} {ticker:<8} {n:>8} {str(first_ts)[:19]:<20} {str(last_ts)[:19]:<20}")


if __name__ == "__main__":
    asyncio.run(main())
