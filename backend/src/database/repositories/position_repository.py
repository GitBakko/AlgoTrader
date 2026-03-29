"""
Position repository with trading-specific queries.
"""

from datetime import UTC, datetime

import numpy as np
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
        result = await self.session.execute(select(Position).where(Position.deal_id == deal_id))
        return result.scalar_one_or_none()

    async def get_by_epic(
        self, epic: str, status: str | None = None, limit: int = 500
    ) -> list[Position]:
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
        naive_start = start_date.replace(tzinfo=None) if start_date.tzinfo else start_date
        naive_end = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
        result = await self.session.execute(
            select(Position)
            .where(Position.status == "CLOSED")
            .where(Position.closed_at >= naive_start)
            .where(Position.closed_at <= naive_end)
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
        position.closed_at = datetime.now(UTC).replace(tzinfo=None)
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
        position.closed_at = datetime.now(UTC).replace(tzinfo=None)
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
            naive_from = date_from.replace(tzinfo=None) if date_from.tzinfo else date_from
            base = base.where(Position.closed_at >= naive_from)
            count_q = count_q.where(Position.closed_at >= naive_from)
        if date_to:
            naive_to = date_to.replace(tzinfo=None) if date_to.tzinfo else date_to
            base = base.where(Position.closed_at <= naive_to)
            count_q = count_q.where(Position.closed_at <= naive_to)
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
            # Strip tzinfo for asyncpg TIMESTAMP WITHOUT TIME ZONE columns
            naive_from = date_from.replace(tzinfo=None) if date_from.tzinfo else date_from
            query = query.where(Position.closed_at >= naive_from)
        if date_to:
            naive_to = date_to.replace(tzinfo=None) if date_to.tzinfo else date_to
            query = query.where(Position.closed_at <= naive_to)
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
            gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
        )

        # P&L by epic + last trade time per epic
        pnl_by_epic: dict[str, float] = {}
        last_trade_by_epic: dict[str, str] = {}
        for p in positions:
            pnl_by_epic[p.epic] = pnl_by_epic.get(p.epic, 0) + float(p.profit_loss)
            if p.closed_at:
                last_trade_by_epic[p.epic] = p.closed_at.isoformat()

        # Equity curve (cumulative P&L over time) — enriched per-day
        # First pass: group trades by day
        from collections import defaultdict

        daily_buckets: dict[str, list[float]] = defaultdict(list)
        for p in positions:
            if p.closed_at:
                day = p.closed_at.strftime("%Y-%m-%d")
                daily_buckets[day].append(float(p.profit_loss))

        # Second pass: build enriched equity points
        from src.utils.config import get_settings

        initial_equity = get_settings().initial_capital
        equity_points: list[dict] = []
        cumulative = 0.0
        cumulative_trades = 0
        cumulative_wins = 0
        peak_equity = initial_equity
        for day in sorted(daily_buckets.keys()):
            day_pnls = daily_buckets[day]
            daily_pnl = sum(day_pnls)
            day_wins = sum(1 for v in day_pnls if v > 0)
            cumulative += daily_pnl
            cumulative_trades += len(day_pnls)
            cumulative_wins += day_wins
            equity_now = initial_equity + cumulative
            peak_equity = max(peak_equity, equity_now)
            dd_pct = (equity_now - peak_equity) / peak_equity * 100 if peak_equity > 0 else 0.0
            equity_points.append(
                {
                    "date": day,
                    "value": round(cumulative, 2),
                    "daily_pnl": round(daily_pnl, 2),
                    "drawdown_pct": round(dd_pct, 2),
                    "trade_count": len(day_pnls),
                    "win_count": day_wins,
                    "cumulative_trades": cumulative_trades,
                    "cumulative_win_rate": (
                        round(cumulative_wins / cumulative_trades, 3)
                        if cumulative_trades > 0
                        else 0.0
                    ),
                }
            )

        # Risk-adjusted ratios from equity curve
        if equity_points and len(equity_points) > 1:
            values = np.array([p["value"] for p in equity_points], dtype=np.float64)
            # Use trade-to-trade returns (not percentage returns of cumulative equity)
            returns = np.diff(values)

            avg_return = float(np.mean(returns))
            std_return = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
            downside_returns = returns[returns < 0]
            downside_std = (
                float(np.std(downside_returns, ddof=1)) if len(downside_returns) > 1 else 0.0
            )

            # Annualize assuming ~252 trading days
            sharpe_ratio = (avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0
            sortino_ratio = (avg_return / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

            # Max drawdown from equity curve
            peak = np.maximum.accumulate(values)
            drawdowns = (peak - values) / np.maximum(np.abs(peak), 1e-10)
            max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

            # Calmar ratio (annualized return / max drawdown)
            total_days = max(len(equity_points), 1)
            if values[0] != 0 and total_days > 0:
                total_return = values[-1] / max(abs(values[0]), 1e-10)
                annualized_return = (abs(total_return) ** (252 / total_days) - 1) * (
                    1 if total_return >= 0 else -1
                )
            else:
                annualized_return = 0.0
            calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0
        else:
            sharpe_ratio = sortino_ratio = max_drawdown = calmar_ratio = 0.0

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
            "last_trade_by_epic": last_trade_by_epic,
            "equity_curve": equity_points,
            "sharpe_ratio": round(float(sharpe_ratio), 3),
            "sortino_ratio": round(float(sortino_ratio), 3),
            "calmar_ratio": round(float(calmar_ratio), 3),
            "max_drawdown": round(float(max_drawdown), 4),
        }
