"""Tests for partial close functionality in ExecutionEngine and PositionTracker."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.execution_engine import ExecutionEngine
from src.execution.position_tracker import PositionTracker
from src.execution.schemas import ExecutionMode, ExecutionOrder, ExecutionResult


@pytest.fixture
def tracker():
    """Create a position tracker in paper mode."""
    return PositionTracker(mode=ExecutionMode.PAPER)


@pytest.fixture
def engine():
    """Create an execution engine in paper mode."""
    return ExecutionEngine(broker=None, mode=ExecutionMode.PAPER)


@pytest.mark.unit
@pytest.mark.execution
class TestPositionTrackerPartialClose:
    """Tests for PositionTracker.reduce_paper_position()."""

    def test_reduce_paper_position(self, tracker):
        """Size correctly reduced by reduce_pct."""
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
            stop_loss=1960.0,
        )
        tracker.open_paper_position(order, 2000.0, "PAPER-001")

        # Reduce by 30%
        result = tracker.reduce_paper_position("PAPER-001", 0.30)

        assert result is not None
        assert result["size"] == pytest.approx(0.70, rel=1e-4)
        assert result["deal_id"] == "PAPER-001"
        assert result["epic"] == "XAUUSD"

    def test_reduce_50_pct(self, tracker):
        """Verify math: 1.0 * (1-0.5) = 0.5."""
        order = ExecutionOrder(
            epic="BTCUSD",
            direction="SELL",
            size=1.0,
            entry_price=50000.0,
        )
        tracker.open_paper_position(order, 50000.0, "PAPER-002")

        result = tracker.reduce_paper_position("PAPER-002", 0.50)

        assert result is not None
        assert result["size"] == pytest.approx(0.50, rel=1e-4)

    def test_reduce_full_close(self, tracker):
        """reduce_pct=1.0 closes position."""
        order = ExecutionOrder(
            epic="US500",
            direction="BUY",
            size=2.0,
            entry_price=4500.0,
        )
        tracker.open_paper_position(order, 4500.0, "PAPER-003")

        result = tracker.reduce_paper_position("PAPER-003", 1.0)

        assert result is not None  # Returns closed position
        # Position should be removed from internal state
        assert tracker.paper_position_count == 0

    def test_reduce_unknown_position(self, tracker):
        """Returns None when position not found."""
        result = tracker.reduce_paper_position("UNKNOWN-DEAL", 0.50)
        assert result is None

    def test_reduce_preserves_other_fields(self, tracker):
        """Epic, direction, levels unchanged after reduction."""
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
            stop_loss=1960.0,
            take_profit=2080.0,
        )
        tracker.open_paper_position(order, 2000.0, "PAPER-004")

        result = tracker.reduce_paper_position("PAPER-004", 0.25)

        assert result is not None
        assert result["epic"] == "XAUUSD"
        assert result["direction"] == "BUY"
        assert result["level"] == 2000.0
        assert result["stop_level"] == 1960.0
        assert result["profit_level"] == 2080.0
        assert result["size"] == pytest.approx(0.75, rel=1e-4)


@pytest.mark.unit
@pytest.mark.execution
class TestExecutionEnginePartialClose:
    """Tests for ExecutionEngine.partial_close()."""

    @pytest.mark.asyncio
    async def test_partial_close_success(self, engine):
        """Engine partial_close in paper mode."""
        # First open a position
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
        )
        engine._position_tracker.open_paper_position(order, 2000.0, "PAPER-001")

        # Partial close
        result = await engine.partial_close("PAPER-001", 0.40, reason="TP1_PARTIAL")

        assert result.success is True
        assert result.deal_id == "PAPER-001"
        # Check position was reduced
        positions = engine._position_tracker.get_paper_positions_sync()
        assert len(positions) == 1
        assert positions[0]["size"] == pytest.approx(0.60, rel=1e-4)

    @pytest.mark.asyncio
    async def test_partial_close_invalid_pct(self, engine):
        """close_pct <= 0 returns error."""
        result = await engine.partial_close("PAPER-001", 0.0)
        assert result.success is False
        assert "Invalid close_pct" in result.error

        result = await engine.partial_close("PAPER-001", -0.5)
        assert result.success is False
        assert "Invalid close_pct" in result.error

    @pytest.mark.asyncio
    async def test_partial_close_full_when_100pct(self, engine):
        """close_pct=1.0 fully closes."""
        order = ExecutionOrder(
            epic="BTCUSD",
            direction="SELL",
            size=0.5,
            entry_price=50000.0,
        )
        engine._position_tracker.open_paper_position(order, 50000.0, "PAPER-002")

        result = await engine.partial_close("PAPER-002", 1.0)

        assert result.success is True
        # Position should be fully closed
        assert engine._position_tracker.paper_position_count == 0

    @pytest.mark.asyncio
    async def test_partial_close_unknown_deal(self, engine):
        """Returns error for unknown deal_id."""
        result = await engine.partial_close("UNKNOWN-DEAL", 0.50)
        assert result.success is False
        assert "Position not found" in result.error

    @pytest.mark.asyncio
    async def test_multiple_partial_closes(self, engine):
        """Reduce twice (0.5 then 0.5 of remaining)."""
        order = ExecutionOrder(
            epic="US500",
            direction="BUY",
            size=1.0,
            entry_price=4500.0,
        )
        engine._position_tracker.open_paper_position(order, 4500.0, "PAPER-003")

        # First reduction: 50%
        result1 = await engine.partial_close("PAPER-003", 0.50)
        assert result1.success is True
        positions = engine._position_tracker.get_paper_positions_sync()
        assert positions[0]["size"] == pytest.approx(0.50, rel=1e-4)

        # Second reduction: 50% of remaining (0.5 * 0.5 = 0.25 total remaining)
        result2 = await engine.partial_close("PAPER-003", 0.50)
        assert result2.success is True
        positions = engine._position_tracker.get_paper_positions_sync()
        assert positions[0]["size"] == pytest.approx(0.25, rel=1e-4)

    @pytest.mark.asyncio
    async def test_partial_close_preserves_other_fields(self, engine):
        """Epic, direction etc unchanged."""
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="SELL",
            size=2.0,
            entry_price=2100.0,
            stop_loss=2140.0,
            take_profit=2020.0,
        )
        engine._position_tracker.open_paper_position(order, 2100.0, "PAPER-004")

        result = await engine.partial_close("PAPER-004", 0.33)

        assert result.success is True
        positions = engine._position_tracker.get_paper_positions_sync()
        assert len(positions) == 1
        pos = positions[0]
        assert pos["epic"] == "XAUUSD"
        assert pos["direction"] == "SELL"
        assert pos["level"] == 2100.0
        assert pos["stop_level"] == 2140.0
        assert pos["profit_level"] == 2020.0
        assert pos["size"] == pytest.approx(1.34, rel=1e-2)  # 2.0 * (1 - 0.33)


@pytest.mark.unit
@pytest.mark.execution
class TestExecutionEnginePartialCloseDemo:
    """Tests for partial_close in DEMO/LIVE mode (close-then-reopen)."""

    @pytest.fixture
    def demo_engine(self):
        """Create an execution engine in DEMO mode with mocked broker."""
        mock_broker = MagicMock()
        mock_broker.list_positions = AsyncMock(return_value=[])
        engine = ExecutionEngine(broker=mock_broker, mode=ExecutionMode.DEMO)
        return engine

    @pytest.mark.asyncio
    async def test_demo_partial_close_closes_and_reopens(self, demo_engine):
        """DEMO partial close: closes full position, reopens with reduced size."""
        # Pre-inject a position into the tracker
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
            stop_loss=1960.0,
            take_profit=2080.0,
        )
        demo_engine._position_tracker.open_paper_position(order, 2000.0, "DEAL-001")

        # Mock close_order → success
        demo_engine._order_manager.close_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="DEAL-001", fill_price=2005.0)
        )
        # Mock submit_order → success with new deal_id
        demo_engine._order_manager.submit_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="REOPEN-001", fill_price=2005.0)
        )

        result = await demo_engine.partial_close("DEAL-001", 0.5, "TP1_HIT")

        assert result.success is True
        assert result.deal_id == "REOPEN-001"  # new deal_id from reopen
        demo_engine._order_manager.close_order.assert_awaited_once_with("DEAL-001")
        demo_engine._order_manager.submit_order.assert_awaited_once()

        # Verify reopened position has correct size (0.5 of 1.0)
        reopen_order = demo_engine._order_manager.submit_order.call_args[0][0]
        assert reopen_order.size == pytest.approx(0.5)
        assert reopen_order.stop_loss == 1960.0
        assert reopen_order.take_profit == 2080.0

    @pytest.mark.asyncio
    async def test_demo_partial_close_position_not_found(self, demo_engine):
        """Returns error when position not found in tracker."""
        result = await demo_engine.partial_close("UNKNOWN", 0.5)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_demo_partial_close_reopen_failure(self, demo_engine):
        """If reopen fails, reports honest failure: degenerate full close (M1.6)."""
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
        )
        demo_engine._position_tracker.open_paper_position(order, 2000.0, "DEAL-002")

        # Mock close → success
        demo_engine._order_manager.close_order = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="DEAL-002", fill_price=2005.0)
        )
        # Mock reopen → failure
        demo_engine._order_manager.submit_order = AsyncMock(
            return_value=ExecutionResult(success=False, deal_id=None, error="InsufficientFunds")
        )

        result = await demo_engine.partial_close("DEAL-002", 0.5, "TP1_HIT")

        # Audit M1.6: the position is GONE (full close, reopen rejected) —
        # the engine must NOT report success, or the caller books a partial
        # close against a flat position.
        assert result.success is False
        assert (result.error_detail or {}).get("degenerate_full_close") is True
        assert result.error is not None  # reopen failure noted
        assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_demo_partial_close_broker_close_fails(self, demo_engine):
        """If broker close fails, returns the failure immediately."""
        order = ExecutionOrder(
            epic="BTCUSD",
            direction="SELL",
            size=0.5,
            entry_price=68000.0,
        )
        demo_engine._position_tracker.open_paper_position(order, 68000.0, "DEAL-003")

        # Mock close → failure
        demo_engine._order_manager.close_order = AsyncMock(
            return_value=ExecutionResult(success=False, deal_id="DEAL-003", error="BrokerRejected")
        )

        result = await demo_engine.partial_close("DEAL-003", 0.5)

        assert result.success is False
        assert "BrokerRejected" in result.error
        # submit_order should NOT have been called
        demo_engine._order_manager.submit_order = AsyncMock()
        demo_engine._order_manager.submit_order.assert_not_awaited()
