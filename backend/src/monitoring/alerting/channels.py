"""
Alert delivery channels.
Email, Slack, Telegram, and Webhook notification channels.
"""

import asyncio
from abc import ABC, abstractmethod

import httpx
from loguru import logger

from src.monitoring.alerting.schemas import Alert


class AlertChannel(ABC):
    """Base class for alert channels."""

    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """
        Send alert through this channel.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        pass


class EmailChannel(AlertChannel):
    """
    Email alert channel using aiosmtplib.
    Note: Requires aiosmtplib to be installed.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        from_email: str = "alerts@mantis.ai",
        to_emails: list[str] = None,
        use_tls: bool = True,
    ):
        """
        Initialize email channel.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            smtp_user: SMTP username (optional)
            smtp_password: SMTP password (optional)
            from_email: Sender email address
            to_emails: List of recipient emails
            use_tls: Use TLS connection
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.to_emails = to_emails or []
        self.use_tls = use_tls

    async def send(self, alert: Alert) -> bool:
        """Send alert via email."""
        if not self.to_emails:
            logger.warning("Email channel has no recipients configured")
            return False

        try:
            # Lazy import aiosmtplib (optional dependency)
            import aiosmtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            # Create email message
            msg = MIMEMultipart()
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            msg["Subject"] = f"[{alert.severity.value}] {alert.title}"

            # Add plain text body
            body = alert.format_text()
            msg.attach(MIMEText(body, "plain"))

            # Send email
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                use_tls=self.use_tls,
            )

            logger.info(f"Alert sent via email to {len(self.to_emails)} recipients")
            return True

        except ImportError:
            logger.error("aiosmtplib not installed. Install with: pip install aiosmtplib")
            return False
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False


class SlackChannel(AlertChannel):
    """Slack alert channel using Incoming Webhooks."""

    def __init__(
        self, webhook_url: str, username: str = "MANTIS AI", icon_emoji: str = ":robot_face:"
    ):
        """
        Initialize Slack channel.

        Args:
            webhook_url: Slack Incoming Webhook URL
            username: Bot username
            icon_emoji: Bot icon emoji
        """
        self.webhook_url = webhook_url
        self.username = username
        self.icon_emoji = icon_emoji

    async def send(self, alert: Alert) -> bool:
        """Send alert to Slack."""
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured")
            return False

        try:
            # Build Slack message
            payload = {
                "username": self.username,
                "icon_emoji": self.icon_emoji,
                "text": alert.format_markdown(),
            }

            # Send to Slack
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info("Alert sent to Slack successfully")
                    return True
                else:
                    logger.error(f"Slack API error: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False


class WebhookChannel(AlertChannel):
    """Generic webhook alert channel."""

    def __init__(
        self,
        webhook_url: str,
        headers: dict[str, str] | None = None,
        method: str = "POST",
    ):
        """
        Initialize webhook channel.

        Args:
            webhook_url: Webhook URL
            headers: Optional HTTP headers
            method: HTTP method (POST, PUT, etc.)
        """
        self.webhook_url = webhook_url
        self.headers = headers or {"Content-Type": "application/json"}
        self.method = method.upper()

    async def send(self, alert: Alert) -> bool:
        """Send alert to webhook."""
        if not self.webhook_url:
            logger.warning("Webhook URL not configured")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=self.method,
                    url=self.webhook_url,
                    json=alert.to_dict(),
                    headers=self.headers,
                    timeout=10.0,
                )

                if 200 <= response.status_code < 300:
                    logger.info(f"Alert sent to webhook: {response.status_code}")
                    return True
                else:
                    logger.error(f"Webhook error: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
            return False


class TelegramChannel(AlertChannel):
    """
    Telegram alert channel using the Telegram Bot API.
    Uses httpx (already installed) — no extra dependency required.

    Setup:
      1. Create a bot via @BotFather and get the token.
      2. Send any message to the bot to get the chat_id.
      3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
    """

    _TELEGRAM_API = "https://api.telegram.org"

    def __init__(self, bot_token: str, chat_id: str, parse_mode: str = "Markdown"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.parse_mode = parse_mode

    async def send(self, alert: Alert) -> bool:
        """Send alert via Telegram Bot API sendMessage.

        Tries Markdown first; falls back to plain text if Telegram rejects it.
        """
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram channel: bot_token or chat_id not configured")
            return False

        url = f"{self._TELEGRAM_API}/bot{self.bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient() as client:
                # First attempt: Markdown
                payload = {
                    "chat_id": self.chat_id,
                    "text": alert.format_markdown(),
                    "parse_mode": self.parse_mode,
                    "disable_web_page_preview": True,
                }
                response = await client.post(url, json=payload, timeout=10.0)
                data = response.json()

                if response.status_code == 200 and data.get("ok"):
                    logger.info("Alert sent to Telegram successfully")
                    return True

                # Markdown rejected — retry as plain text
                logger.warning(
                    f"Telegram Markdown rejected ({response.status_code}), retrying as plain text"
                )
                payload_plain = {
                    "chat_id": self.chat_id,
                    "text": alert.format_text(),
                    "disable_web_page_preview": True,
                }
                response2 = await client.post(url, json=payload_plain, timeout=10.0)
                data2 = response2.json()

                if response2.status_code == 200 and data2.get("ok"):
                    logger.info("Alert sent to Telegram (plain text fallback)")
                    return True

                logger.error(f"Telegram API error: {response2.status_code} - {data2}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
