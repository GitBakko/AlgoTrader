"""Phase 1 expansion (2026-05-23): activate the total-exposure guard
at the default MAX_TOTAL_EXPOSURE=1.0 by changing the gate from `< 1.0`
to `<= 1.0` in risk_manager.py:212.

Before the fix, the entire enforcement branch was skipped at default 1.0
because the gate read `if self.limits.max_total_exposure < 1.0 and …`.
After the fix it reads `<= 1.0`, so a position summing >= 100% of equity
is rejected with rejection_reason containing "Total exposure".
"""

from unittest.mock import MagicMock, patch

from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.schemas import SignalDirection, TradingSignal


def _signal(epic: str = "EURUSD", entry: float = 1.10, direction: str = "BUY") -> TradingSignal:
    """Minimal BUY/SELL signal with a sane SL/TP pair (R:R = 1.0)."""
    sl = entry - 0.005 if direction == "BUY" else entry + 0.005
    tp = entry + 0.005 if direction == "BUY" else entry - 0.005
    return TradingSignal(
        epic=epic,
        direction=getattr(SignalDirection, direction),
        confidence=0.80,
        signal_class=2 if direction == "BUY" else 0,
        entry_price=entry,
        suggested_stop=sl,
        suggested_tp=tp,
    )


def _settings_stub(min_rr: float = 0.0):
    """Mirror of test_risk_manager._non_scalp_settings — MagicMock so
    env-loading doesn't fight us in CI. ``min_rr=0.0`` disables the
    §4-ter R:R floor so the exposure gate alone decides each test."""
    s = MagicMock()
    s.scalp_mode_enabled = False
    s.min_risk_amount_usd = 0.0
    s.min_notional_usd = 0.0
    s.forex_usd_base_size_multiplier = 1.0
    s.forex_max_leverage_multiplier = 1.0
    s.min_signal_rr_threshold = min_rr
    s.epic_risk_multipliers = {}
    return s


def test_guard_active_at_default_1_0() -> None:
    """At MAX_TOTAL_EXPOSURE=1.0 (default), sum of open notionals beyond
    equity must be rejected. Before the fix the branch was skipped."""
    rm = RiskManager(initial_equity=10_000.0, limits=RiskLimits())  # default 1.0
    # Existing open position with notional = 0.1 * 100_010 = 10001 (>100% equity)
    open_positions = [{"epic": "BTCUSD", "size": 0.1, "level": 100_010.0, "direction": "BUY"}]
    signal = _signal(epic="EURUSD")
    with patch("src.risk.risk_manager.get_settings", return_value=_settings_stub()):
        result = rm.check_trade(
            signal=signal,
            equity=10_000.0,
            atr=0.001,
            open_positions=open_positions,
        )
    assert result.approved is False
    assert "exposure" in (result.rejection_reason or "").lower()


def test_guard_passes_below_cap_at_default_1_0() -> None:
    """Sum of open notionals under equity must NOT be rejected for
    exposure. (May still be rejected for other gates — that's fine.)"""
    rm = RiskManager(initial_equity=10_000.0, limits=RiskLimits())
    # 0.05 * 100_000 = 5000 notional, well below 10k equity cap
    open_positions = [{"epic": "BTCUSD", "size": 0.05, "level": 100_000.0, "direction": "BUY"}]
    signal = _signal(epic="EURUSD")
    with patch("src.risk.risk_manager.get_settings", return_value=_settings_stub()):
        result = rm.check_trade(
            signal=signal,
            equity=10_000.0,
            atr=0.001,
            open_positions=open_positions,
        )
    if not result.approved:
        assert "exposure" not in (result.rejection_reason or "").lower()


def test_guard_at_099_still_works() -> None:
    """Back-compat: users who set MAX_TOTAL_EXPOSURE=0.99 expect the same
    rejection at sum ≥ 9900. Pre-fix `< 1.0` already handles 0.99 — this
    test guards against an accidental flip that breaks legacy configs."""
    rm = RiskManager(
        initial_equity=10_000.0, limits=RiskLimits(max_total_exposure=0.99)
    )
    # 0.1 * 99_500 = 9950 notional → 99.5% exposure ≥ 99% cap
    open_positions = [{"epic": "BTCUSD", "size": 0.1, "level": 99_500.0, "direction": "BUY"}]
    signal = _signal(epic="EURUSD")
    with patch("src.risk.risk_manager.get_settings", return_value=_settings_stub()):
        result = rm.check_trade(
            signal=signal,
            equity=10_000.0,
            atr=0.001,
            open_positions=open_positions,
        )
    assert result.approved is False
    assert "exposure" in (result.rejection_reason or "").lower()
