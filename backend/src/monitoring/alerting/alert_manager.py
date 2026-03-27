"""
Alert manager for routing and sending alerts.
Manages multiple channels and alert rules.
"""

import asyncio

from loguru import logger

from src.monitoring.alerting.channels import (
    AlertChannel,
    EmailChannel,
    SlackChannel,
    TelegramChannel,
    WebhookChannel,
)
from src.monitoring.alerting.in_app_channel import InAppChannel
from src.monitoring.alerting.schemas import Alert, AlertSeverity, AlertType
from src.utils.config import get_settings


class AlertManager:
    """
    Manager for creating and routing alerts to multiple channels.
    Supports Email, Slack, and Webhook notifications.
    """

    def __init__(self):
        """Initialize alert manager with configured channels."""
        self.channels: list[AlertChannel] = []
        self.settings = get_settings()
        # In-app channel is always active (DB + WS broadcast)
        self.in_app_channel = InAppChannel()
        self.channels.append(self.in_app_channel)
        self._initialize_channels()

    def _initialize_channels(self):
        """Initialize alert channels from configuration."""
        # Email channel
        email_enabled = getattr(self.settings, "alert_email_enabled", False)
        if email_enabled:
            smtp_host = getattr(self.settings, "alert_email_smtp_host", "")
            smtp_port = getattr(self.settings, "alert_email_smtp_port", 587)
            smtp_user = getattr(self.settings, "alert_email_smtp_user", None)
            smtp_password = getattr(self.settings, "alert_email_smtp_password", None)
            from_email = getattr(self.settings, "alert_email_from", "alerts@mantis.ai")
            to_emails = getattr(self.settings, "alert_email_to", "").split(",")
            to_emails = [email.strip() for email in to_emails if email.strip()]

            if smtp_host and to_emails:
                self.channels.append(
                    EmailChannel(
                        smtp_host=smtp_host,
                        smtp_port=smtp_port,
                        smtp_user=smtp_user,
                        smtp_password=smtp_password,
                        from_email=from_email,
                        to_emails=to_emails,
                    )
                )
                logger.info(f"Email alerting enabled: {len(to_emails)} recipients")

        # Slack channel
        slack_enabled = getattr(self.settings, "alert_slack_enabled", False)
        if slack_enabled:
            webhook_url = getattr(self.settings, "alert_slack_webhook_url", "")
            if webhook_url:
                self.channels.append(SlackChannel(webhook_url=webhook_url))
                logger.info("Slack alerting enabled")

        # Webhook channel
        webhook_enabled = getattr(self.settings, "alert_webhook_enabled", False)
        if webhook_enabled:
            webhook_url = getattr(self.settings, "alert_webhook_url", "")
            if webhook_url:
                self.channels.append(WebhookChannel(webhook_url=webhook_url))
                logger.info("Webhook alerting enabled")

        # Telegram channel
        telegram_enabled = getattr(self.settings, "alert_telegram_enabled", False)
        if telegram_enabled:
            bot_token = getattr(self.settings, "telegram_bot_token", "")
            chat_id = getattr(self.settings, "telegram_chat_id", "")
            if bot_token and chat_id:
                self.channels.append(TelegramChannel(bot_token=bot_token, chat_id=chat_id))
                logger.info("Telegram alerting enabled")

        if len(self.channels) <= 1:  # Only InAppChannel
            logger.warning("No external alert channels configured. Alerts will only be in-app.")

    async def send_alert(self, alert: Alert) -> dict[str, bool]:
        """
        Send alert through all configured channels.

        Args:
            alert: Alert to send

        Returns:
            Dict of channel results {channel_name: success}
        """
        # Send to all channels concurrently
        tasks = [channel.send(alert) for channel in self.channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dict
        channel_results = {}
        for _i, (channel, result) in enumerate(zip(self.channels, results)):
            channel_name = channel.__class__.__name__
            if isinstance(result, Exception):
                logger.error(f"{channel_name} failed: {result}")
                channel_results[channel_name] = False
            else:
                channel_results[channel_name] = result

        # Log alert
        logger.log(
            alert.severity.value,
            f"Alert: {alert.title} | {alert.message} | Channels: {channel_results}",
        )

        return channel_results

    async def alert_circuit_breaker(self, epic: str, reason: str, consecutive_losses: int):
        """
        Send circuit breaker alert.

        Args:
            epic: Asset epic
            reason: Circuit breaker reason
            consecutive_losses: Number of consecutive losses
        """
        alert = Alert(
            alert_type=AlertType.CIRCUIT_BREAKER,
            severity=AlertSeverity.CRITICAL,
            title=f"Circuit Breaker Activated: {epic}",
            message=f"Trading halted for {epic} after {consecutive_losses} consecutive losses.",
            epic=epic,
            details={
                "reason": reason,
                "consecutive_losses": consecutive_losses,
            },
        )
        await self.send_alert(alert)

    async def alert_drawdown(self, drawdown_pct: float, drawdown_type: str, current_equity: float):
        """
        Send drawdown exceeded alert.

        Args:
            drawdown_pct: Drawdown percentage
            drawdown_type: "daily" or "total"
            current_equity: Current account equity
        """
        alert = Alert(
            alert_type=AlertType.DRAWDOWN_EXCEEDED,
            severity=AlertSeverity.WARNING,
            title=f"{drawdown_type.title()} Drawdown Limit Exceeded",
            message=f"{drawdown_type.title()} drawdown of {drawdown_pct:.2f}% exceeds limit. Current equity: ${current_equity:,.2f}",
            details={
                "drawdown_type": drawdown_type,
                "drawdown_pct": drawdown_pct,
                "current_equity": current_equity,
            },
        )
        await self.send_alert(alert)

    async def alert_database_failure(self, error: str, operation: str):
        """
        Send database failure alert.

        Args:
            error: Error message
            operation: Database operation that failed
        """
        alert = Alert(
            alert_type=AlertType.DATABASE_FAILURE,
            severity=AlertSeverity.CRITICAL,
            title="Database Connection Failed",
            message=f"Database operation '{operation}' failed: {error}",
            details={
                "operation": operation,
                "error": error,
            },
        )
        await self.send_alert(alert)

    async def alert_broker_disconnected(self, reason: str, reconnect_attempts: int):
        """
        Send broker disconnection alert.

        Args:
            reason: Disconnection reason
            reconnect_attempts: Number of reconnection attempts
        """
        alert = Alert(
            alert_type=AlertType.BROKER_DISCONNECTED,
            severity=AlertSeverity.WARNING,
            title="Broker Connection Lost",
            message=f"Lost connection to Capital.com broker. Reconnection attempts: {reconnect_attempts}",
            details={
                "reason": reason,
                "reconnect_attempts": reconnect_attempts,
            },
        )
        await self.send_alert(alert)

    async def alert_system_error(self, component: str, error: str, stacktrace: str | None = None):
        """
        Send generic system error alert.

        Args:
            component: System component that failed
            error: Error message
            stacktrace: Optional stacktrace
        """
        details = {
            "component": component,
            "error": error,
        }
        if stacktrace:
            details["stacktrace"] = stacktrace

        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            severity=AlertSeverity.CRITICAL,
            title=f"System Error in {component}",
            message=f"Critical error in {component}: {error}",
            details=details,
        )
        await self.send_alert(alert)

    async def alert_trade_opened(
        self,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        deal_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ):
        """Send trade opened alert."""
        sl_str = f" SL={stop_loss:.4f}" if stop_loss else ""
        tp_str = f" TP={take_profit:.4f}" if take_profit else ""
        alert = Alert(
            alert_type=AlertType.TRADE_OPENED,
            severity=AlertSeverity.INFO,
            title=f"Trade Opened: {epic} {direction}",
            message=(
                f"{direction} {epic} size={size:.4f} @ {entry_price:.4f}"
                f"{sl_str}{tp_str} deal={deal_id}"
            ),
            epic=epic,
            details={
                "direction": direction,
                "size": size,
                "entry_price": entry_price,
                "deal_id": deal_id,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
        )
        await self.send_alert(alert)

    async def alert_trade_closed(
        self,
        epic: str,
        direction: str,
        deal_id: str,
        exit_price: float,
        pnl: float,
        reason: str,
    ):
        """Send trade closed alert."""
        severity = AlertSeverity.INFO if pnl >= 0 else AlertSeverity.WARNING
        sign = "+" if pnl >= 0 else ""
        alert = Alert(
            alert_type=AlertType.TRADE_CLOSED,
            severity=severity,
            title=f"Trade Closed: {epic} P&L={sign}{pnl:.2f}",
            message=(
                f"Closed {direction} {epic} @ {exit_price:.4f} "
                f"P&L={sign}{pnl:.2f} reason={reason} deal={deal_id}"
            ),
            epic=epic,
            details={
                "direction": direction,
                "deal_id": deal_id,
                "exit_price": exit_price,
                "pnl": pnl,
                "reason": reason,
            },
        )
        await self.send_alert(alert)


# Global alert manager instance
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get global AlertManager instance (singleton)."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
