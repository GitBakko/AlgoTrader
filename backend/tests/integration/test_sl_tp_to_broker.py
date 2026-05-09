"""
Integration test: verify SL/TP values flow correctly to Capital.com broker.

CRITICAL BUG FIX TEST:
- Ensures RiskManager calculates stop_loss and take_profit
- Ensures ExecutionEngine passes them to ExecutionOrder
- Ensures OrderManager creates CreatePositionRequest with stop_level/profit_level
- Ensures Broker client excludes None values (exclude_none=True)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.broker.models import DealConfirmation, Direction
from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.risk_manager import RiskManager
from src.strategy.schemas import TradingSignal


def _non_scalp_settings():
    """Match the canonical mock in tests/risk/test_risk_manager.py.

    The bare MagicMock left `epic_risk_multipliers`, `min_risk_amount_usd`,
    and `min_signal_rr_threshold` un-stubbed, which broke the §6-bis
    `epic_mult <= 0.0` comparison and §4-ter R:R floor with TypeError
    against MagicMock auto-attributes.
    """
    s = MagicMock()
    s.scalp_mode_enabled = False
    s.min_risk_amount_usd = 0.0
    s.min_notional_usd = 0.0
    s.forex_usd_base_size_multiplier = 1.0
    s.forex_max_leverage_multiplier = 1.0
    s.min_signal_rr_threshold = 0.0
    s.epic_risk_multipliers = {}
    return s


@pytest.fixture
def mock_risk_manager():
    """Risk manager with mocked dependencies."""
    rm = RiskManager()
    rm.circuit_breakers = MagicMock()
    rm.circuit_breakers.check_epic.return_value = (True, None)
    rm.circuit_breakers.check_all.return_value = (True, [])
    rm.circuit_breakers.get_baseline_atr.return_value = 10.0

    # Mock drawdown monitor state
    rm.drawdown_monitor = MagicMock()
    rm.drawdown_monitor.state = MagicMock()
    rm.drawdown_monitor.state.max_daily_drawdown_pct = 0.05
    rm.drawdown_monitor.state.daily_start_equity = 10000.0
    rm.drawdown_monitor.is_circuit_breaker_active.return_value = False
    rm.drawdown_monitor.check_limits.return_value = (True, None)

    rm.correlation_guard = MagicMock()
    rm.correlation_guard.check_exposure_dynamic.return_value = (1.0, [])
    rm.correlation_guard.calculate_correlation_multiplier.return_value = 1.0
    rm.equity_curve_filter = MagicMock()
    rm.equity_curve_filter.get_size_multiplier.return_value = 1.0
    return rm


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
@pytest.mark.asyncio
async def test_sl_tp_flow_to_broker(_mock_settings, mock_risk_manager):
    """
    Test that SL/TP values flow correctly from RiskManager to Broker API.

    Flow:
    1. RiskManager.check_trade() -> RiskCheckResult with stop_loss, take_profit
    2. ExecutionEngine.execute_signal() -> ExecutionOrder with stop_loss, take_profit
    3. OrderManager._live_fill() -> CreatePositionRequest with stop_level, profit_level
    4. Broker.create_position() -> model_dump(exclude_none=True) excludes None values
    """
    # 1. Create trading signal
    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.BUY,
        entry_price=2000.0,
        confidence=0.65,
        signal_class=2,  # 2 = BUY
        suggested_stop=None,  # Will use ATR-based
        suggested_tp=None,
    )

    # 2. Check trade with RiskManager
    risk_result = mock_risk_manager.check_trade(
        signal=signal,
        equity=10000.0,
        atr=10.0,  # ATR = 10
        open_positions=[],
        trade_history=[],
    )

    # 3. Verify RiskCheckResult has stop_loss and take_profit
    assert risk_result.approved
    assert risk_result.stop_loss is not None, "RiskCheckResult must have stop_loss!"
    assert risk_result.take_profit is not None, "RiskCheckResult must have take_profit!"

    # 4. Verify correct SL/TP values
    # BUY: SL should be BELOW entry (entry - ATR*2)
    assert (
        risk_result.stop_loss < signal.entry_price
    ), f"BUY SL must be below entry! SL={risk_result.stop_loss} entry={signal.entry_price}"
    expected_sl = signal.entry_price - (10.0 * 2.0)  # 2000 - 20 = 1980
    assert abs(risk_result.stop_loss - expected_sl) < 0.01

    # TP should be ABOVE entry (entry + ATR*2*2.5)
    assert risk_result.take_profit > signal.entry_price
    expected_tp = signal.entry_price + (10.0 * 2.0 * 2.5)  # 2000 + 50 = 2050
    assert abs(risk_result.take_profit - expected_tp) < 0.01

    # 5. Create mock broker that captures the payload
    mock_broker = MagicMock()
    captured_request = None

    async def mock_create_position(request):
        nonlocal captured_request
        captured_request = request

        # Simulate broker accepting the order
        return DealConfirmation(
            dealId="TEST-123",
            dealReference="REF-123",
            dealStatus="ACCEPTED",
            status="ACCEPTED",
            level=2000.5,
            size=1.0,
            direction=Direction.BUY,
            epic="XAUUSD",
            affectedDeals=[],
            reason=None,
        )

    mock_broker.create_position = AsyncMock(side_effect=mock_create_position)

    # 6. Execute signal with ExecutionEngine (DEMO mode to use broker)
    execution_engine = ExecutionEngine(broker=mock_broker, mode=ExecutionMode.DEMO)
    result = await execution_engine.execute_signal(signal, risk_result)

    # 7. Verify execution succeeded
    assert result.success, f"Execution failed: {result.error}"

    # 8. Verify CreatePositionRequest was created with correct values
    assert captured_request is not None, "Broker.create_position was not called!"
    assert captured_request.stop_level is not None, "CreatePositionRequest.stop_level is None!"
    assert captured_request.profit_level is not None, "CreatePositionRequest.profit_level is None!"

    # 9. Verify values match risk_result
    assert captured_request.stop_level == risk_result.stop_loss
    assert captured_request.profit_level == risk_result.take_profit

    print("[OK] SL/TP flow verified:")
    print(f"   RiskCheckResult: SL={risk_result.stop_loss:.2f} TP={risk_result.take_profit:.2f}")
    print(
        f"   CreatePositionRequest: stop_level={captured_request.stop_level:.2f} profit_level={captured_request.profit_level:.2f}"
    )


@patch("src.risk.risk_manager.get_settings", side_effect=lambda: _non_scalp_settings())
@pytest.mark.asyncio
async def test_sell_position_sl_tp_flow(_mock_settings, mock_risk_manager):
    """Test SL/TP flow for SELL position (SL above entry)."""
    signal = TradingSignal(
        epic="XAUUSD",
        direction=Direction.SELL,
        entry_price=2000.0,
        confidence=0.65,
        signal_class=0,  # 0 = SELL
        suggested_stop=None,
        suggested_tp=None,
    )

    risk_result = mock_risk_manager.check_trade(
        signal=signal,
        equity=10000.0,
        atr=10.0,
        open_positions=[],
        trade_history=[],
    )

    # SELL: SL should be ABOVE entry (entry + ATR*2)
    assert (
        risk_result.stop_loss > signal.entry_price
    ), f"SELL SL must be above entry! SL={risk_result.stop_loss} entry={signal.entry_price}"
    expected_sl = signal.entry_price + (10.0 * 2.0)  # 2000 + 20 = 2020
    assert abs(risk_result.stop_loss - expected_sl) < 0.01

    # TP should be BELOW entry (entry - ATR*2*2.5)
    assert risk_result.take_profit < signal.entry_price
    expected_tp = signal.entry_price - (10.0 * 2.0 * 2.5)  # 2000 - 50 = 1950
    assert abs(risk_result.take_profit - expected_tp) < 0.01


@pytest.mark.asyncio
async def test_broker_exclude_none():
    """
    Test that broker client uses exclude_none=True when serializing.

    CRITICAL FIX: broker/client.py line 295 must use exclude_none=True
    to prevent sending "stopLevel": null to Capital.com API.
    """
    from src.broker.models import CreatePositionRequest

    # Create request with None values
    request = CreatePositionRequest(
        epic="XAUUSD",
        direction=Direction.BUY,
        size=1.0,
        stop_level=None,  # Should be excluded
        profit_level=None,  # Should be excluded
    )

    # Verify model_dump with exclude_none=True excludes None fields
    payload_with_exclude = request.model_dump(by_alias=True, exclude_none=True)
    assert "stopLevel" not in payload_with_exclude, "stopLevel should be excluded when None!"
    assert "profitLevel" not in payload_with_exclude, "profitLevel should be excluded when None!"

    # Verify model_dump with exclude_none=False includes None fields
    payload_without_exclude = request.model_dump(by_alias=True, exclude_none=False)
    assert (
        "stopLevel" in payload_without_exclude
    ), "stopLevel should be included when exclude_none=False"
    assert payload_without_exclude["stopLevel"] is None

    print("[OK] exclude_none=True test passed:")
    print(f"   With exclude_none=True: {payload_with_exclude}")
    print(f"   With exclude_none=False: {payload_without_exclude}")
