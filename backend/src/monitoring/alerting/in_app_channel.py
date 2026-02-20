"""
In-app notification channel.
Persists alerts to PostgreSQL and broadcasts via WebSocket.
Always active, independent of ALERTS_ENABLED setting.
"""

from loguru import logger

from src.monitoring.alerting.channels import AlertChannel
from src.monitoring.alerting.schemas import ALERT_EMOJI, SEVERITY_EMOJI, Alert, AlertType


class InAppChannel(AlertChannel):
    """
    Persists alerts to the notifications DB table and broadcasts via WS.
    Requires db_session_factory to be injected after app startup.
    """

    def __init__(self):
        self._db_session_factory = None

    def set_db_session_factory(self, factory) -> None:
        """Inject DB session factory (called during app lifespan startup)."""
        self._db_session_factory = factory

    async def send(self, alert: Alert) -> bool:
        """Persist alert to DB and broadcast via WebSocket."""
        notification_id = None

        # 1. Persist to DB
        if self._db_session_factory:
            try:
                from src.database.repositories.notification_repository import (
                    NotificationRepository,
                )

                async with self._db_session_factory() as session:
                    repo = NotificationRepository(session)
                    notif = await repo.create(
                        alert_type=alert.alert_type.value,
                        severity=alert.severity.value,
                        title=alert.title,
                        message=alert.message,
                        epic=alert.epic,
                        details=alert.details,
                    )
                    notification_id = notif.id
                    await session.commit()
            except Exception as e:
                logger.warning(f"InAppChannel DB persist failed: {e}")

        # 2. Broadcast via WebSocket
        try:
            from src.api.websocket import ws_manager

            emoji = self._get_emoji(alert)
            payload = {
                "id": notification_id,
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "epic": alert.epic,
                "emoji": emoji,
                "details": alert.details,
                "is_read": False,
                "created_at": alert.timestamp.isoformat(),
            }
            await ws_manager.broadcast("notifications", payload)
        except Exception as e:
            logger.warning(f"InAppChannel WS broadcast failed: {e}")

        return True

    @staticmethod
    def _get_emoji(alert: Alert) -> str:
        """Get emoji for alert type (reuse logic from Alert._get_emoji)."""
        emoji = ALERT_EMOJI.get(alert.alert_type, SEVERITY_EMOJI.get(alert.severity, "\U0001f535"))
        if alert.alert_type == AlertType.TRADE_CLOSED:
            pnl = alert.details.get("pnl")
            if pnl is not None:
                try:
                    if float(pnl) < 0:
                        emoji = "\U0001f53b"
                except (ValueError, TypeError):
                    pass
        return emoji
