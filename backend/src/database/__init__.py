"""
Database layer for AlgoTrader AI.
SQLModel ORM models, repositories, and database utilities.
"""

from src.database.models import (
    Account,
    BacktestRun,
    MarketDataSnapshot,
    Model,
    Order,
    Position,
    Signal,
    Strategy,
    SystemEvent,
    Trade,
    metadata,
)
from src.database.repositories import PositionRepository, SignalRepository, StrategyRepository
from src.database.repository import BaseRepository
from src.database.session import DatabaseManager, get_db_session

__all__ = [
    # Models
    "Account",
    "Position",
    "Order",
    "Trade",
    "Signal",
    "Strategy",
    "Model",
    "MarketDataSnapshot",
    "SystemEvent",
    "BacktestRun",
    "metadata",
    # Session Management
    "DatabaseManager",
    "get_db_session",
    # Repositories
    "BaseRepository",
    "PositionRepository",
    "SignalRepository",
    "StrategyRepository",
]
