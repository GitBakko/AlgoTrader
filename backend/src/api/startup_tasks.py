"""
Background startup tasks for AlgoTrader AI.
These run as asyncio tasks and do not block application startup.
"""

import asyncio

from loguru import logger

from src.utils.constants import ALL_ASSETS


async def initial_data_download(app_state) -> None:
    """
    Check if historical data exists; if not, download via broker.
    Runs as a background task after startup.
    """
    broker = getattr(app_state, "broker_client", None)
    storage = getattr(app_state, "storage", None)

    if not broker or not storage:
        logger.info("Skipping data download (no broker or storage)")
        return

    # Check if we already have data
    try:
        from src.data.data_access import DataAccessLayer

        data_access = app_state.data_access
        if data_access is None:
            return

        # Check for 1h XAUUSD data as a proxy
        df = data_access.get_candles("XAUUSD", "1h", limit=10)
        if not df.is_empty():
            logger.info(f"Historical data exists ({len(df)} recent candles), skipping download")
            return
    except Exception as e:
        logger.debug(f"Data existence check failed, proceeding to download: {e}")

    # No data found - download
    logger.info("No historical data found, starting initial download...")
    try:
        from src.data.historical_downloader import HistoricalDownloader

        downloader = HistoricalDownloader(client=broker, storage=storage)

        # Download 1 year of 1h, 4h, 1d for all 21 assets (Phase 12: Portfolio Expansion)
        results = await downloader.download_all_assets(
            assets=ALL_ASSETS,
            timeframes=["1h", "4h", "1d"],
            days_back=365,
        )

        total = sum(r.downloaded_candles for r in results)
        logger.info(f"Initial data download complete: {total} candles across {len(results)} series")
    except Exception as e:
        logger.error(f"Initial data download failed: {e}")


async def start_data_scheduler(app_state) -> None:
    """
    Start the APScheduler for periodic data collection.
    """
    broker = getattr(app_state, "broker_client", None)
    storage = getattr(app_state, "storage", None)

    if not broker or not storage:
        logger.info("Skipping scheduler start (no broker or storage)")
        return

    data_access = getattr(app_state, "data_access", None)
    if not data_access:
        logger.info("Skipping scheduler start (no data_access)")
        return

    try:
        from src.data.scheduler import DataScheduler

        prediction_service = getattr(app_state, "prediction_service", None)
        scheduler = DataScheduler(
            client=broker,
            storage=storage,
            data_access=data_access,
            prediction_service=prediction_service,
        )
        scheduler.setup()
        scheduler.start()
        app_state.data_scheduler = scheduler
        logger.info("Data scheduler started (with weekly model retrain)")
    except Exception as e:
        logger.error(f"Failed to start data scheduler: {e}")
