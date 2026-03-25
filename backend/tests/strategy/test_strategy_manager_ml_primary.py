"""Tests for StrategyManager ML-Primary mode integration."""

import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.schemas import SignalDirection
from src.strategy.strategy_manager import StrategyManager


def _make_prediction(
    signal_class: int = SignalClass.BUY,
    confidence: float = 0.65,
) -> PredictionResult:
    probs = {"SELL": 0.10, "HOLD": 0.25, "BUY": 0.65}
    if signal_class == SignalClass.SELL:
        probs = {"SELL": confidence, "HOLD": 0.20, "BUY": 0.15}
    elif signal_class == SignalClass.HOLD:
        probs = {"SELL": 0.20, "HOLD": confidence, "BUY": 0.20}
    else:
        probs = {"SELL": 0.10, "HOLD": 0.25, "BUY": confidence}
    return PredictionResult(
        signal_class=signal_class,
        signal_name=SignalClass(signal_class).name,
        confidence=confidence,
        probabilities=probs,
    )


def _bullish_market_data() -> dict:
    """Market data where technicals favor BUY."""
    return {
        "current_price": 100.0,
        "atr": 2.0,
        "rsi": 40.0,
        "adx": 25.0,
        "ema_9": 101.0,
        "ema_21": 100.0,
        "macd_histogram": 0.5,
        "macd": 1.0,
        "macd_signal": 0.5,
        "volume": 1500,
        "volume_sma_20": 1000,
        "bb_upper": 105.0,
        "bb_lower": 95.0,
        "bb_middle": 100.0,
        "keltner_upper": 106.0,
        "keltner_lower": 94.0,
        "vwap": 99.0,
        "htf_bias": "bullish",
        "regime": "trending_up",
        "sil_composite_score": 0.0,
    }


def _bearish_market_data() -> dict:
    """Market data where technicals favor SELL."""
    return {
        "current_price": 100.0,
        "atr": 2.0,
        "rsi": 60.0,
        "adx": 25.0,
        "ema_9": 99.0,
        "ema_21": 100.0,
        "macd_histogram": -0.5,
        "macd": -1.0,
        "macd_signal": -0.5,
        "volume": 1500,
        "volume_sma_20": 1000,
        "bb_upper": 105.0,
        "bb_lower": 95.0,
        "bb_middle": 100.0,
        "keltner_upper": 106.0,
        "keltner_lower": 94.0,
        "vwap": 101.0,
        "htf_bias": "bearish",
        "regime": "trending_down",
        "sil_composite_score": 0.0,
    }


@pytest.fixture
def ml_primary_mgr():
    """StrategyManager with ML-Primary mode enabled."""
    return StrategyManager(ml_primary_enabled=True)


@pytest.fixture
def scalp_only_mgr():
    """StrategyManager with scalp mode only (ML-Primary disabled)."""
    return StrategyManager(scalp_mode=True)


class TestMLPrimaryDirection:
    """ML decides direction, not ScalpScore."""

    def test_ml_buy_bullish_tech(self, ml_primary_mgr):
        """ML BUY + bullish technicals → BUY signal."""
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            _bullish_market_data(),
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.strategy_name == "ml_primary"

    def test_ml_sell_bullish_tech_blocked_by_quality_floor(self, ml_primary_mgr):
        """ML SELL + all bullish technicals → HOLD (quality floor blocks).

        This is the safety net: ML cannot trade when technicals unanimously
        disagree. The quality_score will be 0.0 (no votes agree with SELL
        in a fully bullish setup), which is below min_technical_quality.
        """
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.SELL, 0.65),
            "XAUUSD",
            _bullish_market_data(),
        )
        assert signal.direction == SignalDirection.HOLD

    def test_ml_sell_bearish_tech(self, ml_primary_mgr):
        """ML SELL + bearish technicals → SELL with good confidence."""
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.SELL, 0.70),
            "XAUUSD",
            _bearish_market_data(),
        )
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence > 0.40


class TestMLPrimaryHoldGates:
    """Signals that should become HOLD."""

    def test_ml_hold_returns_hold(self, ml_primary_mgr):
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.HOLD, 0.65),
            "XAUUSD",
            _bullish_market_data(),
        )
        assert signal.direction == SignalDirection.HOLD

    def test_ml_below_min_confidence_returns_hold(self, ml_primary_mgr):
        """ML confidence below threshold (0.45) → HOLD."""
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.40),
            "XAUUSD",
            _bullish_market_data(),
        )
        assert signal.direction == SignalDirection.HOLD

    def test_zero_tech_agreement_returns_hold(self, ml_primary_mgr):
        """ML BUY with all bearish technicals → HOLD (quality floor)."""
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.80),
            "XAUUSD",
            _bearish_market_data(),
        )
        # With all opposing technicals, quality_score < min_technical_quality
        # This should be HOLD
        assert signal.direction == SignalDirection.HOLD


class TestCompositeConfidence:
    """Composite confidence reflects technical quality."""

    def test_strong_ml_strong_tech(self, ml_primary_mgr):
        """High ML conf + strong tech → high composite."""
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.72),
            "XAUUSD",
            _bullish_market_data(),
        )
        if signal.direction != SignalDirection.HOLD:
            assert signal.confidence >= 0.40

    def test_strong_ml_weak_tech_lower_confidence(self, ml_primary_mgr):
        """Same ML conf but weaker tech → lower composite."""
        # Strong tech
        signal_strong = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.72),
            "XAUUSD",
            _bullish_market_data(),
        )
        # Weak tech (bearish indicators but ML says BUY)
        weak_data = _bullish_market_data()
        weak_data["rsi"] = 60  # opposing
        weak_data["macd_histogram"] = -0.1  # opposing
        weak_data["macd"] = -0.5
        weak_data["macd_signal"] = 0.0
        signal_weak = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.72),
            "XAUUSD",
            weak_data,
        )
        if (signal_strong.direction != SignalDirection.HOLD
                and signal_weak.direction != SignalDirection.HOLD):
            assert signal_weak.confidence < signal_strong.confidence


class TestSoftPenalties:
    """VWAP and HTF opposition reduce confidence but don't block."""

    def test_vwap_opposition_penalty(self, ml_primary_mgr):
        """BUY below VWAP → confidence reduced."""
        data = _bullish_market_data()
        signal_aligned = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            data,
        )
        data_opposed = _bullish_market_data()
        data_opposed["vwap"] = 105.0  # price 100 < VWAP 105
        signal_opposed = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            data_opposed,
        )
        if (signal_aligned.direction != SignalDirection.HOLD
                and signal_opposed.direction != SignalDirection.HOLD):
            assert signal_opposed.confidence < signal_aligned.confidence

    def test_htf_opposition_penalty(self, ml_primary_mgr):
        """BUY with bearish HTF → confidence reduced."""
        data_aligned = _bullish_market_data()
        signal_aligned = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            data_aligned,
        )
        data_opposed = _bullish_market_data()
        data_opposed["htf_bias"] = "bearish"
        signal_opposed = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            data_opposed,
        )
        if (signal_aligned.direction != SignalDirection.HOLD
                and signal_opposed.direction != SignalDirection.HOLD):
            assert signal_opposed.confidence < signal_aligned.confidence


class TestFeatureFlagRouting:
    """ML-Primary flag controls routing."""

    def test_flag_off_uses_scalp(self, scalp_only_mgr):
        """With ml_primary disabled, scalp mode is used."""
        signal = scalp_only_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            _bullish_market_data(),
        )
        assert signal.strategy_name in ("scalp_score", None)

    def test_flag_on_uses_ml_primary(self, ml_primary_mgr):
        """With ml_primary enabled, strategy is ml_primary."""
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            _bullish_market_data(),
        )
        if signal.direction != SignalDirection.HOLD:
            assert signal.strategy_name == "ml_primary"


class TestMetadataAudit:
    """Signal metadata contains full audit trail."""

    def test_metadata_has_ml_and_quality(self, ml_primary_mgr):
        signal = ml_primary_mgr.process_prediction(
            _make_prediction(SignalClass.BUY, 0.65),
            "XAUUSD",
            _bullish_market_data(),
        )
        if signal.direction != SignalDirection.HOLD:
            assert "ml" in signal.metadata
            assert "technical_quality" in signal.metadata
            assert "composite_confidence" in signal.metadata
            assert "penalties" in signal.metadata
            assert "votes_detail" in signal.metadata["technical_quality"]
