from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    or_high: float | None = None
    or_low: float | None = None
    rvol: float | None = None

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
    needs_opening_range: bool = False

    @abstractmethod
    def universe(self) -> list[str]:
        """Epics this strategy trades."""

    @abstractmethod
    def should_enter(self, ctx: MarketContext) -> Signal | None:
        """Return an entry Signal or None. MUST use only data in ctx (no look-ahead)."""

    @abstractmethod
    def exit_rule(self, pos: OpenPosition, ctx: MarketContext) -> bool:
        """True if the position should be closed now (SL is broker-side, not here)."""


@dataclass
class GapFadeStrategy(ForwardStrategy):
    epics: list[str]
    gap_threshold: float = 0.01
    stop_atr_mult: float = 1.0
    stop_pct_fallback: float = 0.015
    fill_fraction: float = 0.5
    name: str = field(default="gap_fade")

    def universe(self) -> list[str]:
        return list(self.epics)

    def _stop_distance(self, ctx: MarketContext) -> float:
        if ctx.atr and ctx.atr > 0:
            return ctx.atr * self.stop_atr_mult
        return ctx.today_open * self.stop_pct_fallback

    def should_enter(self, ctx: MarketContext) -> Signal | None:
        if ctx.prev_close <= 0:
            return None
        gap = ctx.gap
        if abs(gap) < self.gap_threshold:
            return None
        dist = self._stop_distance(ctx)
        if gap > 0:  # gap up -> fade short, stop above
            return Signal(ctx.epic, Direction.SELL, ctx.today_open + dist,
                          f"gap +{gap * 100:.2f}% fade short")
        return Signal(ctx.epic, Direction.BUY, ctx.today_open - dist,  # gap down -> fade long
                      f"gap {gap * 100:.2f}% fade long")

    def exit_rule(self, pos: OpenPosition, ctx: MarketContext) -> bool:
        if ctx.now >= ctx.session_close:  # EOD flatten (time stop)
            return True
        gap_size = pos.today_open - pos.prev_close
        target = pos.today_open - self.fill_fraction * gap_size  # 50% retrace toward prev_close
        if pos.direction == Direction.SELL:
            return ctx.current_price <= target
        return ctx.current_price >= target


@dataclass
class ORBStrategy(ForwardStrategy):
    epics: list[str]
    rvol_min: float = 1.5
    breakout_buffer: float = 0.0          # fraction beyond OR required (0 = touch)
    stop_atr_mult: float = 1.0
    stop_pct_fallback: float = 0.015      # used when atr is absent
    name: str = field(default="orb")
    needs_opening_range: bool = field(default=True)

    def universe(self) -> list[str]:
        return list(self.epics)

    def _stop_floor(self, ctx: MarketContext) -> float:
        if ctx.atr and ctx.atr > 0:
            return ctx.atr * self.stop_atr_mult
        return ctx.current_price * self.stop_pct_fallback

    def should_enter(self, ctx: MarketContext) -> Signal | None:
        if ctx.or_high is None or ctx.or_low is None:
            return None
        if ctx.rvol is not None and ctx.rvol < self.rvol_min:
            return None
        floor = self._stop_floor(ctx)
        up = ctx.or_high * (1.0 + self.breakout_buffer)
        dn = ctx.or_low * (1.0 - self.breakout_buffer)
        if ctx.current_price > up:                                   # break up -> long
            sl = min(ctx.or_low, ctx.current_price - floor)          # stop below, >= floor away
            return Signal(ctx.epic, Direction.BUY, sl,
                          f"ORB long {ctx.current_price:.2f}>{ctx.or_high:.2f} rvol={ctx.rvol}")
        if ctx.current_price < dn:                                   # break down -> short
            sl = max(ctx.or_high, ctx.current_price + floor)         # stop above, >= floor away
            return Signal(ctx.epic, Direction.SELL, sl,
                          f"ORB short {ctx.current_price:.2f}<{ctx.or_low:.2f} rvol={ctx.rvol}")
        return None

    def exit_rule(self, pos: OpenPosition, ctx: MarketContext) -> bool:
        return ctx.now >= ctx.session_close                          # EOD flatten; SL is broker-side
