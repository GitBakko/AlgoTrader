"""
Test fix for inverted stop-loss logic in RiskManager.
CRITICAL BUG: Stop losses were being set ABOVE entry for longs!
"""

from unittest.mock import MagicMock, Mock, patch

from src.broker.models import Direction
from src.models.schemas import SignalClass
from src.risk.risk_manager import RiskManager
from src.strategy.schemas import TradingSignal


def _non_scalp_settings():
    s = MagicMock()
    s.scalp_mode_enabled = False
    s.epic_risk_multipliers = {}
    return s


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_buy_position_sl_below_entry(mock_check_exposure, _mock_settings):
    """Test that BUY positions have SL BELOW entry price."""

    # Mock static method for correlation check
    mock_check_exposure.return_value = (1.0, [])  # No correlation warnings

    # Create RiskManager
    risk_manager = RiskManager()

    # Mock dependencies
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.circuit_breakers.check_epic.return_value = (True, None)
    risk_manager.circuit_breakers.check_all.return_value = (True, [])  # No breakers tripped

    # Properly mock drawdown_monitor state with real numeric values
    state_mock = Mock()
    state_mock.daily_start_equity = 10000.0
    state_mock.max_daily_drawdown_pct = 0.05
    state_mock.circuit_breaker_reason = None
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.drawdown_monitor.state = state_mock
    risk_manager.drawdown_monitor.is_circuit_breaker_active.return_value = False
    risk_manager.drawdown_monitor.check_all.return_value = []  # No drawdown issues
    risk_manager.drawdown_monitor.check_limits.return_value = (True, None)  # No limit breaches
    risk_manager.drawdown_monitor.update.return_value = (
        None  # Update method called but returns nothing
    )

    risk_manager.correlation_guard = MagicMock()
    risk_manager.correlation_guard.check_exposure_dynamic.return_value = (1.0, [])
    risk_manager.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.get_size_multiplier.return_value = 1.0

    # Create BUY signal
    atr = 10.0  # Define ATR as local variable for later use
    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.BUY,
        entry_price=2000.0,
        confidence=0.65,
        suggested_stop=None,  # Will use ATR-based SL
        suggested_tp=None,
        signal_class=SignalClass.BUY,
    )

    # Check trade
    result = risk_manager.check_trade(
        signal=signal,
        equity=10000.0,
        atr=atr,  # Use local ATR variable
        open_positions=[],
        trade_history=[],
    )

    # Verify
    assert result.approved
    assert result.stop_loss is not None

    # CRITICAL: SL must be BELOW entry for BUY
    assert result.stop_loss < signal.entry_price, (
        f"BUY position SL must be below entry! "
        f"Entry={signal.entry_price}, SL={result.stop_loss}"
    )

    # Expected SL = entry - (ATR * 2) = 2000 - 20 = 1980
    expected_sl = signal.entry_price - (atr * 2.0)
    assert abs(result.stop_loss - expected_sl) < 0.01


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_sell_position_sl_above_entry(mock_check_exposure, _mock_settings):
    """Test that SELL positions have SL ABOVE entry price."""

    # Mock static method for correlation check
    mock_check_exposure.return_value = (1.0, [])  # No correlation warnings

    # Create RiskManager
    risk_manager = RiskManager()

    # Mock dependencies
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.circuit_breakers.check_epic.return_value = (True, None)
    risk_manager.circuit_breakers.check_all.return_value = (True, [])  # No breakers tripped

    # Properly mock drawdown_monitor state with real numeric values
    state_mock = Mock()
    state_mock.daily_start_equity = 10000.0
    state_mock.max_daily_drawdown_pct = 0.05
    state_mock.circuit_breaker_reason = None
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.drawdown_monitor.state = state_mock
    risk_manager.drawdown_monitor.is_circuit_breaker_active.return_value = False
    risk_manager.drawdown_monitor.check_all.return_value = []  # No drawdown issues
    risk_manager.drawdown_monitor.check_limits.return_value = (True, None)  # No limit breaches
    risk_manager.drawdown_monitor.update.return_value = (
        None  # Update method called but returns nothing
    )

    risk_manager.correlation_guard = MagicMock()
    risk_manager.correlation_guard.check_exposure_dynamic.return_value = (1.0, [])
    risk_manager.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.get_size_multiplier.return_value = 1.0

    # Create SELL signal
    atr = 10.0  # Define ATR as local variable for later use
    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.SELL,
        entry_price=2000.0,
        confidence=0.65,
        suggested_stop=None,  # Will use ATR-based SL
        suggested_tp=None,
        signal_class=SignalClass.SELL,
    )

    # Check trade
    result = risk_manager.check_trade(
        signal=signal,
        equity=10000.0,
        atr=atr,  # Use local ATR variable
        open_positions=[],
        trade_history=[],
    )

    # Verify
    assert result.approved
    assert result.stop_loss is not None

    # CRITICAL: SL must be ABOVE entry for SELL
    assert result.stop_loss > signal.entry_price, (
        f"SELL position SL must be above entry! "
        f"Entry={signal.entry_price}, SL={result.stop_loss}"
    )

    # Expected SL = entry + (ATR * 2) = 2000 + 20 = 2020
    expected_sl = signal.entry_price + (atr * 2.0)
    assert abs(result.stop_loss - expected_sl) < 0.01


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_buy_with_suggested_stop_chooses_tighter(mock_check_exposure, _mock_settings):
    """BUY with suggested_stop only: SL must be the TIGHTER (closer-to-entry) value.

    For BUY, SL is below entry → tighter SL has the LARGER value.
    Bug fix 2026-04-28 — see risk_manager.py §4-bis.
    """

    # Mock static method for correlation check
    mock_check_exposure.return_value = (1.0, [])  # No correlation warnings

    # Create RiskManager
    risk_manager = RiskManager()

    # Mock dependencies
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.circuit_breakers.check_epic.return_value = (True, None)
    risk_manager.circuit_breakers.check_all.return_value = (True, [])  # No breakers tripped

    # Properly mock drawdown_monitor state with real numeric values
    state_mock = Mock()
    state_mock.daily_start_equity = 10000.0
    state_mock.max_daily_drawdown_pct = 0.05
    state_mock.circuit_breaker_reason = None
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.drawdown_monitor.state = state_mock
    risk_manager.drawdown_monitor.is_circuit_breaker_active.return_value = False
    risk_manager.drawdown_monitor.check_all.return_value = []  # No drawdown issues
    risk_manager.drawdown_monitor.check_limits.return_value = (True, None)  # No limit breaches
    risk_manager.drawdown_monitor.update.return_value = (
        None  # Update method called but returns nothing
    )

    risk_manager.correlation_guard = MagicMock()
    risk_manager.correlation_guard.check_exposure_dynamic.return_value = (1.0, [])
    risk_manager.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.get_size_multiplier.return_value = 1.0

    # ATR-based SL would be: 2000 - 20 = 1980
    # Suggested SL: 1990 (tighter, closer to entry)
    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.BUY,
        entry_price=2000.0,
        confidence=0.65,
        suggested_stop=1990.0,  # Tighter than ATR-based
        suggested_tp=None,
        signal_class=SignalClass.BUY,
    )

    result = risk_manager.check_trade(
        signal=signal,
        equity=10000.0,
        atr=10.0,
        open_positions=[],
        trade_history=[],
    )

    # For BUY (SL below entry), tighter = larger value (closer to entry).
    # ATR SL = 1980, suggested = 1990 → max(1980, 1990) = 1990 (tighter).
    assert result.stop_loss == max(1980.0, 1990.0)  # = 1990
    assert result.stop_loss < signal.entry_price


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_sell_with_suggested_stop_chooses_tighter(mock_check_exposure, _mock_settings):
    """SELL with suggested_stop only: SL must be the TIGHTER (closer-to-entry) value.

    For SELL, SL is above entry → tighter SL has the SMALLER value.
    Bug fix 2026-04-28 — see risk_manager.py §4-bis.
    """

    # Mock static method for correlation check
    mock_check_exposure.return_value = (1.0, [])  # No correlation warnings

    risk_manager = RiskManager()

    # Mock dependencies
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.circuit_breakers.check_epic.return_value = (True, None)
    risk_manager.circuit_breakers.check_all.return_value = (True, [])  # No breakers tripped

    # Properly mock drawdown_monitor state with real numeric values
    state_mock = Mock()
    state_mock.daily_start_equity = 10000.0
    state_mock.max_daily_drawdown_pct = 0.05
    state_mock.circuit_breaker_reason = None
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.drawdown_monitor.state = state_mock
    risk_manager.drawdown_monitor.is_circuit_breaker_active.return_value = False
    risk_manager.drawdown_monitor.check_all.return_value = []  # No drawdown issues
    risk_manager.drawdown_monitor.check_limits.return_value = (True, None)  # No limit breaches
    risk_manager.drawdown_monitor.update.return_value = (
        None  # Update method called but returns nothing
    )

    risk_manager.correlation_guard = MagicMock()
    risk_manager.correlation_guard.check_exposure_dynamic.return_value = (1.0, [])
    risk_manager.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.get_size_multiplier.return_value = 1.0

    # ATR-based SL would be: 2000 + 20 = 2020
    # Suggested SL: 2010 (tighter, closer to entry)
    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.SELL,
        entry_price=2000.0,
        confidence=0.65,
        suggested_stop=2010.0,  # Tighter than ATR-based
        suggested_tp=None,
        signal_class=SignalClass.SELL,
    )

    result = risk_manager.check_trade(
        signal=signal,
        equity=10000.0,
        atr=10.0,
        open_positions=[],
        trade_history=[],
    )

    # For SELL (SL above entry), tighter = smaller value (closer to entry).
    # ATR SL = 2020, suggested = 2010 → min(2020, 2010) = 2010 (tighter).
    assert result.stop_loss == min(2020.0, 2010.0)  # = 2010
    assert result.stop_loss > signal.entry_price


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_paired_suggested_sl_tp_used_as_is(mock_check_exposure, _mock_settings):
    """Strategy that pairs suggested_stop + suggested_tp keeps both as-is.

    Bug fix 2026-04-28: previously the risk manager mixed its own ATR-derived
    SL with the strategy's TP, producing inverted R:R (e.g. 0.13 instead of
    the calibrated 0.75). When both sides are suggested, trust the pair.
    """
    mock_check_exposure.return_value = (1.0, [])
    risk_manager = RiskManager()
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.circuit_breakers.check_epic.return_value = (True, None)
    risk_manager.circuit_breakers.check_all.return_value = (True, [])
    state_mock = Mock()
    state_mock.daily_start_equity = 10000.0
    state_mock.max_daily_drawdown_pct = 0.05
    state_mock.circuit_breaker_reason = None
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.drawdown_monitor.state = state_mock
    risk_manager.drawdown_monitor.is_circuit_breaker_active.return_value = False
    risk_manager.drawdown_monitor.check_all.return_value = []
    risk_manager.drawdown_monitor.check_limits.return_value = (True, None)
    risk_manager.drawdown_monitor.update.return_value = None
    risk_manager.correlation_guard = MagicMock()
    risk_manager.correlation_guard.check_exposure_dynamic.return_value = (1.0, [])
    risk_manager.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.get_size_multiplier.return_value = 1.0

    # MR-style calibrated pair: tight SL+TP both close to entry.
    # ATR SL would be 1980 (wide); strategy says SL=1995 + TP=2010.
    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.BUY,
        entry_price=2000.0,
        confidence=0.65,
        suggested_stop=1995.0,
        suggested_tp=2010.0,
        signal_class=SignalClass.BUY,
    )

    result = risk_manager.check_trade(
        signal=signal,
        equity=10000.0,
        atr=10.0,
        open_positions=[],
        trade_history=[],
    )

    # Paired SL+TP must be used verbatim — strategy's calibrated R:R survives.
    assert result.stop_loss == 1995.0
    assert result.take_profit == 2010.0
    sl_dist = signal.entry_price - result.stop_loss
    tp_dist = result.take_profit - signal.entry_price
    assert sl_dist == 5.0 and tp_dist == 10.0
    assert tp_dist / sl_dist == 2.0  # calibrated R:R preserved
