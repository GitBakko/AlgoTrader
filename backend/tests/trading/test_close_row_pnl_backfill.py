"""Audit M1.9: idempotency guards must BACKFILL NULL P&L on the existing
CLOSE Trade row instead of skip-only.

Locally-initiated closes (local SL/TP enforcement, time-stops, manual API
close) insert the CLOSE Trade audit row with ``profit_loss=NULL`` — the
engine path does not know broker P&L at that moment. When the reconciler
later resolves the REAL P&L and calls ``_persist_position_close`` (or the
engine re-fires ``_persist_close_to_db``), the idempotency guard finds the
existing CLOSE row. Pre-fix it skipped unconditionally, so the NULL was
never repaired and per-trade analytics under-reported.

Contract:
- non-NULL incoming P&L + NULL on the existing row  → backfill.
- incoming exit/fill price (broker-resolved, authoritative) differing from
  the stored one → overwrite.
- NULL incoming P&L must NEVER clobber a non-NULL stored value.
- Invariant #10 holds: NO second CLOSE Trade INSERT in either guard branch.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# paper_loop._persist_position_close — wiring mirrors
# tests/trading/test_persist_unreconciled.py
# ---------------------------------------------------------------------------


def _make_loop_with_existing_close(existing_trade):
    """PaperTradingLoop with a stubbed session whose idempotency-guard
    SELECT returns `existing_trade` (a CLOSE row already persisted)."""
    from src.trading.paper_loop import PaperTradingLoop

    loop = PaperTradingLoop.__new__(PaperTradingLoop)

    pos = MagicMock()
    pos.id = 1
    pos.deal_id = "DEAL-BACKFILL-1"
    pos.opened_at = datetime(2026, 1, 1)  # naive, in the past

    repo = MagicMock()
    repo.get_by_deal_id = AsyncMock(return_value=pos)
    repo.find_open_by_epic_direction_entry = AsyncMock(return_value=None)
    repo.create = AsyncMock()

    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_trade))
    )

    class _SF:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *a):
            return None

    loop._db_session_factory = lambda: _SF()
    return loop, repo, session, pos


def _existing_close_row(profit_loss, price):
    trade = MagicMock()
    trade.id = 77
    trade.trade_type = "CLOSE"
    trade.profit_loss = profit_loss
    trade.price = price
    return trade


@pytest.mark.asyncio
async def test_loop_guard_backfills_null_pnl(monkeypatch):
    """Existing CLOSE row with profit_loss=NULL + reconciler-resolved real
    P&L → row backfilled in place; NO new Trade row inserted."""
    existing_trade = _existing_close_row(profit_loss=None, price=Decimal("2000.0"))
    loop, repo, session, pos = _make_loop_with_existing_close(existing_trade)

    from src.database import repositories as _repos

    monkeypatch.setattr(_repos, "PositionRepository", lambda s: repo)

    await loop._persist_position_close(
        deal_id="DEAL-BACKFILL-1",
        epic="XAUUSD",
        direction="BUY",
        size=1.0,
        entry_price=2000.0,
        exit_price=2010.0,  # broker-resolved exit
        pnl=10.0,  # broker-resolved real P&L
        close_reason="SL",
    )

    # NULL P&L repaired with the real value, price updated to broker exit.
    assert existing_trade.profit_loss == Decimal("10.0")
    assert existing_trade.price == Decimal("2010.0")
    # Invariant #10: no second CLOSE Trade INSERT.
    session.add.assert_not_called()
    repo.create.assert_not_called()
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_loop_guard_never_clobbers_with_null(monkeypatch):
    """Existing CLOSE row already carries real P&L; incoming pnl=None
    (UNRECONCILED path) must NOT clobber it."""
    existing_trade = _existing_close_row(profit_loss=Decimal("7.5"), price=Decimal("2000.0"))
    loop, repo, session, pos = _make_loop_with_existing_close(existing_trade)

    from src.database import repositories as _repos

    monkeypatch.setattr(_repos, "PositionRepository", lambda s: repo)

    await loop._persist_position_close(
        deal_id="DEAL-BACKFILL-1",
        epic="XAUUSD",
        direction="BUY",
        size=1.0,
        entry_price=2000.0,
        exit_price=2000.0,  # same as stored price → no overwrite either
        pnl=None,  # UNRECONCILED — must never erase a real value
        close_reason="UNRECONCILED",
    )

    assert existing_trade.profit_loss == Decimal("7.5")
    assert existing_trade.price == Decimal("2000.0")
    session.add.assert_not_called()
    repo.create.assert_not_called()


# ---------------------------------------------------------------------------
# ExecutionEngine._persist_close_to_db — wiring mirrors
# tests/execution/test_persist_close_dealid_rotation.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_guard_backfills_null_pnl(monkeypatch):
    """Existing CLOSE row (profit_loss=NULL) + Position row now carrying the
    real P&L → engine guard backfills the row; NO second INSERT."""
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.schemas import ExecutionMode

    position_db = MagicMock()
    position_db.id = 42
    position_db.deal_id = "DEAL-ENGINE-1"
    position_db.epic = "XAUUSD"
    position_db.direction = "BUY"
    position_db.size = Decimal("1.0")
    position_db.entry_price = Decimal("2000.0")
    position_db.profit_loss = Decimal("12.5")  # reconciler-resolved on Position

    existing_trade = _existing_close_row(profit_loss=None, price=Decimal("2000.0"))

    repo = MagicMock()
    repo.get_by_deal_id = AsyncMock(return_value=position_db)
    repo.find_open_by_epic_direction_entry = AsyncMock(return_value=None)
    repo.create = AsyncMock()

    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing_trade))
    )

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(
        "src.execution.execution_engine.PositionRepository",
        lambda _sess: repo,
    )

    engine = ExecutionEngine(
        broker=MagicMock(),
        mode=ExecutionMode.DEMO,
        db_session_factory=factory,
    )

    result = await engine._persist_close_to_db(
        deal_id="DEAL-ENGINE-1",
        reason="STOP_LOSS_HIT",
        fill_price=2010.0,  # broker-resolved fill
        epic="XAUUSD",
        direction="BUY",
        size=1.0,
        entry_price=2000.0,
    )

    # NULL P&L repaired from the Position row, price updated to broker fill.
    assert existing_trade.profit_loss == Decimal("12.5")
    assert existing_trade.price == Decimal("2010.0")
    # Invariant #10: no second CLOSE Trade INSERT.
    session.add.assert_not_called()
    repo.create.assert_not_called()
    session.commit.assert_awaited()
    assert result == ("XAUUSD", "BUY", 12.5)
