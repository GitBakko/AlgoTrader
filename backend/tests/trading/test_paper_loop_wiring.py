"""
Tests for Phase 8 paper loop integration wiring.

Verifies that PaperTradingLoop correctly integrates:
- TrailingStopManager: register on open, update_price each iteration, partial_close at TP1
- CircuitBreakers: heartbeat each iteration, record_trade_result on close
- EquityCurveFilter: record_trade_close on position close
- Kelly sizing: pass trade_history to risk_manager.check_trade()
"""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.execution.schemas import ExecutionMode, ExecutionResult
from src.risk.schemas import RiskCheckResult
from src.risk.trailing_stop_manager import TrailingPhase, TrailingStopConfig, TrailingStopManager
from src.strategy.schemas import SignalDirection, TradingSignal
from src.trading.paper_loop import PaperTradingLoop


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_signal(epic: str = "XAUUSD", direction: str = "BUY") -> TradingSignal:
    """Helper to build a TradingSignal with sensible defaults."""
    return TradingSignal(
        epic=epic,
        direction=SignalDirection(direction),
        confidence=0.75,
        signal_class=2 if direction == "BUY" else 0,
        entry_price=2000.0,
        suggested_stop=1980.0,
        suggested_tp=2040.0,
    )


def _make_exec_result(success: bool = True, deal_id: str = "DEAL-001") -> ExecutionResult:
    """Helper to build an ExecutionResult."""
    return ExecutionResult(
        success=success,
        deal_id=deal_id,
        fill_price=2001.0,
        error=None if success else "mock error",
    )


def _make_prediction():
    """Return a mock prediction object with the attributes paper_loop reads."""
    pred = MagicMock()
    pred.signal_name = "BUY"
    pred.confidence = 0.75
    return pred


@pytest.fixture
def mock_prediction_service():
    """PredictionService mock: has_model_for True, predict returns BUY, market data available."""
    svc = MagicMock()
    svc.has_model_for.return_value = True
    svc.predict.return_value = _make_prediction()
    svc.get_market_data.return_value = {"current_price": 2000.0, "atr": 20.0}
    svc.get_loaded_models.return_value = {"XAUUSD": {"model_type": "xgboost"}}
    return svc


@pytest.fixture
def mock_strategy_manager():
    """StrategyManager mock returning a BUY TradingSignal."""
    mgr = MagicMock()
    mgr.process_prediction.return_value = _make_signal()
    return mgr


@pytest.fixture
def mock_risk_manager():
    """RiskManager mock with circuit_breakers, equity_curve_filter, drawdown_monitor stubs."""
    mgr = MagicMock()
    mgr.check_trade.return_value = RiskCheckResult(
        approved=True,
        position_size=0.1,
        stop_loss=1980.0,
        take_profit=2040.0,
    )

    # Sub-objects accessed by paper_loop
    mgr.circuit_breakers = MagicMock()
    mgr.circuit_breakers.heartbeat = MagicMock()
    mgr.circuit_breakers.record_trade_result = MagicMock()
    mgr.circuit_breakers.tripped_breakers = {}
    mgr.circuit_breakers.config.max_open_positions = 6

    mgr.equity_curve_filter = MagicMock()
    mgr.equity_curve_filter.record_trade_close = MagicMock()
    mgr.equity_curve_filter.is_below_sma = False

    mgr.drawdown_monitor = MagicMock()
    mgr.drawdown_monitor.state = MagicMock()
    mgr.drawdown_monitor.state.current_equity = 10000.0

    mgr.update_equity = MagicMock()
    return mgr


@pytest.fixture
def mock_execution_engine():
    """ExecutionEngine async mock: execute_signal succeeds, get_open_positions empty."""
    eng = AsyncMock()
    eng.mode = ExecutionMode.PAPER
    eng.execute_signal = AsyncMock(return_value=_make_exec_result())
    eng.get_open_positions = AsyncMock(return_value=[])
    eng.update_stops = AsyncMock()
    eng.partial_close = AsyncMock(return_value=_make_exec_result(deal_id="DEAL-PARTIAL"))

    # Sync fallback for get_paper_positions (called by get_status)
    tracker = MagicMock()
    tracker.get_paper_positions_sync.return_value = []
    eng._position_tracker = tracker
    return eng


@pytest.fixture
def loop(mock_prediction_service, mock_strategy_manager, mock_risk_manager, mock_execution_engine):
    """PaperTradingLoop fully wired with mocks and a trailing stop config."""
    return PaperTradingLoop(
        prediction_service=mock_prediction_service,
        strategy_manager=mock_strategy_manager,
        risk_manager=mock_risk_manager,
        execution_engine=mock_execution_engine,
        interval_seconds=1,
        epics=["XAUUSD"],
        trailing_stop_config=TrailingStopConfig(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.trading
class TestTrailingStopManagerInit:
    """Test 1: TrailingStopManager is created in __init__."""

    def test_trailing_stop_manager_created(self, loop):
        """PaperTradingLoop.__init__ creates a TrailingStopManager instance."""
        assert hasattr(loop, "trailing_stop_manager")
        assert isinstance(loop.trailing_stop_manager, TrailingStopManager)

    def test_trailing_stop_manager_uses_provided_config(self):
        """When a TrailingStopConfig is provided, the manager uses it."""
        config = TrailingStopConfig(tp1_risk_multiple=1.5, tp2_risk_multiple=3.0)
        pl = PaperTradingLoop(
            prediction_service=MagicMock(),
            strategy_manager=MagicMock(),
            risk_manager=MagicMock(),
            execution_engine=MagicMock(),
            trailing_stop_config=config,
        )
        assert pl.trailing_stop_manager.config.tp1_risk_multiple == 1.5
        assert pl.trailing_stop_manager.config.tp2_risk_multiple == 3.0

    def test_trailing_stop_manager_default_config(self):
        """When no config is given, defaults are used."""
        pl = PaperTradingLoop(
            prediction_service=MagicMock(),
            strategy_manager=MagicMock(),
            risk_manager=MagicMock(),
            execution_engine=MagicMock(),
        )
        assert pl.trailing_stop_manager.config.tp1_risk_multiple == 1.0


@pytest.mark.trading
class TestTrailingStopRegistration:
    """Test 2: After successful execution, register_position is called."""

    @pytest.mark.asyncio
    async def test_register_called_on_successful_execution(self, loop):
        """Successful trade execution registers the position for trailing stops."""
        with patch.object(loop.trailing_stop_manager, "register_position") as mock_reg:
            await loop._run_iteration(force=True)

            mock_reg.assert_called_once_with(
                deal_id="DEAL-001",
                epic="XAUUSD",
                direction="BUY",
                entry_price=2001.0,
                stop_loss=1980.0,
                atr=20.0,
            )

    @pytest.mark.asyncio
    async def test_register_not_called_on_failed_execution(
        self, loop, mock_execution_engine
    ):
        """Failed execution does not register the position."""
        mock_execution_engine.execute_signal.return_value = _make_exec_result(
            success=False, deal_id=None
        )

        with patch.object(loop.trailing_stop_manager, "register_position") as mock_reg:
            await loop._run_iteration(force=True)
            mock_reg.assert_not_called()


@pytest.mark.trading
class TestTrailingStopUpdateIteration:
    """Test 3: _update_trailing_stops calls update_price for tracked positions."""

    @pytest.mark.asyncio
    async def test_update_price_called_for_tracked_positions(
        self, loop, mock_prediction_service
    ):
        """Each iteration calls update_price for every tracked position."""
        # Pre-register a position so it appears in tracked_positions
        loop.trailing_stop_manager.register_position(
            deal_id="DEAL-100",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=20.0,
        )

        # Simulate an open position returned by execution engine
        positions = [{"deal_id": "DEAL-100", "epic": "XAUUSD", "level": 2010.0}]

        with patch.object(
            loop.trailing_stop_manager, "update_price", return_value=(None, TrailingPhase.INITIAL)
        ) as mock_update:
            await loop._update_trailing_stops(positions)

            mock_update.assert_called_once_with(
                deal_id="DEAL-100",
                current_price=2010.0,
                current_atr=20.0,
            )

    @pytest.mark.asyncio
    async def test_unregister_if_position_closed_externally(self, loop):
        """If a tracked position is no longer in current_positions, unregister it."""
        loop.trailing_stop_manager.register_position(
            deal_id="DEAL-GONE",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=20.0,
        )

        # current_positions does NOT include DEAL-GONE
        await loop._update_trailing_stops([])

        assert "DEAL-GONE" not in loop.trailing_stop_manager.tracked_positions


@pytest.mark.trading
class TestTP1PartialClose:
    """Test 4: INITIAL->BREAKEVEN transition triggers partial_close(0.5, 'TP1_HIT')."""

    @pytest.mark.asyncio
    async def test_partial_close_on_tp1_hit(self, loop, mock_execution_engine):
        """When trailing phase transitions INITIAL->BREAKEVEN, partial_close is called."""
        # Register position in INITIAL phase
        loop.trailing_stop_manager.register_position(
            deal_id="DEAL-TP1",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=20.0,
        )

        # Price has reached TP1 (entry + risk_distance * tp1_multiple = 2000 + 20*1.0 = 2020)
        positions = [{"deal_id": "DEAL-TP1", "epic": "XAUUSD", "level": 2025.0}]

        await loop._update_trailing_stops(positions)

        # Verify partial_close was called with 50% and reason
        mock_execution_engine.partial_close.assert_awaited_once_with(
            "DEAL-TP1", 0.5, "TP1_HIT"
        )

    @pytest.mark.asyncio
    async def test_no_partial_close_when_phase_unchanged(self, loop, mock_execution_engine):
        """No partial close if price stays within INITIAL phase (below TP1)."""
        loop.trailing_stop_manager.register_position(
            deal_id="DEAL-STAY",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=20.0,
        )

        # Price below TP1 (2020)
        positions = [{"deal_id": "DEAL-STAY", "epic": "XAUUSD", "level": 2010.0}]

        await loop._update_trailing_stops(positions)

        mock_execution_engine.partial_close.assert_not_awaited()


@pytest.mark.trading
class TestCircuitBreakerHeartbeat:
    """Test 5: heartbeat() called at start of each _run_iteration."""

    @pytest.mark.asyncio
    async def test_heartbeat_called_every_iteration(self, loop, mock_risk_manager):
        """Each _run_iteration call invokes circuit_breakers.heartbeat() (at start + per epic)."""
        await loop._run_iteration(force=True)

        # Called at iteration start + once per processed epic
        assert mock_risk_manager.circuit_breakers.heartbeat.call_count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_called_even_when_no_epics_to_process(
        self, loop, mock_prediction_service, mock_risk_manager
    ):
        """heartbeat is called even if no epics have new candles (early return)."""
        mock_prediction_service.has_model_for.return_value = False

        await loop._run_iteration(force=False)

        mock_risk_manager.circuit_breakers.heartbeat.assert_called_once()


@pytest.mark.trading
class TestOnPositionClosed:
    """Test 6: _on_position_closed records results to circuit_breakers, equity_curve, history."""

    def test_winning_trade_recorded(self, loop, mock_risk_manager):
        """Winning trade (pnl > 0) records is_win=True and appends to history."""
        loop._on_position_closed("DEAL-WIN", pnl=150.0)

        mock_risk_manager.circuit_breakers.record_trade_result.assert_called_once_with(
            is_win=True
        )
        mock_risk_manager.equity_curve_filter.record_trade_close.assert_called_once_with(
            10000.0  # current_equity from mock
        )
        assert len(loop._trade_history) == 1
        assert loop._trade_history[0] == {"pnl": 150.0}

    def test_losing_trade_recorded(self, loop, mock_risk_manager):
        """Losing trade (pnl < 0) records is_win=False."""
        loop._on_position_closed("DEAL-LOSE", pnl=-80.0)

        mock_risk_manager.circuit_breakers.record_trade_result.assert_called_once_with(
            is_win=False
        )
        assert loop._trade_history[-1] == {"pnl": -80.0}

    def test_trailing_stop_unregistered(self, loop):
        """After close, trailing stop manager unregisters the deal."""
        loop.trailing_stop_manager.register_position(
            deal_id="DEAL-CLOSE",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=20.0,
        )
        assert "DEAL-CLOSE" in loop.trailing_stop_manager.tracked_positions

        loop._on_position_closed("DEAL-CLOSE", pnl=50.0)

        assert "DEAL-CLOSE" not in loop.trailing_stop_manager.tracked_positions

    def test_trade_history_capped_at_200(self, loop):
        """Trade history is capped at 200 entries."""
        for i in range(210):
            loop._on_position_closed(f"DEAL-{i}", pnl=float(i))

        assert len(loop._trade_history) == 200
        # Oldest entries should have been trimmed (first 10 removed)
        assert loop._trade_history[0] == {"pnl": 10.0}


@pytest.mark.trading
class TestKellyTradeHistory:
    """Test 7: check_trade receives trade_history kwarg."""

    @pytest.mark.asyncio
    async def test_trade_history_passed_to_check_trade(
        self, loop, mock_risk_manager
    ):
        """risk_manager.check_trade() receives trade_history from _trade_history."""
        # Seed some trade history
        loop._trade_history = [{"pnl": 50.0}, {"pnl": -20.0}]

        await loop._run_iteration(force=True)

        # Inspect the kwargs passed to check_trade
        call_kwargs = mock_risk_manager.check_trade.call_args
        assert call_kwargs is not None
        assert "trade_history" in call_kwargs.kwargs or (
            len(call_kwargs.args) > 4
        )
        # Extract trade_history from the call
        if "trade_history" in (call_kwargs.kwargs or {}):
            th = call_kwargs.kwargs["trade_history"]
        else:
            th = call_kwargs.args[4] if len(call_kwargs.args) > 4 else None
        assert th == [{"pnl": 50.0}, {"pnl": -20.0}]

    @pytest.mark.asyncio
    async def test_empty_trade_history_passed_as_none(self, loop, mock_risk_manager):
        """When _trade_history is empty, None is passed (falsy list -> None)."""
        loop._trade_history = []

        await loop._run_iteration(force=True)

        call_kwargs = mock_risk_manager.check_trade.call_args
        if "trade_history" in (call_kwargs.kwargs or {}):
            th = call_kwargs.kwargs["trade_history"]
        else:
            th = call_kwargs.args[4] if len(call_kwargs.args) > 4 else None
        assert th is None


@pytest.mark.trading
class TestGetStatusPhase8Fields:
    """Test 8: get_status() includes Phase 8 fields."""

    def test_status_contains_circuit_breakers_tripped(self, loop):
        """Status dict has circuit_breakers_tripped field."""
        status = loop.get_status()
        assert "circuit_breakers_tripped" in status
        assert status["circuit_breakers_tripped"] == {}

    def test_status_contains_trailing_stops_tracked(self, loop):
        """Status dict has trailing_stops_tracked count."""
        status = loop.get_status()
        assert "trailing_stops_tracked" in status
        assert status["trailing_stops_tracked"] == 0

    def test_status_trailing_stops_tracked_reflects_registered(self, loop):
        """trailing_stops_tracked reflects actual registered positions."""
        loop.trailing_stop_manager.register_position(
            deal_id="D1", epic="XAUUSD", direction="BUY",
            entry_price=2000.0, stop_loss=1980.0, atr=20.0,
        )
        loop.trailing_stop_manager.register_position(
            deal_id="D2", epic="BTCUSD", direction="SELL",
            entry_price=50000.0, stop_loss=51000.0, atr=500.0,
        )

        status = loop.get_status()
        assert status["trailing_stops_tracked"] == 2

    def test_status_contains_equity_curve_below_sma(self, loop):
        """Status dict has equity_curve_below_sma field."""
        status = loop.get_status()
        assert "equity_curve_below_sma" in status
        assert status["equity_curve_below_sma"] is False

    def test_status_contains_kelly_trade_history_size(self, loop):
        """Status dict has kelly_trade_history_size reflecting _trade_history length."""
        loop._trade_history = [{"pnl": 10.0}, {"pnl": -5.0}, {"pnl": 20.0}]

        status = loop.get_status()
        assert "kelly_trade_history_size" in status
        assert status["kelly_trade_history_size"] == 3
