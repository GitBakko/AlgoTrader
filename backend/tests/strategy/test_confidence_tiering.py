"""Tests for confidence tiering: min_confidence threshold and position size scaling."""

import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.risk.risk_manager import RiskManager
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.strategy.signal_generator import SignalGenerator


def _make_prediction(
    signal_class: int = SignalClass.BUY, confidence: float = 0.65
) -> PredictionResult:
    """Helper to build a PredictionResult with correct required fields."""
    return PredictionResult(
        signal_class=signal_class,
        signal_name=SignalClass(signal_class).name,
        confidence=confidence,
        probabilities={"SELL": 0.10, "HOLD": 0.25, "BUY": confidence},
    )


class TestMinConfidenceThreshold:
    """Signals below the new 0.50 default threshold become HOLD."""

    def test_confidence_below_050_rejected(self):
        """Signals below 0.50 confidence are HOLD."""
        pred = _make_prediction(SignalClass.BUY, confidence=0.45)
        signal = SignalGenerator.generate_signal(
            prediction=pred,
            epic="XAUUSD",
            current_price=100.0,
            atr=2.0,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_confidence_at_050_accepted(self):
        """Signals at exactly 0.50 should pass the default threshold."""
        pred = _make_prediction(SignalClass.BUY, confidence=0.50)
        signal = SignalGenerator.generate_signal(
            prediction=pred,
            epic="XAUUSD",
            current_price=100.0,
            atr=2.0,
        )
        assert signal.direction == SignalDirection.BUY

    def test_default_min_confidence_is_050(self):
        """StrategyConfig default min_confidence is 0.50."""
        cfg = StrategyConfig()
        assert cfg.min_confidence == 0.50


class TestConfidenceSizeMultiplier:
    """RiskManager.confidence_size_multiplier tiers position size by confidence."""

    def test_confidence_below_050_returns_zero(self):
        assert RiskManager.confidence_size_multiplier(0.30) == 0.0
        assert RiskManager.confidence_size_multiplier(0.49) == 0.0

    def test_confidence_tier_050_gets_half_size(self):
        assert RiskManager.confidence_size_multiplier(0.50) == 0.50
        assert RiskManager.confidence_size_multiplier(0.52) == 0.50
        assert RiskManager.confidence_size_multiplier(0.57) == 0.50

    def test_confidence_tier_058_gets_75pct(self):
        assert RiskManager.confidence_size_multiplier(0.58) == 0.75
        assert RiskManager.confidence_size_multiplier(0.60) == 0.75
        assert RiskManager.confidence_size_multiplier(0.64) == 0.75

    def test_confidence_tier_065_gets_full(self):
        assert RiskManager.confidence_size_multiplier(0.65) == 1.0
        assert RiskManager.confidence_size_multiplier(0.68) == 1.0
        assert RiskManager.confidence_size_multiplier(0.80) == 1.0
        assert RiskManager.confidence_size_multiplier(1.0) == 1.0

    def test_boundary_at_058(self):
        """0.5799... rounds to 0.50x tier, 0.58 goes to 0.75x tier."""
        assert RiskManager.confidence_size_multiplier(0.5799) == 0.50
        assert RiskManager.confidence_size_multiplier(0.58) == 0.75

    def test_boundary_at_065(self):
        """0.6499... stays in 0.75x tier, 0.65 goes to 1.0x tier."""
        assert RiskManager.confidence_size_multiplier(0.6499) == 0.75
        assert RiskManager.confidence_size_multiplier(0.65) == 1.0


class TestConfidenceTieringIntegration:
    """Test confidence tiering through the full RiskManager pipeline."""

    def _make_signal(self, confidence: float) -> "TradingSignal":
        from src.strategy.schemas import SignalDirection, TradingSignal
        return TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=confidence,
            signal_class=2,
            entry_price=2000.0,
        )

    def test_low_confidence_reduces_position_size(self):
        rm = RiskManager(initial_equity=10000.0)
        result_high = rm.check_trade(self._make_signal(0.70), equity=10000.0, atr=20.0)
        result_low = rm.check_trade(self._make_signal(0.52), equity=10000.0, atr=20.0)
        assert result_high.approved and result_low.approved
        assert result_low.position_size < result_high.position_size

    def test_confidence_tier_adjustment_logged(self):
        rm = RiskManager(initial_equity=10000.0)
        result = rm.check_trade(self._make_signal(0.52), equity=10000.0, atr=20.0)
        assert result.approved
        assert any("Confidence tier" in adj for adj in result.adjustments)

    def test_high_confidence_no_tier_adjustment(self):
        rm = RiskManager(initial_equity=10000.0)
        result = rm.check_trade(self._make_signal(0.70), equity=10000.0, atr=20.0)
        assert result.approved
        assert not any("Confidence tier" in adj for adj in result.adjustments)
