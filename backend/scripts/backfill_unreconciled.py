"""Backfill UNRECONCILED closed positions using close-detection v2.

Close-detection v2 step 14 (plan `calm-questing-quail.md`).

Iterates every row in ``positions`` with ``status='CLOSED'`` and
``close_reason='UNRECONCILED'`` and ``profit_loss IS NULL``, feeds each
into ``CloseDetector`` (activity-as-source-of-truth + TRADE lookup + FX
convert), and optionally updates the row with the reconciled P&L /
exit price / close reason.

Rows already reconciled (non-NULL ``profit_loss``) are NEVER touched —
including the DE40 row `07101627-0015-549e-0000-0000810436bd` that was
patched manually on 2026-04-22.

Usage::

    # Safe preview — default, no writes:
    python scripts/backfill_unreconciled.py --dry-run

    # Apply — requires explicit flag:
    python scripts/backfill_unreconciled.py --apply --yes

Exit codes:
    0  success
    1  unexpected error
    2  refused (e.g. --apply without --yes)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Ensure `src` package is importable when run as a script from backend/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.broker.client import CapitalComClient
from src.broker.fx import FxConverter
from src.database.models import Position
from src.trading.close_detector import (
    CloseDetector,
    Deferred,
    Reconciled,
    Unreconciled,
)
from src.utils.config import get_settings


# Exit codes
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2


@dataclass
class BackfillReport:
    """Aggregated results of a backfill run."""

    reconciled: list[str] = field(default_factory=list)
    deferred: list[tuple[str, str]] = field(default_factory=list)
    unreconciled_v2: list[tuple[str, str]] = field(default_factory=list)
    skipped_non_null: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return (
            len(self.reconciled)
            + len(self.deferred)
            + len(self.unreconciled_v2)
            + len(self.errors)
        )

    def print_summary(self, *, applied: bool) -> None:
        verb = "APPLIED" if applied else "DRY-RUN (no writes)"
        logger.info(f"=== Backfill summary ({verb}) ===")
        logger.info(f"Reconciled:        {len(self.reconciled):4d}")
        logger.info(f"Deferred:          {len(self.deferred):4d}")
        logger.info(f"Still UNRECONCILED:{len(self.unreconciled_v2):4d}")
        logger.info(f"Skipped (non-null):{len(self.skipped_non_null):4d}")
        logger.info(f"Errors:            {len(self.errors):4d}")

        if self.reconciled:
            logger.info("Reconciled deal_ids:")
            for did in self.reconciled:
                logger.info(f"  - {did}")
        if self.deferred:
            logger.info("Still deferred (no activity / no TRADE row yet):")
            for did, reason in self.deferred:
                logger.info(f"  - {did} ({reason})")
        if self.unreconciled_v2:
            logger.info("v2 Unreconciled (hard stops — manual review required):")
            for did, reason in self.unreconciled_v2:
                logger.info(f"  - {did} ({reason})")
        if self.errors:
            logger.info("Errors:")
            for did, err in self.errors:
                logger.info(f"  - {did}: {err}")


async def fetch_candidates(session: AsyncSession) -> list[Position]:
    """Return every row eligible for backfill.

    Eligible = status='CLOSED' AND close_reason='UNRECONCILED' AND
    profit_loss IS NULL. The profit_loss filter guarantees we never touch
    a row that has already been patched manually.
    """
    stmt = (
        select(Position)
        .where(Position.status == "CLOSED")
        .where(Position.close_reason == "UNRECONCILED")
        .where(Position.profit_loss.is_(None))
        .order_by(Position.closed_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


def _position_to_prev_pos(row: Position) -> dict:
    """Convert a DB Position row into the shape CloseDetector expects."""
    return {
        "deal_id": row.deal_id,
        "epic": row.epic,
        "direction": row.direction,
        "level": float(row.entry_price),
        "size": float(row.size),
        "opened_at": (row.opened_at or datetime.now(UTC)).isoformat(),
        "deal_reference": row.deal_reference,
    }


async def backfill_one(
    *,
    row: Position,
    detector: CloseDetector,
    session: AsyncSession,
    report: BackfillReport,
    apply_writes: bool,
    window_minutes: int = 10,
) -> None:
    """Run CloseDetector on a single DB row and (optionally) update it.

    The activity window is ``closed_at ± window_minutes``. For fresh rows
    the default (10 min) is enough; for historical backfill, pass a larger
    value via --window-minutes (Capital.com keeps ~7d of activity).
    """
    prev_pos = _position_to_prev_pos(row)

    closed_at = row.closed_at or row.opened_at or datetime.now(UTC)
    if closed_at.tzinfo is None:
        closed_at = closed_at.replace(tzinfo=UTC)
    from_dt = closed_at - timedelta(minutes=window_minutes)
    to_dt = closed_at + timedelta(minutes=window_minutes)
    # Capital.com rejects `to` in the future → clamp to now-60s.
    now_utc = datetime.now(UTC)
    if to_dt > now_utc:
        to_dt = now_utc - timedelta(seconds=60)
    logger.info(
        f"[{row.epic}] {row.deal_id} closed_at={closed_at.isoformat()} "
        f"window=±{window_minutes}min"
    )

    activities = await detector._broker.get_activity_history(from_dt, to_dt)
    transactions = await detector._broker.get_transaction_history(from_dt, to_dt)

    try:
        outcomes = await detector.detect(
            previous={row.deal_id: prev_pos},
            current=[],
            activities=activities,
            transactions=transactions,
        )
    except Exception as exc:  # defensive — detector is pure but broker fetch can raise
        report.errors.append((row.deal_id, f"detector: {exc!r}"))
        return

    if not outcomes:
        report.deferred.append((row.deal_id, "no_outcome_emitted"))
        return

    outcome = outcomes[0]
    if isinstance(outcome, Reconciled):
        logger.info(
            f"[{row.epic}] {row.deal_id} → Reconciled "
            f"(pnl=${outcome.pnl:.2f}, exit={outcome.exit_price:.6f}, "
            f"reason={outcome.close_reason})"
        )
        if apply_writes:
            row.profit_loss = Decimal(f"{outcome.pnl:.2f}")
            row.current_price = Decimal(f"{outcome.exit_price:.6f}")
            row.close_reason = outcome.close_reason
            row.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(row)
        report.reconciled.append(row.deal_id)
    elif isinstance(outcome, Deferred):
        logger.info(f"[{row.epic}] {row.deal_id} → Deferred ({outcome.reason})")
        report.deferred.append((row.deal_id, outcome.reason))
    elif isinstance(outcome, Unreconciled):
        logger.warning(
            f"[{row.epic}] {row.deal_id} → v2 Unreconciled ({outcome.reason})"
        )
        report.unreconciled_v2.append((row.deal_id, outcome.reason))


async def run_backfill(
    *,
    session: AsyncSession,
    detector: CloseDetector,
    apply_writes: bool,
    window_minutes: int = 10,
) -> BackfillReport:
    """Iterate every eligible row, reconcile, report."""
    rows = await fetch_candidates(session)
    logger.info(f"Found {len(rows)} UNRECONCILED row(s) with profit_loss=NULL")
    report = BackfillReport()
    for row in rows:
        await backfill_one(
            row=row,
            detector=detector,
            session=session,
            report=report,
            apply_writes=apply_writes,
            window_minutes=window_minutes,
        )
    if apply_writes and report.reconciled:
        await session.commit()
        logger.info(f"Committed {len(report.reconciled)} update(s)")
    elif apply_writes:
        logger.info("No rows reconciled — nothing to commit")
    else:
        logger.info("Dry-run: rollback (no writes performed)")
        await session.rollback()
    return report


async def _main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
        echo=False,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Build broker + detector. CapitalComClient reads credentials from
    # settings based on USE_DEMO, so no kwargs needed here.
    broker = CapitalComClient()
    try:
        await broker.connect()
    except Exception as exc:
        logger.error(f"Broker connect failed: {exc!r}")
        await engine.dispose()
        return EXIT_ERROR

    detector = CloseDetector(
        broker=broker, fx_converter=FxConverter(), account_currency=args.account_currency
    )

    try:
        async with session_factory() as session:
            report = await run_backfill(
                session=session,
                detector=detector,
                apply_writes=args.apply,
                window_minutes=args.window_minutes,
            )
    finally:
        try:
            await broker.close()
        except Exception:
            pass
        await engine.dispose()

    report.print_summary(applied=args.apply)
    return EXIT_OK


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill UNRECONCILED positions via close-detection v2."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without writing (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Persist reconciled rows to the DB.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="Skip the interactive confirmation prompt for --apply.",
    )
    parser.add_argument(
        "--account-currency",
        default="USD",
        help="Account currency for FX conversion (default: USD).",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=10,
        help=(
            "Half-width of the activity fetch window around closed_at "
            "(default: 10). For historical backfills bump to e.g. 2880 "
            "(±48h) since closed_at in the DB may be the UNRECONCILED "
            "timeout moment, not the real broker close."
        ),
    )
    args = parser.parse_args(argv)
    # --apply and --dry-run default to False/True respectively — normalize.
    if args.apply:
        args.dry_run = False
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.apply and not args.yes:
        logger.error(
            "--apply requires --yes to avoid accidental writes. "
            "Re-run with `--apply --yes` after previewing with `--dry-run`."
        )
        return EXIT_REFUSED
    try:
        return asyncio.run(_main(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
