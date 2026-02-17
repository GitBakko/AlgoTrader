"""
Audit logger for recording user and system events.
Provides async logging to database with structured event data.
"""

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.schemas import AuditEventType
from src.database.models import SystemEvent


class AuditLogger:
    """
    Audit logger for tracking user actions and system events.
    Records events to database with user context and metadata.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize audit logger.

        Args:
            session: Async database session
        """
        self.session = session

    async def log_event(
        self,
        event_type: AuditEventType | str,
        message: str,
        user_id: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        response_status_code: int | None = None,
        severity: str = "INFO",
        component: str = "system",
        details: dict[str, Any] | None = None,
    ) -> SystemEvent:
        """
        Log an audit event to the database.

        Args:
            event_type: Type of audit event (from AuditEventType enum)
            message: Human-readable event description
            user_id: ID of user who triggered the event
            ip_address: Client IP address
            user_agent: Client user agent string
            request_method: HTTP method (GET, POST, etc.)
            request_path: HTTP request path
            response_status_code: HTTP response status code
            severity: Event severity (CRITICAL, HIGH, MEDIUM, LOW, INFO)
            component: System component that generated the event
            details: Additional event details as JSON

        Returns:
            Created SystemEvent record
        """
        # Ensure event_type is string
        if isinstance(event_type, AuditEventType):
            event_type = event_type.value

        # Build details dict with request/response info
        event_details = details or {}
        if user_id:
            event_details["user_id"] = user_id
        if ip_address:
            event_details["ip_address"] = ip_address
        if user_agent:
            event_details["user_agent"] = user_agent
        if request_method:
            event_details["request_method"] = request_method
        if request_path:
            event_details["request_path"] = request_path
        if response_status_code:
            event_details["response_status_code"] = response_status_code

        # Create event record
        event = SystemEvent(
            event_type=event_type,
            severity=severity,
            component=component,
            message=message,
            details=event_details if event_details else None,
            occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)

        logger.info(
            f"Audit event logged: {event_type} | User: {user_id} | {message}"
        )

        return event

    async def log_auth_event(
        self,
        user_id: int | None,
        username: str,
        success: bool,
        ip_address: str,
        user_agent: str | None = None,
        reason: str | None = None,
    ) -> SystemEvent:
        """
        Log authentication event (login/logout).

        Args:
            user_id: User ID (None if login failed)
            username: Username attempted
            success: Whether auth was successful
            ip_address: Client IP
            user_agent: Client user agent
            reason: Failure reason if unsuccessful

        Returns:
            Created audit event
        """
        event_type = AuditEventType.AUTH_LOGIN if success else AuditEventType.AUTH_FAILED
        message = (
            f"User '{username}' logged in successfully"
            if success
            else f"Failed login attempt for '{username}': {reason}"
        )
        severity = "INFO" if success else "MEDIUM"

        return await self.log_event(
            event_type=event_type,
            message=message,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=severity,
            component="auth",
            details={"username": username, "success": success, "reason": reason},
        )

    async def log_trade_event(
        self,
        user_id: int | None,
        trade_action: str,
        epic: str,
        deal_id: str | None = None,
        size: float | None = None,
        price: float | None = None,
        direction: str | None = None,
        success: bool = True,
        reason: str | None = None,
    ) -> SystemEvent:
        """
        Log trading execution event.

        Args:
            user_id: User who initiated trade
            trade_action: Action type (EXECUTE, CLOSE, MODIFY)
            epic: Asset epic
            deal_id: Deal ID if available
            size: Position size
            price: Execution price
            direction: BUY or SELL
            success: Whether trade succeeded
            reason: Failure reason if unsuccessful

        Returns:
            Created audit event
        """
        event_type = AuditEventType.TRADE_EXECUTE if success else AuditEventType.TRADE_REJECTED
        message = f"Trade {trade_action.lower()}: {epic} {direction} {size} @ {price}"
        if not success:
            message += f" - REJECTED: {reason}"

        severity = "INFO" if success else "MEDIUM"

        return await self.log_event(
            event_type=event_type,
            message=message,
            user_id=user_id,
            severity=severity,
            component="trading",
            details={
                "action": trade_action,
                "epic": epic,
                "deal_id": deal_id,
                "size": size,
                "price": price,
                "direction": direction,
                "success": success,
                "reason": reason,
            },
        )

    async def log_config_change(
        self,
        user_id: int,
        setting_name: str,
        old_value: Any,
        new_value: Any,
        ip_address: str | None = None,
    ) -> SystemEvent:
        """
        Log configuration or settings change.

        Args:
            user_id: User who made the change
            setting_name: Name of setting changed
            old_value: Previous value
            new_value: New value
            ip_address: Client IP

        Returns:
            Created audit event
        """
        message = f"Setting '{setting_name}' changed from '{old_value}' to '{new_value}'"

        return await self.log_event(
            event_type=AuditEventType.CONFIG_CHANGE,
            message=message,
            user_id=user_id,
            ip_address=ip_address,
            severity="MEDIUM",
            component="config",
            details={
                "setting_name": setting_name,
                "old_value": str(old_value),
                "new_value": str(new_value),
            },
        )

    async def log_risk_event(
        self,
        risk_event_type: str,
        epic: str,
        message: str,
        user_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> SystemEvent:
        """
        Log risk management event (circuit breaker, drawdown, etc.).

        Args:
            risk_event_type: Type of risk event
            epic: Asset affected
            message: Event description
            user_id: User if applicable
            details: Additional event details

        Returns:
            Created audit event
        """
        event_type = (
            AuditEventType.CIRCUIT_BREAKER_TRIP
            if "circuit" in risk_event_type.lower()
            else AuditEventType.DRAWDOWN_LIMIT_HIT
        )

        return await self.log_event(
            event_type=event_type,
            message=message,
            user_id=user_id,
            severity="HIGH",
            component="risk",
            details=details or {"epic": epic, "risk_event": risk_event_type},
        )
