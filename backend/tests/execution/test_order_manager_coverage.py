"""
Tests for OrderManager covering broker exception paths in _live_fill() and modify_stops().

All tests exercise the LIVE/DEMO execution mode with a mocked broker client,
covering each specific CapitalComError subclass handling branch.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.broker.exceptions import (
    CapitalComError,
    InsufficientFundsError,
    MarketClosedError,
    OrderRejectedError,
    RateLimitError,
)
from src.execution.order_manager import OrderManager
from src.execution.schemas import ExecutionMode, ExecutionOrder, ExecutionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_broker():
    """Create a mock broker client with async methods."""
    broker = MagicMock()
    broker.create_position = AsyncMock()
    broker.close_position = AsyncMock()
    broker.modify_position = AsyncMock()
    return broker


@pytest.fixture
def live_order_manager(mock_broker):
    """OrderManager in LIVE mode with a mocked broker."""
    return OrderManager(broker=mock_broker, mode=ExecutionMode.LIVE)


@pytest.fixture
def sample_order():
    """A sample ExecutionOrder for tests."""
    return ExecutionOrder(
        epic="XAUUSD",
        direction="BUY",
        size=1.0,
        entry_price=2000.0,
        stop_loss=1960.0,
        take_profit=2080.0,
    )


# ===========================================================================
# _live_fill() exception handling tests
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveFillMarketClosed:
    """_live_fill() handles MarketClosedError correctly."""

    async def test_market_closed_error_returns_failure(self, live_order_manager, sample_order, mock_broker):
        mock_broker.create_position.side_effect = MarketClosedError(
            "Rejected. XAUUSD is currently closed."
        )

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is False
        assert result.error is not None
        assert "chiuso" in result.error.lower() or "closed" in result.error.lower()
        assert result.error_detail is not None
        assert result.execution_time_ms >= 0


@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveFillInsufficientFunds:
    """_live_fill() handles InsufficientFundsError correctly."""

    async def test_insufficient_funds_error_returns_failure(self, live_order_manager, sample_order, mock_broker):
        mock_broker.create_position.side_effect = InsufficientFundsError(
            "Insufficient funds to open position"
        )

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is False
        assert result.error is not None
        assert result.error_detail is not None
        assert result.execution_time_ms >= 0


@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveFillOrderRejected:
    """_live_fill() handles OrderRejectedError correctly."""

    async def test_order_rejected_error_returns_failure(self, live_order_manager, sample_order, mock_broker):
        mock_broker.create_position.side_effect = OrderRejectedError(
            "Order rejected: minimum size not met"
        )

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is False
        assert result.error is not None
        assert result.error_detail is not None


@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveFillRateLimit:
    """_live_fill() handles RateLimitError correctly."""

    async def test_rate_limit_error_returns_failure(self, live_order_manager, sample_order, mock_broker):
        mock_broker.create_position.side_effect = RateLimitError(
            "Rate limit exceeded"
        )

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is False
        assert result.error is not None
        assert result.error_detail is not None


@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveFillGenericCapitalComError:
    """_live_fill() handles generic CapitalComError correctly."""

    async def test_generic_broker_error_returns_failure(self, live_order_manager, sample_order, mock_broker):
        mock_broker.create_position.side_effect = CapitalComError(
            "Unexpected broker error XYZ"
        )

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is False
        assert result.error is not None
        assert result.error_detail is not None


# ===========================================================================
# _live_fill() success path
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveFillSuccess:
    """_live_fill() successful execution returns proper result."""

    async def test_live_fill_success(self, live_order_manager, sample_order, mock_broker):
        confirmation = MagicMock()
        confirmation.deal_id = "LIVE-ABC123"
        confirmation.level = 2001.5  # Slightly different from entry
        mock_broker.create_position.return_value = confirmation

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is True
        assert result.deal_id == "LIVE-ABC123"
        assert result.fill_price == 2001.5
        assert result.slippage == pytest.approx(1.5, abs=1e-6)
        assert result.execution_time_ms >= 0
        mock_broker.create_position.assert_called_once()


# ===========================================================================
# modify_stops() tests (LIVE mode)
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.execution
class TestModifyStopsLive:
    """modify_stops() in LIVE mode success and error paths."""

    async def test_modify_stops_success(self, live_order_manager, mock_broker):
        mock_broker.modify_position.return_value = None  # void on success

        result = await live_order_manager.modify_stops(
            deal_id="DEAL-001",
            stop_level=1950.0,
            profit_level=2100.0,
        )

        assert result.success is True
        assert result.deal_id == "DEAL-001"
        mock_broker.modify_position.assert_called_once()

    async def test_modify_stops_broker_exception(self, live_order_manager, mock_broker):
        mock_broker.modify_position.side_effect = CapitalComError(
            "Failed to modify: position not found"
        )

        result = await live_order_manager.modify_stops(
            deal_id="DEAL-999",
            stop_level=1900.0,
        )

        assert result.success is False
        assert result.deal_id == "DEAL-999"
        assert result.error is not None
        assert "position not found" in result.error.lower()

    async def test_modify_stops_only_stop_level(self, live_order_manager, mock_broker):
        """Modify only the stop-loss level, leaving TP unchanged."""
        mock_broker.modify_position.return_value = None

        result = await live_order_manager.modify_stops(
            deal_id="DEAL-002",
            stop_level=1940.0,
        )

        assert result.success is True
        # Verify the request was constructed with profit_level=None
        call_args = mock_broker.modify_position.call_args
        req = call_args[0][1]  # second positional arg is the request
        assert req.stop_level == 1940.0
        assert req.profit_level is None


# ===========================================================================
# _live_close() tests
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveClose:
    """close_order() in LIVE mode tests."""

    async def test_live_close_success(self, live_order_manager, mock_broker):
        confirmation = MagicMock()
        confirmation.deal_id = "DEAL-CLOSED"
        confirmation.level = 2050.0
        mock_broker.close_position.return_value = confirmation

        result = await live_order_manager.close_order("DEAL-001")

        assert result.success is True
        assert result.deal_id == "DEAL-CLOSED"
        assert result.fill_price == 2050.0

    async def test_live_close_broker_error(self, live_order_manager, mock_broker):
        mock_broker.close_position.side_effect = CapitalComError(
            "Position already closed"
        )

        result = await live_order_manager.close_order("DEAL-001")

        assert result.success is False
        assert result.deal_id == "DEAL-001"
        assert "already closed" in result.error.lower()
