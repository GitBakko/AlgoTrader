"""Tests for strategy manager orchestrator."""

import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.strategy.strategy_manager import StrategyManager


def _make_prediction(signal_class=SignalClass.BUY, confidence=0.80) -> PredictionResult:
    return PredictionResult(
        signal_class=signal_class,
        signal_name=SignalClass(signal_class).name,
        confidence=confidence,
        probabilities={"SELL": 0.10, "HOLD": 0.10, "BUY": confidence},
    )


class TestStrategyManager:
    def test_process_buy_prediction(self):
        sm = StrategyManager()
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = sm.process_prediction(pred, "XAUUSD", {"current_price": 2000.0, "atr": 20.0})
        assert signal.direction == SignalDirection.BUY
        assert signal.epic == "XAUUSD"

    def test_process_with_regime(self):
        sm = StrategyManager()
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = sm.process_prediction(
            pred, "XAUUSD",
            {"current_price": 2000.0, "atr": 20.0, "regime": "trending_up"}
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.regime == "trending_up"

    def test_process_with_rsi_filter(self):
        sm = StrategyManager()
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = sm.process_prediction(
            pred, "XAUUSD",
            {"current_price": 2000.0, "atr": 20.0, "rsi": 85.0}
        )
        assert signal.direction == SignalDirection.HOLD

    def test_custom_config(self):
        config = StrategyConfig(epic="XAUUSD", min_confidence=0.90)
        sm = StrategyManager(configs={"XAUUSD": config})
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = sm.process_prediction(pred, "XAUUSD", {"current_price": 2000.0, "atr": 20.0})
        assert signal.direction == SignalDirection.HOLD  # 0.80 < 0.90

    def test_get_allocation(self):
        sm = StrategyManager()
        alloc = sm.get_allocation()
        assert "XAUUSD" in alloc
        assert sum(alloc.values()) == pytest.approx(1.0)

    def test_get_allocation_with_regime(self):
        sm = StrategyManager()
        alloc = sm.get_allocation("bear")
        assert alloc["XAUUSD"] > alloc["BTCUSD"]

    def test_missing_current_price_raises(self):
        sm = StrategyManager()
        pred = _make_prediction(SignalClass.BUY, 0.80)
        with pytest.raises(ValueError, match="current_price"):
            sm.process_prediction(pred, "XAUUSD", {"atr": 20.0})

    def test_invalid_current_price_raises(self):
        sm = StrategyManager()
        pred = _make_prediction(SignalClass.BUY, 0.80)
        with pytest.raises(ValueError, match="Invalid current_price"):
            sm.process_prediction(pred, "XAUUSD", {"current_price": -1, "atr": 20.0})

    def test_invalid_atr_raises(self):
        sm = StrategyManager()
        pred = _make_prediction(SignalClass.BUY, 0.80)
        with pytest.raises(ValueError, match="Invalid ATR"):
            sm.process_prediction(pred, "XAUUSD", {"current_price": 2000.0, "atr": 0})
