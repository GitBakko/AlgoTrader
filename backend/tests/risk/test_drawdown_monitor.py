"""Tests for drawdown monitor module."""

import pytest

from src.risk.drawdown_monitor import DrawdownMonitor
from src.risk.schemas import RiskLimits


class TestDrawdownMonitor:
    def test_initial_state(self):
        monitor = DrawdownMonitor(initial_equity=10000.0)
        assert monitor.state.peak_equity == 10000.0
        assert monitor.state.current_equity == 10000.0
        assert monitor.state.current_drawdown_pct == 0.0
        assert not monitor.state.circuit_breaker_active

    def test_equity_increase_updates_peak(self):
        monitor = DrawdownMonitor(10000.0)
        monitor.update(11000.0)
        assert monitor.state.peak_equity == 11000.0
        assert monitor.state.current_drawdown_pct == 0.0

    def test_equity_decrease_shows_drawdown(self):
        monitor = DrawdownMonitor(10000.0)
        monitor.update(9000.0)
        # DD = (10000 - 9000) / 10000 = 10%
        assert monitor.state.current_drawdown_pct == pytest.approx(0.10)

    def test_drawdown_after_peak(self):
        monitor = DrawdownMonitor(10000.0)
        monitor.update(12000.0)  # New peak
        monitor.update(10800.0)  # Drawdown from new peak
        # DD = (12000 - 10800) / 12000 = 10%
        assert monitor.state.peak_equity == 12000.0
        assert monitor.state.current_drawdown_pct == pytest.approx(0.10)

    def test_check_limits_within(self):
        monitor = DrawdownMonitor(10000.0)
        monitor.update(9800.0)  # 2% DD
        limits = RiskLimits(max_total_drawdown=0.15, max_daily_drawdown=0.05)
        ok, reason = monitor.check_limits(limits)
        assert ok is True
        assert reason is None

    def test_check_limits_total_dd_breached(self):
        monitor = DrawdownMonitor(10000.0)
        monitor.update(8000.0)  # 20% DD
        limits = RiskLimits(max_total_drawdown=0.15)
        ok, reason = monitor.check_limits(limits)
        assert ok is False
        assert "Total drawdown" in reason

    def test_check_limits_daily_dd_breached(self):
        monitor = DrawdownMonitor(10000.0)
        # Daily start is 10000, drop to 9400 = 6% daily loss
        monitor.update(9400.0)
        limits = RiskLimits(max_daily_drawdown=0.05)
        ok, reason = monitor.check_limits(limits)
        assert ok is False
        assert "Daily drawdown" in reason

    def test_circuit_breaker_activation(self):
        monitor = DrawdownMonitor(10000.0)
        assert not monitor.is_circuit_breaker_active()
        monitor.activate_circuit_breaker("Test reason")
        assert monitor.is_circuit_breaker_active()
        assert monitor.state.circuit_breaker_reason == "Test reason"

    def test_circuit_breaker_deactivation(self):
        monitor = DrawdownMonitor(10000.0)
        monitor.activate_circuit_breaker("Test")
        monitor.deactivate_circuit_breaker()
        assert not monitor.is_circuit_breaker_active()
        assert monitor.state.circuit_breaker_reason is None

    def test_reset_daily(self):
        monitor = DrawdownMonitor(10000.0)
        monitor.update(9500.0)  # Some daily loss
        assert monitor.state.daily_pnl == pytest.approx(-500.0)

        monitor.reset_daily()
        assert monitor.state.daily_start_equity == 9500.0
        assert monitor.state.daily_pnl == 0.0
