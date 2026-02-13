"""
Tests for advanced circuit breakers.
"""

import time
from unittest.mock import patch

import pytest

from src.risk.circuit_breakers import (
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerType,
)


@pytest.mark.unit
@pytest.mark.risk
class TestCircuitBreakerManager:
    """Tests for CircuitBreakerManager."""

    def _make_manager(self, **kwargs) -> CircuitBreakerManager:
        config = CircuitBreakerConfig(**kwargs)
        return CircuitBreakerManager(config=config)

    def test_default_no_trip(self):
        """All clear when no limits breached."""
        mgr = self._make_manager()
        mgr.heartbeat()
        ok, reasons = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is True
        assert reasons == []
        assert mgr.is_tripped is False

    def test_daily_loss_trip(self):
        """Daily loss exceeding limit trips breaker."""
        mgr = self._make_manager(daily_loss_limit=0.03)
        mgr.heartbeat()
        ok, reasons = mgr.check_all(daily_pnl_pct=-0.04, open_position_count=0)
        assert ok is False
        assert any("Daily loss" in r for r in reasons)
        assert CircuitBreakerType.DAILY_LOSS.value in mgr.tripped_breakers

    def test_daily_loss_not_tripped_within_limit(self):
        """Daily loss within limit does not trip."""
        mgr = self._make_manager(daily_loss_limit=0.03)
        mgr.heartbeat()
        ok, _ = mgr.check_all(daily_pnl_pct=-0.02, open_position_count=0)
        assert ok is True

    def test_consecutive_losses_trip(self):
        """Consecutive losses exceeding limit trips breaker."""
        mgr = self._make_manager(max_consecutive_losses=3)
        mgr.heartbeat()
        mgr.record_trade_result(is_win=False)
        mgr.record_trade_result(is_win=False)
        mgr.record_trade_result(is_win=False)
        ok, reasons = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is False
        assert any("Consecutive" in r for r in reasons)

    def test_consecutive_losses_reset_on_win(self):
        """Winning trade resets consecutive loss counter."""
        mgr = self._make_manager(max_consecutive_losses=3)
        mgr.heartbeat()
        mgr.record_trade_result(is_win=False)
        mgr.record_trade_result(is_win=False)
        mgr.record_trade_result(is_win=True)
        ok, _ = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is True

    def test_max_positions_trip(self):
        """Too many open positions trips breaker."""
        mgr = self._make_manager(max_open_positions=3)
        mgr.heartbeat()
        ok, reasons = mgr.check_all(daily_pnl_pct=0.0, open_position_count=3)
        assert ok is False
        assert any("positions" in r.lower() for r in reasons)

    def test_max_positions_within_limit(self):
        """Positions within limit does not trip."""
        mgr = self._make_manager(max_open_positions=6)
        mgr.heartbeat()
        ok, _ = mgr.check_all(daily_pnl_pct=0.0, open_position_count=5)
        assert ok is True

    def test_volatility_spike_trip(self):
        """Volatility spike trips breaker."""
        mgr = self._make_manager(volatility_spike_multiplier=3.0)
        mgr.heartbeat()
        ok, reasons = mgr.check_all(
            daily_pnl_pct=0.0,
            open_position_count=0,
            current_atr=15.0,
            baseline_atr=3.0,
        )
        assert ok is False
        assert any("Volatility" in r for r in reasons)

    def test_volatility_spike_within_limit(self):
        """Volatility within limit does not trip."""
        mgr = self._make_manager(volatility_spike_multiplier=5.0)
        mgr.heartbeat()
        ok, _ = mgr.check_all(
            daily_pnl_pct=0.0,
            open_position_count=0,
            current_atr=10.0,
            baseline_atr=3.0,
        )
        assert ok is True

    def test_heartbeat_timeout_trip(self):
        """Heartbeat timeout trips breaker."""
        mgr = self._make_manager(heartbeat_timeout_seconds=5.0)
        # Set heartbeat to old time
        mgr._last_heartbeat = time.monotonic() - 10.0
        ok, reasons = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is False
        assert any("Heartbeat" in r for r in reasons)

    def test_heartbeat_clears_timeout(self):
        """Calling heartbeat clears timeout breaker."""
        mgr = self._make_manager(heartbeat_timeout_seconds=5.0)
        mgr._last_heartbeat = time.monotonic() - 10.0
        mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert mgr.is_tripped
        mgr.heartbeat()
        ok, _ = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is True

    def test_slippage_anomaly_trip(self):
        """Excessive slippage trips breaker."""
        mgr = self._make_manager(
            slippage_threshold_pct=0.003,
            slippage_window=3,
        )
        mgr.heartbeat()
        mgr.record_slippage(0.005)
        mgr.record_slippage(0.004)
        mgr.record_slippage(0.006)
        ok, reasons = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is False
        assert any("Slippage" in r for r in reasons)

    def test_slippage_within_limit(self):
        """Normal slippage does not trip."""
        mgr = self._make_manager(
            slippage_threshold_pct=0.005,
            slippage_window=3,
        )
        mgr.heartbeat()
        mgr.record_slippage(0.001)
        mgr.record_slippage(0.002)
        mgr.record_slippage(0.001)
        ok, _ = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is True

    def test_auto_reset(self):
        """Breakers auto-reset after cooldown period."""
        mgr = self._make_manager(
            daily_loss_limit=0.03,
            auto_reset_after_minutes=5,  # minimum allowed
        )
        mgr.heartbeat()
        # Trip the breaker
        mgr.check_all(daily_pnl_pct=-0.05, open_position_count=0)
        assert mgr.is_tripped

        # Simulate time passing beyond cooldown (6 min > 5 min)
        for cb_type in list(mgr._tripped_at.keys()):
            mgr._tripped_at[cb_type] = time.monotonic() - 360  # 6 min ago

        # Should auto-reset
        ok, _ = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is True

    def test_manual_reset_all(self):
        """Manual reset clears all breakers."""
        mgr = self._make_manager(daily_loss_limit=0.03)
        mgr.heartbeat()
        mgr.check_all(daily_pnl_pct=-0.05, open_position_count=0)
        assert mgr.is_tripped
        reset_types = mgr.reset_all()
        assert len(reset_types) > 0
        assert mgr.is_tripped is False

    def test_multiple_breakers_combined(self):
        """Multiple breakers can trip simultaneously."""
        mgr = self._make_manager(
            daily_loss_limit=0.03,
            max_open_positions=3,
        )
        mgr.heartbeat()
        ok, reasons = mgr.check_all(daily_pnl_pct=-0.05, open_position_count=5)
        assert ok is False
        assert len(reasons) >= 2

    def test_reset_daily(self):
        """reset_daily clears daily loss breaker."""
        mgr = self._make_manager(daily_loss_limit=0.03)
        mgr.heartbeat()
        mgr.check_all(daily_pnl_pct=-0.05, open_position_count=0)
        assert mgr.is_tripped
        mgr.reset_daily()
        # After reset, daily loss breaker is cleared
        ok, _ = mgr.check_all(daily_pnl_pct=0.0, open_position_count=0)
        assert ok is True

    def test_get_status(self):
        """get_status returns all relevant info."""
        mgr = self._make_manager()
        mgr.heartbeat()
        status = mgr.get_status()
        assert "is_tripped" in status
        assert "consecutive_losses" in status
        assert status["is_tripped"] is False

    def test_baseline_atr_tracking(self):
        """Baseline ATR can be stored and retrieved."""
        mgr = self._make_manager()
        mgr.update_baseline_atr("XAUUSD", 5.0)
        assert mgr.get_baseline_atr("XAUUSD") == 5.0
        assert mgr.get_baseline_atr("BTCUSD") is None
