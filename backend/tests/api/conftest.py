"""
Shared fixtures for API tests.
Uses FastAPI TestClient with dependency overrides.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_broker_client,
    get_data_access,
    get_db_session,
    get_execution_engine,
    get_feature_builder,
    get_model_versioning,
    get_position_repo,
    get_prediction_service,
    get_risk_manager,
    get_signal_repo,
    get_strategy_manager,
    get_strategy_repo,
    get_trade_repo,
)
from src.api.main import app
from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.strategy_manager import StrategyManager


@pytest.fixture
def engine():
    """Paper mode execution engine for tests."""
    return ExecutionEngine(mode=ExecutionMode.PAPER)


@pytest.fixture
def risk_mgr():
    """Risk manager with default limits."""
    return RiskManager(initial_equity=10000.0, limits=RiskLimits())


@pytest.fixture
def strategy_mgr():
    """Strategy manager with default configs."""
    return StrategyManager()


@pytest.fixture
def client(engine, risk_mgr, strategy_mgr):
    """
    FastAPI TestClient with dependency overrides for services.
    App state is also populated for routers that access request.app.state.
    All DB/external dependencies overridden to None for unit tests.
    """
    # Override singleton service dependencies
    app.dependency_overrides[get_execution_engine] = lambda: engine
    app.dependency_overrides[get_risk_manager] = lambda: risk_mgr
    app.dependency_overrides[get_strategy_manager] = lambda: strategy_mgr

    # Override external dependencies to None (graceful degradation)
    app.dependency_overrides[get_broker_client] = lambda: None
    app.dependency_overrides[get_data_access] = lambda: None
    app.dependency_overrides[get_feature_builder] = lambda: None
    app.dependency_overrides[get_prediction_service] = lambda: None
    app.dependency_overrides[get_model_versioning] = lambda: None

    # Override DB session and repositories to None (no DB in unit tests)
    async def no_db_session():
        yield None

    app.dependency_overrides[get_db_session] = no_db_session
    app.dependency_overrides[get_position_repo] = lambda: None
    app.dependency_overrides[get_signal_repo] = lambda: None
    app.dependency_overrides[get_trade_repo] = lambda: None
    app.dependency_overrides[get_strategy_repo] = lambda: None

    # Populate app.state for routers that use request.app.state directly
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
        yield tc

    app.dependency_overrides.clear()
