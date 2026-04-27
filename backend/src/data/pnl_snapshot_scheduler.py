"""60s P&L snapshot scheduler for the Paper Trading v2 cockpit.

Captures the current Paper Trading state every minute and persists it to
``paper_pnl_snapshots`` (global figures) and ``position_pnl_snapshots``
(per open position). The Paper Trading v2 frontend reads these tables
to render the KPI strip and position-card charts with real history
instead of synthetic data.

Lifecycle:
- ``start()``     → registers the 60s job + a 04:30 UTC nightly prune.
- ``stop()``      → shutdown.

The job is intentionally tolerant: any single tick can fail silently
without taking down the rest of the scheduler. Errors are logged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from src.database.models import PositionPnlSnapshot
from src.database.repositories.pnl_snapshot_repository import (
    PaperPnlSnapshotRepository,
    PositionPnlSnapshotRepository,
)
from src.database.repositories.position_repository import PositionRepository

DbSessionFactory = Callable[[], Any]
"""Callable that returns an async context manager yielding ``AsyncSession``."""


class PnlSnapshotScheduler:
    """APScheduler-based 60s P&L recorder."""

    SNAPSHOT_INTERVAL_SECONDS = 60
    PRUNE_RETENTION_DAYS = 7

    def __init__(
        self,
        *,
        db_session_factory: DbSessionFactory | None,
        get_paper_loop: Callable[[], Any | None],
        get_broker_client: Callable[[], Any | None],
    ) -> None:
        self._db_session_factory = db_session_factory
        self._get_paper_loop = get_paper_loop
        self._get_broker_client = get_broker_client
        self._scheduler = AsyncIOScheduler()
        self._tick_count = 0

    def start(self) -> None:
        if self._db_session_factory is None:
            logger.warning(
                "PnlSnapshotScheduler skipped: no db_session_factory available"
            )
            return
        self._scheduler.add_job(
            self._safe_take_snapshot,
            IntervalTrigger(seconds=self.SNAPSHOT_INTERVAL_SECONDS),
            id="paper_pnl_snapshot",
            name="Paper Trading P&L 60s snapshot",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._safe_prune,
            CronTrigger(hour=4, minute=30),
            id="paper_pnl_snapshot_prune",
            name="Paper Trading P&L snapshot prune",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "P&L snapshot scheduler started "
            f"(interval={self.SNAPSHOT_INTERVAL_SECONDS}s, "
            f"retention={self.PRUNE_RETENTION_DAYS}d)"
        )

    def stop(self) -> None:
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:
            pass

    # ── Snapshot tick ────────────────────────────────────────────────

    async def _safe_take_snapshot(self) -> None:
        try:
            await self._take_snapshot()
        except Exception as exc:
            logger.warning(f"P&L snapshot tick failed: {exc}")

    async def _take_snapshot(self) -> None:
        if self._db_session_factory is None:
            return

        captured_at = datetime.now(UTC)
        paper_loop = self._get_paper_loop()
        broker_client = self._get_broker_client()

        # Pull live broker positions; fall back to paper_loop view when broker
        # is unreachable so we always record SOMETHING during outages.
        positions = await self._fetch_positions(paper_loop, broker_client)

        # Aggregate the global figures.
        pnl_open = 0.0
        for pos in positions:
            upl = self._position_upl(pos)
            if upl is not None:
                pnl_open += float(upl)

        equity = self._extract_equity(broker_client, paper_loop)
        currency = self._extract_currency(broker_client)

        async with self._db_session_factory() as session:
            today_start = captured_at.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            position_repo = PositionRepository(session)
            try:
                closed_today = await position_repo.get_closed_in_period(
                    today_start,
                    captured_at,
                )
                pnl_today = sum(
                    float(p.profit_loss)
                    for p in closed_today
                    if p.profit_loss is not None
                )
            except Exception as exc:
                logger.debug(f"today realized lookup failed: {exc}")
                pnl_today = 0.0

            paper_repo = PaperPnlSnapshotRepository(session)
            await paper_repo.insert(
                captured_at=captured_at,
                pnl_open=round(pnl_open, 6),
                pnl_today=round(pnl_today, 6),
                equity=round(equity, 6) if equity is not None else None,
                open_count=len(positions),
                currency=currency,
            )

            position_rows: list[PositionPnlSnapshot] = []
            for pos in positions:
                deal_id = self._position_deal_id(pos)
                if not deal_id:
                    continue
                price = self._position_current_price(pos)
                upl = self._position_upl(pos)
                entry = self._position_entry(pos)
                pnl_pct = 0.0
                if entry and price:
                    direction = self._position_direction(pos)
                    base = (price - entry) / entry * 100.0
                    pnl_pct = base if direction == "BUY" else -base
                position_rows.append(
                    PositionPnlSnapshot(
                        deal_id=str(deal_id),
                        epic=str(self._position_epic(pos) or ""),
                        captured_at=captured_at,
                        pnl=float(upl) if upl is not None else 0.0,
                        pnl_pct=round(pnl_pct, 6),
                        current_price=float(price) if price is not None else 0.0,
                    )
                )
            if position_rows:
                position_pnl_repo = PositionPnlSnapshotRepository(session)
                await position_pnl_repo.insert_many(position_rows)

            await session.commit()

        self._tick_count += 1
        if self._tick_count % 30 == 1:
            logger.debug(
                "P&L snapshot recorded "
                f"pnl_open={pnl_open:.2f} pnl_today={pnl_today:.2f} "
                f"open={len(positions)}"
            )

    # ── Prune ────────────────────────────────────────────────────────

    async def _safe_prune(self) -> None:
        try:
            await self._prune()
        except Exception as exc:
            logger.warning(f"P&L snapshot prune failed: {exc}")

    async def _prune(self) -> None:
        if self._db_session_factory is None:
            return
        async with self._db_session_factory() as session:
            paper_repo = PaperPnlSnapshotRepository(session)
            position_repo = PositionPnlSnapshotRepository(session)
            removed_paper = await paper_repo.prune_older_than(
                days=self.PRUNE_RETENTION_DAYS
            )
            removed_position = await position_repo.prune_older_than(
                days=self.PRUNE_RETENTION_DAYS
            )
            await session.commit()
            logger.info(
                "P&L snapshot prune: "
                f"paper={removed_paper} positions={removed_position}"
            )

    # ── Position field accessors (broker model OR dict) ──────────────

    @staticmethod
    def _position_upl(pos: Any) -> float | None:
        if isinstance(pos, dict):
            return pos.get("upl")
        return getattr(pos, "upl", None)

    @staticmethod
    def _position_deal_id(pos: Any) -> str | None:
        if isinstance(pos, dict):
            return pos.get("deal_id") or pos.get("dealId")
        return getattr(pos, "deal_id", None)

    @staticmethod
    def _position_epic(pos: Any) -> str | None:
        if isinstance(pos, dict):
            return pos.get("epic")
        return getattr(pos, "epic", None)

    @staticmethod
    def _position_current_price(pos: Any) -> float | None:
        if isinstance(pos, dict):
            for key in ("current_price", "currentPrice", "level", "price"):
                value = pos.get(key)
                if value is not None:
                    return float(value)
            return None
        for attr in ("current_price", "level"):
            value = getattr(pos, attr, None)
            if value is not None:
                return float(value)
        return None

    @staticmethod
    def _position_entry(pos: Any) -> float | None:
        if isinstance(pos, dict):
            return pos.get("level")
        return getattr(pos, "level", None)

    @staticmethod
    def _position_direction(pos: Any) -> str:
        if isinstance(pos, dict):
            return str(pos.get("direction") or "").upper()
        return str(getattr(pos, "direction", "") or "").upper()

    # ── Side helpers ─────────────────────────────────────────────────

    @staticmethod
    async def _fetch_positions(
        paper_loop: Any | None, broker_client: Any | None
    ) -> list[Any]:
        """Try broker first (authoritative UPL) then paper_loop fallback."""
        if broker_client is not None:
            try:
                positions = await broker_client.list_positions()
                if positions is not None:
                    return list(positions)
            except Exception as exc:
                logger.debug(f"broker list_positions failed: {exc}")
        if paper_loop is not None:
            try:
                local = paper_loop.get_paper_positions()
                return list(local or [])
            except Exception as exc:
                logger.debug(f"paper_loop.get_paper_positions failed: {exc}")
        return []

    @staticmethod
    def _extract_equity(
        broker_client: Any | None, paper_loop: Any | None
    ) -> float | None:
        if paper_loop is not None:
            try:
                rm = getattr(paper_loop, "risk_manager", None)
                if rm is not None:
                    monitor = getattr(rm, "drawdown_monitor", None)
                    if monitor is not None:
                        state = getattr(monitor, "state", None)
                        if state is not None:
                            value = getattr(state, "current_equity", None)
                            if value is not None:
                                return float(value)
            except Exception:
                pass
        return None

    @staticmethod
    def _extract_currency(broker_client: Any | None) -> str | None:
        # Cheap path — broker accounts are not awaitable from a sync stub here
        # and we deliberately skip the network round-trip every 60s. The API
        # endpoint resolves the live currency on read instead.
        return None
