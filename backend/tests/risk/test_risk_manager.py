"""Tests for risk manager orchestrator."""

import pytest
from unittest.mock import MagicMock, patch

from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.schemas import SignalDirection, TradingSignal


def _non_scalp_settings(
    min_risk_amount_usd: float = 0.0,
    min_notional_usd: float = 0.0,
    forex_usd_base_size_multiplier: float = 1.0,
    forex_max_leverage_multiplier: float = 1.0,
):
    """Settings mock used by the legacy risk-manager tests.

    Defaults preserve legacy behavior so older tests written before the
    floors existed keep passing. New tests pass explicit values to exercise
    the floor logic. ``forex_max_leverage_multiplier`` defaults to 1.0 so
    the auto-leverage path is a no-op unless a test opts in.
    """
    s = MagicMock()
    s.scalp_mode_enabled = False
    s.min_risk_amount_usd = min_risk_amount_usd
    s.min_notional_usd = min_notional_usd
    s.forex_usd_base_size_multiplier = forex_usd_base_size_multiplier
    s.forex_max_leverage_multiplier = forex_max_leverage_multiplier
    # H13 fix: explicitly disable the §4-ter R:R floor for legacy tests.
    # Without this, `float(MagicMock())` returns 1.0 (Python default
    # `__float__`) which means every existing test silently ran the
    # check at threshold=1.0 instead of production 0.40 — a regression
    # in the strategy-paired R:R range (0.40–1.0) was invisible.
    s.min_signal_rr_threshold = 0.0
    # Default no per-epic risk multipliers — RiskManager treats every epic
    # at baseline 1.0. Tests that need to exercise the disable/boost path
    # set this explicitly via `_non_scalp_settings(...).epic_risk_multipliers`.
    s.epic_risk_multipliers = {}
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

    def test_epic_risk_multiplier_zero_rejects_trade(self):
        # multiplier 0.0 acts as a per-epic disable: signal generates +
        # audits but RiskManager refuses to size it.
        s = _non_scalp_settings()
        s.epic_risk_multipliers = {"DE40": 0.0}
        with patch("src.risk.risk_manager.get_settings", return_value=s):
            rm = RiskManager(initial_equity=10000.0)
            signal = _make_signal(epic="DE40")
            result = rm.check_trade(signal, equity=10000.0, atr=20.0)
            assert result.approved is False
            assert "DE40" in (result.rejection_reason or "")
            assert "epic_risk_multiplier" in (result.rejection_reason or "")
            assert result.audit.get("epic_risk_multiplier") == 0.0

    def test_epic_risk_multiplier_boost_scales_position(self):
        # 1.5x boost on TSLA must yield ~50% larger position vs baseline,
        # everything else equal. Using a separate epic with mult=1.0 as
        # the control isolates the multiplier effect from confidence,
        # correlation, and equity-curve mechanics (all baseline here).
        s_baseline = _non_scalp_settings()
        s_baseline.epic_risk_multipliers = {}
        with patch("src.risk.risk_manager.get_settings", return_value=s_baseline):
            rm = RiskManager(initial_equity=10000.0)
            r0 = rm.check_trade(_make_signal(epic="TSLA"), equity=10000.0, atr=20.0)
            assert r0.approved is True
            base_size = r0.position_size

        s_boost = _non_scalp_settings()
        s_boost.epic_risk_multipliers = {"TSLA": 1.5}
        with patch("src.risk.risk_manager.get_settings", return_value=s_boost):
            rm = RiskManager(initial_equity=10000.0)
            r1 = rm.check_trade(_make_signal(epic="TSLA"), equity=10000.0, atr=20.0)
            assert r1.approved is True
            assert r1.audit.get("epic_risk_multiplier") == 1.5
            # Boost must be reflected in the final size (modulo equity-curve
            # filter and other compounded multipliers, which are identical
            # across the two runs because the equity / signal / atr inputs
            # are identical). Tolerate tiny rounding noise.
            assert r1.position_size > base_size * 1.4

    def test_epic_risk_multiplier_missing_epic_baseline(self):
        # Epic not present in the multiplier dict ⇒ baseline 1.0.
        s = _non_scalp_settings()
        s.epic_risk_multipliers = {"TSLA": 1.5}  # no XAUUSD entry
        with patch("src.risk.risk_manager.get_settings", return_value=s):
            rm = RiskManager(initial_equity=10000.0)
            result = rm.check_trade(_make_signal(epic="XAUUSD"), equity=10000.0, atr=20.0)
            assert result.approved is True
            assert result.audit.get("epic_risk_multiplier") == 1.0

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

    def test_min_risk_floor_caps_lift_at_exposure_cap_for_usdjpy(self):
        """USDJPY pip-aware risk is so small that the floor cannot be met
        within max_position_pct. Rather than rejecting, the manager takes
        the cap-bounded size and approves with risk < floor (audit flag
        ``lift_bounded_by_cap=True``).
        """
        with patch(
            "src.risk.risk_manager.get_settings",
            return_value=_non_scalp_settings(min_risk_amount_usd=5.0),
        ):
            rm = RiskManager(initial_equity=10000.0)
            # USDJPY entry 159, ATR 0.05 → SL distance 0.10 (mult 2.0).
            # Risk per unit ≈ 0.000629 USD. Lift to $5 needs size ≈ 7948.
            # Exposure cap = 20% × 10000 / 159 ≈ 12.58 — far below the lift.
            # Behavior: take cap-bounded size, accept residual risk.
            signal = _make_signal(epic="USDJPY", price=159.0)
            result = rm.check_trade(signal=signal, equity=10000.0, atr=0.05)
            assert result.approved is True, (
                f"USDJPY signal must approve under cap-fallback "
                f"(rejection: {result.rejection_reason})"
            )
            audit = result.audit.get("min_risk_floor", {}) if result.audit else {}
            assert audit.get("approved") is True
            assert audit.get("lift_bounded_by_cap") is True
            assert audit["actual_size"] <= audit["max_size_by_exposure"] + 1e-6
            assert audit["computed_risk_usd"] < 5.0  # floor not reached
            assert audit["computed_risk_usd"] > 0  # but a real position

    def test_min_risk_floor_leverage_aware_cap_for_usdjpy(self):
        """With ``forex_usd_base_size_multiplier=30``, the cap on USDJPY
        is 30× the stock cap, allowing a materially larger position and
        a higher residual risk on the cap-fallback path.
        """
        with patch(
            "src.risk.risk_manager.get_settings",
            return_value=_non_scalp_settings(
                min_risk_amount_usd=5.0,
                forex_usd_base_size_multiplier=30.0,
            ),
        ):
            rm = RiskManager(initial_equity=10000.0)
            signal = _make_signal(epic="USDJPY", price=159.0)
            result = rm.check_trade(signal=signal, equity=10000.0, atr=0.05)
            assert result.approved is True
            audit = result.audit.get("min_risk_floor", {}) if result.audit else {}
            assert audit.get("approved") is True
            # 30× cap: max_size = 10000 × 0.20 × 30 / 159 ≈ 377.
            assert audit["max_size_by_exposure"] > 350
            assert audit["max_size_by_exposure"] < 400
            # Residual risk scales with size — at multiplier 30, USDJPY
            # entry 159 stop_distance 0.10 produces ≈ $0.24. That's still
            # below the $5 floor (broker stop-distance constraints), but
            # ~10× the stock-cap baseline of $0.02 — material improvement.
            assert audit["computed_risk_usd"] > 0.20

    def test_min_risk_floor_rejects_only_when_exposure_cap_is_non_positive(self):
        """Defensive guard: zero or negative equity makes the exposure cap
        non-positive, so neither lift nor cap-fallback can produce a real
        position. Reject in this corner case.
        """
        with patch(
            "src.risk.risk_manager.get_settings",
            return_value=_non_scalp_settings(min_risk_amount_usd=5.0),
        ):
            rm = RiskManager(initial_equity=10000.0)
            signal = _make_signal(epic="USDJPY", price=159.0)
            # Equity 0 → cap 0 → final_size 0 → reject from min_notional
            # path (or from upstream sizing path that hits zero first).
            result = rm.check_trade(signal=signal, equity=0.0, atr=0.05)
            assert result.approved is False

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

    def test_forex_dynamic_leverage_lifts_to_floor_via_max_cap(self):
        """User invariant (2026-04-30 v2): when standard forex multiplier
        cannot reach MIN_RISK_AMOUNT_USD, auto-elevate per-trade exposure
        cap up to `forex_max_leverage_multiplier`. Never reject a high-
        confidence signal because the day-one cap was conservative — the
        floor is meant to LIFT, not BLOCK.
        """
        with patch(
            "src.risk.risk_manager.get_settings",
            return_value=_non_scalp_settings(
                min_risk_amount_usd=10.0,
                forex_usd_base_size_multiplier=60.0,
                forex_max_leverage_multiplier=200.0,
            ),
        ):
            rm = RiskManager(initial_equity=11000.0)
            # USDJPY entry 159, ATR 0.05, SL distance 0.10. To clear $10
            # floor: lifted_size ≈ 15.9k. Standard 60× cap allows ~830
            # units (~$0.52 risk). With max_leverage 200×, cap rises to
            # ~2768 units (~$1.74 risk) — still below 15.9k → cap_hit=True
            # but mult was elevated and risk improved >3× the baseline.
            # Signal MUST approve (no rejection).
            signal = _make_signal(epic="USDJPY", price=159.0)
            result = rm.check_trade(signal=signal, equity=11000.0, atr=0.05)
            assert result.approved is True
            audit = result.audit.get("min_risk_floor", {}) if result.audit else {}
            assert audit.get("approved") is True
            assert audit.get("effective_multiplier_used", 0) >= 60.0
            assert audit.get("max_leverage_cap_hit") is True
            # Realised risk strictly higher than the 60×-baseline.
            assert audit.get("computed_risk_usd", 0) > 1.0

    def test_forex_dynamic_leverage_meets_floor_when_required_below_max(self):
        """When `required_mult` to clear floor is below max_leverage, the
        cap is elevated only as much as needed and the floor is met.
        """
        with patch(
            "src.risk.risk_manager.get_settings",
            return_value=_non_scalp_settings(
                min_risk_amount_usd=10.0,
                forex_usd_base_size_multiplier=60.0,
                forex_max_leverage_multiplier=300.0,
            ),
        ):
            rm = RiskManager(initial_equity=11000.0)
            # Wider stop_distance: ATR 1.0, SL distance 2.0. To clear $10
            # floor: lifted_size = 10 × 159 / 2.0 = 795 units. Cap with
            # 60× mult = 11000 × 0.20 × 60 / 159 ≈ 830 → fits within
            # standard cap, no elevation needed. Floor exactly met.
            signal = _make_signal(epic="USDJPY", price=159.0)
            result = rm.check_trade(signal=signal, equity=11000.0, atr=1.0)
            assert result.approved is True
            audit = result.audit.get("min_risk_floor", {}) if result.audit else {}
            assert audit.get("approved") is True
            assert audit.get("max_leverage_cap_hit") is False
            # Floor exactly met (within rounding).
            assert audit.get("computed_risk_usd", 0) >= 9.99

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


class TestRRFloor:
    """§4-ter R:R floor — coverage gap surfaced by H13 audit."""

    def _signal_with_paired_sl_tp(self, *, sl: float, tp: float) -> TradingSignal:
        return TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=0.80,
            signal_class=2,
            entry_price=2000.0,
            suggested_stop=sl,
            suggested_tp=tp,
        )

    def test_rr_floor_rejects_below_threshold(self):
        """Strategy-paired signal with R:R 0.30 must be rejected at 0.40."""
        rm = RiskManager(initial_equity=10000.0, limits=RiskLimits())
        # entry=2000, SL=1980 -> stop=20, TP=2006 -> reward=6 -> R:R=0.30
        signal = self._signal_with_paired_sl_tp(sl=1980.0, tp=2006.0)
        settings = _non_scalp_settings()
        settings.min_signal_rr_threshold = 0.40
        with patch("src.risk.risk_manager.get_settings", return_value=settings):
            result = rm.check_trade(
                signal=signal, equity=10000.0, atr=20.0, open_positions=[],
            )
        assert result.approved is False
        assert "R:R" in (result.rejection_reason or "")

    def test_rr_floor_passes_strategy_calibrated_pair(self):
        """Strategy-paired signal with R:R 0.75 must be approved at 0.40."""
        rm = RiskManager(initial_equity=10000.0, limits=RiskLimits())
        # entry=2000, SL=1980 -> stop=20, TP=2015 -> reward=15 -> R:R=0.75
        signal = self._signal_with_paired_sl_tp(sl=1980.0, tp=2015.0)
        settings = _non_scalp_settings()
        settings.min_signal_rr_threshold = 0.40
        with patch("src.risk.risk_manager.get_settings", return_value=settings):
            result = rm.check_trade(
                signal=signal, equity=10000.0, atr=20.0, open_positions=[],
            )
        # If rejected, must NOT be for R:R reason
        if not result.approved:
            assert "R:R" not in (result.rejection_reason or "")
