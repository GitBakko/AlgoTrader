"""
Position repository with trading-specific queries.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Position
from src.database.repository import BaseRepository


class PositionRepository(BaseRepository[Position]):
    """Repository for Position model with custom queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Position, session)

    async def get_open_positions(self) -> list[Position]:
        """
        Get all open positions.

        Returns:
            List of open positions
        """
        result = await self.session.execute(
            select(Position).where(Position.status == "OPEN").order_by(Position.opened_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_deal_id(self, deal_id: str) -> Position | None:
        """
        Get position by Capital.com deal ID.

        Args:
            deal_id: Capital.com deal ID

        Returns:
            Position or None if not found
        """
        result = await self.session.execute(
            select(Position).where(Position.deal_id == deal_id)
        )
        return result.scalar_one_or_none()

    async def get_by_epic(self, epic: str, status: str | None = None) -> list[Position]:
        """
        Get positions by epic (asset).

        Args:
            epic: Asset epic code (e.g., "GOLD", "BITCOIN")
            status: Optional status filter (OPEN, CLOSED, CANCELLED)

        Returns:
            List of positions
        """
        query = select(Position).where(Position.epic == epic)
        if status:
            query = query.where(Position.status == status)
        query = query.order_by(Position.opened_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_strategy(self, strategy_id: int) -> list[Position]:
        """
        Get positions by strategy ID.

        Args:
            strategy_id: Strategy ID

        Returns:
            List of positions
        """
        result = await self.session.execute(
            select(Position)
            .where(Position.strategy_id == strategy_id)
            .order_by(Position.opened_at.desc())
        )
        return list(result.scalars().all())

    async def get_closed_in_period(
        self, start_date: datetime, end_date: datetime
    ) -> list[Position]:
        """
        Get positions closed in a date range.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of closed positions
        """
        result = await self.session.execute(
            select(Position)
            .where(Position.status == "CLOSED")
            .where(Position.closed_at >= start_date)
            .where(Position.closed_at <= end_date)
            .order_by(Position.closed_at.desc())
        )
        return list(result.scalars().all())

    async def close_position(
        self, deal_id: str, close_price: float, profit_loss: float, close_reason: str
    ) -> Position | None:
        """
        Close an open position.

        Args:
            deal_id: Capital.com deal ID
            close_price: Closing price
            profit_loss: Realized P&L
            close_reason: Reason for closing (SL, TP, MANUAL, EXPIRED)

        Returns:
            Updated position or None if not found
        """
        position = await self.get_by_deal_id(deal_id)
        if not position or position.status != "OPEN":
            return None

        position.status = "CLOSED"
        position.current_price = close_price
        position.profit_loss = profit_loss
        position.closed_at = datetime.now(timezone.utc)
        position.close_reason = close_reason

        await self.session.flush()
        await self.session.refresh(position)
        return position
