"""Tests that TradeLogger fires AlertManager for DEMO/LIVE trade events."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.monitoring.trade_logger import TradeLogger, ExecutionStatus, RiskEventType


@pytest.mark.unit
class TestTradeLoggerAlertWiring:
    """Tests for alert integration in TradeLogger."""

    @pytest.mark.asyncio
    async def test_log_execution_fires_alert_in_demo_mode(self, tmp_path):
        """log_execution() calls alert_manager.alert_trade_opened() for demo_trading source."""
        tl = TradeLogger(log_dir=tmp_path)

        mock_alert_mgr = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.alerts_enabled = True

        with (
            patch("src.monitoring.alerting.alert_manager.get_alert_manager", return_value=mock_alert_mgr),
            patch("src.utils.config.get_settings", return_value=mock_settings),
        ):
            await tl.log_execution(
                epic="XAUUSD", direction="BUY", size=0.1,
                entry_price=2050.0, status=ExecutionStatus.EXECUTED,
                deal_id="DEAL-001", stop_loss=2020.0, take_profit=2100.0,
                source="demo_trading",
            )

        mock_alert_mgr.alert_trade_opened.assert_awaited_once_with(
            epic="XAUUSD",
            direction="BUY",
            size=0.1,
            entry_price=2050.0,
            deal_id="DEAL-001",
            stop_loss=2020.0,
            take_profit=2100.0,
        )

    @pytest.mark.asyncio
    async def test_log_execution_no_alert_for_paper_mode(self, tmp_path):
        """log_execution() does NOT call alert for paper_trading source."""
        tl = TradeLogger(log_dir=tmp_path)

        mock_alert_mgr = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.alerts_enabled = True

        with (
            patch("src.monitoring.alerting.alert_manager.get_alert_manager", return_value=mock_alert_mgr),
            patch("src.utils.config.get_settings", return_value=mock_settings),
        ):
            await tl.log_execution(
                epic="XAUUSD", direction="BUY", size=0.1,
                entry_price=2050.0, status=ExecutionStatus.EXECUTED,
                deal_id="DEAL-001", source="paper_trading",
            )

        mock_alert_mgr.alert_trade_opened.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_execution_no_alert_when_rejected(self, tmp_path):
        """log_execution() does NOT alert on REJECTED status even in demo mode."""
        tl = TradeLogger(log_dir=tmp_path)

        mock_alert_mgr = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.alerts_enabled = True

        with (
            patch("src.monitoring.alerting.alert_manager.get_alert_manager", return_value=mock_alert_mgr),
            patch("src.utils.config.get_settings", return_value=mock_settings),
        ):
            await tl.log_execution(
                epic="XAUUSD", direction="BUY", size=0.1,
                entry_price=2050.0, status=ExecutionStatus.REJECTED,
                source="demo_trading",
            )

        mock_alert_mgr.alert_trade_opened.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_risk_fires_alert_on_circuit_breaker(self, tmp_path):
        """log_risk_decision() fires circuit breaker alert when alerts_enabled."""
        tl = TradeLogger(log_dir=tmp_path)

        mock_alert_mgr = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.alerts_enabled = True

        with (
            patch("src.monitoring.alerting.alert_manager.get_alert_manager", return_value=mock_alert_mgr),
            patch("src.utils.config.get_settings", return_value=mock_settings),
        ):
            await tl.log_risk_decision(
                event_type=RiskEventType.CIRCUIT_BREAKER,
                description="Daily loss limit exceeded",
                action="stopped_trading",
                epic="XAUUSD",
                consecutive_losses=5,
                source="demo_trading",
            )

        mock_alert_mgr.alert_circuit_breaker.assert_awaited_once_with(
            epic="XAUUSD",
            reason="Daily loss limit exceeded",
            consecutive_losses=5,
        )

    @pytest.mark.asyncio
    async def test_log_risk_no_alert_for_non_circuit_breaker(self, tmp_path):
        """log_risk_decision() does NOT alert for POSITION_LIMIT events."""
        tl = TradeLogger(log_dir=tmp_path)

        mock_alert_mgr = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.alerts_enabled = True

        with (
            patch("src.monitoring.alerting.alert_manager.get_alert_manager", return_value=mock_alert_mgr),
            patch("src.utils.config.get_settings", return_value=mock_settings),
        ):
            await tl.log_risk_decision(
                event_type=RiskEventType.POSITION_LIMIT,
                description="Max positions reached",
                action="rejected_trade",
            )

        mock_alert_mgr.alert_circuit_breaker.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_alert_failure_does_not_break_logging(self, tmp_path):
        """Alert failure is caught and does not prevent log writing."""
        tl = TradeLogger(log_dir=tmp_path)

        mock_settings = MagicMock()
        mock_settings.alerts_enabled = True

        with (
            patch(
                "src.monitoring.alerting.alert_manager.get_alert_manager",
                side_effect=Exception("AlertManager init failed"),
            ),
            patch("src.utils.config.get_settings", return_value=mock_settings),
        ):
            # Should NOT raise — alert failure is caught
            await tl.log_execution(
                epic="XAUUSD", direction="BUY", size=0.1,
                entry_price=2050.0, status=ExecutionStatus.EXECUTED,
                deal_id="DEAL-001", source="demo_trading",
            )

        # Verify log file was still written (fallback)
        assert (tmp_path / "executions.jsonl").exists()
