from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.broker.models import Direction


@dataclass(frozen=True)
class MarketContext:
    epic: str
    prev_close: float
    today_open: float
    current_price: float
    now: datetime
    session_close: datetime
    atr: float | None = None

    @property
    def gap(self) -> float:
        return (self.today_open / self.prev_close - 1.0) if self.prev_close > 0 else 0.0


@dataclass(frozen=True)
class Signal:
    epic: str
    direction: Direction
    stop_level: float
    rationale: str


@dataclass(frozen=True)
class OpenPosition:
    epic: str
    direction: Direction
    entry: float
    size: float
    stop_level: float
    prev_close: float
    today_open: float
    opened_at: datetime
    deal_id: str


class ForwardStrategy(ABC):
    name: str = "abstract"

    @abstractmethod
    def universe(self) -> list[str]:
        """Epics this strategy trades."""

    @abstractmethod
    def should_enter(self, ctx: MarketContext) -> Signal | None:
        """Return an entry Signal or None. MUST use only data in ctx (no look-ahead)."""

    @abstractmethod
    def exit_rule(self, pos: OpenPosition, ctx: MarketContext) -> bool:
        """True if the position should be closed now (SL is broker-side, not here)."""
