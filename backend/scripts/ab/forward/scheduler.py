from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone, date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

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
    eod_flatten_et: str = "16:45"
    screener: object | None = None                 # RvolScreener (optional; needed for ORB)
    session_open_et: str = "09:30"
    or_window_min: int = 30
    watch_end_et: str = "12:00"
    scan_pacing_s: float = 0.0   # sleep between per-epic broker GETs (10 req/s limit; wide universe)
    _state: SessionState = field(default_factory=SessionState, init=False, repr=False)

    @property
    def _registry(self) -> dict[str, ForwardStrategy]:
        return {s.name: s for s in self.strategies}

    async def _ensure_account(self) -> None:
        """Re-assert the experiment account. The broker session re-authenticates
        periodically and reverts to the API key's DEFAULT account, so a one-time
        startup switch is not enough — every pass must re-ensure before broker calls."""
        acct = self.executor.experiment_account_id
        if not acct:
            return
        try:
            if await self.client.get_active_account_id() != acct:
                await self.client.switch_account(acct)
        except Exception as e:  # noqa: BLE001 — never let an account-check hiccup kill the pass
            logger.error(f"[forward-lab] account re-assert failed: {e}")

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

    def _et_to_utc(self, d: _date, hhmm: str) -> datetime:
        """An ET wall-clock HH:MM on calendar date d, as a tz-aware UTC datetime (DST-correct)."""
        hh, mm = (int(x) for x in hhmm.split(":"))
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=_ET).astimezone(timezone.utc)

    def _session_close(self, now: datetime) -> datetime:
        return self._et_to_utc(now.date(), self.eod_flatten_et)

    def _in_window(self, now: datetime) -> bool:
        if now.weekday() >= 5:                       # Sat/Sun
            return False
        open_dt = self._et_to_utc(now.date(), self.session_open_et)
        end_dt = self._et_to_utc(now.date(), self.watch_end_et)
        return open_dt <= now < end_dt

    async def _opening_range(self, epic: str, now: datetime) -> tuple[float, float] | None:
        """OR high/low from Capital.com MINUTE_5 bars in [open, open+or_window_min).

        max_candles=60 (5h lookback) so the OR window is still covered when the
        first fetch happens late in the watch window (e.g. watchdog restart
        mid-session; 20 bars = 100min lost the window after ~open+70min)."""
        try:
            candles = await self.client.get_historical_prices(
                epic, Resolution.MINUTE_5, max_candles=60)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[forward-lab] {epic} MINUTE_5 fetch failed: {e} — skip OR")
            return None
        open_dt = self._et_to_utc(now.date(), self.session_open_et)
        end_dt = open_dt + timedelta(minutes=self.or_window_min)
        # Bar timestamps are the bar-START (probe-confirmed); half-open
        # [open_dt, end_dt) includes the last OR bar and excludes end_dt.
        # MUST filter on snapshotTimeUTC: snapshotTime is SERVER-LOCAL (UTC+2
        # in summer) and shifted every bar out of the UTC window -> OR never
        # formed, ORB never armed (live bug 2026-06-05, 3 days N=0).
        win = []
        for c in candles:
            raw = c.timestamp_utc or c.timestamp
            ts = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            if open_dt <= ts < end_dt:
                win.append(c)
        if not win:
            return None
        return max(c.high for c in win), min(c.low for c in win)

    async def _session_open_price(self, epic: str, now: datetime) -> float | None:
        """Today's cash-session OPEN = open of the first MINUTE_5 bar at/after the
        session open (09:30 ET), from a HISTORICAL bar. Fixed once that bar exists,
        so a mid-session restart reconstructs the TRUE open instead of
        re-snapshotting the current live mid into a false gap (the restart wart:
        gap = today_open/prev_close, and the 50%-fill exit target both derive from
        today_open).

        MUST filter on snapshotTimeUTC: snapshotTime is SERVER-LOCAL (UTC+2 in
        summer), so a local-time filter would let a pre-open bar pass the
        `>= open_dt` test and become the spurious 'earliest' bar. max_candles=60
        (5h) always covers back to the 09:30 open from anywhere in the entry
        window (mirrors _opening_range)."""
        try:
            candles = await self.client.get_historical_prices(
                epic, Resolution.MINUTE_5, max_candles=60)
        except Exception as e:  # noqa: BLE001 — any broker/parse error => caller falls back to mid
            logger.warning(f"[forward-lab] {epic} MINUTE_5 fetch failed (session-open): {e} — skip")
            return None
        if not candles:
            return None
        open_dt = self._et_to_utc(now.date(), self.session_open_et)
        best_ts: datetime | None = None
        best_open: float | None = None
        for c in candles:
            raw = c.timestamp_utc or c.timestamp
            ts = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            if ts < open_dt:
                continue
            if best_ts is None or ts < best_ts:
                best_ts, best_open = ts, float(c.open)
        return best_open

    async def entry_pass(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if not self._in_window(now):
            return
        self._state.ensure_day(now.date())
        await self._ensure_account()
        session_date = now.date().isoformat()
        open_dt = self._et_to_utc(now.date(), self.session_open_et)
        or_ready = now >= open_dt + timedelta(minutes=self.or_window_min)

        for strat in self.strategies:
            for epic in strat.universe():
                # ORB: gate on window + RVOL eligibility BEFORE any per-epic broker
                # GET — a wide universe must NOT fetch mid/OR for the ~95% of names
                # that aren't "in play" today (the screen is one cheap yfinance call,
                # not per-epic broker calls).
                if strat.needs_opening_range:
                    if not or_ready:
                        continue
                    if not self._state.screened:                 # screen once per day
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

                # prev_close — only strategies that use it (gap_fade), cached once/day.
                # ORB ignores it: skip the daily-close GET AND never gate the entry on
                # a failed/absent daily close.
                if strat.needs_prev_close:
                    if epic not in self._state.prev_close:
                        pc = await self._prev_close(epic, now)
                        if pc is None:
                            continue
                        self._state.prev_close[epic] = pc
                    prev_close = self._state.prev_close[epic]
                else:
                    prev_close = 0.0

                mid = await self._mid(epic)
                if mid is None:
                    continue
                if self.scan_pacing_s:                           # pace per-epic GETs (10 req/s limit)
                    await asyncio.sleep(self.scan_pacing_s)

                # today_open = the TRUE 09:30 cash-session open (historical M5 bar),
                # not the live mid — so a mid-session restart can't re-snapshot a
                # false gap. Only strategies that consume today_open pay the fetch
                # (ORB ignores it). Falls back to mid until the open bar exists.
                if epic not in self._state.open_px and strat.uses_today_open:
                    sop = await self._session_open_price(epic, now)
                    if sop is not None:
                        self._state.open_px[epic] = sop
                today_open = self._state.open_px.get(epic, mid)

                if strat.needs_opening_range:
                    if epic not in self._state.or_levels:
                        orng = await self._opening_range(epic, now)
                        if orng is None:
                            continue
                        self._state.or_levels[epic] = orng
                    hi, lo = self._state.or_levels[epic]
                    ctx = MarketContext(epic=epic, prev_close=prev_close,
                                        today_open=today_open, current_price=mid,
                                        now=now, session_close=self._session_close(now),
                                        or_high=hi, or_low=lo,
                                        rvol=self._state.rvol.get(epic))
                else:
                    ctx = MarketContext(epic=epic, prev_close=prev_close,
                                        today_open=today_open, current_price=mid,
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

    def _match_broker_position(self, row: dict, positions: list):
        """Find the live broker position for a ledger row WITHOUT relying on exact
        dealId equality (Capital.com rotates the open-position dealId vs the
        create-confirmation dealId we stored). Match on epic + direction + entry≈level."""
        entry = float(row["entry"])
        tol = max(1e-6, abs(entry) * 1e-3)   # 0.1% of entry price
        for p in positions:
            if p.epic != row["epic"]:
                continue
            if p.direction.value != row["direction"]:   # p.direction is a Direction enum; row["direction"] is "BUY"/"SELL"
                continue
            if abs(float(p.level) - entry) <= tol:
                return p
        return None

    async def mark_pass(self, now: datetime | None = None) -> None:
        """Close positions whose exit_rule fires, then reconcile realized P&L
        from broker transaction history (no invented P&L)."""
        now = now or datetime.now(timezone.utc)
        if self.executor.dry_run:
            return
        open_rows = self.executor.ledger.list_open()
        if not open_rows:
            return
        await self._ensure_account()
        registry = self._registry
        broker_positions = await self.client.list_positions()
        for row in open_rows:
            strat = registry.get(row["strategy"])
            if strat is None:
                logger.warning(f"[forward-lab] no strategy {row['strategy']!r} for open row — skip")
                continue
            mid = await self._mid(row["epic"])
            if mid is None:
                continue
            matched = self._match_broker_position(row, broker_positions)
            still_open = matched is not None
            pos = OpenPosition(
                epic=row["epic"], direction=Direction(row["direction"]),
                entry=row["entry"], size=row["size"], stop_level=row["stop_level"],
                prev_close=row["prev_close"] if row.get("prev_close") is not None else 0.0,
                today_open=row["today_open"] if row.get("today_open") is not None else row["entry"],
                opened_at=now, deal_id=row["deal_id"])
            # ctx carries only current_price/now/session_close for exit_rule; the gap history lives on `pos` above
            ctx = MarketContext(epic=row["epic"], prev_close=0.0, today_open=row["entry"],
                                current_price=mid, now=now,
                                session_close=self._session_close(now))
            should_exit = strat.exit_rule(pos, ctx)
            if still_open and should_exit:
                await self.client.close_position(matched.deal_id)   # broker's CURRENT dealId, not the stored one
                logger.info(f"[forward-lab] close sent for {row['epic']} ({row['strategy']}) "
                            "— reconcile deferred to next pass (broker history lag)")
                continue
            if not still_open:
                net, exitpx, reason = await self._realized(row, mid)
                if reason == "PENDING_RECONCILE" and self._row_age_hours(row, now) < 24:
                    logger.info(f"[forward-lab] {row['epic']} close not in broker history yet "
                                "— retrying next pass")
                    continue
                self.executor.ledger.record_close(
                    deal_id=row["deal_id"], exit_price=exitpx, net_pnl=net,
                    closed_at=now.isoformat(), close_reason=reason)
                logger.info(f"[forward-lab] closed {row['epic']} ({row['strategy']}) "
                            f"net={net:+.2f} ({reason})")

    def _row_age_hours(self, row: dict, now: datetime) -> float:
        """Hours since the row was opened; +inf when opened_at is unparseable so
        an unparseable row can still be finalized (zombie guard, not a retry loop)."""
        opened = self._parse_dt(row.get("opened_at"))
        if opened is None:
            return float("inf")
        return (now - opened).total_seconds() / 3600.0

    async def _realized(self, row: dict, fallback_px: float) -> tuple[float, float, str]:
        """Realized P&L from the broker (broker truth, no invented P&L).

        Tier 1: TRADE row whose dealId == our position deal_id — the case for
                OUR DELETE-initiated closes (EOD flatten).
        Tier 2: broker-initiated SL/TP closes rotate the dealId, so link via
                /history/activity: a close event (is_close_event) for this epic
                whose details.openPrice == our entry (and date >= opened_at)
                carries the close-side dealId, which matches the TRADE row for P&L.
        Else:   PENDING_RECONCILE (no guess, no invented P&L)."""
        now = datetime.now(timezone.utc)
        to_date = now - timedelta(seconds=60)   # broker rejects future `to` (error.invalid.daterange); clamp for clock drift
        opened = self._parse_dt(row.get("opened_at"))
        from_date = (opened - timedelta(hours=1)) if opened else (to_date - timedelta(days=1))
        txns = await self.client.get_transaction_history(from_date, to_date)
        trades = [t for t in txns if (t.transaction_type or "").upper() == "TRADE"]

        # Tier 1 — exact dealId (our own close)
        for t in trades:
            if t.deal_id and t.deal_id == row["deal_id"]:
                pnl = t.pl_value_in("USD")
                if pnl is not None:
                    return float(pnl), fallback_px, "BROKER_TRADE"

        # Tier 2 — broker-initiated close: link via activity (rotated dealId)
        entry = row.get("entry")
        opened_at = self._parse_dt(row.get("opened_at"))
        if entry is not None:
            try:
                acts = await self.client.get_activity_history(from_date, to_date)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[forward-lab] activity fetch failed for {row['epic']}: {e}")
                acts = []
            tol = max(1e-6, abs(float(entry)) * 1e-4)
            for a in acts:
                if not a.is_close_event() or a.epic != row["epic"]:
                    continue
                op = a.details.open_price
                if op is None or abs(float(op) - float(entry)) > tol:
                    continue
                if opened_at is not None:
                    a_date = a.date if a.date.tzinfo else a.date.replace(tzinfo=timezone.utc)
                    if a_date < opened_at:
                        continue
                for t in trades:
                    if t.deal_id and t.deal_id == a.deal_id:
                        pnl = t.pl_value_in("USD")
                        if pnl is not None:
                            return float(pnl), fallback_px, "BROKER_ACTIVITY"
        return 0.0, fallback_px, "PENDING_RECONCILE"

    @staticmethod
    def _parse_dt(s: object) -> datetime | None:
        if not s or not isinstance(s, str):
            return None
        try:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
