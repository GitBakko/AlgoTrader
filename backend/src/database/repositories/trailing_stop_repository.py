"""
Repository for trailing stop states.
Enables persistence and recovery of trailing stop manager state.
"""

from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.broker.models import Direction
from src.database.models import TrailingStopState


class TrailingStopRepository:
    """Repository for trailing stop state persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_active(self) -> list[TrailingStopState]:
        """
        Get all active trailing stop states.

        Returns:
            List of all trailing stop states in the database.
        """
        result = await self.session.execute(select(TrailingStopState))
        return list(result.scalars().all())

    async def get_by_deal_id(self, deal_id: str) -> TrailingStopState | None:
        """
        Get trailing stop state by deal ID.

        Args:
            deal_id: Position deal identifier

        Returns:
            Trailing stop state or None if not found
        """
        result = await self.session.execute(
            select(TrailingStopState).where(TrailingStopState.deal_id == deal_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        deal_id: str,
        epic: str,
        direction: Direction,
        entry_price: Decimal,
        current_stop: Decimal,
        phase: int,
        tp1_level: Decimal | None = None,
        tp2_level: Decimal | None = None,
        highest_price: Decimal | None = None,
        lowest_price: Decimal | None = None,
    ) -> TrailingStopState:
        """
        Create or update trailing stop state.

        Args:
            deal_id: Position deal identifier
            epic: Asset symbol
            direction: BUY or SELL
            entry_price: Entry price
            current_stop: Current stop loss level
            phase: Trailing stop phase (1-4)
            tp1_level: First take profit level
            tp2_level: Second take profit level
            highest_price: Highest price reached (for longs)
            lowest_price: Lowest price reached (for shorts)

        Returns:
            Created or updated trailing stop state
        """
        existing = await self.get_by_deal_id(deal_id)

        if existing:
            # Update existing
            existing.epic = epic
            existing.direction = direction.value
            existing.entry_price = entry_price
            existing.current_stop = current_stop
            existing.phase = phase
            existing.tp1_level = tp1_level
            existing.tp2_level = tp2_level
            existing.highest_price = highest_price
            existing.lowest_price = lowest_price
            await self.session.flush()
            logger.debug(f"Updated trailing stop state for {deal_id} (phase {phase})")
            return existing
        else:
            # Create new
            state = TrailingStopState(
                deal_id=deal_id,
                epic=epic,
                direction=direction.value,
                entry_price=entry_price,
                current_stop=current_stop,
                phase=phase,
                tp1_level=tp1_level,
                tp2_level=tp2_level,
                highest_price=highest_price,
                lowest_price=lowest_price,
            )
            self.session.add(state)
            await self.session.flush()
            logger.debug(f"Created trailing stop state for {deal_id} (phase {phase})")
            return state

    async def delete_by_deal_id(self, deal_id: str) -> bool:
        """
        Delete trailing stop state by deal ID.

        Args:
            deal_id: Position deal identifier

        Returns:
            True if deleted, False if not found
        """
        state = await self.get_by_deal_id(deal_id)
        if state:
            await self.session.delete(state)
            await self.session.flush()
            logger.debug(f"Deleted trailing stop state for {deal_id}")
            return True
        return False

    async def bulk_delete(self, deal_ids: list[str]) -> int:
        """
        Delete multiple trailing stop states.

        Args:
            deal_ids: List of position deal identifiers

        Returns:
            Number of states deleted
        """
        count = 0
        for deal_id in deal_ids:
            if await self.delete_by_deal_id(deal_id):
                count += 1
        return count
