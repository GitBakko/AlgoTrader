"""Partial-close honesty tests (audit M1.6).

Capital.com has no partial-close API: ``ExecutionEngine.partial_close`` in
DEMO/LIVE closes the FULL position then reopens the remainder. Two hazards:

1. The remainder is never validated against the broker minimum deal size —
   a 50% scale-out on a position at/near minDealSize is guaranteed rejected
   on reopen.
2. On reopen failure the engine used to return ``success=True`` while the
   ENTIRE position was gone — the caller recorded "TP1 partial close 50%"
   against a flat book.

Contract under test:
- remainder < min_deal_size  -> refuse BEFORE the close leg (success=False,
  no order submitted at all).
- close OK + reopen FAILED   -> success=False with
  error_detail["degenerate_full_close"] = True and the remainder in error.
- min_deal_size=None         -> legacy behavior preserved (no pre-check).
- happy path with min        -> unchanged (both legs fire, success=True).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode, ExecutionOrder, ExecutionResult


@pytest.fixture
def demo_engine():
    """Execution engine in DEMO mode with mocked broker (close+reopen path)."""
    mock_broker = MagicMock()
    mock_broker.list_positions = AsyncMock(return_value=[])
    return ExecutionEngine(broker=mock_broker, mode=ExecutionMode.DEMO)


def _seed_position(engine, deal_id="DEAL-M16", size=1.0):
    order = ExecutionOrder(
        epic="XAUUSD",
        direction="BUY",
        size=size,
        entry_price=2000.0,
        stop_loss=1960.0,
        take_profit=2080.0,
    )
    engine._position_tracker.open_paper_position(order, 2000.0, deal_id)
    return order


@pytest.mark.unit
@pytest.mark.execution
class TestPartialCloseHonesty:
    """Audit M1.6: partial_close must never lie about a degenerate full close."""

    @pytest.mark.asyncio
    async def test_reopen_failure_reports_degenerate_full_close(self, demo_engine):
        """Close leg OK + reopen leg FAILED -> success=False + degenerate flag."""
        _seed_position(demo_engine, "DEAL-M16", size=1.0)

        demo_engine._order_manager.close_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="DEAL-M16", fill_price=2010.0)
        )
        demo_engine._order_manager.submit_order = AsyncMock(
            return_value=ExecutionResult(success=False, deal_id=None, error="MinimumDealSize")
        )

        result = await demo_engine.partial_close("DEAL-M16", 0.5, "TP1_HIT")

        assert result.success is False
        assert (result.error_detail or {}).get("degenerate_full_close") is True
        # Error must mention the remainder that failed to reopen
        assert "0.5" in (result.error or "")
        # The close fill is still reported (the close DID happen)
        assert result.fill_price == 2010.0

    @pytest.mark.asyncio
    async def test_remainder_below_min_deal_size_refused(self, demo_engine):
        """Remainder < broker minimum -> refused BEFORE any order is sent."""
        _seed_position(demo_engine, "DEAL-MIN", size=1.0)

        demo_engine._order_manager.close_order = AsyncMock()
        demo_engine._order_manager.submit_order = AsyncMock()

        # 50% of 1.0 = 0.5 remainder < 0.6 broker minimum
        result = await demo_engine.partial_close("DEAL-MIN", 0.5, "TP1_HIT", min_deal_size=0.6)

        assert result.success is False
        assert result.error is not None
        assert "minimum" in result.error.lower()
        # NO order submitted at all — the close leg must never have fired
        demo_engine._order_manager.close_order.assert_not_awaited()
        demo_engine._order_manager.submit_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_min_deal_size_none_preserves_legacy(self, demo_engine):
        """min_deal_size=None (caller can't supply it) -> no pre-check, legacy path."""
        _seed_position(demo_engine, "DEAL-LEG", size=1.0)

        demo_engine._order_manager.close_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="DEAL-LEG", fill_price=2010.0)
        )
        demo_engine._order_manager.submit_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="REOPEN-LEG", fill_price=2010.0)
        )

        result = await demo_engine.partial_close("DEAL-LEG", 0.5, "TP1_HIT", min_deal_size=None)

        assert result.success is True
        assert result.deal_id == "REOPEN-LEG"
        demo_engine._order_manager.close_order.assert_awaited_once()
        demo_engine._order_manager.submit_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_partial_close_unchanged(self, demo_engine):
        """Happy path with min supplied and remainder >= min -> both legs fire."""
        _seed_position(demo_engine, "DEAL-OK", size=1.0)

        demo_engine._order_manager.close_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="DEAL-OK", fill_price=2010.0)
        )
        demo_engine._order_manager.submit_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="REOPEN-OK", fill_price=2010.0)
        )

        # 50% of 1.0 = 0.5 remainder >= 0.1 broker minimum
        result = await demo_engine.partial_close("DEAL-OK", 0.5, "TP1_HIT", min_deal_size=0.1)

        assert result.success is True
        assert result.deal_id == "REOPEN-OK"
        demo_engine._order_manager.close_order.assert_awaited_once_with("DEAL-OK")
        demo_engine._order_manager.submit_order.assert_awaited_once()
        reopen_order = demo_engine._order_manager.submit_order.call_args[0][0]
        assert reopen_order.size == pytest.approx(0.5)
