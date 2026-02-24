"""
Test fix for inverted stop-loss logic in RiskManager.
CRITICAL BUG: Stop losses were being set ABOVE entry for longs!
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskCheckResult
from src.strategy.schemas import TradingSignal
from src.models.schemas import SignalClass
from src.broker.models import Direction


@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_buy_position_sl_below_entry(mock_check_exposure):
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
    risk_manager.drawdown_monitor.update.return_value = None  # Update method called but returns nothing

    risk_manager.correlation_guard = MagicMock()
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

    # Expected SL = entry - (ATR * 3) = 2000 - 30 = 1970
    expected_sl = signal.entry_price - (atr * 3.0)
    assert abs(result.stop_loss - expected_sl) < 0.01


@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_sell_position_sl_above_entry(mock_check_exposure):
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
    risk_manager.drawdown_monitor.update.return_value = None  # Update method called but returns nothing

    risk_manager.correlation_guard = MagicMock()
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

    # Expected SL = entry + (ATR * 3) = 2000 + 30 = 2030
    expected_sl = signal.entry_price + (atr * 3.0)
    assert abs(result.stop_loss - expected_sl) < 0.01


@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_buy_with_suggested_stop_chooses_min(mock_check_exposure):
    """Test that BUY with suggested stop chooses the MIN (tighter stop)."""

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
    risk_manager.drawdown_monitor.update.return_value = None  # Update method called but returns nothing

    risk_manager.correlation_guard = MagicMock()
    risk_manager.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.get_size_multiplier.return_value = 1.0

    # ATR-based SL would be: 2000 - 30 = 1970
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

    # For BUY: min() chooses the LOWER value (further from entry = more conservative)
    # ATR SL = 1970, suggested = 1990 → min(1970, 1990) = 1970
    assert result.stop_loss == min(1970.0, 1990.0)  # = 1970
    assert result.stop_loss < signal.entry_price


@patch("src.risk.risk_manager.CorrelationGuard.check_exposure")
def test_sell_with_suggested_stop_chooses_max(mock_check_exposure):
    """Test that SELL with suggested stop chooses the MAX (tighter stop)."""

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
    risk_manager.drawdown_monitor.update.return_value = None  # Update method called but returns nothing

    risk_manager.correlation_guard = MagicMock()
    risk_manager.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.get_size_multiplier.return_value = 1.0

    # ATR-based SL would be: 2000 + 30 = 2030
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

    # For SELL: max() gives HIGHER value (further from entry = more conservative)
    # ATR SL = 2030, suggested = 2010 → max(2030, 2010) = 2030
    assert result.stop_loss == max(2030.0, 2010.0)  # = 2030
    assert result.stop_loss > signal.entry_price
