"""
Alert schemas and models.
"""

from datetime import UTC, datetime
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
    TRADE_OPENED = "TRADE_OPENED"
    TRADE_CLOSED = "TRADE_CLOSED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    TRAINING_STARTED = "training_started"
    TRAINING_COMPLETE = "training_complete"
    TRAINING_FAILED = "training_failed"


# Per-event-type emoji for Telegram/Slack notifications
ALERT_EMOJI: dict[str, str] = {
    AlertType.TRADE_OPENED: "🟢",
    AlertType.TRADE_CLOSED: "💰",  # overridden to 🔻 when P&L < 0
    AlertType.SIGNAL_GENERATED: "🎯",
    AlertType.CIRCUIT_BREAKER: "🚨",
    AlertType.DRAWDOWN_EXCEEDED: "📉",
    AlertType.CONSECUTIVE_LOSSES: "❌",
    AlertType.RISK_LIMIT_BREACH: "⚠️",
    AlertType.POSITION_STUCK: "🔒",
    AlertType.DATABASE_FAILURE: "🗄️",
    AlertType.BROKER_DISCONNECTED: "📡",
    AlertType.BROKER_ERROR: "🏦",
    AlertType.SYSTEM_ERROR: "💥",
    AlertType.BACKUP_START: "📦",
    AlertType.BACKUP_COMPLETE: "✅",
    AlertType.TRAINING_STARTED: "\U0001f3cb",  # weight lifter
    AlertType.TRAINING_COMPLETE: "\u2705",  # check mark
    AlertType.TRAINING_FAILED: "\u274c",  # cross mark
}

# Severity fallback (used only when alert_type not in ALERT_EMOJI)
SEVERITY_EMOJI: dict[str, str] = {
    AlertSeverity.CRITICAL: "🔴",
    AlertSeverity.WARNING: "🟡",
    AlertSeverity.INFO: "🔵",
}


class Alert(BaseModel):
    """Alert model."""

    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
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

    def _get_emoji(self) -> str:
        """Get the emoji for this alert based on type, with P&L override for TRADE_CLOSED."""
        emoji = ALERT_EMOJI.get(self.alert_type, SEVERITY_EMOJI.get(self.severity, "🔵"))
        # Override for losing trades
        if self.alert_type == AlertType.TRADE_CLOSED:
            pnl = self.details.get("pnl")
            if pnl is not None:
                try:
                    if float(pnl) < 0:
                        emoji = "🔻"
                except (ValueError, TypeError):
                    pass
        return emoji

    def format_text(self) -> str:
        """Format alert as plain text."""
        emoji = self._get_emoji()
        lines = [
            f"{emoji} {self.severity.value}: {self.title}",
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

    @staticmethod
    def _escape_telegram_md(text: str) -> str:
        """Escape special characters for Telegram Markdown v1."""
        for ch in ("_", "*", "`", "["):
            text = text.replace(ch, f"\\{ch}")
        return text

    def format_markdown(self) -> str:
        """Format alert as Markdown (for Slack/Telegram)."""
        emoji = self._get_emoji()
        esc = self._escape_telegram_md

        lines = [
            f"{emoji} *{esc(self.severity.value)}: {esc(self.title)}*",
            f"*Type:* {esc(self.alert_type.value)}",
            f"*Time:* {self.timestamp.isoformat()}",
            "",
            esc(self.message),
        ]

        if self.epic:
            lines.append(f"*Asset:* `{self.epic}`")

        if self.details:
            lines.append("")
            lines.append("*Details:*")
            for key, value in self.details.items():
                lines.append(f"  • {esc(str(key))}: `{value}`")

        return "\n".join(lines)
