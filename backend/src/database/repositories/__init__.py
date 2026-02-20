"""
Model-specific repositories with custom query methods.
"""

from src.database.repositories.position_repository import PositionRepository
from src.database.repositories.risk_state_repository import RiskStateRepository
from src.database.repositories.signal_repository import SignalRepository
from src.database.repositories.strategy_repository import StrategyRepository
from src.database.repositories.market_spec_repository import MarketSpecRepository
from src.database.repositories.notification_repository import NotificationRepository
from src.database.repositories.trade_journal_note_repository import (
    TradeJournalNoteRepository,
)
from src.database.repositories.trade_repository import TradeRepository
from src.database.repositories.trailing_stop_repository import (
    TrailingStopRepository,
)

__all__ = [
    "MarketSpecRepository",
    "NotificationRepository",
    "PositionRepository",
    "RiskStateRepository",
    "SignalRepository",
    "StrategyRepository",
    "TradeJournalNoteRepository",
    "TradeRepository",
    "TrailingStopRepository",
]
