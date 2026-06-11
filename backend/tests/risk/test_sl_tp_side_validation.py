"""
Tests for §4-quater side validation in RiskManager.check_trade (audit M1.7).

A side-inverted SL/TP pair (e.g. BUY with SL >= entry, or SELL with SL <= entry)
must be rejected at the gate — never silently approved because R:R abs() distances
look healthy. This is the 2026-04-28 inversion class.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.broker.models import Direction
from src.models.schemas import SignalClass
from src.risk.risk_manager import RiskManager
from src.strategy.schemas import TradingSignal

# ---------------------------------------------------------------------------
# Shared helpers — mirror the conventions in test_stop_loss_direction_fix.py
# ---------------------------------------------------------------------------


def _non_scalp_settings(min_signal_rr_threshold: float = 0.0):
    """Settings mock that disables optional gates, keeping tests focused on
    §4-quater side validation only.

    min_signal_rr_threshold=0.0 disables §4-ter so an inverted pair that
    sneaks through §4-quater is not incidentally caught by the R:R floor —
    making the distinction between the two gates visible in failures.
    """
    s = MagicMock()
    s.scalp_mode_enabled = False
    s.min_risk_amount_usd = 0.0
    s.min_notional_usd = 0.0
    s.forex_usd_base_size_multiplier = 1.0
    s.forex_max_leverage_multiplier = 1.0
    s.min_signal_rr_threshold = min_signal_rr_threshold
    s.epic_risk_multipliers = {}
    return s


def _build_risk_manager() -> RiskManager:
    """Construct a RiskManager with all downstream dependencies mocked so
    only the §4-quater / §4-ter gates are under test."""
    rm = RiskManager()

    rm.circuit_breakers = MagicMock()
    rm.circuit_breakers.check_epic.return_value = (True, None)
    rm.circuit_breakers.check_all.return_value = (True, [])

    state_mock = Mock()
    state_mock.daily_start_equity = 10_000.0
    state_mock.max_daily_drawdown_pct = 0.05
    state_mock.circuit_breaker_reason = None

    rm.drawdown_monitor = MagicMock()
    rm.drawdown_monitor.state = state_mock
    rm.drawdown_monitor.is_circuit_breaker_active.return_value = False
    rm.drawdown_monitor.check_all.return_value = []
    rm.drawdown_monitor.check_limits.return_value = (True, None)
    rm.drawdown_monitor.update.return_value = None

    rm.correlation_guard = MagicMock()
    rm.correlation_guard.check_exposure_dynamic.return_value = (1.0, [])
    rm.correlation_guard.calculate_correlation_multiplier.return_value = 1.0

    rm.equity_curve_filter = MagicMock()
    rm.equity_curve_filter.get_size_multiplier.return_value = 1.0

    return rm


# ---------------------------------------------------------------------------
# Parametrised rejection cases — all have BOTH suggested_stop AND
# suggested_tp set, exercising the §4-bis trusted-pair path.
# ---------------------------------------------------------------------------

_REJECTION_CASES = [
    pytest.param(
        Direction.BUY,
        SignalClass.BUY,
        100.0,  # entry
        105.0,  # SL above entry — wrong side for BUY
        110.0,  # TP above entry — fine
        id="buy_sl_above_entry",
    ),
    pytest.param(
        Direction.BUY,
        SignalClass.BUY,
        100.0,  # entry
        95.0,  # SL below entry — fine
        98.0,  # TP below entry — wrong side for BUY (TP must be > entry)
        id="buy_tp_below_entry",
    ),
    pytest.param(
        Direction.SELL,
        SignalClass.SELL,
        100.0,  # entry
        95.0,  # SL below entry — wrong side for SELL (SL must be > entry)
        90.0,  # TP below entry — fine
        id="sell_sl_below_entry",
    ),
    pytest.param(
        Direction.SELL,
        SignalClass.SELL,
        100.0,  # entry
        105.0,  # SL above entry — fine
        110.0,  # TP above entry — wrong side for SELL (TP must be < entry)
        id="sell_tp_above_entry",
    ),
]


@pytest.mark.parametrize("direction,sig_class,entry,sl,tp", _REJECTION_CASES)
@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
def test_side_inverted_pair_is_rejected(_mock_settings, direction, sig_class, entry, sl, tp):
    """A side-inverted SL/TP pair must be rejected with 'side' in the reason."""
    rm = _build_risk_manager()

    signal = TradingSignal(
        epic="XAUUSD",
        direction=direction,
        entry_price=entry,
        confidence=0.75,
        suggested_stop=sl,
        suggested_tp=tp,
        signal_class=sig_class,
    )

    result = rm.check_trade(
        signal=signal,
        equity=10_000.0,
        atr=2.0,
        open_positions=[],
        trade_history=[],
    )

    assert result.approved is False, (
        f"Expected rejection for {direction.value} entry={entry} SL={sl} TP={tp} "
        f"but got approved=True"
    )
    assert result.rejection_reason is not None
    assert (
        "side" in result.rejection_reason.lower()
    ), f"Expected 'side' in rejection_reason but got: {result.rejection_reason!r}"


# ---------------------------------------------------------------------------
# Control test — correctly-sided pair with healthy R:R must NOT be rejected
# on side grounds.  The rejection_reason must not mention "side".
# ---------------------------------------------------------------------------


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
def test_correctly_sided_pair_passes_side_gate(_mock_settings):
    """BUY entry=100 SL=98 TP=104 is a valid pair — side gate must not reject it.

    The signal has an R:R of 2.0 so §4-ter is irrelevant (threshold=0.0).
    Downstream gates (sizing, equity, exposure) are all mocked to pass.
    """
    rm = _build_risk_manager()

    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.BUY,
        entry_price=100.0,
        confidence=0.75,
        suggested_stop=98.0,  # below entry — correct for BUY
        suggested_tp=104.0,  # above entry — correct for BUY, R:R=2.0
        signal_class=SignalClass.BUY,
    )

    result = rm.check_trade(
        signal=signal,
        equity=10_000.0,
        atr=2.0,
        open_positions=[],
        trade_history=[],
    )

    # Must pass the side gate — if rejected for another reason that's fine,
    # but "side" must not appear in the rejection reason.
    if not result.approved:
        assert result.rejection_reason is not None
        assert (
            "side" not in result.rejection_reason.lower()
        ), f"Side gate incorrectly rejected a valid pair: {result.rejection_reason!r}"
