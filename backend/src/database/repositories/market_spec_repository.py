"""
Repository for market specifications (dealing rules from Capital.com).
Caches minDealSize per epic per environment (DEMO/LIVE).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import MarketSpec


class MarketSpecRepository:
    """Repository for market spec persistence and retrieval."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_epic(self, epic: str, environment: str) -> MarketSpec | None:
        """Get market spec for a specific epic and environment."""
        result = await self.session.execute(
            select(MarketSpec)
            .where(MarketSpec.epic == epic)
            .where(MarketSpec.environment == environment)
        )
        return result.scalar_one_or_none()

    async def get_all_for_environment(self, environment: str) -> list[MarketSpec]:
        """Get all market specs for a given environment (DEMO/LIVE)."""
        result = await self.session.execute(
            select(MarketSpec).where(MarketSpec.environment == environment)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        epic: str,
        environment: str,
        min_deal_size: float,
        min_deal_size_unit: str = "UNITS",
        max_deal_size: float | None = None,
        market_name: str | None = None,
    ) -> MarketSpec:
        """Create or update market spec for an epic."""
        existing = await self.get_by_epic(epic, environment)
        now = datetime.now(UTC).replace(tzinfo=None)

        if existing:
            existing.min_deal_size = Decimal(str(min_deal_size))
            existing.min_deal_size_unit = min_deal_size_unit
            existing.max_deal_size = (
                Decimal(str(max_deal_size)) if max_deal_size is not None else None
            )
            existing.market_name = market_name
            existing.fetched_at = now
            existing.updated_at = now
            await self.session.flush()
            return existing

        spec = MarketSpec(
            epic=epic,
            environment=environment,
            min_deal_size=Decimal(str(min_deal_size)),
            min_deal_size_unit=min_deal_size_unit,
            max_deal_size=(Decimal(str(max_deal_size)) if max_deal_size is not None else None),
            market_name=market_name,
            fetched_at=now,
        )
        self.session.add(spec)
        await self.session.flush()
        return spec

    async def bulk_upsert(self, specs: list[dict], environment: str) -> int:
        """Upsert multiple market specs. Returns count of upserted records."""
        count = 0
        for spec_data in specs:
            await self.upsert(
                epic=spec_data["epic"],
                environment=environment,
                min_deal_size=spec_data["min_deal_size"],
                min_deal_size_unit=spec_data.get("min_deal_size_unit", "UNITS"),
                max_deal_size=spec_data.get("max_deal_size"),
                market_name=spec_data.get("market_name"),
            )
            count += 1
        return count
