"""Tests for position tracker module."""

import pytest

from src.execution.position_tracker import PositionTracker
from src.execution.schemas import ExecutionMode, ExecutionOrder


@pytest.fixture
def tracker():
    return PositionTracker(mode=ExecutionMode.PAPER)


class TestPositionTracker:
    @pytest.mark.asyncio
    async def test_empty_positions(self, tracker):
        positions = await tracker.sync_positions()
        assert positions == []

    def test_open_paper_position(self, tracker):
        order = ExecutionOrder(
            epic="XAUUSD", direction="BUY", size=1.0,
            entry_price=2000.0, stop_loss=1960.0
        )
        pos = tracker.open_paper_position(order, 2000.0, "PAPER-001")
        assert pos["deal_id"] == "PAPER-001"
        assert pos["epic"] == "XAUUSD"
        assert pos["direction"] == "BUY"
        assert pos["size"] == 1.0

    @pytest.mark.asyncio
    async def test_get_open_positions(self, tracker):
        order = ExecutionOrder(epic="XAUUSD", direction="BUY", size=1.0, entry_price=2000.0)
        tracker.open_paper_position(order, 2000.0, "PAPER-001")
        positions = await tracker.get_open_positions()
        assert len(positions) == 1

    @pytest.mark.asyncio
    async def test_get_positions_by_epic(self, tracker):
        o1 = ExecutionOrder(epic="XAUUSD", direction="BUY", size=1.0, entry_price=2000.0)
        o2 = ExecutionOrder(epic="BTCUSD", direction="SELL", size=0.5, entry_price=50000.0)
        tracker.open_paper_position(o1, 2000.0, "PAPER-001")
        tracker.open_paper_position(o2, 50000.0, "PAPER-002")

        gold = await tracker.get_open_positions("XAUUSD")
        assert len(gold) == 1
        btc = await tracker.get_open_positions("BTCUSD")
        assert len(btc) == 1

    @pytest.mark.asyncio
    async def test_get_position_by_deal_id(self, tracker):
        order = ExecutionOrder(epic="XAUUSD", direction="BUY", size=1.0, entry_price=2000.0)
        tracker.open_paper_position(order, 2000.0, "PAPER-001")
        pos = await tracker.get_position("PAPER-001")
        assert pos is not None
        assert pos["epic"] == "XAUUSD"

    @pytest.mark.asyncio
    async def test_get_missing_position(self, tracker):
        pos = await tracker.get_position("NONEXISTENT")
        assert pos is None

    def test_close_paper_position(self, tracker):
        order = ExecutionOrder(epic="XAUUSD", direction="BUY", size=1.0, entry_price=2000.0)
        tracker.open_paper_position(order, 2000.0, "PAPER-001")
        closed = tracker.close_paper_position("PAPER-001")
        assert closed is not None
        assert tracker.paper_position_count == 0

    def test_close_nonexistent_position(self, tracker):
        closed = tracker.close_paper_position("NONEXISTENT")
        assert closed is None

    def test_paper_position_count(self, tracker):
        assert tracker.paper_position_count == 0
        order = ExecutionOrder(epic="XAUUSD", direction="BUY", size=1.0, entry_price=2000.0)
        tracker.open_paper_position(order, 2000.0, "PAPER-001")
        assert tracker.paper_position_count == 1
