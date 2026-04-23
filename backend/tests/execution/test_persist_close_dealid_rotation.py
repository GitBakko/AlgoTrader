"""Regression: Capital.com rotates the dealId between order-confirmation
and /positions / close events (last hex nibble +1). ``_persist_close_to_db``
must update the original OPEN row via the stable
``(epic, direction, entry_price ± 0.1%)`` triple instead of creating a NEW
CLOSED row with the rotated dealId, which would leave the original row
OPEN forever and fire a false UNRECONCILED orphan on the next restart.

Documented incident 2026-04-23: DOGUSD + NATGAS both had rotated-dealId
CLOSED rows next to an original-dealId OPEN row; the OPEN rows survived,
were reinjected as orphans at backend restart, and fired UNRECONCILED.
"""

from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode


def _make_engine(session_factory):
    engine = ExecutionEngine(
        broker=MagicMock(),
        mode=ExecutionMode.DEMO,
        db_session_factory=session_factory,
    )
    return engine


@pytest.mark.unit
@pytest.mark.execution
class TestPersistCloseDealIdRotation:
    @pytest.mark.asyncio
    async def test_rotated_dealid_updates_original_open_row(self, monkeypatch):
        """Original OPEN row matched by (epic, direction, entry_price)
        must be updated to CLOSED; no second row created."""
        original_open = MagicMock()
        original_open.id = 42
        original_open.deal_id = "043c715d-0055-311e-0000-0000809a436f"  # original
        original_open.epic = "DOGUSD"
        original_open.direction = "SELL"
        original_open.entry_price = Decimal("0.0977")
        original_open.size = Decimal("34352.3072")
        original_open.status = "OPEN"

        repo = MagicMock()
        repo.get_by_deal_id = AsyncMock(return_value=None)  # rotated dealId not found
        repo.find_open_by_epic_direction_entry = AsyncMock(return_value=original_open)
        repo.create = AsyncMock()  # MUST NOT be called

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()

        @asynccontextmanager
        async def factory():
            yield session

        monkeypatch.setattr(
            "src.execution.execution_engine.PositionRepository",
            lambda _sess: repo,
        )

        engine = _make_engine(factory)
        await engine._persist_close_to_db(
            deal_id="043c715d-0055-311e-0000-0000809a4370",  # rotated dealId
            reason="TAKE_PROFIT_HIT",
            fill_price=0.0972,
            epic="DOGUSD",
            direction="SELL",
            size=34352.3072,
            entry_price=0.0977,
        )

        repo.find_open_by_epic_direction_entry.assert_awaited_once_with(
            epic="DOGUSD", direction="SELL", entry_price=0.0977
        )
        repo.create.assert_not_called()  # critical: no duplicate row
        assert original_open.status == "CLOSED"
        assert original_open.close_reason == "TP"
        assert original_open.deal_id == "043c715d-0055-311e-0000-0000809a4370"
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_fallback_when_deal_id_already_found(self, monkeypatch):
        """When the rotated dealId happens to already be in DB, don't run
        the fallback — primary lookup wins."""
        pos = MagicMock()
        pos.id = 1
        pos.deal_id = "D"
        pos.epic = "NATGAS"
        pos.direction = "SELL"
        pos.entry_price = Decimal("2.8455")
        pos.size = Decimal("1541.85")

        repo = MagicMock()
        repo.get_by_deal_id = AsyncMock(return_value=pos)
        repo.find_open_by_epic_direction_entry = AsyncMock()  # MUST NOT be called
        repo.create = AsyncMock()

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()

        @asynccontextmanager
        async def factory():
            yield session

        monkeypatch.setattr(
            "src.execution.execution_engine.PositionRepository",
            lambda _sess: repo,
        )

        engine = _make_engine(factory)
        await engine._persist_close_to_db(
            deal_id="D",
            reason="STOP_LOSS_HIT",
            fill_price=2.9,
            epic="NATGAS",
            direction="SELL",
            size=1541.85,
            entry_price=2.8455,
        )

        repo.find_open_by_epic_direction_entry.assert_not_called()
        repo.create.assert_not_called()
        assert pos.status == "CLOSED"

    @pytest.mark.asyncio
    async def test_no_match_creates_new_closed_row(self, monkeypatch):
        """Genuine 'never-persisted' case: neither dealId nor triple
        matches → create a fresh CLOSED row as before."""
        repo = MagicMock()
        repo.get_by_deal_id = AsyncMock(return_value=None)
        repo.find_open_by_epic_direction_entry = AsyncMock(return_value=None)
        created_pos = MagicMock(id=99)
        repo.create = AsyncMock(return_value=created_pos)

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()

        @asynccontextmanager
        async def factory():
            yield session

        monkeypatch.setattr(
            "src.execution.execution_engine.PositionRepository",
            lambda _sess: repo,
        )

        engine = _make_engine(factory)
        await engine._persist_close_to_db(
            deal_id="NEW-DEAL",
            reason="MANUAL",
            fill_price=100.0,
            epic="GOLD",
            direction="BUY",
            size=1.0,
            entry_price=99.0,
        )

        repo.find_open_by_epic_direction_entry.assert_awaited_once()
        repo.create.assert_awaited()
