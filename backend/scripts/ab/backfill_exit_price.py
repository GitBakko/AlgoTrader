"""One-shot: backfill trades.exit_price with the broker close level from
/history/activity for historical BROKER_ACTIVITY closes (exit_price was the
reconcile-time mid before the 2026-06-12 fix).

Usage (from backend/):
  .venv/Scripts/python.exe scripts/ab/backfill_exit_price.py --dry-run
  .venv/Scripts/python.exe scripts/ab/backfill_exit_price.py

BACK UP THE LEDGER FIRST:
  copy data\\forward_lab\\ledger.db data\\forward_lab\\ledger.pre-backfill.db
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from loguru import logger  # noqa: E402

DEFAULT_DB = ROOT / "data" / "forward_lab" / "ledger.db"


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def backfill(db_path, client, dry_run: bool = True) -> dict:
    """For each closed BROKER_ACTIVITY row, find its close event in a <24h
    activity window ending at closed_at and rewrite exit_price = details.level.
    Same matching rule as scheduler._realized Tier-2 (epic + openPrice≈entry)."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, epic, entry, opened_at, closed_at, exit_price FROM trades "
        "WHERE closed_at IS NOT NULL AND close_reason='BROKER_ACTIVITY'"
    ).fetchall()
    report = {"total": len(rows), "updated": 0, "no_match": 0, "no_level": 0}
    for row in rows:
        closed = _parse_dt(row["closed_at"])
        act_from = closed - timedelta(hours=23)
        try:
            acts = await client.get_activity_history(act_from, closed)
        except Exception as e:  # noqa: BLE001 — per-row failure must not kill the run
            logger.warning(f"[backfill] {row['epic']} id={row['id']}: activity fetch failed: {e}")
            report["no_match"] += 1
            continue
        entry = float(row["entry"])
        tol = max(1e-6, abs(entry) * 1e-4)
        level = None
        for a in acts:
            if not a.is_close_event() or a.epic != row["epic"]:
                continue
            op = a.details.open_price
            if op is None or abs(float(op) - entry) > tol:
                continue
            level = a.details.level
            break
        if level is None:
            key = "no_level" if acts else "no_match"
            report[key] += 1
            logger.info(f"[backfill] {row['epic']} id={row['id']}: unresolved ({key})")
            continue
        logger.info(
            f"[backfill] {row['epic']} id={row['id']}: exit_price "
            f"{row['exit_price']} -> {float(level)}{' (dry-run)' if dry_run else ''}")
        report["updated"] += 1
        if not dry_run:
            con.execute("UPDATE trades SET exit_price=? WHERE id=?", (float(level), row["id"]))
            con.commit()
    con.close()
    logger.success(f"[backfill] done: {report}")
    return report


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from src.broker.client import CapitalComClient
    from src.utils.config import get_settings

    s = get_settings()
    client = CapitalComClient(api_key=s.capital_experiment_api_key,
                              email=s.capital_experiment_email,
                              password=s.capital_experiment_password)
    await client.connect()
    try:
        if s.capital_experiment_account_id and (
            await client.get_active_account_id() != s.capital_experiment_account_id
        ):
            await client.switch_account(s.capital_experiment_account_id)
        await backfill(Path(args.db), client, dry_run=args.dry_run)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(_main())
