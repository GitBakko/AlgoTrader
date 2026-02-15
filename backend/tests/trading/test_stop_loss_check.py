"""
Test automatic stop loss checking in paper trading loop.
Critical bug fix: positions must be auto-closed when SL is violated.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.trading.paper_loop import PaperTradingLoop
from src.execution.schemas import ExecutionResult


@pytest.fixture
def mock_paper_loop():
    """Create a paper loop with mocked dependencies."""
    prediction_service = MagicMock()
    strategy_manager = MagicMock()
    risk_manager = MagicMock()
    execution_engine = MagicMock()
    data_access = MagicMock()

    loop = PaperTradingLoop(
        prediction_service=prediction_service,
        strategy_manager=strategy_manager,
        risk_manager=risk_manager,
        execution_engine=execution_engine,
        data_access=data_access,
        epics=["XAUUSD", "BTCUSD"],
    )

    return loop


@pytest.mark.asyncio
async def test_long_position_sl_violated(mock_paper_loop):
    """Test that a LONG position is closed when price drops below SL."""

    # Position: BUY @ 2000, SL @ 1990
    position = {
        "deal_id": "TEST001",
        "epic": "XAUUSD",
        "direction": "BUY",
        "level": 2000.0,
        "stop_level": 1990.0,
        "size": 1.0,
    }

    # Current price = 1985 (BELOW SL → should close)
    mock_paper_loop.data_access.get_latest_price.return_value = {
        "timestamp": datetime.now(timezone.utc),
        "close": 1985.0,
    }

    # Mock close_position to succeed
    mock_paper_loop.execution_engine.close_position = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            deal_id="TEST001",
            realized_pnl=-15.0,
        )
    )

    # Run the check
    await mock_paper_loop._check_stop_losses([position])

    # Verify position was closed
    mock_paper_loop.execution_engine.close_position.assert_called_once_with(
        deal_id="TEST001",
        reason="STOP_LOSS_HIT"
    )


@pytest.mark.asyncio
async def test_short_position_sl_violated(mock_paper_loop):
    """Test that a SHORT position is closed when price rises above SL."""

    # Position: SELL @ 2000, SL @ 2010
    position = {
        "deal_id": "TEST002",
        "epic": "XAUUSD",
        "direction": "SELL",
        "level": 2000.0,
        "stop_level": 2010.0,
        "size": 1.0,
    }

    # Current price = 2015 (ABOVE SL → should close)
    mock_paper_loop.data_access.get_latest_price.return_value = {
        "timestamp": datetime.now(timezone.utc),
        "close": 2015.0,
    }

    # Mock close_position to succeed
    mock_paper_loop.execution_engine.close_position = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            deal_id="TEST002",
            realized_pnl=-15.0,
        )
    )

    # Run the check
    await mock_paper_loop._check_stop_losses([position])

    # Verify position was closed
    mock_paper_loop.execution_engine.close_position.assert_called_once()


@pytest.mark.asyncio
async def test_long_position_sl_not_violated(mock_paper_loop):
    """Test that a LONG position is NOT closed when price is above SL."""

    # Position: BUY @ 2000, SL @ 1990
    position = {
        "deal_id": "TEST003",
        "epic": "XAUUSD",
        "direction": "BUY",
        "level": 2000.0,
        "stop_level": 1990.0,
        "size": 1.0,
    }

    # Current price = 2005 (ABOVE SL → should NOT close)
    mock_paper_loop.data_access.get_latest_price.return_value = {
        "timestamp": datetime.now(timezone.utc),
        "close": 2005.0,
    }

    # Mock close_position
    mock_paper_loop.execution_engine.close_position = AsyncMock()

    # Run the check
    await mock_paper_loop._check_stop_losses([position])

    # Verify position was NOT closed
    mock_paper_loop.execution_engine.close_position.assert_not_called()


@pytest.mark.asyncio
async def test_short_position_sl_not_violated(mock_paper_loop):
    """Test that a SHORT position is NOT closed when price is below SL."""

    # Position: SELL @ 2000, SL @ 2010
    position = {
        "deal_id": "TEST004",
        "epic": "XAUUSD",
        "direction": "SELL",
        "level": 2000.0,
        "stop_level": 2010.0,
        "size": 1.0,
    }

    # Current price = 1995 (BELOW SL → should NOT close)
    mock_paper_loop.data_access.get_latest_price.return_value = {
        "timestamp": datetime.now(timezone.utc),
        "close": 1995.0,
    }

    # Mock close_position
    mock_paper_loop.execution_engine.close_position = AsyncMock()

    # Run the check
    await mock_paper_loop._check_stop_losses([position])

    # Verify position was NOT closed
    mock_paper_loop.execution_engine.close_position.assert_not_called()


@pytest.mark.asyncio
async def test_position_without_sl_ignored(mock_paper_loop):
    """Test that positions without SL are ignored."""

    # Position: BUY @ 2000, NO SL
    position = {
        "deal_id": "TEST005",
        "epic": "XAUUSD",
        "direction": "BUY",
        "level": 2000.0,
        "stop_level": None,
        "size": 1.0,
    }

    # Current price = 1900 (below entry, but no SL set)
    mock_paper_loop.data_access.get_latest_price.return_value = {
        "timestamp": datetime.now(timezone.utc),
        "close": 1900.0,
    }

    # Mock close_position
    mock_paper_loop.execution_engine.close_position = AsyncMock()

    # Run the check
    await mock_paper_loop._check_stop_losses([position])

    # Verify position was NOT closed (no SL to check)
    mock_paper_loop.execution_engine.close_position.assert_not_called()
