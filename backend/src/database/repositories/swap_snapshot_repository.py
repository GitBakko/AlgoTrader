"""Repository for the `swap_daily_snapshots` table.

Stores one row per (epic, date) with the broker overnight rate and the
aggregate OPEN-position notional at snapshot time. Dashboard v2
/swap-accum reads from here to render the last N days of real swap
exposure instead of extrapolating today's rate across history.

See migration ``b2c7d9e8f3a1``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import SwapDailySnapshot


class SwapSnapshotRepository:
    """CRUD layer for `swap_daily_snapshots`."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, epic: str, snapshot_date: date) -> SwapDailySnapshot | None:
        stmt = select(SwapDailySnapshot).where(
            and_(
                SwapDailySnapshot.epic == epic,
                SwapDailySnapshot.snapshot_date == snapshot_date,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent(self, epic: str, days: int) -> list[SwapDailySnapshot]:
        """Return rows for ``epic`` within the last ``days`` calendar days
        (inclusive of today), ordered by snapshot_date ascending.
        """
        cutoff = date.today() - timedelta(days=max(days - 1, 0))
        stmt = (
            select(SwapDailySnapshot)
            .where(
                and_(
                    SwapDailySnapshot.epic == epic,
                    SwapDailySnapshot.snapshot_date >= cutoff,
                )
            )
            .order_by(SwapDailySnapshot.snapshot_date.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        epic: str,
        snapshot_date: date,
        long_rate_pct: float | None,
        short_rate_pct: float | None,
        currency: str | None,
        source: str,
        direction: str,
        notional: float,
        swap_realized: float | None = None,
    ) -> SwapDailySnapshot:
        """Insert or update the row for (epic, snapshot_date)."""
        existing = await self.get(epic, snapshot_date)
        if existing is not None:
            existing.long_rate_pct = long_rate_pct
            existing.short_rate_pct = short_rate_pct
            existing.currency = currency
            existing.source = source
            existing.direction = direction
            existing.notional = notional
            existing.swap_realized = swap_realized
            await self.session.flush()
            return existing

        row = SwapDailySnapshot(
            epic=epic,
            snapshot_date=snapshot_date,
            long_rate_pct=long_rate_pct,
            short_rate_pct=short_rate_pct,
            currency=currency,
            source=source,
            direction=direction,
            notional=notional,
            swap_realized=swap_realized,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.session.add(row)
        await self.session.flush()
        return row
