"""
Unit tests for ExecutionEngine database persistence (CRIT-2).

Tests:
- Successful trade creates Position + Trade in database
- Failed trade does NOT create database records
- Closing position updates Position and creates CLOSE Trade
- Graceful degradation when repositories are None
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode, ExecutionResult
from src.risk.schemas import RiskCheckResult
from src.strategy.schemas import TradingSignal
from src.broker.models import Direction


class TestExecutionEngineDbPersistence:
    """Test CRIT-2: Database persistence in ExecutionEngine."""

    @pytest.mark.asyncio
    async def test_successful_trade_persisted_to_database(self):
        """
        Test that successful trade execution creates Position + Trade in database.

        Scenario: Execute signal → Should save to DB
        """
        # Mock repositories
        mock_position_repo = MagicMock()
        mock_trade_repo = MagicMock()

        # Mock database models
        mock_position_db = MagicMock()
        mock_position_db.id = 123

        mock_position_repo.create = AsyncMock(return_value=mock_position_db)
        mock_trade_repo.create = AsyncMock(return_value=MagicMock())

        # Mock order manager to return successful result
        mock_broker = MagicMock()
        engine = ExecutionEngine(
            broker=mock_broker,
            mode=ExecutionMode.DEMO,
            position_repository=mock_position_repo,
            trade_repository=mock_trade_repo,
        )

        async def mock_submit_order(order):
            return ExecutionResult(
                success=True,
                deal_id="DEAL-123",
                fill_price=2000.5,
                slippage=0.5,
            )

        engine._order_manager.submit_order = AsyncMock(side_effect=mock_submit_order)

        # Execute signal
        signal = TradingSignal(
            epic="XAUUSD",
            direction=Direction.BUY,
            entry_price=2000.0,
            confidence=0.65,
            signal_class=2,
        )

        risk_result = RiskCheckResult(
            approved=True,
            position_size=1.0,
            stop_loss=1980.0,
            take_profit=2040.0,
        )

        result = await engine.execute_signal(signal, risk_result)

        # Verify execution succeeded
        assert result.success is True
        assert result.deal_id == "DEAL-123"

        # CRITICAL: Verify database persistence was called
        assert mock_position_repo.create.called, "Position repository create() was not called!"
        assert mock_trade_repo.create.called, "Trade repository create() was not called!"

        # Verify Position data
        position_call_args = mock_position_repo.create.call_args[0][0]
        assert position_call_args.deal_id == "DEAL-123"
        assert position_call_args.epic == "XAUUSD"
        assert position_call_args.direction == "BUY"
        assert position_call_args.status == "OPEN"

        # Verify Trade data
        trade_call_args = mock_trade_repo.create.call_args[0][0]
        assert trade_call_args.position_id == 123
        assert trade_call_args.trade_type == "OPEN"
        assert trade_call_args.epic == "XAUUSD"

    @pytest.mark.asyncio
    async def test_failed_trade_no_database_persistence(self):
        """
        Test that failed trade execution does NOT create database records.

        Scenario: Trade fails → No database writes
        """
        mock_position_repo = MagicMock()
        mock_trade_repo = MagicMock()

        mock_position_repo.create = AsyncMock()
        mock_trade_repo.create = AsyncMock()

        engine = ExecutionEngine(
            broker=MagicMock(),
            mode=ExecutionMode.DEMO,
            position_repository=mock_position_repo,
            trade_repository=mock_trade_repo,
        )

        # Mock order manager to return failure
        async def mock_submit_order(order):
            return ExecutionResult(
                success=False,
                error="Market closed",
            )

        engine._order_manager.submit_order = AsyncMock(side_effect=mock_submit_order)

        signal = TradingSignal(
            epic="XAUUSD",
            direction=Direction.BUY,
            entry_price=2000.0,
            confidence=0.65,
            signal_class=2,
        )

        risk_result = RiskCheckResult(
            approved=True,
            position_size=1.0,
            stop_loss=1980.0,
            take_profit=2040.0,
        )

        result = await engine.execute_signal(signal, risk_result)

        # Verify execution failed
        assert result.success is False

        # CRITICAL: Verify NO database writes occurred
        assert not mock_position_repo.create.called, "Position should NOT be created on failure!"
        assert not mock_trade_repo.create.called, "Trade should NOT be created on failure!"

    @pytest.mark.asyncio
    async def test_close_position_updates_database(self):
        """
        Test that closing position updates Position and creates CLOSE Trade.

        Scenario: Close position → Update Position to CLOSED + create Trade
        """
        mock_position_repo = MagicMock()
        mock_trade_repo = MagicMock()

        # Mock existing position in DB
        mock_position_db = MagicMock()
        mock_position_db.id = 123
        mock_position_db.epic = "XAUUSD"
        mock_position_db.direction = "BUY"
        mock_position_db.entry_price = Decimal("2000.0")
        mock_position_db.size = Decimal("1.0")

        mock_position_repo.get_by_deal_id = AsyncMock(return_value=mock_position_db)
        mock_position_repo.update = AsyncMock(return_value=mock_position_db)
        mock_trade_repo.create = AsyncMock()

        engine = ExecutionEngine(
            broker=MagicMock(),
            mode=ExecutionMode.DEMO,
            position_repository=mock_position_repo,
            trade_repository=mock_trade_repo,
        )

        # Mock close_order success
        async def mock_close_order(deal_id):
            return ExecutionResult(
                success=True,
                deal_id=deal_id,
                fill_price=2010.0,
            )

        engine._order_manager.close_order = AsyncMock(side_effect=mock_close_order)

        # Mock position tracker
        engine._position_tracker.get_position = AsyncMock(return_value={
            "deal_id": "DEAL-123",
            "epic": "XAUUSD",
            "direction": "BUY",
            "level": 2000.0,
            "size": 1.0,
        })
        engine._position_tracker.close_paper_position = MagicMock(return_value={
            "deal_id": "DEAL-123",
            "epic": "XAUUSD",
            "direction": "BUY",
        })

        # Close position
        result = await engine.close_position("DEAL-123", reason="MANUAL")

        # Verify close succeeded
        assert result.success is True

        # CRITICAL: Verify database updates
        assert mock_position_repo.get_by_deal_id.called
        assert mock_position_repo.update.called
        assert mock_trade_repo.create.called

        # Verify Position updated to CLOSED
        assert mock_position_db.status == "CLOSED"
        assert mock_position_db.close_reason == "MANUAL"

        # Verify CLOSE Trade created
        trade_call_args = mock_trade_repo.create.call_args[0][0]
        assert trade_call_args.trade_type == "CLOSE"
        assert trade_call_args.position_id == 123

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_repositories(self):
        """
        Test that engine works WITHOUT repositories (graceful degradation).

        Scenario: No repositories provided → Still executes trades (no DB writes)
        """
        engine = ExecutionEngine(
            broker=MagicMock(),
            mode=ExecutionMode.DEMO,
            position_repository=None,  # No DB
            trade_repository=None,
        )

        # Mock successful execution
        async def mock_submit_order(order):
            return ExecutionResult(
                success=True,
                deal_id="DEAL-123",
                fill_price=2000.5,
            )

        engine._order_manager.submit_order = AsyncMock(side_effect=mock_submit_order)

        signal = TradingSignal(
            epic="XAUUSD",
            direction=Direction.BUY,
            entry_price=2000.0,
            confidence=0.65,
            signal_class=2,
        )

        risk_result = RiskCheckResult(
            approved=True,
            position_size=1.0,
            stop_loss=1980.0,
            take_profit=2040.0,
        )

        # Should still execute successfully
        result = await engine.execute_signal(signal, risk_result)

        assert result.success is True
        # No database errors should occur
