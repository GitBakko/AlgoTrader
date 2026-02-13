"""
Tests for PaperTradingLoop covering uncovered paths:
- _is_market_open() with cache hit
- _is_market_open() with cache miss + broker timeout
- _run_iteration() when no epics have new candles
- _run_iteration() with epic that has open position (skipped)
- _process_epic() when market is closed
- _process_epic() when execution fails
- _fetch_equity() when broker fetch fails
"""

import asyncio
import time as _time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode, ExecutionResult
from src.models.schemas import PredictionResult, SignalClass
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.strategy_manager import StrategyManager
from src.trading.paper_loop import PaperTradingLoop


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_prediction_service():
    """Mock PredictionService with default canned BUY prediction."""
    service = MagicMock()
    service.has_models = True
    service.has_model_for.return_value = True
    service.get_loaded_models.return_value = {
        "XAUUSD": {"model_id": "test-model", "model_type": "xgboost"},
    }
    service.predict.return_value = PredictionResult(
        signal_class=SignalClass.BUY,
        signal_name="BUY",
        confidence=0.85,
        probabilities={"SELL": 0.05, "HOLD": 0.10, "BUY": 0.85},
    )
    service.get_market_data.return_value = {
        "current_price": 2000.0,
        "atr": 20.0,
    }
    return service


@pytest.fixture
def mock_broker():
    """Mock broker for DEMO/LIVE market info calls."""
    broker = MagicMock()
    broker.get_market_details = AsyncMock()
    broker.get_accounts = AsyncMock()
    return broker


@pytest.fixture
def paper_loop(mock_prediction_service):
    """PaperTradingLoop with mocked prediction service (no broker)."""
    return PaperTradingLoop(
        prediction_service=mock_prediction_service,
        strategy_manager=StrategyManager(),
        risk_manager=RiskManager(initial_equity=10000.0, limits=RiskLimits()),
        execution_engine=ExecutionEngine(mode=ExecutionMode.PAPER),
        interval_seconds=1,
        epics=["XAUUSD"],
    )


@pytest.fixture
def paper_loop_with_broker(mock_prediction_service, mock_broker):
    """PaperTradingLoop with a mock broker for market info tests."""
    return PaperTradingLoop(
        prediction_service=mock_prediction_service,
        strategy_manager=StrategyManager(),
        risk_manager=RiskManager(initial_equity=10000.0, limits=RiskLimits()),
        execution_engine=ExecutionEngine(mode=ExecutionMode.PAPER),
        broker=mock_broker,
        interval_seconds=1,
        epics=["XAUUSD"],
    )


# ===========================================================================
# _is_market_open() tests
# ===========================================================================

@pytest.mark.asyncio
class TestIsMarketOpen:
    """Tests for _is_market_open()."""

    async def test_no_broker_returns_true(self, paper_loop):
        """Without broker, market is assumed open (PAPER mode)."""
        is_open, reason = await paper_loop._is_market_open("XAUUSD")
        assert is_open is True
        assert reason is None

    async def test_cache_hit_returns_cached_result(self, paper_loop_with_broker, mock_broker):
        """When cache is valid, returns cached market info without broker call."""
        # Pre-populate cache with TRADEABLE status
        paper_loop_with_broker._market_info_cache["XAUUSD"] = {
            "snapshot": {"marketStatus": "TRADEABLE"},
        }
        paper_loop_with_broker._market_cache_ts["XAUUSD"] = _time.monotonic()

        is_open, reason = await paper_loop_with_broker._is_market_open("XAUUSD")

        assert is_open is True
        assert reason is None
        # Broker should NOT have been called (cache hit)
        mock_broker.get_market_details.assert_not_called()

    async def test_cache_hit_market_closed(self, paper_loop_with_broker, mock_broker):
        """Cached market info shows market closed -> returns False with reason."""
        paper_loop_with_broker._market_info_cache["XAUUSD"] = {
            "snapshot": {"marketStatus": "CLOSED"},
        }
        paper_loop_with_broker._market_cache_ts["XAUUSD"] = _time.monotonic()

        is_open, reason = await paper_loop_with_broker._is_market_open("XAUUSD")

        assert is_open is False
        assert reason is not None
        assert "chiuso" in reason.lower() or "CLOSED" in reason

    async def test_cache_miss_broker_timeout_returns_true(self, paper_loop_with_broker, mock_broker):
        """When broker times out, gracefully returns True (try anyway)."""
        mock_broker.get_market_details.side_effect = asyncio.TimeoutError()

        is_open, reason = await paper_loop_with_broker._is_market_open("XAUUSD")

        assert is_open is True
        assert reason is None

    async def test_cache_miss_broker_exception_returns_true(self, paper_loop_with_broker, mock_broker):
        """When broker raises generic exception, gracefully returns True."""
        mock_broker.get_market_details.side_effect = Exception("Network error")

        is_open, reason = await paper_loop_with_broker._is_market_open("XAUUSD")

        assert is_open is True
        assert reason is None

    async def test_cache_expired_fetches_fresh(self, paper_loop_with_broker, mock_broker):
        """When cache has expired, fetches fresh data from broker."""
        # Cache exists but expired (set timestamp far in the past)
        paper_loop_with_broker._market_info_cache["XAUUSD"] = {
            "snapshot": {"marketStatus": "CLOSED"},
        }
        paper_loop_with_broker._market_cache_ts["XAUUSD"] = _time.monotonic() - 7200  # 2h ago

        mock_broker.get_market_details.return_value = {
            "snapshot": {"marketStatus": "TRADEABLE"},
        }

        is_open, reason = await paper_loop_with_broker._is_market_open("XAUUSD")

        assert is_open is True
        mock_broker.get_market_details.assert_called_once_with("XAUUSD")


# ===========================================================================
# _run_iteration() tests
# ===========================================================================

@pytest.mark.asyncio
class TestRunIteration:
    """Tests for _run_iteration() edge cases."""

    async def test_no_new_candles_early_return(self, paper_loop, mock_prediction_service):
        """When no epics have new candles, iteration returns early (no processing)."""
        # Set up data_access to indicate no new candle
        da = MagicMock()
        # get_latest_price returns the same timestamp as last processed
        same_ts = datetime(2026, 1, 1, 12, 0, 0)
        da.get_latest_price.return_value = {"timestamp": same_ts}
        paper_loop.data_access = da

        # Pre-set last candle timestamp so _has_new_candle returns False
        paper_loop._last_candle_ts["XAUUSD"] = same_ts

        await paper_loop._run_iteration(force=False)

        # No iteration should have been counted (early return)
        assert paper_loop._iteration_count == 0
        assert paper_loop.signal_count == 0

    async def test_epic_with_open_position_skipped(self, paper_loop, mock_prediction_service):
        """Epic that already has an open position is skipped."""
        # Mock the position fetch to return an open position for XAUUSD
        paper_loop.execution_engine = MagicMock()
        paper_loop.execution_engine.mode = ExecutionMode.PAPER
        paper_loop.execution_engine._position_tracker = MagicMock()
        paper_loop.execution_engine._position_tracker.get_paper_positions_sync.return_value = [
            {"epic": "XAUUSD", "deal_id": "PAPER-001", "direction": "BUY"},
        ]

        # Make get_positions_async return positions with XAUUSD
        async def fake_positions():
            return [{"epic": "XAUUSD", "deal_id": "PAPER-001", "direction": "BUY"}]

        paper_loop.get_positions_async = fake_positions

        await paper_loop._run_iteration(force=True)

        # XAUUSD should have been skipped due to open position
        assert paper_loop.signal_count == 0

    async def test_forced_iteration_processes_all_epics(self, paper_loop):
        """force=True processes all epics regardless of candle check."""
        await paper_loop._run_iteration(force=True)

        assert paper_loop._iteration_count == 1
        assert paper_loop.signal_count >= 1


# ===========================================================================
# _process_epic() tests
# ===========================================================================

@pytest.mark.asyncio
class TestProcessEpic:
    """Tests for _process_epic() edge cases."""

    async def test_market_closed_logs_and_returns(self, paper_loop_with_broker, mock_broker):
        """When market is closed, _process_epic logs and returns without trading."""
        # Set cached market info as CLOSED
        paper_loop_with_broker._market_info_cache["XAUUSD"] = {
            "snapshot": {"marketStatus": "CLOSED"},
        }
        paper_loop_with_broker._market_cache_ts["XAUUSD"] = _time.monotonic()

        await paper_loop_with_broker._process_epic("XAUUSD", [])

        # Signal should be recorded as market_closed
        assert "XAUUSD" in paper_loop_with_broker._last_signals
        signal_info = paper_loop_with_broker._last_signals["XAUUSD"]
        assert signal_info["status"] == "market_closed"
        assert signal_info["direction"] == "HOLD"
        # No trade should have been executed
        assert paper_loop_with_broker.trade_count == 0

    async def test_execution_failure_records_status(self, paper_loop, mock_prediction_service):
        """When execution fails, signal_info.status is set to exec_failed."""
        # Mock execution engine to return failure
        paper_loop.execution_engine = MagicMock()
        paper_loop.execution_engine.mode = ExecutionMode.PAPER
        paper_loop.execution_engine.execute_signal = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                error="Simulated execution failure",
                error_detail={"error_type": "test_error", "summary": "test"},
            )
        )

        await paper_loop._process_epic("XAUUSD", [])

        assert "XAUUSD" in paper_loop._last_signals
        signal_info = paper_loop._last_signals["XAUUSD"]
        assert signal_info["status"] == "exec_failed"
        assert signal_info.get("rejection_reason") == "Simulated execution failure"
        assert signal_info.get("error_detail") is not None
        assert paper_loop.trade_count == 0

    async def test_prediction_none_skips_processing(self, paper_loop, mock_prediction_service):
        """When prediction returns None, _process_epic returns early."""
        mock_prediction_service.predict.return_value = None

        await paper_loop._process_epic("XAUUSD", [])

        # No signal recorded for this path (early return before signal creation)
        assert paper_loop.signal_count == 0
        assert paper_loop.trade_count == 0

    async def test_no_market_data_skips_processing(self, paper_loop, mock_prediction_service):
        """When get_market_data returns None, _process_epic returns early."""
        mock_prediction_service.get_market_data.return_value = None

        await paper_loop._process_epic("XAUUSD", [])

        # Prediction was called but no signal generated (no market data)
        assert paper_loop.signal_count == 0
        assert paper_loop.trade_count == 0


# ===========================================================================
# _fetch_equity() tests
# ===========================================================================

@pytest.mark.asyncio
class TestFetchEquity:
    """Tests for _fetch_equity() edge cases."""

    async def test_paper_mode_uses_drawdown_monitor(self, paper_loop):
        """In PAPER mode (no broker), _fetch_equity uses drawdown_monitor."""
        equity = await paper_loop._fetch_equity()
        assert equity == paper_loop.risk_manager.drawdown_monitor.state.current_equity

    async def test_broker_fetch_failure_falls_back(self, mock_prediction_service, mock_broker):
        """When broker equity fetch fails, falls back to drawdown_monitor."""
        # Create a loop with broker but in DEMO mode (so it tries broker path)
        loop = PaperTradingLoop(
            prediction_service=mock_prediction_service,
            strategy_manager=StrategyManager(),
            risk_manager=RiskManager(initial_equity=10000.0, limits=RiskLimits()),
            execution_engine=ExecutionEngine(mode=ExecutionMode.PAPER),
            broker=mock_broker,
            interval_seconds=1,
            epics=["XAUUSD"],
        )
        # Override execution engine mode to trigger broker path
        loop.execution_engine._mode = ExecutionMode.DEMO

        mock_broker.get_accounts.side_effect = Exception("Connection refused")

        equity = await loop._fetch_equity()

        # Should fall back to drawdown monitor
        assert equity == loop.risk_manager.drawdown_monitor.state.current_equity

    async def test_broker_fetch_success(self, mock_prediction_service, mock_broker):
        """When broker returns accounts, _fetch_equity uses broker data."""
        loop = PaperTradingLoop(
            prediction_service=mock_prediction_service,
            strategy_manager=StrategyManager(),
            risk_manager=RiskManager(initial_equity=10000.0, limits=RiskLimits()),
            execution_engine=ExecutionEngine(mode=ExecutionMode.PAPER),
            broker=mock_broker,
            interval_seconds=1,
            epics=["XAUUSD"],
        )
        loop.execution_engine._mode = ExecutionMode.DEMO

        # Mock account response
        mock_account = MagicMock()
        mock_account.deposit = 10000.0
        mock_account.available = 9500.0
        mock_account.balance = 0.0
        mock_account.profit_loss = 150.0
        mock_broker.get_accounts.return_value = [mock_account]

        equity = await loop._fetch_equity()

        # Should be deposit + profit_loss = 10150.0
        assert equity == pytest.approx(10150.0)

    async def test_broker_returns_empty_accounts_list(self, mock_prediction_service, mock_broker):
        """When broker returns empty accounts list, falls back to drawdown_monitor."""
        loop = PaperTradingLoop(
            prediction_service=mock_prediction_service,
            strategy_manager=StrategyManager(),
            risk_manager=RiskManager(initial_equity=10000.0, limits=RiskLimits()),
            execution_engine=ExecutionEngine(mode=ExecutionMode.PAPER),
            broker=mock_broker,
            interval_seconds=1,
            epics=["XAUUSD"],
        )
        loop.execution_engine._mode = ExecutionMode.DEMO

        mock_broker.get_accounts.return_value = []

        equity = await loop._fetch_equity()

        assert equity == loop.risk_manager.drawdown_monitor.state.current_equity


# ===========================================================================
# _on_position_closed() tests
# ===========================================================================

class TestOnPositionClosed:
    """Tests for _on_position_closed() method (Phase 8 integration)."""

    def test_records_winning_trade(self, paper_loop):
        """Winning trade updates circuit breaker and trade history."""
        paper_loop._on_position_closed("PAPER-001", pnl=50.0)

        assert len(paper_loop._trade_history) == 1
        assert paper_loop._trade_history[0]["pnl"] == 50.0

    def test_records_losing_trade(self, paper_loop):
        """Losing trade updates circuit breaker and trade history."""
        paper_loop._on_position_closed("PAPER-002", pnl=-30.0)

        assert len(paper_loop._trade_history) == 1
        assert paper_loop._trade_history[0]["pnl"] == -30.0

    def test_trade_history_capped_at_200(self, paper_loop):
        """Trade history is capped at 200 entries."""
        for i in range(210):
            paper_loop._on_position_closed(f"PAPER-{i}", pnl=float(i))

        assert len(paper_loop._trade_history) == 200
        # Should contain the most recent 200 trades
        assert paper_loop._trade_history[-1]["pnl"] == 209.0

    def test_unregisters_trailing_stop(self, paper_loop):
        """Closing a position unregisters it from trailing stop manager."""
        # Register a position first
        paper_loop.trailing_stop_manager.register_position(
            deal_id="PAPER-TST",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1960.0,
            atr=20.0,
        )
        assert "PAPER-TST" in paper_loop.trailing_stop_manager.tracked_positions

        paper_loop._on_position_closed("PAPER-TST", pnl=100.0)

        assert "PAPER-TST" not in paper_loop.trailing_stop_manager.tracked_positions
