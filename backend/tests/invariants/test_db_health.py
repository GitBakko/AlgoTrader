"""Runtime DB invariants for close-detection v2.

Step 11 of plan `calm-questing-quail.md` (Tier 4 of the 6-tier regression
harness).

Each assertion below describes a **DB state that must never appear** in a
healthy MANTIS deployment. The tests run against whatever Postgres is
configured in the environment (real CI service, docker-compose dev
container, or a staging snapshot); they skip gracefully if the DB is
unreachable, so a developer without Postgres running does not take a
spurious failure.

The same queries are intended to back a production cronjob that pages
Telegram whenever any of these counters becomes non-zero.

Invariants
----------
1. No CLOSED + UNRECONCILED row older than 10 min — either reconciliation
   landed (profit_loss non-NULL) or the explicit UNRECONCILED path
   emitted; a stale row means the deferred retry loop got stuck.
2. No CLOSED row with `profit_loss IS NULL` outside the dedicated
   UNRECONCILED family (`UNRECONCILED`,
   `UNRECONCILED_NO_ACTIVITY`, `UNRECONCILED_NO_TRADE`,
   `UNRECONCILED_FX_UNAVAILABLE`). Every other `close_reason` must carry
   a realized P&L.
3. No CLOSED row where `current_price = entry_price` AND the close
   reason is not in the UNRECONCILED family. That equality is the
   signature of the old synthetic-P&L fallback (deleted in Step 7).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from src.utils.config import get_settings


# The dedicated "explicitly unreconciled" close-reason family. Rows in
# this family are allowed to have `profit_loss IS NULL` and
# `current_price = entry_price` because their contract is exactly that:
# no broker truth available, P&L missing by design.
UNRECONCILED_FAMILY = (
    "UNRECONCILED",
    "UNRECONCILED_NO_ACTIVITY",
    "UNRECONCILED_NO_TRADE",
    "UNRECONCILED_FX_UNAVAILABLE",
)

# Closes older than the v2 deployment window can carry historical artefacts
# from the removed `(exit-entry)*size` arithmetic fallback (Step 7) — we do
# NOT back-patch those here; the backfill script handles rows worth
# reconciling. Invariants only alert on the forward-facing window.
INVARIANT_WINDOW_DAYS = 7

STALE_UNRECONCILED_GRACE_MINUTES = 15  # a bit above the 10-min retry cap


async def _connect_or_skip():
    """Build an async engine against the configured DB; skip on failure."""
    settings = get_settings()
    url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (OperationalError, Exception) as exc:
        await engine.dispose()
        pytest.skip(f"Postgres not reachable: {exc!r}")
    return engine


@pytest.mark.asyncio
@pytest.mark.integration
class TestCloseDetectionDbInvariants:
    async def test_no_stale_unreconciled_rows(self):
        """Every UNRECONCILED row should either be reconciled within 10 min
        or have gone through the explicit UNRECONCILED terminal path. Any
        row still sitting at pnl=NULL + close_reason='UNRECONCILED' after
        15 minutes indicates the retry queue stalled."""
        engine = await _connect_or_skip()
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        f"""
                        SELECT deal_id, epic, closed_at, updated_at
                        FROM positions
                        WHERE status = 'CLOSED'
                          AND close_reason = 'UNRECONCILED'
                          AND profit_loss IS NULL
                          AND updated_at < NOW() - INTERVAL '{STALE_UNRECONCILED_GRACE_MINUTES} minutes'
                        """
                    )
                )
                rows = result.all()
        finally:
            await engine.dispose()

        assert not rows, (
            f"Stale UNRECONCILED rows detected ({len(rows)}): "
            + ", ".join(f"{r.deal_id}({r.epic})" for r in rows[:5])
            + (" ..." if len(rows) > 5 else "")
        )

    async def test_no_null_pnl_outside_unreconciled_family(self):
        """Every CLOSED row must carry a realized P&L unless its close_reason
        is in the dedicated UNRECONCILED family. `profit_loss IS NULL`
        elsewhere means a code path persisted a close without broker
        reconciliation — exactly what Steps 7/8 deleted."""
        engine = await _connect_or_skip()
        try:
            async with engine.connect() as conn:
                family_list = ",".join(f"'{r}'" for r in UNRECONCILED_FAMILY)
                result = await conn.execute(
                    text(
                        f"""
                        SELECT deal_id, epic, close_reason, closed_at
                        FROM positions
                        WHERE status = 'CLOSED'
                          AND profit_loss IS NULL
                          AND (close_reason IS NULL
                               OR close_reason NOT IN ({family_list}))
                          AND closed_at > NOW() - INTERVAL '{INVARIANT_WINDOW_DAYS} days'
                        """
                    )
                )
                rows = result.all()
        finally:
            await engine.dispose()

        assert not rows, (
            f"CLOSED rows with NULL P&L outside UNRECONCILED family ({len(rows)}): "
            + ", ".join(
                f"{r.deal_id}({r.epic}/{r.close_reason})" for r in rows[:5]
            )
            + (" ..." if len(rows) > 5 else "")
        )

    @pytest.mark.xfail(
        reason=(
            "Under v1 authoritative close-detection the Capital.com TRADE row "
            "schema has no closeLevel, so `_match_transaction._finalize` "
            "falls back to entry_price for `current_price` while still "
            "writing the real broker P&L. That fallback is legitimate, so "
            "exit == entry is not actionable until CLOSE_DETECTION_V2_ENABLED "
            "is flipped on (Step 15). At that point CloseDetector always "
            "writes `activity.details.level`, which is never equal to entry "
            "by construction, and this invariant becomes a hard guard."
        ),
        strict=False,
    )
    async def test_no_exit_equals_entry_outside_unreconciled_family(self):
        """Guard against a return of the `(exit - entry) * size` arithmetic
        fallback deleted in Step 7. Marked xfail until v2 is authoritative —
        see reason string above."""
        engine = await _connect_or_skip()
        try:
            async with engine.connect() as conn:
                family_list = ",".join(f"'{r}'" for r in UNRECONCILED_FAMILY)
                result = await conn.execute(
                    text(
                        f"""
                        SELECT deal_id, epic, close_reason, entry_price, current_price
                        FROM positions
                        WHERE status = 'CLOSED'
                          AND current_price IS NOT NULL
                          AND entry_price IS NOT NULL
                          AND current_price = entry_price
                          AND (close_reason IS NULL
                               OR close_reason NOT IN ({family_list}))
                          AND closed_at > NOW() - INTERVAL '{INVARIANT_WINDOW_DAYS} days'
                        """
                    )
                )
                rows = result.all()
        finally:
            await engine.dispose()

        assert not rows, (
            f"CLOSED rows with exit_price == entry_price outside UNRECONCILED "
            f"family ({len(rows)}): "
            + ", ".join(
                f"{r.deal_id}({r.epic}/{r.close_reason})" for r in rows[:5]
            )
            + (" ..." if len(rows) > 5 else "")
        )
