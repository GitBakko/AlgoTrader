"""Weekly data-quality audit.

Scans Postgres + today's log file for anomalies that the long-running
trading loop should never produce:

  - UNRECONCILED rows with profit_loss=NULL         → any = anomaly
  - Recent STALE_CLEANUP rows (last 7 days)         → any = anomaly
  - OPEN positions older than 7 days                → any = anomaly
  - Position.exit_price == entry_price on closed    → arithmetic fallback
    rows outside the UNRECONCILED family
  - swap_daily_snapshots gaps (< (days-1) rows per  → scheduler missed
    epic in the last `days` window)                  days

Writes a markdown report to ``docs/reports/weekly_data_quality_YYYY-MM-DD.md``.
Exits 1 when any anomaly is found (caller can alert). Exit 0 means clean.

Usage:
    python scripts/weekly_data_quality.py [--days 7]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Ensure project root (backend/) is on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


async def _main() -> int:
    from loguru import logger
    from sqlalchemy import text

    from src.database.session import DatabaseManager
    from src.utils.constants import TRADABLE_ASSETS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7,
                        help="Rolling window in days for gap/snapshot checks")
    args = parser.parse_args()
    window_days = max(1, args.days)

    DatabaseManager.initialize()

    anomalies: list[str] = []
    sections: list[str] = []

    async with DatabaseManager.session() as session:
        # ---- 1. UNRECONCILED with NULL pnl ----
        r = await session.execute(text("""
            SELECT deal_id, epic, direction, closed_at
            FROM positions
            WHERE status='CLOSED'
              AND close_reason='UNRECONCILED'
              AND profit_loss IS NULL
            ORDER BY closed_at DESC
            LIMIT 50
        """))
        unrecon = r.fetchall()
        sections.append(
            "## UNRECONCILED (pnl=NULL)\n\n"
            f"- total: {len(unrecon)}\n"
            + ("- **anomaly** — run backfill_unreconciled.py --dry-run\n"
               if unrecon else "- clean\n")
            + "".join(
                f"  - `{row.deal_id}` {row.epic} {row.direction} @ {row.closed_at}\n"
                for row in unrecon[:10]
            )
        )
        if unrecon:
            anomalies.append(f"unreconciled={len(unrecon)}")

        # ---- 2. STALE_CLEANUP rows in the last `window_days` ----
        r = await session.execute(
            text("""
                SELECT COUNT(*) AS c
                FROM positions
                WHERE close_reason='STALE_CLEANUP'
                  AND closed_at > now() - make_interval(days => :d)
            """),
            {"d": window_days},
        )
        stale_recent = r.scalar_one() or 0
        sections.append(
            f"## Recent STALE_CLEANUP (last {window_days}d)\n\n"
            f"- count: {stale_recent}\n"
            + ("- **anomaly** — loop is flagging positions as stale\n"
               if stale_recent else "- clean\n")
        )
        if stale_recent:
            anomalies.append(f"stale_recent={stale_recent}")

        # ---- 3. OPEN rows older than 7d ----
        r = await session.execute(text("""
            SELECT deal_id, epic, direction, opened_at
            FROM positions
            WHERE status='OPEN'
              AND opened_at < now() - interval '7 days'
            ORDER BY opened_at ASC
        """))
        old_open = r.fetchall()
        sections.append(
            "## OPEN positions older than 7 days\n\n"
            f"- count: {len(old_open)}\n"
            + ("- **anomaly** — investigate, broker may have closed them silently\n"
               if old_open else "- clean\n")
            + "".join(
                f"  - `{row.deal_id}` {row.epic} {row.direction} @ {row.opened_at}\n"
                for row in old_open[:10]
            )
        )
        if old_open:
            anomalies.append(f"old_open={len(old_open)}")

        # ---- 4. Arithmetic-fallback suspects: exit == entry on non-UNRECON ----
        r = await session.execute(text("""
            SELECT deal_id, epic, close_reason, entry_price, current_price
            FROM positions
            WHERE status='CLOSED'
              AND close_reason NOT IN ('UNRECONCILED', 'STALE_CLEANUP')
              AND profit_loss IS NOT NULL
              AND entry_price IS NOT NULL
              AND current_price IS NOT NULL
              AND ABS(entry_price - current_price) < 1e-6
            ORDER BY closed_at DESC
            LIMIT 50
        """))
        arith_suspects = r.fetchall()
        sections.append(
            "## Arithmetic-fallback suspects (exit==entry)\n\n"
            f"- count: {len(arith_suspects)}\n"
            + ("- **anomaly** — exit==entry + known pnl is a historical "
               "arithmetic fallback symptom\n"
               if arith_suspects else "- clean\n")
            + "".join(
                f"  - `{row.deal_id}` {row.epic} reason={row.close_reason} "
                f"entry={row.entry_price}\n"
                for row in arith_suspects[:10]
            )
        )
        if arith_suspects:
            anomalies.append(f"arith_suspects={len(arith_suspects)}")

        # ---- 5. Swap-snapshot gaps ----
        cutoff = date.today() - timedelta(days=window_days - 1)
        r = await session.execute(
            text("""
                SELECT epic, COUNT(*) AS c
                FROM swap_daily_snapshots
                WHERE snapshot_date >= :cutoff
                GROUP BY epic
            """),
            {"cutoff": cutoff},
        )
        snap_counts = {row.epic: row.c for row in r.fetchall()}

        expected = min(window_days, (date.today() - cutoff).days + 1)
        gap_lines: list[str] = []
        gapped = 0
        for epic in TRADABLE_ASSETS:
            have = snap_counts.get(epic.upper(), 0)
            missing = expected - have
            if missing > 0:
                gapped += 1
                gap_lines.append(
                    f"  - {epic.upper()}: {have}/{expected} rows "
                    f"(missing {missing})\n"
                )
        sections.append(
            f"## Swap snapshot gaps (last {window_days}d, {expected} expected/epic)\n\n"
            f"- epics with gaps: {gapped}\n"
            + ("- **anomaly** — scheduler not writing every day\n"
               if gapped else "- clean\n")
            + "".join(gap_lines[:12])
        )
        if gapped > 0:
            anomalies.append(f"swap_gaps={gapped}")

    await DatabaseManager.close()

    # ---- Report ----
    today_iso = date.today().isoformat()
    header = (
        f"# Weekly Data Quality — {today_iso}\n\n"
        f"Window: last {window_days} days. Generated: "
        f"{datetime.now(UTC).isoformat()}\n\n"
        f"**Status**: {'anomalies' if anomalies else 'clean'}"
        + (f" — {', '.join(anomalies)}" if anomalies else "")
        + "\n\n---\n\n"
    )
    report = header + "\n".join(sections)

    reports_dir = Path(_BACKEND_ROOT).parent / "docs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"weekly_data_quality_{today_iso}.md"
    out_path.write_text(report, encoding="utf-8")
    logger.info(f"Report written: {out_path}")

    if anomalies:
        logger.warning(f"Anomalies detected: {', '.join(anomalies)}")
        return 1

    logger.info("Data quality check clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
