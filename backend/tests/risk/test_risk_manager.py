"""Tests for risk manager orchestrator."""

import pytest
from unittest.mock import MagicMock, patch

from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.schemas import SignalDirection, TradingSignal


def _non_scalp_settings(min_risk_amount_usd: float = 0.0, min_notional_usd: float = 0.0):
    """Settings mock used by the legacy risk-manager tests.

    The two USD floors default to 0 so older tests written before the floors
    existed keep passing. New tests pass explicit values to exercise the
    floor logic.
    """
    s = MagicMock()
    s.scalp_mode_enabled = False
    s.min_risk_amount_usd = min_risk_amount_usd
    s.min_notional_usd = min_notional_usd
    return s


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
    @pytest.fixture(autouse=True)
    def _disable_scalp(self):
        with patch("src.risk.risk_manager.get_settings", return_value=_non_scalp_settings()):
            yield

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

    def test_usdjpy_notional_uses_size_only_for_account_base_pair(self):
        """USDJPY: account=USD == pair base. Notional in USD == size,
        NOT size*level (which would yield JPY-denominated phantom notional).

        Regression for the 2026-04-27 production rejection: a single
        100-USD USDJPY SELL produced exposure 179.6% (== 100 * 159.286 /
        8868) instead of the real 1.1% (== 100 / 8868).
        """
        limits = RiskLimits(max_total_exposure=0.80)
        rm = RiskManager(initial_equity=8868.14, limits=limits)

        open_positions = [
            {
                "epic": "USDJPY",
                "direction": "SELL",
                "size": 100.0,
                "level": 159.286,
                "currency": "JPY",
            },
        ]
        signal = _make_signal(epic="EURUSD")
        result = rm.check_trade(
            signal=signal, equity=8868.14, atr=0.001,
            open_positions=open_positions,
        )
        # 100 / 8868 ≈ 1.1% — well below the 80% cap → must approve.
        assert result.approved is True, (
            f"Expected approval; got rejection: {result.rejection_reason}"
        )

    def test_eurusd_notional_uses_size_times_level(self):
        """EURUSD: quote=USD matches account → size*level still applies.

        Confirms the fix doesn't break the standard case for FX pairs
        whose quote currency IS the account currency.
        """
        limits = RiskLimits(max_total_exposure=0.50)
        rm = RiskManager(initial_equity=10000.0, limits=limits)

        # 5000 EUR @ 1.10 USD/EUR → 5500 USD notional, 55% exposure → reject.
        open_positions = [
            {
                "epic": "EURUSD",
                "direction": "BUY",
                "size": 5000.0,
                "level": 1.10,
                "currency": "USD",
            },
        ]
        signal = _make_signal(epic="GBPUSD")
        result = rm.check_trade(
            signal=signal, equity=10000.0, atr=0.001,
            open_positions=open_positions,
        )
        assert result.approved is False
        assert "Total exposure" in result.rejection_reason

    def test_min_risk_floor_lifts_size_when_under_cap(self):
        """USDJPY with pip-aware risk computation gets size-lifted to the
        MIN_RISK_AMOUNT_USD floor when the lift is within the exposure cap.
        """
        with patch(
            "src.risk.risk_manager.get_settings",
            return_value=_non_scalp_settings(min_risk_amount_usd=5.0),
        ):
            rm = RiskManager(initial_equity=10000.0)
            # USDJPY entry 159, ATR 0.05 → SL distance 0.10 (mult 2.0).
            # Risk per unit = 0.10 / 159 ≈ 0.000629 USD.
            # To reach $5 floor → size ≈ 7948.
            # Exposure cap = 20% × 10000 / 159 ≈ 12.58 — far below the lift,
            # so the lift hits the cap → expect rejection.
            signal = _make_signal(epic="USDJPY", price=159.0)
            result = rm.check_trade(signal=signal, equity=10000.0, atr=0.05)
            assert result.approved is False
            assert "min_notional" in (result.rejection_reason or "").lower()
            audit = result.audit.get("min_risk_floor", {}) if result.audit else {}
            assert audit.get("approved") is False
            assert audit["computed_risk_usd"] < 5.0

    def test_min_risk_floor_off_when_zero(self):
        """Default test fixture sets min_risk_amount_usd=0 → floor disabled
        and tiny-risk forex trade is approved (legacy behaviour).
        """
        rm = RiskManager(initial_equity=10000.0)
        signal = _make_signal(epic="USDJPY", price=159.0)
        result = rm.check_trade(signal=signal, equity=10000.0, atr=0.05)
        # Floor disabled → no rejection from this path. Trade may still
        # fail other checks, but not min_notional.
        if not result.approved:
            assert "min_notional" not in (result.rejection_reason or "").lower()

    def test_min_risk_floor_passes_for_realistic_btc_trade(self):
        """BTC trade with stop_distance large enough to clear $5 floor is
        approved without size lift.
        """
        with patch(
            "src.risk.risk_manager.get_settings",
            return_value=_non_scalp_settings(min_risk_amount_usd=5.0),
        ):
            rm = RiskManager(initial_equity=100000.0)
            # BTCUSD 60000, ATR 200 → SL distance 400. Size cap 20% ×
            # 100000 / 60000 = 0.333. Risk = 0.333 × 400 = $133 — well above $5.
            signal = _make_signal(epic="BTCUSD", price=60000.0)
            result = rm.check_trade(signal=signal, equity=100000.0, atr=200.0)
            assert result.approved is True
            audit = result.audit.get("min_risk_floor", {}) if result.audit else {}
            assert audit.get("approved") is True
            assert audit["computed_risk_usd"] >= 5.0

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
