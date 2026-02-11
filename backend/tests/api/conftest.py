"""
Shared fixtures for API tests.
Uses FastAPI TestClient with dependency overrides.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_execution_engine,
    get_risk_manager,
    get_strategy_manager,
    init_services,
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
    """
    app.dependency_overrides[get_execution_engine] = lambda: engine
    app.dependency_overrides[get_risk_manager] = lambda: risk_mgr
    app.dependency_overrides[get_strategy_manager] = lambda: strategy_mgr

    # Populate app.state for routers that use request.app.state directly
    app.state.execution_engine = engine
    app.state.risk_manager = risk_mgr
    app.state.strategy_manager = strategy_mgr
    app.state.signal_history = []
    app.state.backtest_runs = {}

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()
