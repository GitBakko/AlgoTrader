"""
Alert schemas and models.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    CRITICAL = "CRITICAL"  # System failure, trading halted
    WARNING = "WARNING"  # Degraded performance, risk limits hit
    INFO = "INFO"  # Informational, non-urgent


class AlertType(str, Enum):
    """Types of alerts."""

    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    DRAWDOWN_EXCEEDED = "DRAWDOWN_EXCEEDED"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    DATABASE_FAILURE = "DATABASE_FAILURE"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    BROKER_ERROR = "BROKER_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    RISK_LIMIT_BREACH = "RISK_LIMIT_BREACH"
    POSITION_STUCK = "POSITION_STUCK"
    BACKUP_START = "BACKUP_START"
    BACKUP_COMPLETE = "BACKUP_COMPLETE"


class Alert(BaseModel):
    """Alert model."""

    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = Field(default_factory=dict)
    epic: str | None = None
    user_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "epic": self.epic,
            "user_id": self.user_id,
        }

    def format_text(self) -> str:
        """Format alert as plain text."""
        lines = [
            f"🚨 {self.severity.value}: {self.title}",
            f"Type: {self.alert_type.value}",
            f"Time: {self.timestamp.isoformat()}",
            "",
            self.message,
        ]

        if self.epic:
            lines.append(f"Asset: {self.epic}")

        if self.details:
            lines.append("")
            lines.append("Details:")
            for key, value in self.details.items():
                lines.append(f"  • {key}: {value}")

        return "\n".join(lines)

    def format_markdown(self) -> str:
        """Format alert as Markdown (for Slack)."""
        severity_emoji = {
            AlertSeverity.CRITICAL: "🔴",
            AlertSeverity.WARNING: "🟡",
            AlertSeverity.INFO: "🔵",
        }

        lines = [
            f"{severity_emoji[self.severity]} *{self.severity.value}: {self.title}*",
            f"*Type:* {self.alert_type.value}",
            f"*Time:* {self.timestamp.isoformat()}",
            "",
            self.message,
        ]

        if self.epic:
            lines.append(f"*Asset:* `{self.epic}`")

        if self.details:
            lines.append("")
            lines.append("*Details:*")
            for key, value in self.details.items():
                lines.append(f"  • {key}: `{value}`")

        return "\n".join(lines)
