"""
Strategy module.
Provides signal generation, regime adaptation, portfolio allocation,
and the unified strategy manager.
"""

from src.strategy.portfolio_allocator import PortfolioAllocator
from src.strategy.regime_adapter import RegimeAdapter
from src.strategy.schemas import (
    AllocationConfig,
    SignalDirection,
    StrategyConfig,
    TradingSignal,
)
from src.strategy.signal_generator import SignalGenerator
from src.strategy.strategy_manager import StrategyManager

__all__ = [
    "AllocationConfig",
    "PortfolioAllocator",
    "RegimeAdapter",
    "SignalDirection",
    "SignalGenerator",
    "StrategyConfig",
    "StrategyManager",
    "TradingSignal",
]
