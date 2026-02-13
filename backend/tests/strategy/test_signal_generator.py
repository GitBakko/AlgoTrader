"""Tests for signal generator module."""

import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.strategy.signal_generator import SignalGenerator


def _make_prediction(signal_class=SignalClass.BUY, confidence=0.80) -> PredictionResult:
    return PredictionResult(
        signal_class=signal_class,
        signal_name=SignalClass(signal_class).name,
        confidence=confidence,
        probabilities={"SELL": 0.10, "HOLD": 0.10, "BUY": confidence},
    )


class TestSignalGenerator:
    def test_buy_signal(self):
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(pred, "XAUUSD", 2000.0, atr=20.0)
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.80
        assert signal.suggested_stop is not None
        assert signal.suggested_stop < 2000.0
        assert signal.suggested_tp is not None
        assert signal.suggested_tp > 2000.0

    def test_sell_signal(self):
        pred = _make_prediction(SignalClass.SELL, 0.75)
        signal = SignalGenerator.generate_signal(pred, "XAUUSD", 2000.0, atr=20.0)
        assert signal.direction == SignalDirection.SELL
        assert signal.suggested_stop > 2000.0
        assert signal.suggested_tp < 2000.0

    def test_hold_returns_hold(self):
        pred = _make_prediction(SignalClass.HOLD, 0.60)
        signal = SignalGenerator.generate_signal(pred, "XAUUSD", 2000.0, atr=20.0)
        assert signal.direction == SignalDirection.HOLD

    def test_low_confidence_returns_hold(self):
        pred = _make_prediction(SignalClass.BUY, 0.35)
        signal = SignalGenerator.generate_signal(pred, "XAUUSD", 2000.0, atr=20.0)
        assert signal.direction == SignalDirection.HOLD

    def test_rsi_overbought_blocks_buy(self):
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, rsi=85.0
        )
        assert signal.direction == SignalDirection.HOLD

    def test_rsi_oversold_blocks_sell(self):
        pred = _make_prediction(SignalClass.SELL, 0.80)
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, rsi=15.0
        )
        assert signal.direction == SignalDirection.HOLD

    def test_rsi_normal_allows_signal(self):
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, rsi=50.0
        )
        assert signal.direction == SignalDirection.BUY

    def test_counter_trend_penalty(self):
        """SELL in trending_up should have reduced confidence."""
        pred = _make_prediction(SignalClass.SELL, 0.80)
        config = StrategyConfig(counter_trend_penalty=0.5, min_confidence=0.50)
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, regime="trending_up", config=config
        )
        # 0.80 * 0.5 = 0.40 < 0.50 -> should become HOLD
        assert signal.direction == SignalDirection.HOLD

    def test_counter_trend_mild_penalty(self):
        """High-confidence counter-trend should still trade if penalty isn't too harsh."""
        pred = _make_prediction(SignalClass.SELL, 0.95)
        config = StrategyConfig(counter_trend_penalty=0.7, min_confidence=0.50)
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, regime="trending_up", config=config
        )
        # 0.95 * 0.7 = 0.665 > 0.50 -> should still SELL
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence == pytest.approx(0.665)

    # ===== ADX Pre-Signal Filter Tests =====

    def test_adx_low_rejects_directional_signal(self):
        """ADX below ranging threshold rejects BUY/SELL -> HOLD."""
        pred = _make_prediction(SignalClass.BUY, 0.80)
        config = StrategyConfig(adx_ranging_threshold=20.0)
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, config=config, adx=15.0
        )
        assert signal.direction == SignalDirection.HOLD

    def test_adx_trending_boosts_confidence(self):
        """ADX above trending threshold boosts confidence."""
        pred = _make_prediction(SignalClass.BUY, 0.70)
        config = StrategyConfig(
            adx_trending_threshold=25.0,
            adx_confidence_boost=0.05,
        )
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, config=config, adx=30.0
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == pytest.approx(0.75)

    def test_adx_none_skips_filter(self):
        """adx=None should not affect signal (backward compatible)."""
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, adx=None
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.80

    def test_atr_zero_returns_hold(self):
        """ATR <= 0 should return HOLD immediately."""
        pred = _make_prediction(SignalClass.BUY, 0.80)
        signal = SignalGenerator.generate_signal(pred, "XAUUSD", 2000.0, atr=0.0)
        assert signal.direction == SignalDirection.HOLD

    def test_atr_negative_returns_hold(self):
        """Negative ATR should return HOLD."""
        pred = _make_prediction(SignalClass.SELL, 0.90)
        signal = SignalGenerator.generate_signal(pred, "XAUUSD", 2000.0, atr=-5.0)
        assert signal.direction == SignalDirection.HOLD

    def test_adx_between_thresholds_no_effect(self):
        """ADX between ranging and trending thresholds: no reject, no boost."""
        pred = _make_prediction(SignalClass.BUY, 0.70)
        config = StrategyConfig(
            adx_ranging_threshold=20.0,
            adx_trending_threshold=25.0,
        )
        signal = SignalGenerator.generate_signal(
            pred, "XAUUSD", 2000.0, atr=20.0, config=config, adx=22.0
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.70
