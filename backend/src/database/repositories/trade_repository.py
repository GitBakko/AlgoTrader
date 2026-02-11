"""
Trade repository with audit trail queries.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Trade
from src.database.repository import BaseRepository


class TradeRepository(BaseRepository[Trade]):
    """Repository for Trade model with audit-specific queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Trade, session)

    async def get_by_position(self, position_id: int) -> list[Trade]:
        """Get all trades for a position (audit trail)."""
        result = await self.session.execute(
            select(Trade)
            .where(Trade.position_id == position_id)
            .order_by(Trade.executed_at.asc())
        )
        return list(result.scalars().all())

    async def get_recent_trades(self, hours: int = 24) -> list[Trade]:
        """Get trades executed in the last N hours."""
        from datetime import timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.session.execute(
            select(Trade)
            .where(Trade.executed_at >= cutoff)
            .order_by(Trade.executed_at.desc())
        )
        return list(result.scalars().all())

    async def get_trades_for_audit(
        self, start: datetime, end: datetime
    ) -> list[Trade]:
        """Get trades in a date range for audit purposes."""
        result = await self.session.execute(
            select(Trade)
            .where(Trade.executed_at >= start)
            .where(Trade.executed_at <= end)
            .order_by(Trade.executed_at.asc())
        )
        return list(result.scalars().all())

    async def get_pnl_summary(self, start: datetime, end: datetime) -> dict:
        """
        Get P&L summary for trades in a date range.

        Returns:
            Dict with total_pnl, trade_count, avg_pnl
        """
        result = await self.session.execute(
            select(
                func.sum(Trade.profit_loss).label("total_pnl"),
                func.count(Trade.id).label("trade_count"),
                func.avg(Trade.profit_loss).label("avg_pnl"),
            )
            .where(Trade.executed_at >= start)
            .where(Trade.executed_at <= end)
            .where(Trade.trade_type == "CLOSE")
        )
        row = result.one()
        return {
            "total_pnl": float(row.total_pnl or 0),
            "trade_count": int(row.trade_count or 0),
            "avg_pnl": float(row.avg_pnl or 0),
        }
