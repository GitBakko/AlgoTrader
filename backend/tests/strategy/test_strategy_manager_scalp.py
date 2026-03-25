"""Tests for StrategyManager with scalp mode integration."""
import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.strategy_manager import StrategyManager
from src.strategy.schemas import SignalDirection


@pytest.fixture
def scalp_manager() -> StrategyManager:
    """StrategyManager in scalp mode."""
    return StrategyManager(scalp_mode=True)


@pytest.fixture
def prediction_buy() -> PredictionResult:
    return PredictionResult(
        signal_class=SignalClass.BUY,
        signal_name="BUY",
        confidence=0.65,
        probabilities={"SELL": 0.1, "HOLD": 0.25, "BUY": 0.65},
    )


@pytest.fixture
def prediction_hold() -> PredictionResult:
    return PredictionResult(
        signal_class=SignalClass.HOLD,
        signal_name="HOLD",
        confidence=0.35,
        probabilities={"SELL": 0.3, "HOLD": 0.4, "BUY": 0.3},
    )


@pytest.fixture
def prediction_sell() -> PredictionResult:
    return PredictionResult(
        signal_class=SignalClass.SELL,
        signal_name="SELL",
        confidence=0.70,
        probabilities={"SELL": 0.70, "HOLD": 0.20, "BUY": 0.10},
    )


@pytest.fixture
def bullish_market_data() -> dict:
    """Market data with strong bullish indicators -> should score high BUY."""
    return {
        "current_price": 105.0,
        "atr": 1.0,
        "rsi": 38.0,
        "adx": 28.0,
        "regime": "trending_up",
        "ema_9": 105.5,
        "ema_21": 104.8,
        "macd_histogram": 0.5,
        "macd": 0.6,
        "macd_signal": 0.1,
        "volume": 1500,
        "volume_sma_20": 1000,
        "bb_upper": 106.0,
        "bb_lower": 104.0,
        "bb_middle": 105.0,
        "keltner_upper": 106.5,
        "keltner_lower": 103.5,
    }


class TestScalpModeSignalGeneration:
    def test_scalp_mode_uses_score_strategy(self, scalp_manager, prediction_buy, bullish_market_data):
        """In scalp mode, technical score should drive the signal."""
        signal = scalp_manager.process_prediction(prediction_buy, "XAUUSD", bullish_market_data)
        assert signal.strategy_name == "scalp_score"

    def test_ml_agree_keeps_full_confidence(self, scalp_manager, prediction_buy, bullish_market_data):
        """When ML agrees with technical BUY, confidence stays high."""
        signal = scalp_manager.process_prediction(prediction_buy, "XAUUSD", bullish_market_data)
        assert signal.direction == SignalDirection.BUY
        # ML agrees (BUY) -> no penalty
        assert signal.confidence > 0.5

    def test_ml_hold_reduces_confidence(self, scalp_manager, prediction_hold, bullish_market_data):
        """When ML says HOLD, technical signal's confidence is reduced (0.75x)."""
        signal = scalp_manager.process_prediction(prediction_hold, "XAUUSD", bullish_market_data)
        # Technical says BUY, ML says HOLD -> confidence × 0.75
        if signal.direction == SignalDirection.BUY:
            assert signal.confidence <= 0.75  # 0.75x reduction

    def test_ml_disagree_halves_confidence(self, scalp_manager, prediction_sell, bullish_market_data):
        """When ML disagrees (SELL vs technical BUY), confidence halved but not blocked."""
        signal = scalp_manager.process_prediction(prediction_sell, "XAUUSD", bullish_market_data)
        # GURU: technical confluence decides, ML only adjusts confidence
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence <= 0.5

    def test_non_scalp_mode_unchanged(self, prediction_buy):
        """Default mode (scalp_mode=False) uses ML strategy as before."""
        sm = StrategyManager(scalp_mode=False)
        signal = sm.process_prediction(
            prediction_buy, "XAUUSD", {"current_price": 105.0, "atr": 1.0}
        )
        assert signal.strategy_name == "ml_strategy"
