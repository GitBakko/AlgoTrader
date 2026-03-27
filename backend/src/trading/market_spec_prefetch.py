"""
Market specification pre-fetcher.
Proactively fetches and caches min deal sizes from Capital.com
for all tradeable assets at startup.
"""

import asyncio

from loguru import logger

from src.broker.client import CapitalComClient
from src.utils.constants import TRADABLE_ASSETS


async def prefetch_market_specs(
    broker: CapitalComClient,
    db_session_factory=None,
    environment: str = "DEMO",
    batch_size: int = 5,
    delay_between_batches: float = 0.6,
) -> dict[str, float]:
    """
    Fetch market details for all tradeable assets in parallel batches.
    Persists results to DB if available, returns in-memory dict.

    Args:
        broker: Connected Capital.com client
        db_session_factory: Async session factory (None if DB unavailable)
        environment: "DEMO" or "LIVE"
        batch_size: Concurrent API calls per batch (5 stays under 10 req/sec)
        delay_between_batches: Seconds between batches

    Returns:
        Dict of {epic: min_deal_size} for all successfully fetched assets
    """
    epics = list(TRADABLE_ASSETS)

    logger.info(
        f"Pre-fetching market specs for {len(epics)} assets "
        f"(batch_size={batch_size}, env={environment})"
    )

    async def _fetch_one(epic: str) -> tuple[str, dict | None]:
        try:
            info = await asyncio.wait_for(broker.get_market_details(epic), timeout=10.0)
            return epic, info
        except Exception as e:
            logger.warning(f"[{epic}] Market spec fetch failed: {e}")
            return epic, None

    results: dict[str, dict] = {}
    for i in range(0, len(epics), batch_size):
        batch = epics[i : i + batch_size]
        batch_results = await asyncio.gather(*[_fetch_one(e) for e in batch])
        for epic, info in batch_results:
            if info is not None:
                results[epic] = info
        if i + batch_size < len(epics):
            await asyncio.sleep(delay_between_batches)

    # Extract min_deal_size from results
    min_sizes: dict[str, float] = {}
    db_records: list[dict] = []

    for epic, info in results.items():
        dealing_rules = info.get("dealingRules", {})
        min_deal = dealing_rules.get("minDealSize", {})
        max_deal = dealing_rules.get("maxDealSize", {})
        value = min_deal.get("value")

        if value is not None:
            min_sizes[epic] = float(value)
            db_records.append(
                {
                    "epic": epic,
                    "min_deal_size": float(value),
                    "min_deal_size_unit": min_deal.get("unit", "UNITS"),
                    "max_deal_size": (
                        float(max_deal["value"]) if max_deal.get("value") is not None else None
                    ),
                    "market_name": info.get("instrument", {}).get("name"),
                }
            )

    # Persist to DB if available
    if db_session_factory and db_records:
        try:
            from src.database.repositories.market_spec_repository import (
                MarketSpecRepository,
            )

            async with db_session_factory() as session:
                repo = MarketSpecRepository(session)
                count = await repo.bulk_upsert(db_records, environment)
                await session.commit()
                logger.info(f"Persisted {count} market specs to DB ({environment})")
        except Exception as e:
            logger.warning(f"Market spec DB persistence failed: {e}")

    logger.info(
        f"Pre-fetch complete: {len(min_sizes)}/{len(epics)} assets "
        f"(failed: {len(epics) - len(results)})"
    )
    return min_sizes


async def load_market_specs_from_db(
    db_session_factory,
    environment: str = "DEMO",
) -> dict[str, float]:
    """
    Load cached market specs from the database.
    Used at startup for immediate availability before broker pre-fetch completes.

    Returns:
        Dict of {epic: min_deal_size}
    """
    if db_session_factory is None:
        return {}

    try:
        from src.database.repositories.market_spec_repository import (
            MarketSpecRepository,
        )

        async with db_session_factory() as session:
            repo = MarketSpecRepository(session)
            specs = await repo.get_all_for_environment(environment)
            await session.commit()

        result = {spec.epic: float(spec.min_deal_size) for spec in specs}
        if result:
            logger.info(f"Loaded {len(result)} market specs from DB ({environment})")
        return result
    except Exception as e:
        logger.warning(f"Failed to load market specs from DB: {e}")
        return {}
