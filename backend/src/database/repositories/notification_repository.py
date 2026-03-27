"""
Repository for in-app notifications (CRUD + pagination).
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Notification


class NotificationRepository:
    """Repository for notification persistence and retrieval."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        epic: str | None = None,
        details: dict | None = None,
    ) -> Notification:
        """Insert a new notification."""
        notif = Notification(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            epic=epic,
            details=details,
        )
        self.session.add(notif)
        await self.session.flush()
        return notif

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        alert_type: str | None = None,
        severity: str | None = None,
        epic: str | None = None,
        is_read: bool | None = None,
    ) -> tuple[list[Notification], int]:
        """Get paginated notifications with optional filters. Returns (items, total)."""
        query = select(Notification)
        count_query = select(func.count()).select_from(Notification)

        if alert_type:
            query = query.where(Notification.alert_type == alert_type)
            count_query = count_query.where(Notification.alert_type == alert_type)
        if severity:
            query = query.where(Notification.severity == severity)
            count_query = count_query.where(Notification.severity == severity)
        if epic:
            query = query.where(Notification.epic == epic)
            count_query = count_query.where(Notification.epic == epic)
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
            count_query = count_query.where(Notification.is_read == is_read)

        total = (await self.session.execute(count_query)).scalar() or 0

        query = query.order_by(Notification.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.is_read == False)  # noqa: E712
        )
        return result.scalar() or 0

    async def mark_as_read(self, notification_id: int) -> bool:
        """Mark a single notification as read. Returns True if found."""
        result = await self.session.execute(
            update(Notification).where(Notification.id == notification_id).values(is_read=True)
        )
        return result.rowcount > 0

    async def mark_all_read(self) -> int:
        """Mark all unread notifications as read. Returns count updated."""
        result = await self.session.execute(
            update(Notification)
            .where(Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
        )
        return result.rowcount

    async def delete_one(self, notification_id: int) -> bool:
        """Delete a single notification. Returns True if found."""
        result = await self.session.execute(
            delete(Notification).where(Notification.id == notification_id)
        )
        return result.rowcount > 0
