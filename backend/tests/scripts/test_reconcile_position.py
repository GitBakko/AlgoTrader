"""Tests for scripts/reconcile_position.py CLI — manual P&L reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.reconcile_position import reconcile_deal_id


def _make_mock_session(position=None):
    """Build a mock async SQLAlchemy session that returns `position` on scalar_one_or_none."""
    session = AsyncMock()

    # session.execute() returns a result whose scalar_one_or_none() returns position
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = position
    session.execute = AsyncMock(return_value=execute_result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_position(**kwargs) -> MagicMock:
    """Build a mock Position object with sensible defaults."""
    p = MagicMock()
    p.deal_id = kwargs.get("deal_id", "test-deal")
    p.epic = kwargs.get("epic", "WTIUSD")
    p.direction = kwargs.get("direction", "BUY")
    p.size = kwargs.get("size", Decimal("10.0"))
    p.entry_price = kwargs.get("entry_price", Decimal("84.50"))
    p.status = kwargs.get("status", "CLOSED")
    p.profit_loss = kwargs.get("profit_loss", None)
    p.current_price = kwargs.get("current_price", None)
    p.close_reason = kwargs.get("close_reason", "UNRECONCILED")
    p.opened_at = kwargs.get("opened_at", datetime.now(UTC).replace(tzinfo=None))
    p.closed_at = kwargs.get("closed_at", datetime.now(UTC).replace(tzinfo=None))
    return p


@pytest.mark.asyncio
async def test_refuses_open_position():
    """An OPEN position must be refused without calling the broker."""
    p = _make_position(deal_id="still-open", status="OPEN")
    session = _make_mock_session(position=p)
    broker = AsyncMock()

    result = await reconcile_deal_id(
        deal_id="still-open",
        session=session,
        broker=broker,
        assume_yes=True,
    )

    assert result["status"] == "refused"
    broker.get_transaction_history.assert_not_called()


@pytest.mark.asyncio
async def test_updates_unreconciled_when_match_found():
    """When a matching transaction is found, the position is updated with real broker data."""
    from src.broker.models import Transaction

    p = _make_position(
        deal_id="rec-1",
        epic="WTIUSD",
        entry_price=Decimal("84.50"),
        status="CLOSED",
        profit_loss=None,
        close_reason="UNRECONCILED",
    )
    session = _make_mock_session(position=p)

    broker = AsyncMock()
    broker.get_transaction_history.return_value = [
        Transaction(
            date=datetime(2026, 4, 20, 0, 2, 0),
            type="DEAL",
            reference="ref-1",
            instrumentName="Oil - Crude",
            openLevel=84.50,
            closeLevel=85.60,
            profitAndLoss="USD246.86",
            size=10.0,
            currency="USD",
        )
    ]

    result = await reconcile_deal_id(
        deal_id="rec-1",
        session=session,
        broker=broker,
        assume_yes=True,
    )

    assert result["status"] == "updated"
    assert result["profit_loss"] == pytest.approx(246.86)
    assert result["current_price"] == pytest.approx(85.60)

    # Verify the position object was mutated before commit
    assert float(p.profit_loss) == pytest.approx(246.86)
    assert float(p.current_price) == pytest.approx(85.60)
    assert p.close_reason == "TP"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_returns_skipped_when_no_match_and_yes_flag():
    """With --yes flag and no matching transaction, return skipped without modifying position."""
    p = _make_position(
        deal_id="rec-nomatch",
        epic="EURUSD",
        entry_price=Decimal("1.08"),
        status="CLOSED",
        profit_loss=None,
        close_reason="UNRECONCILED",
    )
    session = _make_mock_session(position=p)

    broker = AsyncMock()
    broker.get_transaction_history.return_value = []

    result = await reconcile_deal_id(
        deal_id="rec-nomatch",
        session=session,
        broker=broker,
        assume_yes=True,
    )

    assert result["status"] == "skipped"
    # Position profit_loss must remain None (no commit)
    assert p.profit_loss is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_returns_not_found_when_deal_id_missing():
    """When the deal_id doesn't exist in the DB, return not_found immediately."""
    session = _make_mock_session(position=None)
    broker = AsyncMock()

    result = await reconcile_deal_id(
        deal_id="nonexistent-deal-id",
        session=session,
        broker=broker,
        assume_yes=True,
    )

    assert result["status"] == "not_found"
    broker.get_transaction_history.assert_not_called()
