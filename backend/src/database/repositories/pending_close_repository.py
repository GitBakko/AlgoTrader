"""Repository for the `pending_close_detections` table.

Close-detection v2 persists its retry queue here so ``retry_count`` and
``first_seen`` survive backend restarts. See
migration `a910f5d6e7b2` and plan calm-questing-quail.md.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PendingCloseDetection


class PendingCloseRepository:
    """CRUD layer for `pending_close_detections`."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[PendingCloseDetection]:
        result = await self.session.execute(select(PendingCloseDetection))
        return list(result.scalars().all())

    async def get(self, deal_id: str) -> PendingCloseDetection | None:
        result = await self.session.execute(
            select(PendingCloseDetection).where(PendingCloseDetection.deal_id == deal_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        deal_id: str,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        prev_pos: dict,
        first_seen: datetime,
        retry_count: int,
        deal_reference: str | None = None,
        last_activity_snapshot: dict | None = None,
        last_transaction_snapshot: dict | None = None,
    ) -> PendingCloseDetection:
        """Insert or update the pending close row for ``deal_id``.

        ``first_seen`` on existing rows is preserved; only ``retry_count``
        and the snapshots are updated. This is what makes the
        reconciliation timeout survive restarts.
        """
        existing = await self.get(deal_id)
        if existing:
            existing.retry_count = retry_count
            if deal_reference is not None:
                existing.deal_reference = deal_reference
            if last_activity_snapshot is not None:
                existing.last_activity_snapshot = last_activity_snapshot
            if last_transaction_snapshot is not None:
                existing.last_transaction_snapshot = last_transaction_snapshot
            await self.session.flush()
            return existing

        row = PendingCloseDetection(
            deal_id=deal_id,
            deal_reference=deal_reference,
            epic=epic,
            direction=direction,
            size=Decimal(str(size)),
            entry_price=Decimal(str(entry_price)),
            prev_pos=prev_pos,
            first_seen=first_seen,
            retry_count=retry_count,
            last_activity_snapshot=last_activity_snapshot,
            last_transaction_snapshot=last_transaction_snapshot,
        )
        self.session.add(row)
        await self.session.flush()
        logger.info(
            f"Queued pending close for {deal_id} (epic={epic}, " f"retry_count={retry_count})"
        )
        return row

    async def delete(self, deal_id: str) -> bool:
        row = await self.get(deal_id)
        if not row:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
