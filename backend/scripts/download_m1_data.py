"""
Download M1 (1-minute) historical candles from Capital.com for ORB+FVG strategy.

Capital.com API quirks for MINUTE resolution:
- Returns max ~1000 bars per request when max_candles is specified
- Without max_candles, returns only 10 bars
- Timestamps are in CET/CEST (Europe/Berlin), NOT UTC
- API accepts UTC datetimes as from/to parameters

This script converts all timestamps to UTC before saving.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/download_m1_data.py
    .venv/Scripts/python.exe scripts/download_m1_data.py --assets US500 NAS100
    .venv/Scripts/python.exe scripts/download_m1_data.py --months 6
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Add backend src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl
from loguru import logger

from src.broker.client import CapitalComClient
from src.broker.models import Resolution

# Assets relevant for ORB+FVG intraday strategy
DEFAULT_ASSETS = ["US500", "NAS100", "NVDA", "TSLA"]

# Capital.com: max_candles=1000 with 6-hour window works reliably
MAX_CANDLES = 1000
CHUNK_HOURS = 6

# Rate limiting
REQUEST_DELAY_S = 0.10

# Retry config
MAX_RETRIES = 3
RETRY_DELAY_S = 2.0

# Output directory
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"

# Capital.com returns timestamps in this timezone
BROKER_TZ = ZoneInfo("Europe/Berlin")

# Parquet schema — timestamps stored as naive UTC
PARQUET_SCHEMA = {
    "timestamp": pl.Datetime("us"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
}


def cet_to_utc(dt: datetime) -> datetime:
    """Convert a naive CET/CEST timestamp to naive UTC."""
    # Interpret naive datetime as Europe/Berlin
    aware = dt.replace(tzinfo=BROKER_TZ)
    # Convert to UTC, then strip tzinfo for storage
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def candles_to_dataframe(candles: list) -> pl.DataFrame:
    """Convert OHLCCandle list to a Polars DataFrame with UTC timestamps."""
    if not candles:
        return pl.DataFrame(schema=PARQUET_SCHEMA)

    rows = [
        {
            "timestamp": cet_to_utc(c.timestamp),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": float(c.last_traded_volume) if c.last_traded_volume is not None else 0.0,
        }
        for c in candles
    ]
    return pl.DataFrame(rows, schema=PARQUET_SCHEMA)


def get_parquet_path(epic: str, year: int, month: int) -> Path:
    """Return path: data/historical/{EPIC}/1min/YYYY-MM.parquet"""
    return DATA_DIR / epic / "1min" / f"{year:04d}-{month:02d}.parquet"


def load_existing(path: Path) -> pl.DataFrame:
    """Load existing parquet file, or return empty DataFrame."""
    if path.exists():
        return pl.read_parquet(path)
    return pl.DataFrame(schema=PARQUET_SCHEMA)


def merge_and_deduplicate(existing: pl.DataFrame, new: pl.DataFrame) -> pl.DataFrame:
    """Merge two DataFrames, deduplicate by timestamp, sort ascending."""
    if existing.is_empty():
        return new.sort("timestamp")
    if new.is_empty():
        return existing.sort("timestamp")

    combined = pl.concat([existing, new])
    return combined.unique(subset=["timestamp"]).sort("timestamp")


def save_parquet(df: pl.DataFrame, path: Path) -> None:
    """Save DataFrame to parquet, creating directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


async def fetch_chunk_with_retry(
    client: CapitalComClient,
    epic: str,
    from_dt: datetime,
    to_dt: datetime,
) -> list:
    """Fetch a chunk of M1 candles with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            candles = await client.get_historical_prices(
                epic=epic,
                resolution=Resolution.MINUTE,
                from_date=from_dt,
                to_date=to_dt,
                max_candles=MAX_CANDLES,
            )
            return candles
        except Exception as e:
            err_str = str(e)
            # Don't retry on non-transient errors
            if "not-found" in err_str or "not.found" in err_str:
                return []
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY_S * attempt
                logger.warning(
                    f"  Retry {attempt}/{MAX_RETRIES} for {epic} "
                    f"({from_dt.date()} -> {to_dt.date()}): {e}. "
                    f"Waiting {wait:.1f}s..."
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"  FAILED after {MAX_RETRIES} retries for {epic} "
                    f"({from_dt.date()} -> {to_dt.date()}): {e}"
                )
                return []


async def download_asset(client: CapitalComClient, epic: str, months_back: int) -> int:
    """
    Download M1 data for a single asset, iterating backwards in chunks.

    Returns total number of new candles downloaded.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = now - timedelta(days=months_back * 30)

    logger.info(f"\n{'='*60}")
    logger.info(f"Downloading M1 data for {epic}")
    logger.info(f"  Range: {start_date.date()} -> {now.date()} (~{months_back} months)")
    logger.info(f"{'='*60}")

    cursor = now
    total_candles = 0
    chunk_count = 0
    empty_streak = 0

    all_candles_df = pl.DataFrame(schema=PARQUET_SCHEMA)

    while cursor > start_date:
        chunk_end = cursor
        chunk_start = max(cursor - timedelta(hours=CHUNK_HOURS), start_date)

        chunk_count += 1
        if chunk_count % 10 == 1:
            logger.info(
                f"  Chunk {chunk_count}: {chunk_start.strftime('%Y-%m-%d %H:%M')} "
                f"-> {chunk_end.strftime('%Y-%m-%d %H:%M')} "
                f"(total so far: {total_candles})"
            )

        candles = await fetch_chunk_with_retry(client, epic, chunk_start, chunk_end)

        if candles:
            df = candles_to_dataframe(candles)
            all_candles_df = pl.concat([all_candles_df, df]) if not all_candles_df.is_empty() else df
            total_candles += len(candles)
            empty_streak = 0

            # Move cursor to just before the earliest candle (in UTC)
            earliest_utc = df["timestamp"].min()
            cursor = earliest_utc - timedelta(minutes=1)
        else:
            empty_streak += 1
            cursor = chunk_start - timedelta(minutes=1)

            if empty_streak >= 15:
                logger.warning(
                    f"  15 consecutive empty chunks for {epic}, "
                    f"stopping at {cursor.date()}"
                )
                break

        await asyncio.sleep(REQUEST_DELAY_S)

    logger.info(f"  Downloaded {total_candles} raw candles in {chunk_count} chunks")

    # Deduplicate and save to monthly parquet files
    if not all_candles_df.is_empty():
        all_candles_df = all_candles_df.unique(subset=["timestamp"]).sort("timestamp")

        all_candles_df = all_candles_df.with_columns([
            pl.col("timestamp").dt.year().alias("_year"),
            pl.col("timestamp").dt.month().alias("_month"),
        ])

        monthly_groups = all_candles_df.group_by(["_year", "_month"])
        saved_count = 0

        for (year, month), group_df in monthly_groups:
            month_df = group_df.drop(["_year", "_month"])
            path = get_parquet_path(epic, int(year), int(month))

            existing = load_existing(path)
            merged = merge_and_deduplicate(existing, month_df)
            save_parquet(merged, path)

            new_bars = len(merged) - len(existing)
            saved_count += len(merged)
            logger.info(
                f"  Saved {path.name}: {len(merged)} bars "
                f"(+{new_bars} new)"
            )

        logger.info(f"  Total for {epic}: {saved_count} unique bars across monthly files")
    else:
        logger.warning(f"  No data downloaded for {epic}")

    return total_candles


async def main(args: argparse.Namespace) -> None:
    """Download M1 historical data from Capital.com."""
    assets = args.assets
    months_back = args.months

    logger.info("=" * 60)
    logger.info("MANTIS AI - M1 Data Download (ORB+FVG Strategy)")
    logger.info("=" * 60)
    logger.info(f"Assets: {assets}")
    logger.info(f"Months back: {months_back}")
    logger.info(f"Chunk: {CHUNK_HOURS}h, max_candles={MAX_CANDLES}")
    logger.info(f"Output dir: {DATA_DIR}")
    logger.info(f"Timestamps: converted from CET/CEST to UTC")

    client = CapitalComClient()

    try:
        logger.info("\nConnecting to Capital.com...")
        await client.connect()
        logger.info("Connected successfully")

        results = {}
        for epic in assets:
            try:
                count = await download_asset(client, epic, months_back)
                results[epic] = count
            except Exception as e:
                logger.error(f"Failed to download {epic}: {e}", exc_info=True)
                results[epic] = -1

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("DOWNLOAD SUMMARY")
        logger.info(f"{'='*60}")
        for epic, count in results.items():
            if count >= 0:
                logger.info(f"  [OK]   {epic}: {count:,} candles fetched")
            else:
                logger.error(f"  [FAIL] {epic}: download failed")

        total = sum(c for c in results.values() if c >= 0)
        logger.info(f"\nTotal: {total:,} candles downloaded")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await client.close()
        logger.info("Connection closed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download M1 candles from Capital.com for ORB+FVG strategy"
    )
    parser.add_argument(
        "--assets",
        nargs="+",
        default=DEFAULT_ASSETS,
        help=f"Asset epics to download (default: {' '.join(DEFAULT_ASSETS)})",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=12,
        help="Months of history to download (default: 12)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
