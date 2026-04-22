"""Capture live Capital.com API responses into test fixtures.

Saves raw JSON responses of `/api/v1/history/activity` and
`/api/v1/history/transactions` into
`backend/tests/fixtures/broker_api/` so schema-drift and close-detection
regression tests can replay against deterministic golden data.

Usage (from backend/ dir):

    python scripts/capture_broker_fixtures.py \\
        --hours 48 \\
        --out tests/fixtures/broker_api \\
        --name session_20260421

Writes two files per invocation:
    <name>_activity.json
    <name>_transactions.json

Each contains the raw response body unchanged (so Pydantic parsing is
exercised on the exact bytes the broker returned).

Credentials come from the regular `get_settings()` plumbing — no secrets
are embedded in fixtures. The current account id (demo vs live) IS recorded
in a tiny metadata header so the test harness can guard against accidentally
loading a LIVE-account fixture into the DEMO test suite (and vice versa).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure `src` package is importable when run as a script from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.broker.client import CapitalComClient
from src.utils.config import get_settings


async def capture_fixture(out_dir: Path, name: str, hours: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    client = CapitalComClient()
    await client.connect()

    now = datetime.now(UTC)
    frm = now - timedelta(hours=hours)

    # Activity — authoritative source of close linkage.
    activity_params = {
        "from": frm.strftime("%Y-%m-%dT%H:%M:%S"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "detailed": "true",
    }
    activity_raw = await client._request(
        "GET", "/api/v1/history/activity", params=activity_params
    )

    # Transactions — authoritative source of realized P&L.
    tx_params = {
        "from": frm.strftime("%Y-%m-%dT%H:%M:%S"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "type": "TRADE",
    }
    tx_raw = await client._request(
        "GET", "/api/v1/history/transactions", params=tx_params
    )

    settings = get_settings()
    metadata = {
        "captured_at_utc": now.isoformat(),
        "window_hours": hours,
        "execution_mode": settings.execution_mode,
        "base_url": getattr(settings, "capital_demo_api_url", None)
        if settings.execution_mode == "DEMO"
        else getattr(settings, "capital_live_api_url", None),
    }

    activity_file = out_dir / f"{name}_activity.json"
    tx_file = out_dir / f"{name}_transactions.json"

    with activity_file.open("w", encoding="utf-8") as fh:
        json.dump({"_meta": metadata, "response": activity_raw}, fh, indent=2)
    with tx_file.open("w", encoding="utf-8") as fh:
        json.dump({"_meta": metadata, "response": tx_raw}, fh, indent=2)

    activity_count = len(activity_raw.get("activities", []))
    tx_count = len(tx_raw.get("transactions", []))
    logger.info(
        f"Captured {activity_count} activities → {activity_file.name}, "
        f"{tx_count} transactions → {tx_file.name} "
        f"({metadata['execution_mode']}, window={hours}h)"
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/fixtures/broker_api"),
        help="Destination directory (default: tests/fixtures/broker_api)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=datetime.now(UTC).strftime("capture_%Y%m%d_%H%M%S"),
        help="Fixture basename (default: capture_<utc timestamp>)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=48,
        help="History window in hours (default: 48)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(capture_fixture(args.out, args.name, args.hours))
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        logger.exception(f"Capture failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
