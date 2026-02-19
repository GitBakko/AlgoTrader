"""
Position repository with trading-specific queries.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Position
from src.database.repository import BaseRepository


class PositionRepository(BaseRepository[Position]):
    """Repository for Position model with custom queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Position, session)

    async def get_open_positions(self, limit: int = 500) -> list[Position]:
        """
        Get all open positions.

        Args:
            limit: Maximum positions to return (default: 500)

        Returns:
            List of open positions
        """
        result = await self.session.execute(
            select(Position)
            .where(Position.status == "OPEN")
            .order_by(Position.opened_at.desc())
            .limit(limit)
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

    async def get_by_epic(self, epic: str, status: str | None = None, limit: int = 500) -> list[Position]:
        """
        Get positions by epic (asset).

        Args:
            epic: Asset epic code (e.g., "GOLD", "BITCOIN")
            status: Optional status filter (OPEN, CLOSED, CANCELLED)
            limit: Maximum positions to return (default: 500)

        Returns:
            List of positions
        """
        query = select(Position).where(Position.epic == epic)
        if status:
            query = query.where(Position.status == status)
        query = query.order_by(Position.opened_at.desc()).limit(limit)

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

    async def mark_as_closed(self, deal_id: str, close_reason: str = "EXTERNAL") -> Position | None:
        """
        Mark a position as closed without P&L (for stale position cleanup).

        Used by state recovery when a position exists in DB but not in broker
        (position was closed externally or is stale).

        Args:
            deal_id: Capital.com deal ID
            close_reason: Reason for closing (default: EXTERNAL)

        Returns:
            Updated position or None if not found
        """
        position = await self.get_by_deal_id(deal_id)
        if not position or position.status != "OPEN":
            return None

        position.status = "CLOSED"
        position.closed_at = datetime.now(timezone.utc)
        position.close_reason = close_reason

        await self.session.flush()
        await self.session.refresh(position)
        return position

    async def update_size(self, deal_id: str, new_size: float) -> Position | None:
        """
        Update position size (for reconciliation with broker).

        Used by state recovery when broker reports different size than DB.
        Broker data is considered authoritative.

        Args:
            deal_id: Capital.com deal ID
            new_size: New position size from broker

        Returns:
            Updated position or None if not found
        """
        position = await self.get_by_deal_id(deal_id)
        if not position:
            return None

        position.size = new_size

        await self.session.flush()
        await self.session.refresh(position)
        return position

    async def get_closed_positions(
        self,
        limit: int = 50,
        offset: int = 0,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        close_reason: str | None = None,
        epic: str | None = None,
    ) -> tuple[list[Position], int]:
        """
        Get closed positions with filters and pagination.

        Returns:
            Tuple of (positions list, total count)
        """
        base = select(Position).where(Position.status == "CLOSED")
        count_q = select(func.count(Position.id)).where(Position.status == "CLOSED")

        if date_from:
            base = base.where(Position.closed_at >= date_from)
            count_q = count_q.where(Position.closed_at >= date_from)
        if date_to:
            base = base.where(Position.closed_at <= date_to)
            count_q = count_q.where(Position.closed_at <= date_to)
        if close_reason:
            base = base.where(Position.close_reason == close_reason)
            count_q = count_q.where(Position.close_reason == close_reason)
        if epic:
            base = base.where(Position.epic == epic)
            count_q = count_q.where(Position.epic == epic)

        total = (await self.session.execute(count_q)).scalar() or 0
        query = base.order_by(Position.closed_at.desc()).offset(offset).limit(limit)
        positions = list((await self.session.execute(query)).scalars().all())

        return positions, total

    async def get_performance_stats(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        epic: str | None = None,
    ) -> dict:
        """
        Get comprehensive performance statistics from closed positions.

        Returns:
            Dict with trade_count, win/loss stats, profit_factor, pnl_by_epic, equity_curve
        """
        query = (
            select(Position)
            .where(Position.status == "CLOSED")
            .where(Position.profit_loss.is_not(None))
        )
        if date_from:
            query = query.where(Position.closed_at >= date_from)
        if date_to:
            query = query.where(Position.closed_at <= date_to)
        if epic:
            query = query.where(Position.epic == epic)
        query = query.order_by(Position.closed_at.asc())

        positions = list((await self.session.execute(query)).scalars().all())
        if not positions:
            return {"trade_count": 0}

        pnls = [float(p.profit_loss) for p in positions]
        wins = [v for v in pnls if v > 0]
        losses = [v for v in pnls if v <= 0]

        # Max consecutive wins/losses
        max_cw = max_cl = cur_w = cur_l = 0
        for pnl in pnls:
            if pnl > 0:
                cur_w += 1
                cur_l = 0
                max_cw = max(max_cw, cur_w)
            else:
                cur_l += 1
                cur_w = 0
                max_cl = max(max_cl, cur_l)

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else float("inf") if gross_profit > 0
            else 0
        )

        # P&L by epic
        pnl_by_epic: dict[str, float] = {}
        for p in positions:
            pnl_by_epic[p.epic] = pnl_by_epic.get(p.epic, 0) + float(p.profit_loss)

        # Equity curve (cumulative P&L over time)
        equity_points: list[dict] = []
        cumulative = 0.0
        for p in positions:
            cumulative += float(p.profit_loss)
            if p.closed_at:
                equity_points.append({
                    "date": p.closed_at.strftime("%Y-%m-%d"),
                    "value": round(cumulative, 2),
                })

        return {
            "trade_count": len(pnls),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": len(wins) / len(pnls) if pnls else 0,
            "total_pnl": round(sum(pnls), 2),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.99,
            "max_consecutive_wins": max_cw,
            "max_consecutive_losses": max_cl,
            "best_trade": round(max(pnls), 2) if pnls else 0,
            "worst_trade": round(min(pnls), 2) if pnls else 0,
            "pnl_by_epic": {k: round(v, 2) for k, v in pnl_by_epic.items()},
            "equity_curve": equity_points,
        }
