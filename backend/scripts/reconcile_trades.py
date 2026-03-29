"""
Reconcile MANTIS DB positions with Capital.com broker transaction history.

Queries the broker for real exit prices and P&L, compares with our DB records,
and corrects any mismatches. This fixes the critical P&L pipeline bug where
exit prices were guessed from live prices instead of using actual broker data.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/reconcile_trades.py [--days 7] [--dry-run]
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.broker.client import EPIC_TO_BROKER, CapitalComClient
from src.broker.models import TransactionType
from src.database.session import DatabaseManager
from src.utils.config import get_settings


async def fetch_broker_transactions(client: CapitalComClient, days: int) -> list:
    """Fetch all deal transactions from broker for the given period."""
    now = datetime.now(UTC)
    from_date = now - timedelta(days=days)

    all_txns = []
    # Fetch in 24h chunks to avoid API limits
    chunk_start = from_date
    while chunk_start < now:
        chunk_end = min(chunk_start + timedelta(hours=24), now)
        try:
            txns = await client.get_transaction_history(
                chunk_start, chunk_end, TransactionType.ALL_DEAL
            )
            all_txns.extend(txns)
            if txns:
                logger.info(
                    f"  Fetched {len(txns)} transactions for "
                    f"{chunk_start.strftime('%Y-%m-%d %H:%M')} → "
                    f"{chunk_end.strftime('%Y-%m-%d %H:%M')}"
                )
        except Exception as e:
            logger.warning(f"  Failed to fetch chunk {chunk_start}: {e}")
        chunk_start = chunk_end

    return all_txns


async def get_closed_positions(session, days: int) -> list:
    """Get closed positions from the DB for the given period."""
    from sqlalchemy import text

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    result = await session.execute(
        text(
            "SELECT id, deal_id, epic, direction, size, entry_price, "
            "current_price, profit_loss, close_reason, closed_at "
            "FROM positions WHERE status = 'CLOSED' AND closed_at >= :cutoff "
            "ORDER BY closed_at DESC"
        ),
        {"cutoff": cutoff},
    )
    return result.fetchall()


def match_txn_to_position(txns: list, deal_id: str, epic: str, entry_price: float):
    """Find the broker transaction matching a DB position."""
    broker_epic = EPIC_TO_BROKER.get(epic, epic)

    for txn in txns:
        # Match by reference (deal_id)
        ref_match = txn.reference and deal_id and txn.reference == deal_id

        # Match by instrument + entry level
        instrument_match = txn.instrument_name and (
            epic.lower() in txn.instrument_name.lower()
            or broker_epic.lower() in txn.instrument_name.lower()
        )
        entry_match = (
            txn.open_level is not None
            and entry_price > 0
            and abs(txn.open_level - entry_price) / max(entry_price, 1e-9) < 0.002
        )

        if ref_match or (instrument_match and entry_match):
            return txn

    return None


async def equity_comparison(client: CapitalComClient, dry_run: bool) -> None:
    """Compare total equity between broker and DB when per-trade data unavailable.

    This is the fallback for demo accounts where Transaction History API returns empty.
    Reports the discrepancy but cannot fix individual trades.
    """
    from sqlalchemy import text as sa_text

    INITIAL_CAPITAL = 11_000.0

    # Get broker account state
    accounts = await client.get_accounts()
    acc = accounts[0]
    broker_balance = acc.balance  # deposit + realized P&L
    broker_unrealized = acc.profit_loss  # open positions P&L
    broker_equity = broker_balance + broker_unrealized
    broker_realized_pnl = broker_balance - INITIAL_CAPITAL

    logger.info("=" * 70)
    logger.info("BROKER ACCOUNT STATE")
    logger.info("=" * 70)
    logger.info(f"  Balance (deposit + realized): ${broker_balance:,.2f}")
    logger.info(f"  Unrealized P&L (open pos):    ${broker_unrealized:,.2f}")
    logger.info(f"  Equity (total):               ${broker_equity:,.2f}")
    logger.info(f"  Realized P&L since start:     ${broker_realized_pnl:,.2f}")

    # Get DB state
    DatabaseManager.initialize()
    session_factory = DatabaseManager.get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            sa_text(
                "SELECT COUNT(*), COALESCE(SUM(profit_loss), 0) "
                "FROM positions WHERE status = 'CLOSED'"
            )
        )
        row = result.fetchone()
        db_trade_count = row[0]
        db_realized_pnl = float(row[1])

        # Find suspicious trades (TP with loss, SL with profit)
        result2 = await session.execute(
            sa_text(
                "SELECT COUNT(*), COALESCE(SUM(profit_loss), 0) "
                "FROM positions WHERE status = 'CLOSED' "
                "AND ((close_reason = 'TP' AND profit_loss < 0) "
                "  OR (close_reason = 'SL' AND profit_loss > 0))"
            )
        )
        suspicious = result2.fetchone()
        suspicious_count = suspicious[0]
        suspicious_pnl = float(suspicious[1])

    logger.info("")
    logger.info("=" * 70)
    logger.info("MANTIS DB STATE")
    logger.info("=" * 70)
    logger.info(f"  Closed trades:               {db_trade_count}")
    logger.info(f"  DB realized P&L:             ${db_realized_pnl:,.2f}")
    logger.info(f"  Suspicious trades:           {suspicious_count} (TP+loss or SL+profit)")
    logger.info(f"  Suspicious sum:              ${suspicious_pnl:,.2f}")

    discrepancy = db_realized_pnl - broker_realized_pnl
    logger.info("")
    logger.info("=" * 70)
    logger.info("COMPARISON")
    logger.info("=" * 70)
    logger.info(f"  Broker realized P&L: ${broker_realized_pnl:>10,.2f}")
    logger.info(f"  DB realized P&L:     ${db_realized_pnl:>10,.2f}")
    logger.info(f"  DISCREPANCY:         ${discrepancy:>10,.2f}")
    logger.info(f"  (positive = DB shows less loss than reality)")

    if abs(discrepancy) > 1.0:
        logger.warning(
            f"\n  The DB is off by ${discrepancy:,.2f}. "
            f"This means our P&L records are inaccurate.\n"
            f"  Cannot auto-fix per-trade because Transaction History API "
            f"is empty on demo accounts.\n"
            f"  Options:\n"
            f"    1. Accept the discrepancy and ensure new trades are correct (Fix 1)\n"
            f"    2. Manually review suspicious trades ({suspicious_count} found)\n"
            f"    3. Switch to live account where Transaction History API works"
        )
    else:
        logger.success("DB and broker are in sync (within $1.00)")

    await DatabaseManager.close()


async def reconcile(days: int, dry_run: bool) -> None:
    """Main reconciliation logic."""
    settings = get_settings()
    logger.info(f"{'DRY RUN — ' if dry_run else ''}Reconciling last {days} days of trades")
    logger.info("=" * 70)

    # Connect to broker
    client = CapitalComClient()
    await client.connect()
    logger.success("Connected to Capital.com broker")

    # Fetch broker transactions
    logger.info(f"Fetching broker transactions for last {days} days...")
    broker_txns = await fetch_broker_transactions(client, days)
    logger.info(f"Total broker transactions: {len(broker_txns)}")

    # Filter to only transactions with close data
    close_txns = [t for t in broker_txns if t.close_level is not None and t.pl_value is not None]
    logger.info(f"Transactions with close data: {len(close_txns)}")

    if not close_txns:
        logger.warning(
            "No broker close transactions found (common on demo accounts). "
            "Falling back to equity-based comparison."
        )
        await equity_comparison(client, dry_run)
        await client.close()
        return

    # Connect to DB
    DatabaseManager.initialize()
    from sqlalchemy.ext.asyncio import AsyncSession

    session_factory = DatabaseManager.get_session_factory()

    async with session_factory() as session:
        db_positions = await get_closed_positions(session, days)
        logger.info(f"DB closed positions in period: {len(db_positions)}")

        if not db_positions:
            logger.warning("No closed positions in DB — nothing to reconcile")
            await client.close()
            return

        # Compare
        corrections = 0
        matched = 0
        unmatched_db = 0

        logger.info("")
        logger.info("=" * 70)
        logger.info("RECONCILIATION RESULTS")
        logger.info("=" * 70)

        for row in db_positions:
            pos_id = row[0]
            deal_id = row[1]
            epic = row[2]
            direction = row[3]
            size = float(row[4])
            entry_price = float(row[5])
            db_current_price = float(row[6]) if row[6] else None
            db_pnl = float(row[7]) if row[7] else 0.0
            db_close_reason = row[8]
            closed_at = row[9]

            txn = match_txn_to_position(close_txns, deal_id, epic, entry_price)

            if not txn:
                unmatched_db += 1
                logger.debug(
                    f"  [{epic}] {deal_id} — no broker match "
                    f"(DB P&L=${db_pnl:.2f}, reason={db_close_reason})"
                )
                continue

            matched += 1
            broker_pnl = txn.pl_value
            broker_exit = txn.close_level

            pnl_diff = abs(db_pnl - broker_pnl) if broker_pnl else 0
            exit_diff = (
                abs(db_current_price - broker_exit) if db_current_price and broker_exit else 0
            )

            # Determine correct close reason from broker P&L
            if broker_pnl > 0:
                broker_reason = "TP"
            elif broker_pnl < 0:
                broker_reason = "SL"
            else:
                broker_reason = "EXTERNAL"

            needs_fix = pnl_diff > 0.01 or (
                db_close_reason != broker_reason and db_close_reason in ("SL", "TP")
            )

            if needs_fix:
                corrections += 1
                logger.warning(
                    f"  MISMATCH [{epic}] {deal_id}:\n"
                    f"    DB:     P&L=${db_pnl:>10.2f}  exit={db_current_price or 'N/A':>12}  "
                    f"reason={db_close_reason}\n"
                    f"    BROKER: P&L=${broker_pnl:>10.2f}  exit={broker_exit:>12.6f}  "
                    f"reason={broker_reason}\n"
                    f"    DIFF:   P&L=${pnl_diff:>10.2f}"
                )

                if not dry_run:
                    from sqlalchemy import text

                    await session.execute(
                        text(
                            "UPDATE positions SET "
                            "profit_loss = :pnl, "
                            "current_price = :exit_price, "
                            "close_reason = :reason, "
                            "updated_at = :now "
                            "WHERE id = :id"
                        ),
                        {
                            "pnl": Decimal(str(round(broker_pnl, 2))),
                            "exit_price": Decimal(str(round(broker_exit, 6))),
                            "reason": broker_reason,
                            "now": datetime.now(UTC).replace(tzinfo=None),
                            "id": pos_id,
                        },
                    )

                    # Also update the trades table (CLOSE records)
                    await session.execute(
                        text(
                            "UPDATE trades SET "
                            "profit_loss = :pnl, "
                            "price = :exit_price "
                            "WHERE epic = :epic AND trade_type = 'CLOSE' "
                            "AND position_id = :pos_id"
                        ),
                        {
                            "pnl": Decimal(str(round(broker_pnl, 2))),
                            "exit_price": Decimal(str(round(broker_exit, 6))),
                            "pos_id": pos_id,
                            "epic": epic,
                        },
                    )
            else:
                logger.debug(
                    f"  OK [{epic}] {deal_id}: "
                    f"DB P&L=${db_pnl:.2f} ≈ Broker P&L=${broker_pnl:.2f}"
                )

        if not dry_run and corrections > 0:
            await session.commit()
            logger.success(f"Committed {corrections} corrections to database")

        # Summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("SUMMARY")
        logger.info("=" * 70)
        logger.info(f"  DB positions checked:  {len(db_positions)}")
        logger.info(f"  Matched to broker:     {matched}")
        logger.info(f"  No broker match:       {unmatched_db}")
        logger.info(f"  Corrections needed:    {corrections}")
        if dry_run and corrections > 0:
            logger.info(f"  (DRY RUN — no changes made. Remove --dry-run to apply)")

    await client.close()
    await DatabaseManager.close()


def main():
    parser = argparse.ArgumentParser(description="Reconcile MANTIS trades with broker data")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    args = parser.parse_args()

    asyncio.run(reconcile(args.days, args.dry_run))


if __name__ == "__main__":
    main()
