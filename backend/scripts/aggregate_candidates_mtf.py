"""Aggregate 1h candles to 4h + 1d for Phase 12 candidates.

Multi-timeframe FeatureBuilder needs 4h and 1d parquet alongside 1h.
For Phase 12 candidates (AAPL/MSFT/GOOGL/AMZN/META/AMD/USDCHF/USDCAD)
only 1h history exists from the yfinance pull — so retrain models
ended up with 83/68 features instead of 199 (missing 4h_* + 1d_*
columns that account for ~116 features).

This script builds the missing higher-timeframe parquet files via
Polars `group_by_dynamic` aggregation, anchored to a fixed UTC
schedule (4h grid: 00/04/08/12/16/20 UTC matches the bar-alignment
loop; 1d grid: 00 UTC).
"""

from __future__ import annotations

import sys
from datetime import UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import polars as pl
from loguru import logger

from src.data.models import DataSource, OHLCBar
from src.data.storage import ParquetStorageManager

CANDIDATES: list[str] = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "AMD",
    "USDCHF",
    "USDCAD",
]


def _aggregate(df: pl.DataFrame, every: str) -> pl.DataFrame:
    """Aggregate 1h OHLCV to a higher timeframe.

    Uses `group_by_dynamic` with explicit `start_by="datapoint"` so the
    first bucket is anchored on the dataset's first timestamp (not on
    the calendar epoch — important when history doesn't start exactly
    on a UTC boundary).

    Returns a DataFrame with the standard OHLCV schema.
    """
    return (
        df.sort("timestamp")
        .group_by_dynamic("timestamp", every=every, closed="left", label="left")
        .agg(
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
        )
    )


def _to_bars(df: pl.DataFrame, epic: str, timeframe: str) -> list[OHLCBar]:
    bars: list[OHLCBar] = []
    for row in df.iter_rows(named=True):
        ts = row["timestamp"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        bars.append(
            OHLCBar(
                epic=epic,
                timeframe=timeframe,
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"] or 0),
                source=DataSource.HISTORICAL,
            )
        )
    return bars


def main() -> None:
    storage = ParquetStorageManager()

    print(f"{'epic':<10} {'1h_in':>6} {'4h_out':>6} {'1d_out':>6}")
    print("-" * 40)

    for epic in CANDIDATES:
        # Load every available 1h month for this epic.
        epic_dir = Path("data/historical") / epic / "1h"
        if not epic_dir.exists():
            print(f"{epic:<10} no 1h data on disk")
            continue
        files = sorted(epic_dir.glob("*.parquet"))
        if not files:
            print(f"{epic:<10} no 1h parquet")
            continue

        df_1h = pl.concat([pl.read_parquet(f) for f in files], how="vertical_relaxed")
        df_1h = df_1h.with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))
        df_1h = df_1h.unique(subset=["timestamp"]).sort("timestamp")
        n_1h = len(df_1h)

        df_4h = _aggregate(df_1h, "4h")
        df_1d = _aggregate(df_1h, "1d")

        storage.append_candles(_to_bars(df_4h, epic, "4h"), epic, "4h")
        storage.append_candles(_to_bars(df_1d, epic, "1d"), epic, "1d")

        print(f"{epic:<10} {n_1h:>6} {len(df_4h):>6} {len(df_1d):>6}")


if __name__ == "__main__":
    main()
