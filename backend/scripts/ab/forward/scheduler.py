from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[3]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.storage import ParquetStorageManager  # noqa: E402
from forward.executor import ExperimentExecutor  # noqa: E402
from forward.strategy import ForwardStrategy, MarketContext, OpenPosition  # noqa: E402
from src.broker.models import Direction  # noqa: E402


@dataclass
class ExperimentScheduler:
    client: object
    executor: ExperimentExecutor
    strategy: ForwardStrategy
    eod_flatten_utc: str = "20:45"
    _storage: ParquetStorageManager | None = None

    def __post_init__(self):
        self._storage = self._storage or ParquetStorageManager()

    async def _prev_close(self, epic: str) -> float | None:
        df = self._storage.read_candles(epic, "1d")
        if df.is_empty():
            return None
        return float(df.select("close").to_series().to_list()[-1])

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
        for epic in self.strategy.universe():
            prev_close = await self._prev_close(epic)
            mid = await self._mid(epic)
            if prev_close is None or mid is None:
                logger.warning(f"[forward-lab] missing price for {epic} — skip")
                continue
            ctx = MarketContext(epic=epic, prev_close=prev_close, today_open=mid,
                                current_price=mid, now=now,
                                session_close=self._session_close(now))
            await self.executor.try_enter(self.strategy, ctx, session_date)

    async def mark_pass(self, now: datetime | None = None) -> None:
        """Close positions whose exit_rule fires, then reconcile realized P&L
        from broker transaction history (no invented P&L)."""
        now = now or datetime.now(timezone.utc)
        if self.executor.dry_run:
            return
        open_rows = self.executor.ledger.list_open()
        if not open_rows:
            return
        positions = {p.deal_id: p for p in await self.client.list_positions()}
        for row in open_rows:
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
            should_exit = self.strategy.exit_rule(pos, ctx)
            if still_open and should_exit:
                await self.client.close_position(row["deal_id"])
            if not still_open or should_exit:
                net, exitpx, reason = await self._realized(row, mid)
                self.executor.ledger.record_close(
                    deal_id=row["deal_id"], exit_price=exitpx, net_pnl=net,
                    closed_at=now.isoformat(), close_reason=reason)
                logger.info(f"[forward-lab] closed {row['epic']} net={net:+.2f} ({reason})")

    async def _realized(self, row: dict, fallback_px: float) -> tuple[float, float, str]:
        """Realized P&L from the latest TRADE transaction for this epic (broker truth)."""
        from src.broker.client import CapitalComClient
        broker_epic = (CapitalComClient._to_broker_epic(row["epic"])
                       if hasattr(self.client, "_to_broker_epic") else row["epic"])
        from datetime import timedelta
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=2)
        txns = await self.client.get_transaction_history(from_date, to_date)
        best = None
        for t in txns:
            if (t.transaction_type or "").upper() != "TRADE":
                continue
            if t.instrument_name in (row["epic"], broker_epic):
                best = t
                break
        if best is not None:
            pnl = best.pl_value_in("USD")
            if pnl is not None:
                return float(pnl), fallback_px, "BROKER_TRADE"
        return 0.0, fallback_px, "PENDING_RECONCILE"
