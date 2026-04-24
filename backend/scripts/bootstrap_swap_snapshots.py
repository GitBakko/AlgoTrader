"""One-shot: fire the daily swap-snapshot job immediately.

Useful for bootstrapping the table on first deploy (or after a missed
scheduler window) so Dashboard v2 /swap-accum has at least today's row
per epic.

Usage:
    python scripts/bootstrap_swap_snapshots.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure project root (backend/) is on sys.path when run as ``python scripts/...``
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


async def _main() -> int:
    from loguru import logger

    from src.broker.client import CapitalComClient
    from src.data.data_access import DataAccessLayer
    from src.data.scheduler import DataScheduler
    from src.data.storage import ParquetStorageManager
    from src.database.session import DatabaseManager
    from src.utils.config import get_settings

    settings = get_settings()

    DatabaseManager.initialize()

    client = CapitalComClient()
    await client.connect()
    storage = ParquetStorageManager()
    data_access = DataAccessLayer(storage=storage)
    scheduler = DataScheduler(
        client=client,
        storage=storage,
        data_access=data_access,
    )

    try:
        await scheduler.job_swap_snapshot()
    finally:
        await client.close()
        await DatabaseManager.close()

    logger.info("Bootstrap complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
