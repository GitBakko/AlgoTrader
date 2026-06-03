from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[3]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forward.executor import ExperimentExecutor  # noqa: E402
from forward.strategy import ForwardStrategy, MarketContext, OpenPosition  # noqa: E402
from src.broker.models import Direction, Resolution  # noqa: E402


@dataclass
class ExperimentScheduler:
    client: object
    executor: ExperimentExecutor
    strategies: list[ForwardStrategy]
    eod_flatten_utc: str = "20:45"

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
        hh, mm = (int(x) for x in self.eod_flatten_utc.split(":"))
        return datetime.combine(now.date(), time(hh, mm, tzinfo=timezone.utc))

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
        from datetime import timedelta
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
