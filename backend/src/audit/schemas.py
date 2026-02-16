"""
Audit event schemas and enums.
Defines audit event types and structures.
"""

from enum import Enum


class AuditEventType(str, Enum):
    """Audit event types for tracking user and system actions."""

    # Authentication events
    AUTH_LOGIN = "AUTH_LOGIN"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    AUTH_FAILED = "AUTH_FAILED"
    AUTH_TOKEN_REFRESH = "AUTH_TOKEN_REFRESH"

    # Trading events
    TRADE_EXECUTE = "TRADE_EXECUTE"
    TRADE_CLOSE = "TRADE_CLOSE"
    TRADE_MODIFY = "TRADE_MODIFY"
    TRADE_REJECTED = "TRADE_REJECTED"

    # Configuration events
    CONFIG_CHANGE = "CONFIG_CHANGE"
    SETTINGS_UPDATE = "SETTINGS_UPDATE"

    # Risk events
    RISK_OVERRIDE = "RISK_OVERRIDE"
    CIRCUIT_BREAKER_TRIP = "CIRCUIT_BREAKER_TRIP"
    DRAWDOWN_LIMIT_HIT = "DRAWDOWN_LIMIT_HIT"

    # User management
    USER_CREATE = "USER_CREATE"
    USER_UPDATE = "USER_UPDATE"
    USER_DELETE = "USER_DELETE"
    USER_DEACTIVATE = "USER_DEACTIVATE"

    # System events
    SYSTEM_START = "SYSTEM_START"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    BACKUP_START = "BACKUP_START"
    BACKUP_COMPLETE = "BACKUP_COMPLETE"

    # API access
    API_REQUEST = "API_REQUEST"
    API_ERROR = "API_ERROR"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
