"""Tests for risk manager orchestrator."""

import pytest

from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.schemas import SignalDirection, TradingSignal


def _make_signal(
    epic="XAUUSD", direction=SignalDirection.BUY, confidence=0.80, price=2000.0
) -> TradingSignal:
    return TradingSignal(
        epic=epic,
        direction=direction,
        confidence=confidence,
        signal_class=2,
        entry_price=price,
    )


class TestRiskManager:
    def test_approves_valid_trade(self):
        rm = RiskManager(initial_equity=10000.0)
        signal = _make_signal()
        result = rm.check_trade(signal, equity=10000.0, atr=20.0)
        assert result.approved is True
        assert result.position_size > 0
        assert result.stop_loss > 0
        assert result.take_profit > 0

    def test_rejects_when_circuit_breaker_active(self):
        rm = RiskManager(initial_equity=10000.0)
        rm.drawdown_monitor.activate_circuit_breaker("Circuit breaker: test halt")
        signal = _make_signal()
        result = rm.check_trade(signal, equity=10000.0, atr=20.0)
        assert result.approved is False
        assert result.rejection_reason is not None

    def test_rejects_on_total_drawdown(self):
        rm = RiskManager(initial_equity=10000.0)
        signal = _make_signal()
        # Equity dropped 20% -> exceeds default 15% limit (or circuit breaker daily loss)
        result = rm.check_trade(signal, equity=8000.0, atr=20.0)
        assert result.approved is False
        reason = result.rejection_reason.lower()
        assert "drawdown" in reason or "daily loss" in reason

    def test_rejects_on_daily_drawdown(self):
        rm = RiskManager(initial_equity=10000.0)
        signal = _make_signal()
        # Equity dropped 6% today -> exceeds default 5% limit
        result = rm.check_trade(signal, equity=9400.0, atr=20.0)
        assert result.approved is False

    def test_correlation_adjusts_size(self):
        rm = RiskManager(initial_equity=10000.0)
        signal = _make_signal(epic="XAUUSD", direction=SignalDirection.BUY)
        positions = [{"epic": "BTCUSD", "direction": "BUY"}]
        result = rm.check_trade(signal, equity=10000.0, atr=20.0, open_positions=positions)
        assert result.approved is True
        assert len(result.adjustments) > 0  # Has correlation warning

        # Compare with uncorrelated
        result_nocorr = rm.check_trade(signal, equity=10000.0, atr=20.0, open_positions=[])
        assert result.position_size < result_nocorr.position_size

    def test_update_equity(self):
        rm = RiskManager(initial_equity=10000.0)
        state = rm.update_equity(11000.0)
        assert state.peak_equity == 11000.0
        assert state.current_equity == 11000.0

    def test_reset_daily(self):
        rm = RiskManager(initial_equity=10000.0)
        rm.update_equity(9500.0)
        rm.reset_daily()
        assert rm.drawdown_monitor.state.daily_pnl == 0.0

    def test_custom_limits(self):
        # Use low entry price so we don't hit the position cap
        signal = _make_signal(price=10.0)
        limits = RiskLimits(max_risk_per_trade=0.01, max_position_pct=0.50)
        rm = RiskManager(initial_equity=10000.0, limits=limits)
        result = rm.check_trade(signal, equity=10000.0, atr=0.5)
        assert result.approved is True
        # 1% risk should produce smaller size than default 2%
        rm2 = RiskManager(
            initial_equity=10000.0,
            limits=RiskLimits(max_risk_per_trade=0.02, max_position_pct=0.50),
        )
        result2 = rm2.check_trade(signal, equity=10000.0, atr=0.5)
        assert result.position_size < result2.position_size

    def test_max_total_positions_limit(self):
        """Test that RiskManager rejects new positions when total limit reached."""
        limits = RiskLimits(max_total_open_positions=3)
        rm = RiskManager(initial_equity=10000.0, limits=limits)

        # Simulate 3 open positions
        open_positions = [
            {"epic": "XAUUSD", "direction": "BUY", "size": 1.0},
            {"epic": "BTCUSD", "direction": "BUY", "size": 0.5},
            {"epic": "US500", "direction": "SELL", "size": 2.0},
        ]

        # 4th position should be rejected
        signal = _make_signal(epic="NVDA", direction=SignalDirection.BUY)
        result = rm.check_trade(
            signal=signal,
            equity=10000.0,
            atr=5.0,
            open_positions=open_positions,
        )

        assert result.approved is False
        assert "Max total positions reached" in result.rejection_reason
        assert "3/3" in result.rejection_reason

    def test_rejects_when_total_exposure_exceeded(self):
        """Reject trades when total notional / equity exceeds max_total_exposure."""
        limits = RiskLimits(max_total_exposure=0.50)
        rm = RiskManager(initial_equity=10000.0, limits=limits)

        # Positions with notional = 0.5 * 2000 + 1.0 * 68000 = 69000
        # exposure = 69000 / 10000 = 6.9 → way over 0.50
        open_positions = [
            {"epic": "XAUUSD", "direction": "BUY", "size": 0.5, "level": 2000.0},
            {"epic": "BTCUSD", "direction": "BUY", "size": 1.0, "level": 68000.0},
        ]
        signal = _make_signal(epic="US500")
        result = rm.check_trade(
            signal=signal, equity=10000.0, atr=20.0,
            open_positions=open_positions,
        )
        assert result.approved is False
        assert "Total exposure" in result.rejection_reason

    def test_approves_when_exposure_under_limit(self):
        """Approve trades when exposure is below the cap."""
        limits = RiskLimits(max_total_exposure=0.50)
        rm = RiskManager(initial_equity=100000.0, limits=limits)

        # Notional = 0.01 * 2000 = 20, exposure = 20 / 100000 ≈ 0.0002
        open_positions = [
            {"epic": "XAUUSD", "direction": "BUY", "size": 0.01, "level": 2000.0},
        ]
        signal = _make_signal(epic="BTCUSD")
        result = rm.check_trade(
            signal=signal, equity=100000.0, atr=20.0,
            open_positions=open_positions,
        )
        assert result.approved is True

    def test_exposure_check_skipped_when_default(self):
        """Default max_total_exposure=1.0 skips the check entirely."""
        rm = RiskManager(initial_equity=10000.0)
        assert rm.limits.max_total_exposure == 1.0

        # Even with huge notional, should pass (cap disabled)
        open_positions = [
            {"epic": "BTCUSD", "direction": "BUY", "size": 10.0, "level": 68000.0},
        ]
        signal = _make_signal(epic="XAUUSD")
        result = rm.check_trade(
            signal=signal, equity=10000.0, atr=20.0,
            open_positions=open_positions,
        )
        # Should NOT be rejected for exposure (may be rejected for other reasons
        # but not for "Total exposure")
        if not result.approved:
            assert "Total exposure" not in (result.rejection_reason or "")
