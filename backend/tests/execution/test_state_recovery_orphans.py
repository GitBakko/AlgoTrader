"""Tests for StateRecovery.reinject_orphans — bringing DB-OPEN positions
that no longer exist on broker back into the close-detection retry loop."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.schemas import ExecutionMode
from src.execution.state_recovery import StateRecoveryService

# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_service(broker, paper_loop, db_positions):
    """Build a minimal StateRecoveryService wired for orphan tests."""

    execution_engine = MagicMock()
    execution_engine.mode = ExecutionMode.DEMO
    execution_engine._position_tracker = MagicMock()

    risk_manager = MagicMock()
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.equity_curve_filter = MagicMock()

    trailing_stop_manager = MagicMock()

    # Build a mock session_factory that returns db_positions from the query
    session = AsyncMock()

    # scalars().all() must return the position list
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = db_positions
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return None

    def _factory():
        return _CM()

    service = StateRecoveryService(
        execution_engine=execution_engine,
        risk_manager=risk_manager,
        trailing_stop_manager=trailing_stop_manager,
        broker=broker,
        db_session_factory=_factory,
        paper_loop=paper_loop,
    )
    return service


def _make_db_position(
    deal_id: str,
    epic: str = "WTIUSD",
    direction: str = "BUY",
    size: Decimal = Decimal("10.0"),
    entry_price: Decimal = Decimal("84.50"),
    status: str = "OPEN",
) -> MagicMock:
    """Return a mock Position ORM row."""
    pos = MagicMock()
    pos.deal_id = deal_id
    pos.epic = epic
    pos.direction = direction
    pos.size = size
    pos.entry_price = entry_price
    pos.status = status
    pos.opened_at = datetime.now(UTC).replace(tzinfo=None)
    return pos


def _make_broker_position(deal_id: str) -> MagicMock:
    pos = MagicMock()
    pos.deal_id = deal_id
    return pos


# ─── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orphan_reinjected_into_pending_close_detections():
    """DB has OPEN position, broker no longer reports it → after
    reinject_orphans, paper_loop._pending_close_detections contains it."""
    paper_loop = MagicMock()
    paper_loop._pending_close_detections = {}

    broker = AsyncMock()
    broker.list_positions = AsyncMock(return_value=[])  # broker sees nothing

    db_positions = [_make_db_position("orphan-1", epic="WTIUSD")]

    service = _make_service(broker, paper_loop, db_positions)

    injected = await service.reinject_orphans()

    assert injected == 1
    assert "orphan-1" in paper_loop._pending_close_detections
    pending = paper_loop._pending_close_detections["orphan-1"]
    assert pending.epic == "WTIUSD"
    assert pending.retry_count == 0
    assert pending.size == pytest.approx(10.0)
    assert pending.entry_price == pytest.approx(84.50)
    assert pending.direction == "BUY"
    assert pending.deal_id == "orphan-1"
    assert pending.deal_reference is None
    assert isinstance(pending.first_seen, datetime)


@pytest.mark.asyncio
async def test_no_orphan_when_broker_still_has_position():
    """If broker still reports the position, it is NOT an orphan."""
    paper_loop = MagicMock()
    paper_loop._pending_close_detections = {}

    broker = AsyncMock()
    broker.list_positions = AsyncMock(return_value=[_make_broker_position("still-open-1")])

    db_positions = [_make_db_position("still-open-1")]

    service = _make_service(broker, paper_loop, db_positions)
    injected = await service.reinject_orphans()

    assert injected == 0
    assert "still-open-1" not in paper_loop._pending_close_detections


@pytest.mark.asyncio
async def test_multiple_orphans_all_reinjected():
    """All orphans (broker missing multiple) are injected."""
    paper_loop = MagicMock()
    paper_loop._pending_close_detections = {}

    broker = AsyncMock()
    # Broker has one position open, two are gone
    broker.list_positions = AsyncMock(return_value=[_make_broker_position("still-open-1")])

    db_positions = [
        _make_db_position("orphan-a", epic="XAUUSD"),
        _make_db_position("orphan-b", epic="BTCUSD"),
        _make_db_position("still-open-1", epic="EURUSD"),
    ]

    service = _make_service(broker, paper_loop, db_positions)
    injected = await service.reinject_orphans()

    assert injected == 2
    assert "orphan-a" in paper_loop._pending_close_detections
    assert "orphan-b" in paper_loop._pending_close_detections
    assert "still-open-1" not in paper_loop._pending_close_detections


@pytest.mark.asyncio
async def test_broker_error_returns_zero_no_crash():
    """If broker.list_positions raises, reinject_orphans returns 0 gracefully."""
    paper_loop = MagicMock()
    paper_loop._pending_close_detections = {}

    broker = AsyncMock()
    broker.list_positions = AsyncMock(side_effect=ConnectionError("broker down"))

    db_positions = [_make_db_position("orphan-1")]

    service = _make_service(broker, paper_loop, db_positions)
    injected = await service.reinject_orphans()

    # Must not raise; must return 0 and leave pending untouched
    assert injected == 0
    assert "orphan-1" not in paper_loop._pending_close_detections


@pytest.mark.asyncio
async def test_already_pending_not_duplicated():
    """If deal_id is already in _pending_close_detections, do not overwrite."""
    from src.trading.paper_loop import PendingClose

    existing_pending = PendingClose(
        deal_id="orphan-1",
        deal_reference=None,
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        prev_pos={},
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        retry_count=3,
    )

    paper_loop = MagicMock()
    paper_loop._pending_close_detections = {"orphan-1": existing_pending}

    broker = AsyncMock()
    broker.list_positions = AsyncMock(return_value=[])

    db_positions = [_make_db_position("orphan-1")]

    service = _make_service(broker, paper_loop, db_positions)
    injected = await service.reinject_orphans()

    # Should skip already-pending — count 0 and original object preserved
    assert injected == 0
    assert paper_loop._pending_close_detections["orphan-1"].retry_count == 3


@pytest.mark.asyncio
async def test_no_paper_loop_returns_zero():
    """If paper_loop is None (not wired yet), returns 0 gracefully."""
    broker = AsyncMock()
    broker.list_positions = AsyncMock(return_value=[])

    db_positions = [_make_db_position("orphan-1")]

    service = _make_service(broker, paper_loop=None, db_positions=db_positions)
    injected = await service.reinject_orphans()

    assert injected == 0


@pytest.mark.asyncio
async def test_no_db_session_factory_returns_zero():
    """Without a db_session_factory the method returns 0 gracefully."""
    execution_engine = MagicMock()
    execution_engine.mode = ExecutionMode.DEMO
    execution_engine._position_tracker = MagicMock()

    paper_loop = MagicMock()
    paper_loop._pending_close_detections = {}

    broker = AsyncMock()
    broker.list_positions = AsyncMock(return_value=[])

    service = StateRecoveryService(
        execution_engine=execution_engine,
        risk_manager=MagicMock(),
        trailing_stop_manager=MagicMock(),
        broker=broker,
        db_session_factory=None,
        paper_loop=paper_loop,
    )
    injected = await service.reinject_orphans()

    assert injected == 0
