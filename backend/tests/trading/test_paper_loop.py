"""
Tests for the paper trading loop and trading API endpoints.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode, ExecutionResult
from src.models.schemas import PredictionResult, SignalClass
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.strategy_manager import StrategyManager
from src.trading.paper_loop import PaperTradingLoop


@pytest.fixture
def mock_prediction_service():
    """Mock PredictionService that returns canned predictions."""
    service = MagicMock()
    service.has_models = True
    service.has_model_for.return_value = True
    service.get_loaded_models.return_value = {
        "XAUUSD": {"model_id": "test-model", "model_type": "xgboost"}
    }

    service.predict.return_value = PredictionResult(
        signal_class=SignalClass.BUY,
        signal_name="BUY",
        confidence=0.85,
        probabilities={
            "SELL": 0.05, "HOLD": 0.10,
            "BUY": 0.85,
        },
    )

    service.get_market_data.return_value = {
        "current_price": 2000.0,
        "atr": 20.0,
    }

    return service


@pytest.fixture
def paper_loop(mock_prediction_service):
    """PaperTradingLoop with mocked prediction service."""
    return PaperTradingLoop(
        prediction_service=mock_prediction_service,
        strategy_manager=StrategyManager(),
        risk_manager=RiskManager(initial_equity=10000.0, limits=RiskLimits()),
        execution_engine=ExecutionEngine(mode=ExecutionMode.PAPER),
        interval_seconds=1,
        epics=["XAUUSD"],
    )


class TestPaperTradingLoop:
    """Unit tests for PaperTradingLoop."""

    def test_initial_state(self, paper_loop):
        """Loop starts in stopped state."""
        assert paper_loop.is_running is False
        assert paper_loop.last_run is None
        assert paper_loop.iteration_count == 0
        assert paper_loop.trade_count == 0

    @pytest.mark.asyncio
    async def test_single_iteration(self, paper_loop):
        """Single iteration processes epic and generates trade."""
        await paper_loop._run_iteration()

        assert paper_loop.iteration_count == 1
        assert paper_loop.signal_count >= 1
        assert paper_loop.last_run is not None

    @pytest.mark.asyncio
    async def test_single_iteration_produces_trade(self, paper_loop):
        """Iteration with BUY signal at high confidence should produce a trade."""
        await paper_loop._run_iteration()

        # BUY with 0.85 confidence should pass risk checks
        assert paper_loop.trade_count >= 1

    @pytest.mark.asyncio
    async def test_start_stop(self, paper_loop):
        """Loop can be started and stopped."""
        paper_loop.start()
        assert paper_loop.is_running is True

        # Let it run briefly
        await asyncio.sleep(0.1)

        paper_loop.stop()
        assert paper_loop.is_running is False

    @pytest.mark.asyncio
    async def test_no_models_skips_epic(self, paper_loop, mock_prediction_service):
        """Epic is skipped when no model is loaded for it."""
        mock_prediction_service.has_model_for.return_value = False

        await paper_loop._run_iteration()

        assert paper_loop.signal_count == 0
        assert paper_loop.trade_count == 0

    @pytest.mark.asyncio
    async def test_hold_signal_no_trade(self, paper_loop, mock_prediction_service):
        """HOLD prediction should not produce a trade."""
        mock_prediction_service.predict.return_value = PredictionResult(
            signal_class=SignalClass.HOLD,
            signal_name="HOLD",
            confidence=0.90,
            probabilities={
                "SELL": 0.05, "HOLD": 0.90,
                "BUY": 0.05,
            },
        )

        await paper_loop._run_iteration()

        assert paper_loop.signal_count >= 1
        assert paper_loop.trade_count == 0

    @pytest.mark.asyncio
    async def test_risk_rejection(self, paper_loop):
        """Trade rejected by risk manager is not executed."""
        # Activate circuit breaker to reject all trades
        paper_loop.risk_manager.drawdown_monitor.activate_circuit_breaker("test")

        await paper_loop._run_iteration()

        assert paper_loop.signal_count >= 1
        assert paper_loop.trade_count == 0

    @pytest.mark.asyncio
    async def test_prediction_failure_continues(self, paper_loop, mock_prediction_service):
        """Loop continues even if prediction fails."""
        mock_prediction_service.predict.return_value = None

        await paper_loop._run_iteration()

        assert paper_loop.iteration_count == 1
        assert paper_loop.trade_count == 0

    def test_get_status(self, paper_loop):
        """Status returns expected fields."""
        status = paper_loop.get_status()

        assert "running" in status
        assert "execution_mode" in status
        assert status["execution_mode"] == "PAPER"
        assert "interval_seconds" in status
        assert "epics" in status
        assert "iteration_count" in status
        assert "trade_count" in status
        assert "signal_count" in status
        assert "models_loaded" in status
        assert "open_positions" in status

    @pytest.mark.asyncio
    async def test_last_signals_tracked(self, paper_loop):
        """Last signals per epic are tracked after iteration."""
        # Was a sync test that called `asyncio.get_event_loop().run_until_complete`,
        # which fights pytest-asyncio's per-test loop and broke when other
        # async tests left scheduled coroutines pending in the policy loop.
        await paper_loop._run_iteration()

        assert "XAUUSD" in paper_loop.last_signals
        signal_info = paper_loop.last_signals["XAUUSD"]
        assert "direction" in signal_info
        assert "confidence" in signal_info
        assert "timestamp" in signal_info


class TestTradingEndpoints:
    """Tests for /api/trading/ endpoints."""

    @pytest.fixture
    def trading_client(self, mock_prediction_service):
        """TestClient with paper loop in app state."""
        from src.api.main import app
        from src.api.dependencies import (
            get_execution_engine, get_risk_manager, get_strategy_manager,
            get_broker_client, get_data_access, get_feature_builder,
            get_prediction_service, get_model_versioning,
            get_db_session, get_position_repo, get_signal_repo,
            get_trade_repo, get_strategy_repo,
        )

        engine = ExecutionEngine(mode=ExecutionMode.PAPER)
        risk_mgr = RiskManager(initial_equity=10000.0, limits=RiskLimits())
        strategy_mgr = StrategyManager()

        app.dependency_overrides[get_execution_engine] = lambda: engine
        app.dependency_overrides[get_risk_manager] = lambda: risk_mgr
        app.dependency_overrides[get_strategy_manager] = lambda: strategy_mgr
        app.dependency_overrides[get_broker_client] = lambda: None
        app.dependency_overrides[get_data_access] = lambda: None
        app.dependency_overrides[get_feature_builder] = lambda: None
        app.dependency_overrides[get_prediction_service] = lambda: None
        app.dependency_overrides[get_model_versioning] = lambda: None

        async def no_db():
            yield None

        app.dependency_overrides[get_db_session] = no_db
        app.dependency_overrides[get_position_repo] = lambda: None
        app.dependency_overrides[get_signal_repo] = lambda: None
        app.dependency_overrides[get_trade_repo] = lambda: None
        app.dependency_overrides[get_strategy_repo] = lambda: None

        # Set up app state
        app.state.execution_engine = engine
        app.state.risk_manager = risk_mgr
        app.state.strategy_manager = strategy_mgr
        app.state.signal_history = []
        app.state.backtest_runs = {}
        app.state.broker_client = None
        app.state.data_access = None
        app.state.feature_builder = None
        app.state.prediction_service = None
        app.state.model_versioning = None
        app.state.db_session_factory = None

        with TestClient(app) as tc:
            # Override paper loop AFTER lifespan runs (lifespan creates its own)
            loop = PaperTradingLoop(
                prediction_service=mock_prediction_service,
                strategy_manager=strategy_mgr,
                risk_manager=risk_mgr,
                execution_engine=engine,
            )
            app.state.paper_loop = loop
            yield tc

            # Ensure loop is stopped
            if loop.is_running:
                loop.stop()

        app.dependency_overrides.clear()

    def test_status_endpoint(self, trading_client):
        """GET /api/trading/status returns 200."""
        resp = trading_client.get("/api/trading/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["running"] is False

    def test_start_endpoint(self, trading_client):
        """POST /api/trading/start starts the loop."""
        resp = trading_client.post("/api/trading/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["running"] is True

    def test_stop_endpoint_when_not_running(self, trading_client):
        """POST /api/trading/stop when not running is idempotent (returns success)."""
        resp = trading_client.post("/api/trading/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "fermo" in data["data"]["message"].lower()

    def test_start_stop_cycle(self, trading_client):
        """Start then stop the paper trading loop."""
        start_resp = trading_client.post("/api/trading/start")
        assert start_resp.json()["success"] is True

        stop_resp = trading_client.post("/api/trading/stop")
        assert stop_resp.json()["success"] is True

    def test_double_start_idempotent(self, trading_client):
        """Starting an already running loop is idempotent (returns success)."""
        trading_client.post("/api/trading/start")
        resp = trading_client.post("/api/trading/start")
        data = resp.json()
        assert data["success"] is True
        assert "attivo" in data["data"]["message"].lower()
