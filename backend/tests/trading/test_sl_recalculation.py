"""Test that SL/TP are recalculated from fill price, not candle close."""
import pytest

from src.risk.stop_manager import StopManager


def test_sl_recalculated_from_fill_price_buy():
    """BUY: SL must be below fill price, not candle close."""
    candle_close = 70905.0
    fill_price = 70630.0
    atr = 144.66
    multiplier = 1.0

    # Old behavior: SL from candle close
    old_sl = StopManager.calculate_stop_loss("BUY", candle_close, atr, multiplier)
    assert old_sl == pytest.approx(70760.34, abs=0.1)  # above fill!
    assert old_sl > fill_price  # BUG: SL above entry for BUY

    # Correct behavior: SL from fill price
    correct_sl = StopManager.calculate_stop_loss("BUY", fill_price, atr, multiplier)
    assert correct_sl == pytest.approx(70485.34, abs=0.1)
    assert correct_sl < fill_price  # SL below entry for BUY


def test_sl_recalculated_from_fill_price_sell():
    """SELL: SL must be above fill price."""
    fill_price = 89.10
    atr = 0.554
    multiplier = 1.0

    correct_sl = StopManager.calculate_stop_loss("SELL", fill_price, atr, multiplier)
    assert correct_sl > fill_price  # SL above entry for SELL


def test_tp_recalculated_from_fill_price_buy():
    """TP must use fill price, not candle close."""
    fill_price = 70630.0
    atr = 144.66
    multiplier = 1.0
    rr = 2.0

    tp = StopManager.calculate_take_profit("BUY", fill_price, atr, multiplier, rr)
    assert tp > fill_price  # TP above entry for BUY
    assert tp == pytest.approx(70919.32, abs=0.1)


def test_recalculate_sl_tp_from_fill():
    """Verify the recalculation helper produces valid SL/TP from fill price."""
    from src.trading.paper_loop import _recalculate_sl_tp_from_fill

    # BUY: fill drifted below candle close
    sl, tp = _recalculate_sl_tp_from_fill(
        direction="BUY",
        fill_price=70630.0,
        atr=144.66,
        stop_multiplier=1.0,
        risk_reward=2.0,
    )
    assert sl < 70630.0, f"BUY SL {sl} must be below fill 70630"
    assert tp > 70630.0, f"BUY TP {tp} must be above fill 70630"

    # SELL: fill drifted above candle close
    sl, tp = _recalculate_sl_tp_from_fill(
        direction="SELL",
        fill_price=89.10,
        atr=0.554,
        stop_multiplier=1.0,
        risk_reward=2.0,
    )
    assert sl > 89.10, f"SELL SL {sl} must be above fill 89.10"
    assert tp < 89.10, f"SELL TP {tp} must be below fill 89.10"


def test_sl_side_validation_buy():
    """BUY with SL above entry must be caught."""
    from src.trading.paper_loop import _validate_sl_side

    assert _validate_sl_side("BUY", entry=100.0, sl=95.0) is True
    assert _validate_sl_side("BUY", entry=100.0, sl=105.0) is False


def test_sl_side_validation_sell():
    """SELL with SL below entry must be caught."""
    from src.trading.paper_loop import _validate_sl_side

    assert _validate_sl_side("SELL", entry=100.0, sl=105.0) is True
    assert _validate_sl_side("SELL", entry=100.0, sl=95.0) is False
