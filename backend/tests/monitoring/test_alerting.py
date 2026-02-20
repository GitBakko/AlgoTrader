"""Tests for alert channels and AlertManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.monitoring.alerting.channels import TelegramChannel
from src.monitoring.alerting.schemas import Alert, AlertSeverity, AlertType


@pytest.mark.unit
class TestTelegramChannel:
    """Tests for TelegramChannel."""

    @pytest.mark.asyncio
    async def test_send_success(self):
        """TelegramChannel sends message via Bot API."""
        channel = TelegramChannel(bot_token="TEST_TOKEN", chat_id="12345")
        alert = Alert(
            alert_type=AlertType.TRADE_OPENED,
            severity=AlertSeverity.INFO,
            title="Trade Opened: XAUUSD BUY",
            message="BUY XAUUSD size=0.1 @ 2050.00",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}

        with patch("src.monitoring.alerting.channels.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            result = await channel.send(alert)

        assert result is True
        mock_client.post.assert_awaited_once()
        call_url = mock_client.post.call_args[0][0]
        assert "botTEST_TOKEN" in call_url
        assert "sendMessage" in call_url

    @pytest.mark.asyncio
    async def test_send_api_error(self):
        """TelegramChannel returns False on API error."""
        channel = TelegramChannel(bot_token="BAD_TOKEN", chat_id="12345")
        alert = Alert(
            alert_type=AlertType.CIRCUIT_BREAKER,
            severity=AlertSeverity.CRITICAL,
            title="Test",
            message="Test",
        )
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"ok": False, "description": "Unauthorized"}

        with patch("src.monitoring.alerting.channels.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            result = await channel.send(alert)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_unconfigured(self):
        """TelegramChannel returns False when not configured."""
        channel = TelegramChannel(bot_token="", chat_id="")
        alert = Alert(
            alert_type=AlertType.TRADE_OPENED,
            severity=AlertSeverity.INFO,
            title="T",
            message="M",
        )
        result = await channel.send(alert)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_network_error(self):
        """TelegramChannel returns False on network error."""
        channel = TelegramChannel(bot_token="TOKEN", chat_id="123")
        alert = Alert(
            alert_type=AlertType.TRADE_CLOSED,
            severity=AlertSeverity.WARNING,
            title="T",
            message="M",
        )

        with patch("src.monitoring.alerting.channels.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

            result = await channel.send(alert)

        assert result is False


@pytest.mark.unit
class TestAlertManagerTelegramInit:
    """Tests for AlertManager Telegram channel initialization."""

    def test_initializes_telegram_when_configured(self):
        """AlertManager adds TelegramChannel when env vars are set."""
        mock_settings = MagicMock()
        mock_settings.alert_email_enabled = False
        mock_settings.alert_slack_enabled = False
        mock_settings.alert_webhook_enabled = False
        mock_settings.alert_telegram_enabled = True
        mock_settings.telegram_bot_token = "TEST_BOT_TOKEN"
        mock_settings.telegram_chat_id = "TEST_CHAT_ID"

        with patch("src.monitoring.alerting.alert_manager.get_settings", return_value=mock_settings):
            from src.monitoring.alerting.alert_manager import AlertManager
            am = AlertManager()

        assert any(isinstance(ch, TelegramChannel) for ch in am.channels)
        # InAppChannel is always present + TelegramChannel
        assert len(am.channels) == 2

    def test_skips_telegram_when_disabled(self):
        """AlertManager does NOT add TelegramChannel when disabled."""
        mock_settings = MagicMock()
        mock_settings.alert_email_enabled = False
        mock_settings.alert_slack_enabled = False
        mock_settings.alert_webhook_enabled = False
        mock_settings.alert_telegram_enabled = False

        with patch("src.monitoring.alerting.alert_manager.get_settings", return_value=mock_settings):
            from src.monitoring.alerting.alert_manager import AlertManager
            am = AlertManager()

        assert not any(isinstance(ch, TelegramChannel) for ch in am.channels)


@pytest.mark.unit
class TestAlertTypes:
    """Tests for new AlertType enum values."""

    def test_trade_opened_type(self):
        assert AlertType.TRADE_OPENED == "TRADE_OPENED"

    def test_trade_closed_type(self):
        assert AlertType.TRADE_CLOSED == "TRADE_CLOSED"

    def test_signal_generated_type(self):
        assert AlertType.SIGNAL_GENERATED == "SIGNAL_GENERATED"
