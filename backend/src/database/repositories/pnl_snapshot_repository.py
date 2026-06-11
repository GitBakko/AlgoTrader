"""Repositories for the paper-trading P&L snapshot tables.

`paper_pnl_snapshots` carries one row per 60s tick with the global P&L
state (open + today realized + equity + open_count + currency).
`position_pnl_snapshots` carries one row per 60s tick PER open position
with its individual pnl, pct and current price.

The frontend reads these to render real history charts (KPI strip
sparklines and per-position price chart) instead of fabricating data.

See migration ``c3d8e9f0a1b2``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PaperPnlSnapshot, PositionPnlSnapshot


def _utc_naive(dt: datetime) -> datetime:
    """Strip timezone info so asyncpg accepts the value on TIMESTAMP cols.

    Mirrors the convention applied across the codebase per CLAUDE.md.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


class PaperPnlSnapshotRepository:
    """CRUD layer for `paper_pnl_snapshots`."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(
        self,
        *,
        captured_at: datetime,
        pnl_open: float,
        pnl_today: float,
        equity: float | None,
        open_count: int,
        currency: str | None,
    ) -> None:
        row = PaperPnlSnapshot(
            captured_at=_utc_naive(captured_at),
            pnl_open=pnl_open,
            pnl_today=pnl_today,
            equity=equity,
            open_count=open_count,
            currency=currency,
        )
        self.session.add(row)
        await self.session.flush()

    async def list_recent(self, *, minutes: int) -> list[PaperPnlSnapshot]:
        """Return rows captured within the last ``minutes`` minutes,
        ordered ascending by ``captured_at`` (oldest first) — chart-ready.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=max(minutes, 1))
        stmt = (
            select(PaperPnlSnapshot)
            .where(PaperPnlSnapshot.captured_at >= _utc_naive(cutoff))
            .order_by(PaperPnlSnapshot.captured_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def prune_older_than(self, *, days: int) -> int:
        """Delete rows older than ``days`` days. Returns row count."""
        cutoff = datetime.now(UTC) - timedelta(days=max(days, 1))
        stmt = delete(PaperPnlSnapshot).where(PaperPnlSnapshot.captured_at < _utc_naive(cutoff))
        result = await self.session.execute(stmt)
        return result.rowcount or 0


class PositionPnlSnapshotRepository:
    """CRUD layer for `position_pnl_snapshots`."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert_many(self, rows: list[PositionPnlSnapshot]) -> None:
        if not rows:
            return
        for row in rows:
            row.captured_at = _utc_naive(row.captured_at)
        self.session.add_all(rows)
        await self.session.flush()

    async def list_for_deal(
        self,
        *,
        deal_id: str,
        minutes: int,
    ) -> list[PositionPnlSnapshot]:
        """Rows for a single deal within the last ``minutes``, oldest first."""
        cutoff = datetime.now(UTC) - timedelta(minutes=max(minutes, 1))
        stmt = (
            select(PositionPnlSnapshot)
            .where(
                and_(
                    PositionPnlSnapshot.deal_id == deal_id,
                    PositionPnlSnapshot.captured_at >= _utc_naive(cutoff),
                )
            )
            .order_by(PositionPnlSnapshot.captured_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def prune_older_than(self, *, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=max(days, 1))
        stmt = delete(PositionPnlSnapshot).where(
            PositionPnlSnapshot.captured_at < _utc_naive(cutoff)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
