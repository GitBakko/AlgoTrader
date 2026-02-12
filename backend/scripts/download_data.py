"""
Script per scaricare dati storici da Capital.com demo.
Scarica OHLC data per XAUUSD, BTCUSD, US500 (timeframes: 1h, 4h, 1d).

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/download_data.py
    .venv/Scripts/python.exe scripts/download_data.py --days 365 --assets XAUUSD BTCUSD
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add backend src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from loguru import logger

from src.broker.client import CapitalComClient
from src.data.historical_downloader import HistoricalDownloader
from src.data.models import DownloadProgress
from src.data.storage import ParquetStorageManager


def on_progress(progress: DownloadProgress) -> None:
    """Print download progress."""
    pct = (
        (progress.downloaded_days / progress.total_days * 100)
        if progress.total_days > 0
        else 0
    )
    logger.info(
        f"  [{progress.epic}/{progress.timeframe}] "
        f"{pct:.0f}% - {progress.downloaded_candles} candles"
    )


async def main(args: argparse.Namespace) -> None:
    """Download historical data from Capital.com."""
    logger.info("=" * 60)
    logger.info("AlgoTrader AI - Historical Data Download")
    logger.info("=" * 60)

    assets = args.assets
    timeframes = args.timeframes
    days_back = args.days

    logger.info(f"Assets: {assets}")
    logger.info(f"Timeframes: {timeframes}")
    logger.info(f"Days back: {days_back}")

    storage = ParquetStorageManager()
    client = CapitalComClient()

    try:
        logger.info("Connecting to Capital.com demo...")
        await client.connect()
        logger.info("Connected successfully")

        downloader = HistoricalDownloader(client=client, storage=storage)

        results = await downloader.download_all_assets(
            assets=assets,
            timeframes=timeframes,
            days_back=days_back,
            on_progress=on_progress,
        )

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("DOWNLOAD SUMMARY")
        logger.info("=" * 60)

        total_candles = 0
        for r in results:
            status_icon = "OK" if r.status == "completed" else "FAIL"
            logger.info(
                f"  [{status_icon}] {r.epic}/{r.timeframe}: "
                f"{r.downloaded_candles} candles"
            )
            if r.error_message:
                logger.error(f"       Error: {r.error_message}")
            total_candles += r.downloaded_candles

        logger.info(f"\nTotal: {total_candles} candles downloaded")

        # Verify stored data
        logger.info("\nVerifying stored data:")
        for epic in assets:
            for tf in timeframes:
                df = storage.read_candles(epic=epic, timeframe=tf)
                if not df.is_empty():
                    first = df["timestamp"].min()
                    last = df["timestamp"].max()
                    logger.info(
                        f"  {epic}/{tf}: {len(df)} bars "
                        f"({first.date()} -> {last.date()})"
                    )
                else:
                    logger.warning(f"  {epic}/{tf}: no data")

    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await client.close()
        logger.info("Connection closed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download historical data from Capital.com")
    parser.add_argument(
        "--assets",
        nargs="+",
        default=["XAUUSD", "BTCUSD", "US500", "WTIUSD", "EURUSD",
                 "NVDA", "TSLA", "XAGUSD", "DE40"],
        help="Asset epics to download (default: all 9 assets)",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1h", "4h", "1d"],
        help="Timeframes to download (default: 1h 4h 1d)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=730,
        help="Number of days of historical data (default: 730)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
