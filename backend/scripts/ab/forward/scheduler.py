from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone, date as _date
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[3]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forward.executor import ExperimentExecutor  # noqa: E402
from forward.strategy import ForwardStrategy, MarketContext, OpenPosition  # noqa: E402
from src.broker.models import Direction, Resolution  # noqa: E402


@dataclass
class SessionState:
    day: _date | None = None
    prev_close: dict[str, float] = field(default_factory=dict)  # epic -> prior daily close (cached/day)
    open_px: dict[str, float] = field(default_factory=dict)
    or_levels: dict[str, tuple[float, float]] = field(default_factory=dict)  # epic -> (hi, lo)
    rvol: dict[str, float] = field(default_factory=dict)
    eligible: set[str] = field(default_factory=set)
    screened: bool = False

    def ensure_day(self, d: _date) -> None:
        if self.day != d:
            self.day = d
            self.prev_close.clear()
            self.open_px.clear()
            self.or_levels.clear()
            self.rvol.clear()
            self.eligible.clear()
            self.screened = False


@dataclass
class ExperimentScheduler:
    client: object
    executor: ExperimentExecutor
    strategies: list[ForwardStrategy]
    eod_flatten_utc: str = "20:45"
    screener: object | None = None                 # RvolScreener (optional; needed for ORB)
    session_open_utc: str = "13:30"
    or_window_min: int = 30
    watch_end_utc: str = "16:00"
    _state: SessionState = field(default_factory=SessionState, init=False, repr=False)

    @property
    def _registry(self) -> dict[str, ForwardStrategy]:
        return {s.name: s for s in self.strategies}

    async def _prev_close(self, epic: str, now: datetime) -> float | None:
        """Previous daily close, fetched LIVE from the broker (always fresh — no
        dependency on the local daily cache). prev_close = the most recent
        COMPLETED daily candle's close (excludes today's still-forming candle)."""
        try:
            candles = await self.client.get_historical_prices(
                epic, Resolution.DAY, max_candles=5)
        except Exception as e:  # noqa: BLE001 — any broker/parse error => skip epic
            logger.warning(f"[forward-lab] {epic} daily history fetch failed: {e} — skip")
            return None
        if not candles:
            return None
        today = now.date()
        completed = [c for c in candles if c.timestamp.date() < today] or candles
        return float(completed[-1].close)

    async def _mid(self, epic: str) -> float | None:
        d = await self.client.get_market_details(epic)
        snap = (d or {}).get("snapshot") or {}
        bid, offer = snap.get("bid"), snap.get("offer")
        if bid is None or offer is None:
            return None
        return (float(bid) + float(offer)) / 2.0

    def _session_close(self, now: datetime) -> datetime:
        t = self._hhmm(self.eod_flatten_utc)
        return datetime.combine(now.date(), t)

    def _hhmm(self, s: str) -> time:
        hh, mm = (int(x) for x in s.split(":"))
        return time(hh, mm, tzinfo=timezone.utc)

    def _in_window(self, now: datetime) -> bool:
        if now.weekday() >= 5:                       # Sat/Sun
            return False
        o, e = self._hhmm(self.session_open_utc), self._hhmm(self.watch_end_utc)
        return o <= now.timetz() < e

    async def _opening_range(self, epic: str, now: datetime) -> tuple[float, float] | None:
        """OR high/low from Capital.com MINUTE_5 bars in [open, open+or_window_min)."""
        try:
            candles = await self.client.get_historical_prices(
                epic, Resolution.MINUTE_5, max_candles=20)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[forward-lab] {epic} MINUTE_5 fetch failed: {e} — skip OR")
            return None
        o = self._hhmm(self.session_open_utc)
        open_min = o.hour * 60 + o.minute
        today = now.date()
        # Capital.com MINUTE_5 snapshotTime is the bar-START (probe-confirmed), so the
        # half-open [open, open+or_window_min) includes the 13:55 bar and excludes 14:00.
        win = [c for c in candles if c.timestamp.date() == today
               and open_min <= (c.timestamp.hour * 60 + c.timestamp.minute) < open_min + self.or_window_min]
        if not win:
            return None
        return max(c.high for c in win), min(c.low for c in win)

    async def entry_pass(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if not self._in_window(now):
            return
        self._state.ensure_day(now.date())
        session_date = now.date().isoformat()
        o = self._hhmm(self.session_open_utc)
        open_min = o.hour * 60 + o.minute
        or_ready = (now.hour * 60 + now.minute) >= (open_min + self.or_window_min)

        for strat in self.strategies:
            for epic in strat.universe():
                if epic not in self._state.prev_close:        # cache prev_close once/day/epic
                    pc = await self._prev_close(epic, now)
                    if pc is None:
                        continue
                    self._state.prev_close[epic] = pc
                prev_close = self._state.prev_close[epic]
                mid = await self._mid(epic)
                if mid is None:
                    continue
                self._state.open_px.setdefault(epic, mid)     # first in-window pass = open
                if strat.needs_opening_range:
                    if not or_ready:
                        continue
                    # screen once per day
                    if not self._state.screened:
                        if self.screener is None:
                            logger.warning("[forward-lab] ORB needs a screener but screener=None "
                                           "— ORB entries disabled this session")
                            self._state.screened = True
                        else:
                            pool = sorted({e for s in self.strategies
                                           if s.needs_opening_range for e in s.universe()})
                            res = self.screener.select(pool, now)
                            self._state.rvol.update(res.get("rvol", {}))
                            self._state.eligible = set(res.get("eligible", set()))
                            self._state.screened = True
                    if epic not in self._state.eligible:
                        continue
                    if epic not in self._state.or_levels:
                        orng = await self._opening_range(epic, now)
                        if orng is None:
                            continue
                        self._state.or_levels[epic] = orng
                    hi, lo = self._state.or_levels[epic]
                    ctx = MarketContext(epic=epic, prev_close=prev_close,
                                        today_open=self._state.open_px[epic], current_price=mid,
                                        now=now, session_close=self._session_close(now),
                                        or_high=hi, or_low=lo,
                                        rvol=self._state.rvol.get(epic))
                else:
                    ctx = MarketContext(epic=epic, prev_close=prev_close,
                                        today_open=self._state.open_px[epic], current_price=mid,
                                        now=now, session_close=self._session_close(now))
                await self.executor.try_enter(strat, ctx, session_date)

    async def on_session_open(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        session_date = now.date().isoformat()
        for strat in self.strategies:
            for epic in strat.universe():
                prev_close = await self._prev_close(epic, now)
                mid = await self._mid(epic)
                if prev_close is None or mid is None:
                    logger.warning(f"[forward-lab] missing price for {epic} — skip")
                    continue
                ctx = MarketContext(epic=epic, prev_close=prev_close, today_open=mid,
                                    current_price=mid, now=now,
                                    session_close=self._session_close(now))
                await self.executor.try_enter(strat, ctx, session_date)

    async def mark_pass(self, now: datetime | None = None) -> None:
        """Close positions whose exit_rule fires, then reconcile realized P&L
        from broker transaction history (no invented P&L)."""
        now = now or datetime.now(timezone.utc)
        if self.executor.dry_run:
            return
        open_rows = self.executor.ledger.list_open()
        if not open_rows:
            return
        registry = self._registry
        positions = {p.deal_id: p for p in await self.client.list_positions()}
        for row in open_rows:
            strat = registry.get(row["strategy"])
            if strat is None:
                logger.warning(f"[forward-lab] no strategy {row['strategy']!r} for open row — skip")
                continue
            mid = await self._mid(row["epic"])
            if mid is None:
                continue
            pos = OpenPosition(
                epic=row["epic"], direction=Direction(row["direction"]),
                entry=row["entry"], size=row["size"], stop_level=row["stop_level"],
                prev_close=0.0, today_open=row["entry"],
                opened_at=now, deal_id=row["deal_id"])
            ctx = MarketContext(epic=row["epic"], prev_close=0.0, today_open=row["entry"],
                                current_price=mid, now=now,
                                session_close=self._session_close(now))
            still_open = row["deal_id"] in positions
            should_exit = strat.exit_rule(pos, ctx)
            if still_open and should_exit:
                await self.client.close_position(row["deal_id"])
            if not still_open or should_exit:
                net, exitpx, reason = await self._realized(row, mid)
                self.executor.ledger.record_close(
                    deal_id=row["deal_id"], exit_price=exitpx, net_pnl=net,
                    closed_at=now.isoformat(), close_reason=reason)
                logger.info(f"[forward-lab] closed {row['epic']} ({row['strategy']}) "
                            f"net={net:+.2f} ({reason})")

    async def _realized(self, row: dict, fallback_px: float) -> tuple[float, float, str]:
        """Realized P&L from the broker TRADE transaction matching this row's dealId
        (broker truth). dealId is the deterministic match key for /history/transactions
        TRADE rows; an unmatched id (e.g. broker SL/TP rotation) stays PENDING_RECONCILE
        rather than guessing — no invented P&L."""
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=2)
        txns = await self.client.get_transaction_history(from_date, to_date)
        for t in txns:
            if (t.transaction_type or "").upper() != "TRADE":
                continue
            if t.deal_id and t.deal_id == row["deal_id"]:
                pnl = t.pl_value_in("USD")
                if pnl is not None:
                    return float(pnl), fallback_px, "BROKER_TRADE"
        return 0.0, fallback_px, "PENDING_RECONCILE"
