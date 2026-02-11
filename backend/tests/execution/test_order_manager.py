"""Tests for order manager module."""

import pytest

from src.execution.order_manager import OrderManager
from src.execution.schemas import ExecutionMode, ExecutionOrder


@pytest.fixture
def paper_order_manager():
    return OrderManager(mode=ExecutionMode.PAPER)


@pytest.fixture
def sample_order():
    return ExecutionOrder(
        epic="XAUUSD",
        direction="BUY",
        size=1.0,
        entry_price=2000.0,
        stop_loss=1960.0,
        take_profit=2080.0,
    )


class TestOrderManager:
    @pytest.mark.asyncio
    async def test_paper_submit(self, paper_order_manager, sample_order):
        result = await paper_order_manager.submit_order(sample_order)
        assert result.success is True
        assert result.deal_id.startswith("PAPER-")
        assert result.fill_price == 2000.0
        assert result.slippage == 0.0
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_paper_close(self, paper_order_manager):
        result = await paper_order_manager.close_order("PAPER-12345678")
        assert result.success is True
        assert result.deal_id == "PAPER-12345678"

    @pytest.mark.asyncio
    async def test_paper_modify_stops(self, paper_order_manager):
        result = await paper_order_manager.modify_stops(
            "PAPER-12345678", stop_level=1950.0, profit_level=2100.0
        )
        assert result.success is True

    def test_live_mode_requires_broker(self):
        with pytest.raises(ValueError, match="Broker client is required"):
            OrderManager(mode=ExecutionMode.LIVE)

    @pytest.mark.asyncio
    async def test_paper_unique_deal_ids(self, paper_order_manager, sample_order):
        r1 = await paper_order_manager.submit_order(sample_order)
        r2 = await paper_order_manager.submit_order(sample_order)
        assert r1.deal_id != r2.deal_id

    def test_mode_property(self, paper_order_manager):
        assert paper_order_manager.mode == ExecutionMode.PAPER

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self, paper_order_manager, sample_order):
        result = await paper_order_manager.submit_order(sample_order)
        assert result.execution_time_ms >= 0  # Paper fill can be sub-ms

    @pytest.mark.asyncio
    async def test_close_execution_time(self, paper_order_manager):
        result = await paper_order_manager.close_order("PAPER-test")
        assert result.execution_time_ms >= 0
