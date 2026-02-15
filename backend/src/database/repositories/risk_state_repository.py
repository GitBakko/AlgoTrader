"""
Repository for risk manager state snapshots.
Enables persistence and recovery of risk manager internal state.
"""

from decimal import Decimal

from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RiskStateSnapshot


class RiskStateRepository:
    """Repository for risk state snapshot persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest(self) -> RiskStateSnapshot | None:
        """
        Get the most recent risk state snapshot.

        Returns:
            Latest risk state snapshot or None if no snapshots exist
        """
        result = await self.session.execute(
            select(RiskStateSnapshot).order_by(desc(RiskStateSnapshot.snapshot_at)).limit(1)
        )
        return result.scalar_one_or_none()

    async def create_snapshot(
        self,
        peak_equity: Decimal,
        daily_start_equity: Decimal,
        current_equity: Decimal,
        consecutive_losses: int = 0,
        tripped_breakers: dict | None = None,
        equity_curve_points: list | None = None,
    ) -> RiskStateSnapshot:
        """
        Create a new risk state snapshot.

        Args:
            peak_equity: Peak equity level (for drawdown calculation)
            daily_start_equity: Equity at start of day (for daily drawdown)
            current_equity: Current equity level
            consecutive_losses: Count of consecutive losing trades
            tripped_breakers: Dict of tripped circuit breakers {epic: timestamp_iso}
            equity_curve_points: List of recent equity points for curve filter

        Returns:
            Created risk state snapshot
        """
        snapshot = RiskStateSnapshot(
            peak_equity=peak_equity,
            daily_start_equity=daily_start_equity,
            current_equity=current_equity,
            consecutive_losses=consecutive_losses,
            tripped_breakers=tripped_breakers or {},
            equity_curve_points=equity_curve_points or [],
        )
        self.session.add(snapshot)
        await self.session.flush()
        logger.debug(
            f"Created risk state snapshot: peak={peak_equity}, daily_start={daily_start_equity}, "
            f"current={current_equity}, losses={consecutive_losses}"
        )
        return snapshot

    async def get_history(self, limit: int = 50) -> list[RiskStateSnapshot]:
        """
        Get recent risk state snapshots.

        Args:
            limit: Maximum number of snapshots to retrieve

        Returns:
            List of risk state snapshots (most recent first)
        """
        result = await self.session.execute(
            select(RiskStateSnapshot).order_by(desc(RiskStateSnapshot.snapshot_at)).limit(limit)
        )
        return list(result.scalars().all())
