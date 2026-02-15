"""
Unit tests for OrderManager broker call timeouts (CRIT-6).

Tests:
- create_position timeout
- close_position timeout
- modify_position timeout
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.execution.order_manager import OrderManager
from src.execution.schemas import ExecutionMode, ExecutionOrder
from src.broker.models import Direction


class TestOrderManagerTimeouts:
    """Test CRIT-6: Broker call timeout protection."""

    @pytest.mark.asyncio
    async def test_create_position_timeout(self):
        """
        Test that create_position times out after 10 seconds.

        Scenario: Broker API hangs, should timeout and return error
        """
        # Create mock broker that hangs forever
        mock_broker = MagicMock()

        async def hang_forever(request):
            """Simulate broker API hang."""
            await asyncio.sleep(999)  # Never returns

        mock_broker.create_position = AsyncMock(side_effect=hang_forever)

        # Create order manager in DEMO mode
        manager = OrderManager(broker=mock_broker, mode=ExecutionMode.DEMO)

        # Create order
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
            stop_loss=1980.0,
            take_profit=2040.0,
        )

        # Execute order - should timeout after 10s
        result = await manager.submit_order(order)

        # Verify timeout error
        assert result.success is False
        assert "timeout" in result.error.lower()
        assert result.error_detail["timeout_seconds"] == 10.0

    @pytest.mark.asyncio
    async def test_close_position_timeout(self):
        """
        Test that close_position times out after 10 seconds.

        Scenario: Broker API hangs when closing position
        """
        mock_broker = MagicMock()

        async def hang_forever(deal_id):
            """Simulate broker API hang."""
            await asyncio.sleep(999)

        mock_broker.close_position = AsyncMock(side_effect=hang_forever)

        manager = OrderManager(broker=mock_broker, mode=ExecutionMode.DEMO)

        # Close position - should timeout
        result = await manager.close_order("DEAL123")

        # Verify timeout error
        assert result.success is False
        assert "timeout" in result.error.lower()
        assert result.deal_id == "DEAL123"

    @pytest.mark.asyncio
    async def test_modify_position_timeout(self):
        """
        Test that modify_position times out after 10 seconds.

        Scenario: Broker API hangs when modifying SL/TP
        """
        mock_broker = MagicMock()

        async def hang_forever(deal_id, request):
            """Simulate broker API hang."""
            await asyncio.sleep(999)

        mock_broker.modify_position = AsyncMock(side_effect=hang_forever)

        manager = OrderManager(broker=mock_broker, mode=ExecutionMode.DEMO)

        # Modify stops - should timeout
        result = await manager.modify_stops(
            deal_id="DEAL123",
            stop_level=1980.0,
            profit_level=2040.0,
        )

        # Verify timeout error
        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_create_position_succeeds_under_timeout(self):
        """
        Test that normal broker calls succeed (don't timeout).

        Scenario: Broker API responds in 100ms (well under 10s limit)
        """
        mock_broker = MagicMock()

        async def quick_response(request):
            """Simulate fast broker response."""
            await asyncio.sleep(0.1)  # 100ms
            from src.broker.models import DealConfirmation
            return DealConfirmation(
                dealId="DEAL123",
                dealReference="REF123",
                dealStatus="ACCEPTED",
                status="ACCEPTED",
                level=2000.5,
                size=1.0,
                direction=Direction.BUY,
                epic="XAUUSD",
                affectedDeals=[],
                reason=None,
            )

        mock_broker.create_position = AsyncMock(side_effect=quick_response)

        manager = OrderManager(broker=mock_broker, mode=ExecutionMode.DEMO)

        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
            stop_loss=1980.0,
            take_profit=2040.0,
        )

        # Execute order - should succeed
        result = await manager.submit_order(order)

        # Verify success
        assert result.success is True
        assert result.deal_id == "DEAL123"
        assert result.fill_price == 2000.5

    @pytest.mark.asyncio
    async def test_close_position_succeeds_under_timeout(self):
        """
        Test that normal close calls succeed (don't timeout).

        Scenario: Broker API responds quickly
        """
        mock_broker = MagicMock()

        async def quick_close(deal_id):
            """Simulate fast broker response."""
            await asyncio.sleep(0.05)  # 50ms
            from src.broker.models import DealConfirmation
            return DealConfirmation(
                dealId=deal_id,
                dealReference="REF456",
                dealStatus="ACCEPTED",
                status="ACCEPTED",
                level=2010.0,
                size=1.0,
                direction=Direction.BUY,
                epic="XAUUSD",
                affectedDeals=[],
                reason=None,
            )

        mock_broker.close_position = AsyncMock(side_effect=quick_close)

        manager = OrderManager(broker=mock_broker, mode=ExecutionMode.DEMO)

        # Close position - should succeed
        result = await manager.close_order("DEAL123")

        # Verify success
        assert result.success is True
        assert result.deal_id == "DEAL123"

    @pytest.mark.asyncio
    async def test_timeout_duration_is_exactly_10_seconds(self):
        """
        Test that timeout is exactly 10 seconds (not more, not less).

        This is a timing test to ensure we don't hang longer than necessary.
        """
        mock_broker = MagicMock()

        async def hang_forever(request):
            await asyncio.sleep(999)

        mock_broker.create_position = AsyncMock(side_effect=hang_forever)

        manager = OrderManager(broker=mock_broker, mode=ExecutionMode.DEMO)

        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
        )

        # Measure actual timeout duration
        start = asyncio.get_event_loop().time()
        result = await manager.submit_order(order)
        duration = asyncio.get_event_loop().time() - start

        # Verify timeout happened within 10-11 seconds (with small margin)
        assert 10.0 <= duration <= 11.0, f"Timeout took {duration:.2f}s, expected ~10s"
        assert result.success is False
