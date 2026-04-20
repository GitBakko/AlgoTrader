"""CLI to reconcile a single position against the broker's Transaction History.

Usage:
    python scripts/reconcile_position.py --deal-id <ID> [--days 7] [--yes]

Refuses to run on positions with status='OPEN'. For CLOSED positions
(typically close_reason='UNRECONCILED'), fetches the broker transaction
history, re-applies the three-strategy matching from paper_loop, and
offers to UPDATE the row with the real broker data.

Exit codes:
    0  success (updated or user declined)
    1  position not found
    2  position still OPEN (refused)
    3  no match and nothing entered manually
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# Ensure `src` package is importable when run as a script from the backend dir
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.broker.client import CapitalComClient
from src.broker.models import TransactionType
from src.database.models import Position
from src.trading.paper_loop import PaperTradingLoop
from src.utils.config import get_settings


async def reconcile_deal_id(
    *,
    deal_id: str,
    session,
    broker,
    assume_yes: bool = False,
    days: int = 7,
) -> dict:
    """Core reconciliation logic. Returns a dict describing the outcome.

    Args:
        deal_id: The Position.deal_id to reconcile.
        session: An async SQLAlchemy session.
        broker: A broker client implementing get_transaction_history().
        assume_yes: Skip all confirmation prompts (auto-accept or auto-skip).
        days: How many days back to fetch transaction history.

    Returns:
        A dict with at least a ``status`` key:
        - ``"not_found"``  — deal_id not in DB
        - ``"refused"``    — position is still OPEN
        - ``"updated"``    — position updated successfully
        - ``"skipped"``    — no match found (or manual input skipped)
        - ``"cancelled"``  — user declined the confirmation prompt
    """
    stmt = select(Position).where(Position.deal_id == deal_id)
    position = (await session.execute(stmt)).scalar_one_or_none()

    if position is None:
        return {"status": "not_found", "message": f"No position with deal_id={deal_id!r}"}

    if position.status == "OPEN":
        return {
            "status": "refused",
            "message": (
                f"Position {deal_id!r} is still OPEN. "
                f"Close it via POST /api/positions/close/{deal_id} first."
            ),
        }

    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(days=days)
    transactions = await broker.get_transaction_history(
        from_dt, now, TransactionType.ALL_DEAL
    )

    # Use the same three-strategy matching as paper_loop at runtime.
    # Position model has no deal_reference field, so Strategy 1 is effectively
    # bypassed (deal_reference=None). Strategy 2 (deal_id) and Strategy 3
    # (normalized instrument name + entry price tolerance) carry the load.
    class _Stub:
        _normalize_instrument_name = staticmethod(
            PaperTradingLoop._normalize_instrument_name
        )

    exit_price, pnl, reason = PaperTradingLoop._match_transaction(
        _Stub(),
        transactions,
        deal_id,
        None,  # deal_reference not stored on Position
        position.epic,
        float(position.entry_price or 0),
    )

    if exit_price is None or pnl is None:
        if assume_yes:
            return {"status": "skipped", "message": f"No match in last {days} days (--yes auto-skip)"}

        print(
            f"\nNo matching transaction for {deal_id!r} in the last {days} days.\n"
            "Enter values manually (leave blank to skip):"
        )
        try:
            manual_pnl = input("  P&L: ").strip()
            if not manual_pnl:
                return {"status": "skipped", "message": "No manual value entered"}
            pnl = float(manual_pnl)
            exit_price = float(input("  Exit price: ").strip())
            reason = input("  Close reason [EXTERNAL]: ").strip() or "EXTERNAL"
        except (ValueError, EOFError):
            return {"status": "skipped", "message": "Invalid or empty manual input"}

    # Show the proposed change
    print(
        f"\nReconciliation for {deal_id!r} ({position.epic}):\n"
        f"  current: profit_loss={position.profit_loss!r}, "
        f"current_price={position.current_price!r}, close_reason={position.close_reason!r}\n"
        f"  broker:  profit_loss={pnl:.2f}, current_price={exit_price:.6f}, "
        f"close_reason={reason!r}\n"
    )

    if not assume_yes:
        try:
            confirm = input("Apply UPDATE? [y/N]: ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("y", "yes"):
            return {"status": "cancelled", "message": "User declined"}

    position.profit_loss = Decimal(str(round(pnl, 2)))
    position.current_price = Decimal(str(exit_price))
    position.close_reason = reason or "EXTERNAL"
    await session.commit()

    logger.info(
        f"reconcile_position: updated {deal_id!r} — "
        f"profit_loss={pnl:.2f}, current_price={exit_price:.6f}, close_reason={reason!r}"
    )
    return {
        "status": "updated",
        "profit_loss": float(pnl),
        "current_price": float(exit_price),
        "close_reason": reason,
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile a single position against Capital.com Transaction History.\n"
            "Typically used to fix positions with close_reason='UNRECONCILED'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--deal-id", required=True,
        help="Position deal_id to reconcile (as stored in the positions table)",
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Transaction history window in days (default: 7)",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip all confirmation prompts; auto-skip when no match is found",
    )
    args = parser.parse_args()

    settings = get_settings()

    # Build async DB session (replace sync driver with asyncpg)
    db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Build broker client — CapitalComClient reads credentials from settings internally
    broker = CapitalComClient()
    await broker.connect()

    try:
        async with session_factory() as session:
            result = await reconcile_deal_id(
                deal_id=args.deal_id,
                session=session,
                broker=broker,
                assume_yes=args.yes,
                days=args.days,
            )
    finally:
        await broker.close()
        await engine.dispose()

    status = result["status"]
    message = result.get("message", "")

    if status == "updated":
        return 0
    if status == "cancelled":
        print("Update cancelled.")
        return 0
    if status == "not_found":
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    if status == "refused":
        print(f"ERROR: {message}", file=sys.stderr)
        return 2
    if status == "skipped":
        print(f"Skipped: {message}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
