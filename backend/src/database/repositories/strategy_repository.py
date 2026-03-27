"""
Strategy repository for trading strategy configurations.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Strategy
from src.database.repository import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    """Repository for Strategy model with strategy-specific queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Strategy, session)

    async def get_active_strategies(self) -> list[Strategy]:
        """
        Get all active strategies.

        Returns:
            List of active strategies
        """
        result = await self.session.execute(
            select(Strategy).where(Strategy.is_active == True).order_by(Strategy.name)
        )
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Strategy | None:
        """
        Get strategy by unique name.

        Args:
            name: Strategy name

        Returns:
            Strategy or None if not found
        """
        result = await self.session.execute(select(Strategy).where(Strategy.name == name))
        return result.scalar_one_or_none()

    async def get_by_epic(self, epic: str) -> list[Strategy]:
        """
        Get all strategies for a specific asset.

        Args:
            epic: Asset epic code

        Returns:
            List of strategies
        """
        result = await self.session.execute(
            select(Strategy).where(Strategy.epic == epic).order_by(Strategy.name)
        )
        return list(result.scalars().all())

    async def activate_strategy(self, strategy_id: int) -> Strategy | None:
        """
        Activate a strategy.

        Args:
            strategy_id: Strategy ID

        Returns:
            Updated strategy or None if not found
        """
        strategy = await self.get_by_id(strategy_id)
        if not strategy:
            return None

        strategy.is_active = True
        strategy.activated_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(strategy)
        return strategy

    async def deactivate_strategy(self, strategy_id: int) -> Strategy | None:
        """
        Deactivate a strategy.

        Args:
            strategy_id: Strategy ID

        Returns:
            Updated strategy or None if not found
        """
        strategy = await self.get_by_id(strategy_id)
        if not strategy:
            return None

        strategy.is_active = False
        strategy.deactivated_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(strategy)
        return strategy

    async def update_performance_metrics(self, strategy_id: int, metrics: dict) -> Strategy | None:
        """
        Update strategy performance metrics.

        Args:
            strategy_id: Strategy ID
            metrics: Performance metrics dictionary (sharpe, sortino, win_rate, etc.)

        Returns:
            Updated strategy or None if not found
        """
        strategy = await self.get_by_id(strategy_id)
        if not strategy:
            return None

        strategy.performance_metrics = metrics

        await self.session.flush()
        await self.session.refresh(strategy)
        return strategy
