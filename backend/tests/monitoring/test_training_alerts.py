"""Tests for training alert methods."""
import pytest
from unittest.mock import AsyncMock, patch

from src.monitoring.alerting.schemas import AlertType, AlertSeverity
from src.monitoring.alerting.alert_manager import AlertManager


class TestTrainingAlerts:
    @pytest.fixture
    def manager(self):
        with patch("src.monitoring.alerting.alert_manager.get_settings") as mock_settings:
            mock_settings.return_value.alerts_enabled = False
            mock_settings.return_value.alert_telegram_enabled = False
            mock_settings.return_value.alert_email_enabled = False
            mock_settings.return_value.alert_slack_enabled = False
            mock_settings.return_value.alert_webhook_enabled = False
            return AlertManager()

    @pytest.mark.asyncio
    async def test_alert_training_started(self, manager):
        manager.send_alert = AsyncMock(return_value={})
        await manager.alert_training_started("XAUUSD")
        manager.send_alert.assert_called_once()
        alert = manager.send_alert.call_args[0][0]
        assert alert.alert_type == AlertType.TRAINING_STARTED
        assert "XAUUSD" in alert.title

    @pytest.mark.asyncio
    async def test_alert_training_complete(self, manager):
        manager.send_alert = AsyncMock(return_value={})
        await manager.alert_training_complete("XAUUSD", f1=0.58, accuracy=0.62, duration_s=120.5)
        manager.send_alert.assert_called_once()
        alert = manager.send_alert.call_args[0][0]
        assert alert.alert_type == AlertType.TRAINING_COMPLETE
        assert alert.severity == AlertSeverity.INFO
        assert "0.58" in alert.message

    @pytest.mark.asyncio
    async def test_alert_training_failed(self, manager):
        manager.send_alert = AsyncMock(return_value={})
        await manager.alert_training_failed("BTCUSD", error="Out of memory")
        alert = manager.send_alert.call_args[0][0]
        assert alert.alert_type == AlertType.TRAINING_FAILED
        assert alert.severity == AlertSeverity.CRITICAL
