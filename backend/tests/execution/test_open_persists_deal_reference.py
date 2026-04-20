"""Task 14 — open_position must persist deal_reference from DealConfirmation
onto the Position DB row so Strategy 1 (deterministic match) works at close."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_position(deal_id: str, deal_reference: str | None = None, **kwargs):
    """Construct a Position model instance directly (no real DB required)."""
    from src.database.models import Position

    defaults = dict(
        epic="WTIUSD",
        direction="BUY",
        size=Decimal("10.0"),
        entry_price=Decimal("84.50"),
        status="OPEN",
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    defaults.update(kwargs)
    return Position(
        deal_id=deal_id,
        deal_reference=deal_reference,
        **defaults,
    )


# ─── model-level tests (no real DB) ───────────────────────────────────────────


def test_position_model_has_deal_reference_field():
    """Position SQLModel exposes the deal_reference field after Task 14."""
    from src.database.models import Position
    import inspect

    # Check the field exists in the model's __fields__ (Pydantic v2) or annotations
    assert hasattr(Position, "deal_reference"), (
        "Position model must have deal_reference field"
    )


def test_position_record_stores_deal_reference():
    """Position model correctly stores a deal_reference value distinct from deal_id."""
    p = _make_position(
        deal_id="00018509-0055-311e-0000-0000826217c9",
        deal_reference="O_84cc3c14fa1e_WTI",
    )
    assert p.deal_reference == "O_84cc3c14fa1e_WTI"
    assert p.deal_id != p.deal_reference  # they are distinct identifiers


def test_legacy_position_deal_reference_is_nullable():
    """Legacy rows (no deal_reference) default to None — nullable field."""
    p = _make_position(deal_id="legacy-1")
    assert p.deal_reference is None


def test_position_deal_reference_accepts_none_explicitly():
    """Explicitly passing deal_reference=None is equivalent to omitting it."""
    p = _make_position(deal_id="test-2", deal_reference=None)
    assert p.deal_reference is None


# ─── execution_engine persistence tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_execution_engine_persists_deal_reference_from_result():
    """ExecutionEngine._position_repository.create() receives a Position with
    deal_reference populated from the ExecutionResult."""
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.schemas import ExecutionMode, ExecutionResult
    from src.strategy.schemas import SignalDirection, TradingSignal
    from src.risk.schemas import RiskCheckResult

    # Mock position repository to capture the Position object passed to .create()
    captured_positions: list = []

    async def fake_create(pos):
        captured_positions.append(pos)
        pos.id = 1
        return pos

    pos_repo = MagicMock()
    pos_repo.create = fake_create

    trade_repo = MagicMock()
    trade_repo.create = AsyncMock()

    engine = ExecutionEngine(
        mode=ExecutionMode.PAPER,
        position_repository=pos_repo,
        trade_repository=trade_repo,
    )

    # Override _order_manager.submit_order to return an ExecutionResult with deal_reference
    exec_result = ExecutionResult(
        success=True,
        deal_id="DEMO-abc123",
        deal_reference="O_ref_abc123",
        fill_price=84.50,
    )
    engine._order_manager.submit_order = AsyncMock(return_value=exec_result)

    signal = TradingSignal(
        epic="WTIUSD",
        direction=SignalDirection.BUY,
        entry_price=84.50,
        confidence=0.7,
        signal_class=2,
    )
    risk_result = RiskCheckResult(
        approved=True,
        position_size=10.0,
        stop_loss=82.0,
        take_profit=88.0,
    )

    await engine.execute_signal(signal, risk_result)

    assert len(captured_positions) == 1, "Expected exactly one Position to be created"
    saved_pos = captured_positions[0]
    assert saved_pos.deal_reference == "O_ref_abc123", (
        f"Expected deal_reference='O_ref_abc123', got {saved_pos.deal_reference!r}"
    )
    assert saved_pos.deal_id == "DEMO-abc123"
    assert saved_pos.deal_id != saved_pos.deal_reference


@pytest.mark.asyncio
async def test_execution_persistence_class_persists_deal_reference():
    """ExecutionPersistence.persist_execution() populates Position.deal_reference
    from result.deal_reference."""
    from src.execution.persistence import ExecutionPersistence
    from src.execution.schemas import ExecutionResult
    from src.strategy.schemas import SignalDirection, TradingSignal

    # Capture the Position added to the session
    captured: list = []

    class FakeSession:
        def add(self, obj):
            captured.append(obj)

        async def flush(self):
            pass

        async def refresh(self, obj):
            obj.id = 99

    signal = TradingSignal(
        epic="EURUSD",
        direction=SignalDirection.BUY,
        entry_price=1.08,
        confidence=0.65,
        signal_class=2,
    )
    result = ExecutionResult(
        success=True,
        deal_id="DEMO-xyz",
        deal_reference="O_ref_xyz_EUR",
        fill_price=1.08,
    )

    # Patch lazy imports inside persist_execution (they are imported inside try block)
    with patch("src.api.websocket.ws_manager", create=True), \
         patch("src.utils.event_bus.event_bus", create=True) as mock_bus:
        mock_bus.publish = AsyncMock()

        pos = await ExecutionPersistence.persist_execution(
            session=FakeSession(),
            signal=signal,
            result=result,
            position_size=1000.0,
            stop_loss=1.07,
            take_profit=1.10,
        )

    assert pos is not None
    assert pos.deal_reference == "O_ref_xyz_EUR"
    assert pos.deal_id == "DEMO-xyz"


# ─── ExecutionResult schema test ───────────────────────────────────────────────


def test_execution_result_has_deal_reference_field():
    """ExecutionResult schema now carries deal_reference alongside deal_id."""
    from src.execution.schemas import ExecutionResult

    r = ExecutionResult(
        success=True,
        deal_id="d1",
        deal_reference="ref1",
        fill_price=100.0,
    )
    assert r.deal_reference == "ref1"


def test_execution_result_deal_reference_defaults_none():
    """deal_reference is optional and defaults to None for paper fills."""
    from src.execution.schemas import ExecutionResult

    r = ExecutionResult(success=True, deal_id="PAPER-123", fill_price=50.0)
    assert r.deal_reference is None
