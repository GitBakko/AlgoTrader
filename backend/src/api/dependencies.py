"""
FastAPI dependency injection for shared services.
Services are initialized once in lifespan and stored in app.state.
"""

from fastapi import Depends, Request

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.strategy_manager import StrategyManager
from src.utils.config import get_settings


def get_execution_engine(request: Request) -> ExecutionEngine:
    """Get the singleton ExecutionEngine from app state."""
    return request.app.state.execution_engine


def get_risk_manager(request: Request) -> RiskManager:
    """Get the singleton RiskManager from app state."""
    return request.app.state.risk_manager


def get_strategy_manager(request: Request) -> StrategyManager:
    """Get the singleton StrategyManager from app state."""
    return request.app.state.strategy_manager


def init_services(app) -> None:
    """Initialize all services and store in app.state. Called during lifespan startup."""
    settings = get_settings()

    limits = RiskLimits(
        max_risk_per_trade=settings.max_risk_per_trade,
        max_daily_drawdown=settings.max_daily_drawdown,
        max_total_drawdown=settings.max_total_drawdown,
    )

    app.state.execution_engine = ExecutionEngine(mode=ExecutionMode.PAPER)
    app.state.risk_manager = RiskManager(
        initial_equity=10000.0,
        limits=limits,
    )
    app.state.strategy_manager = StrategyManager()

    # In-memory stores for MVP (no DB required)
    app.state.signal_history = []  # Recent signals
    app.state.backtest_runs = {}  # Backtest results by ID
