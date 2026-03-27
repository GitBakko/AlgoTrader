"""
Notifications API router.
In-app notification center: list, read, mark-as-read, delete.
"""

from fastapi import APIRouter, Depends, Query
from loguru import logger

from src.api.dependencies import get_db_session
from src.api.schemas import error_response, success_response
from src.database.repositories.notification_repository import NotificationRepository
from src.monitoring.alerting.schemas import ALERT_EMOJI, SEVERITY_EMOJI

router = APIRouter()


def _get_repo(session):
    """Create NotificationRepository from session."""
    if session is None:
        return None
    return NotificationRepository(session)


@router.get("/")
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    alert_type: str | None = Query(None),
    severity: str | None = Query(None),
    epic: str | None = Query(None),
    is_read: bool | None = Query(None),
    session=Depends(get_db_session),
):
    """List notifications with pagination and filters."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    items, total = await repo.get_list(
        page=page,
        page_size=page_size,
        alert_type=alert_type,
        severity=severity,
        epic=epic,
        is_read=is_read,
    )

    notifications = []
    for n in items:
        emoji = ALERT_EMOJI.get(n.alert_type, SEVERITY_EMOJI.get(n.severity, "\U0001f535"))
        # Override emoji for losing trades (TRADE_CLOSED with negative P&L)
        if n.alert_type == "TRADE_CLOSED" and n.details:
            pnl = n.details.get("pnl")
            if pnl is not None:
                try:
                    if float(pnl) < 0:
                        emoji = "\U0001f53b"  # 🔻 red triangle down
                except (ValueError, TypeError):
                    pass
        notifications.append(
            {
                "id": n.id,
                "alert_type": n.alert_type,
                "severity": n.severity,
                "title": n.title,
                "message": n.message,
                "epic": n.epic,
                "emoji": emoji,
                "details": n.details,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
        )

    return success_response(
        {
            "notifications": notifications,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/unread-count")
async def unread_count(session=Depends(get_db_session)):
    """Get count of unread notifications."""
    repo = _get_repo(session)
    if repo is None:
        return success_response({"count": 0})

    count = await repo.get_unread_count()
    return success_response({"count": count})


@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: int, session=Depends(get_db_session)):
    """Mark a single notification as read."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    found = await repo.mark_as_read(notification_id)
    if not found:
        return error_response("Notification not found", 404)
    return success_response({"message": "Marked as read"})


@router.put("/read-all")
async def mark_all_read(session=Depends(get_db_session)):
    """Mark all notifications as read."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    count = await repo.mark_all_read()
    return success_response({"message": f"Marked {count} as read", "count": count})


@router.delete("/{notification_id}")
async def delete_notification(notification_id: int, session=Depends(get_db_session)):
    """Delete a single notification."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    found = await repo.delete_one(notification_id)
    if not found:
        return error_response("Notification not found", 404)
    return success_response({"message": "Deleted"})
