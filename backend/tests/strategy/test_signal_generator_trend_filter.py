"""Tests for SMA/EMA trend filters in SignalGenerator."""

import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.strategy.signal_generator import SignalGenerator


def _make_prediction(
    signal_class: int = SignalClass.BUY,
    confidence: float = 0.65,
) -> PredictionResult:
    """Helper to create a PredictionResult with correct schema."""
    return PredictionResult(
        signal_class=signal_class,
        signal_name=SignalClass(signal_class).name,
        confidence=confidence,
        probabilities={"SELL": 0.10, "HOLD": 0.25, "BUY": confidence},
    )


class TestSMATrendFilter:
    """SMA(50) trend filter tests."""

    def test_buy_below_sma50_penalized(self):
        """BUY signal well below SMA50 gets confidence penalty."""
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            sma_50=105.0,  # price well below SMA50
        )
        # 0.80 * 0.70 = 0.56, still above 0.50 default min
        assert signal.confidence < 0.80
        assert signal.direction == SignalDirection.BUY

    def test_sell_above_sma50_penalized(self):
        """SELL signal well above SMA50 gets penalty, may become HOLD."""
        pred = _make_prediction(SignalClass.SELL, 0.55)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=110.0, atr=2.0,
            sma_50=105.0,  # price well above SMA50
        )
        # 0.55 * 0.70 = 0.385, below 0.50 default -> HOLD
        assert signal.direction == SignalDirection.HOLD

    def test_buy_above_sma50_no_penalty(self):
        """BUY above SMA50 is trend-aligned, no penalty."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=110.0, atr=2.0,
            sma_50=105.0,
        )
        assert signal.confidence == 0.65
        assert signal.direction == SignalDirection.BUY

    def test_sell_below_sma50_no_penalty(self):
        """SELL below SMA50 is trend-aligned, no penalty."""
        pred = _make_prediction(SignalClass.SELL, 0.65)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            sma_50=105.0,
        )
        assert signal.confidence == 0.65

    def test_sma_none_no_penalty(self):
        """No penalty when SMA50 is None."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            sma_50=None,
        )
        assert signal.confidence == 0.65

    def test_price_near_sma_no_penalty(self):
        """Price within 0.5% band of SMA50 gets no penalty."""
        pred = _make_prediction(SignalClass.BUY, 0.65)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=104.8, atr=2.0,
            sma_50=105.0,  # price only 0.19% below SMA
        )
        # 104.8 < 105.0 * 0.995 = 104.475? No, 104.8 > 104.475
        assert signal.confidence == 0.65


class TestEMASlopeFilter:
    """EMA slope filter tests."""

    def test_flat_ema_slope_penalized(self):
        """Signal with flat EMA slope gets penalty."""
        pred = _make_prediction(SignalClass.BUY, 0.60)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            ema_slope=0.01,  # 0.01/2.0 = 0.005 < 0.02 threshold
        )
        # 0.60 * 0.80 = 0.48
        assert signal.confidence < 0.60

    def test_strong_ema_slope_no_penalty(self):
        """Signal with strong EMA slope gets no penalty."""
        pred = _make_prediction(SignalClass.BUY, 0.60)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            ema_slope=0.10,  # 0.10/2.0 = 0.05 > 0.02 threshold
        )
        assert signal.confidence == 0.60

    def test_ema_slope_none_no_penalty(self):
        """No penalty when ema_slope is None."""
        pred = _make_prediction(SignalClass.BUY, 0.60)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            ema_slope=None,
        )
        assert signal.confidence == 0.60


class TestCombinedTrendFilters:
    """Tests for SMA + EMA slope combined."""

    def test_both_penalties_stack(self):
        """SMA penalty and EMA slope penalty both apply."""
        pred = _make_prediction(SignalClass.BUY, 0.70)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            sma_50=110.0,   # price below SMA -> 0.70 * 0.70 = 0.49
            ema_slope=0.01,  # flat slope -> 0.49 * 0.80 = 0.392
        )
        # 0.392 < 0.50 min_confidence -> HOLD
        assert signal.direction == SignalDirection.HOLD

    def test_sma_penalty_alone_still_trades(self):
        """SMA penalty alone with high confidence still produces signal."""
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            sma_50=110.0,  # price below SMA -> 0.80 * 0.70 = 0.56
        )
        # 0.56 > 0.50 min_confidence -> still BUY
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == pytest.approx(0.56)

    def test_ema_slope_penalty_alone_still_trades(self):
        """EMA slope penalty alone with high confidence still produces signal."""
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(
            prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
            ema_slope=0.01,  # flat -> 0.80 * 0.80 = 0.64
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == pytest.approx(0.64)
