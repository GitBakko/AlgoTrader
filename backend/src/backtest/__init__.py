"""
Backtesting module for AlgoTrader AI.
Event-driven backtest engine with cost simulation and performance metrics.
"""

from src.backtest.costs import CostSimulator
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import MetricsCalculator
from src.backtest.portfolio import PortfolioTracker
from src.backtest.reporter import BacktestReporter
from src.backtest.schemas import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    TradeDirection,
    TradeStatus,
)

__all__ = [
    # Schemas
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "TradeDirection",
    "TradeStatus",
    # Core
    "CostSimulator",
    "PortfolioTracker",
    "MetricsCalculator",
    "BacktestEngine",
    "BacktestReporter",
]
