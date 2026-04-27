"""Tests for ScalpScore decision audit trail metadata."""
import polars as pl
import pytest
from unittest.mock import MagicMock

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.scalp_score_strategy import ScalpScoreStrategy
from src.strategy.strategy_manager import StrategyManager
from src.strategy.schemas import TradingSignal, SignalDirection, StrategyConfig


class TestTradingSignalMetadata:
    """TradingSignal metadata field tests."""

    def test_trading_signal_has_metadata_field(self):
        """TradingSignal should have a metadata dict, empty by default."""
        sig = TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=0.67,
            signal_class=2,
            entry_price=2047.5,
        )
        assert isinstance(sig.metadata, dict)
        assert sig.metadata == {}

    def test_trading_signal_metadata_survives_model_copy(self):
        """metadata should persist through model_copy() calls."""
        sig = TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=0.67,
            signal_class=2,
            entry_price=2047.5,
            metadata={"votes": {"ema": {"value": 1}}},
        )
        sig2 = sig.model_copy(update={"confidence": 0.33})
        assert sig2.metadata == {"votes": {"ema": {"value": 1}}}
        assert sig2.confidence == 0.33

    def test_trading_signal_metadata_default_factory_isolation(self):
        """Each instance should get its own dict (no shared mutable default)."""
        sig1 = TradingSignal(
            epic="XAUUSD", direction=SignalDirection.BUY,
            confidence=0.5, signal_class=2, entry_price=100.0,
        )
        sig2 = TradingSignal(
            epic="BTCUSD", direction=SignalDirection.SELL,
            confidence=0.5, signal_class=0, entry_price=50000.0,
        )
        sig1.metadata["test"] = True
        assert "test" not in sig2.metadata


def _make_bar(**overrides) -> dict:
    """Create current_bar dict with all-bullish defaults for audit tests."""
    bar = {
        "close": 105.0,
        "high": 105.5,
        "low": 104.5,
        "open": 104.8,
        "volume": 1500,
        "atr_14": 1.0,
        "rsi_14": 38.0,         # oversold → BUY
        "ema_9": 105.5,
        "ema_21": 104.8,        # bullish spread
        "macd_histogram": 0.5,
        "macd": 0.6,
        "macd_signal": 0.1,     # bullish
        "adx_14": 28.0,         # trending
        "volume_sma_20": 1000,  # vol ratio 1.5 > 1.2 → confirms
        "bb_upper": 106.0,
        "bb_lower": 104.0,
        "bb_middle": 105.0,
        "keltner_upper": 106.5,
        "keltner_lower": 103.5,
        "vwap": 104.0,          # price > VWAP → BUY allowed
        "htf_bias": "bullish",
        "utc_hour": 14,         # NY kill zone
    }
    bar.update(overrides)
    return bar


def _make_recent_bars() -> pl.DataFrame:
    return pl.DataFrame({
        "close": [100.0 + i * 0.1 for i in range(20)],
        "high": [100.5 + i * 0.1 for i in range(20)],
        "low": [99.5 + i * 0.1 for i in range(20)],
        "volume": [1000 + i * 10 for i in range(20)],
    })


def _make_config() -> StrategyConfig:
    return StrategyConfig(epic="XAUUSD", stop_multiplier=1.0, risk_reward_ratio=2.0)


class TestVoteFunctionDetails:
    """Each vote function returns (int, dict) with underlying data."""

    def test_vote_ema_bullish(self):
        # Spread must be > 0.1% to be bullish: (2050-2045)/2045 ≈ 0.24%
        value, details = ScalpScoreStrategy._vote_ema(2050.0, 2045.0)
        assert value == 1
        assert details == {"ema_9": 2050.0, "ema_21": 2045.0}

    def test_vote_ema_bearish(self):
        value, details = ScalpScoreStrategy._vote_ema(2040.0, 2045.0)
        assert value == -1
        assert details == {"ema_9": 2040.0, "ema_21": 2045.0}

    def test_vote_ema_neutral(self):
        value, details = ScalpScoreStrategy._vote_ema(2045.0, 2045.0)
        assert value == 0
        assert details == {"ema_9": 2045.0, "ema_21": 2045.0}

    def test_vote_rsi_oversold(self):
        value, details = ScalpScoreStrategy._vote_rsi(38.5)
        assert value == 1
        assert details == {"rsi_14": 38.5}

    def test_vote_rsi_overbought(self):
        value, details = ScalpScoreStrategy._vote_rsi(62.0)
        assert value == -1
        assert details == {"rsi_14": 62.0}

    def test_vote_macd_bullish(self):
        value, details = ScalpScoreStrategy._vote_macd(0.45, 1.23, 0.78)
        assert value == 1
        assert details == {"histogram": 0.45, "macd": 1.23, "signal": 0.78}

    def test_vote_volume_strong(self):
        value, details = ScalpScoreStrategy._vote_volume(15200, 12100)
        assert value == 1
        assert details == {"volume": 15200, "volume_sma_20": 12100}

    def test_vote_volume_weak(self):
        value, details = ScalpScoreStrategy._vote_volume(10000, 12100)
        assert value == 0
        assert details == {"volume": 10000, "volume_sma_20": 12100}

    def test_vote_adx_trending(self):
        value, details = ScalpScoreStrategy._vote_adx(28.7)
        assert value == 1
        assert details == {"adx_14": 28.7}

    def test_vote_adx_flat(self):
        value, details = ScalpScoreStrategy._vote_adx(15.0)
        assert value == 0
        assert details == {"adx_14": 15.0}

    def test_vote_bb_squeeze_breakout_up(self):
        value, details = ScalpScoreStrategy._vote_bb_squeeze(
            bb_upper=2052, bb_lower=2038,
            keltner_upper=2055, keltner_lower=2035,
            price=2047.5, bb_middle=2045,
        )
        assert value == 1
        assert details["bb_upper"] == 2052
        assert details["bb_lower"] == 2038
        assert details["kc_upper"] == 2055
        assert details["kc_lower"] == 2035
        assert details["price"] == 2047.5
        assert details["bb_mid"] == 2045


class TestGenerateSignalMetadata:
    """generate_signal() should populate signal.metadata with full audit data."""

    def test_executed_signal_has_votes_in_metadata(self):
        strategy = ScalpScoreStrategy(min_confluence=3)
        bar = _make_bar()
        signal = strategy.generate_signal(
            "XAUUSD", bar, _make_recent_bars(), _make_config(),
        )
        assert signal.direction == SignalDirection.BUY
        assert "votes" in signal.metadata
        votes = signal.metadata["votes"]
        for name in ["ema", "rsi", "macd", "volume", "adx", "bb_keltner"]:
            assert name in votes, f"Missing vote: {name}"
            assert "value" in votes[name], f"Missing value in vote {name}"

    def test_executed_signal_has_gates_in_metadata(self):
        strategy = ScalpScoreStrategy(min_confluence=3)
        bar = _make_bar()
        signal = strategy.generate_signal(
            "XAUUSD", bar, _make_recent_bars(), _make_config(),
        )
        assert signal.direction == SignalDirection.BUY
        assert "gates" in signal.metadata
        gates = signal.metadata["gates"]
        for gate in ["session", "dead_market", "vwap", "htf", "confluence"]:
            assert gate in gates, f"Missing gate: {gate}"

    def test_executed_signal_has_market_snapshot(self):
        strategy = ScalpScoreStrategy(min_confluence=3)
        bar = _make_bar()
        signal = strategy.generate_signal(
            "XAUUSD", bar, _make_recent_bars(), _make_config(),
        )
        assert signal.direction == SignalDirection.BUY
        assert "market_snapshot" in signal.metadata
        snap = signal.metadata["market_snapshot"]
        for key in ["atr", "rsi", "adx", "vwap", "htf_bias"]:
            assert key in snap, f"Missing snapshot key: {key}"

    def test_hold_signal_has_audit_metadata(self):
        """HOLD signals must carry audit metadata so the signal-audit drawer
        can render the decisional path (gate that failed + market snapshot)
        instead of just a generic rejection_reason string. Regression guard
        for the 2026-04-27 UX gap."""
        strategy = ScalpScoreStrategy(min_confluence=3)
        bar = _make_bar(close=0)  # invalid price → HOLD on data_quality gate
        signal = strategy.generate_signal(
            "XAUUSD", bar, _make_recent_bars(), _make_config(),
        )
        assert signal.direction == SignalDirection.HOLD
        # data_quality gate carries the rejection cause
        assert "gates" in signal.metadata
        assert signal.metadata["gates"]["data_quality"]["passed"] is False
        # market snapshot is always available — even when we hold early.
        assert "market_snapshot" in signal.metadata


class TestProcessScalpMlMetadata:
    """_process_scalp() should add ml section to signal.metadata."""

    def _make_strategy_manager(self):
        sm = StrategyManager.__new__(StrategyManager)
        sm._scalp_strategy = MagicMock()
        sm.scalp_mode = True
        sm._configs = {}
        sm._orb_fvg_strategy = None
        sm.orb_fvg_epics = set()
        sm.excluded_epics = set()
        return sm

    def _make_signal(self, direction=SignalDirection.BUY, confidence=0.67):
        return TradingSignal(
            epic="XAUUSD", direction=direction, confidence=confidence,
            signal_class=2, entry_price=2047.5, strategy_name="scalp_score",
            metadata={"votes": {"ema": {"value": 1}}, "gates": {}, "market_snapshot": {}},
        )

    def _make_prediction(self, signal_class=SignalClass.BUY, confidence=0.72):
        return PredictionResult(
            signal_class=signal_class,
            signal_name="BUY",
            confidence=confidence,
            probabilities={"SELL": 0.15, "HOLD": 0.13, "BUY": 0.72},
        )

    def test_ml_agree_metadata(self):
        sm = self._make_strategy_manager()
        signal = self._make_signal()
        prediction = self._make_prediction(signal_class=SignalClass.BUY, confidence=0.72)
        sm._scalp_strategy.generate_signal.return_value = signal
        market_data = {"current_price": 2047.5, "atr": 16.8}

        result = sm._process_scalp(prediction, "XAUUSD", market_data)

        assert "ml" in result.metadata
        ml = result.metadata["ml"]
        assert ml["agreement"] == "agree"
        assert ml["confidence_before"] == pytest.approx(0.67, abs=0.01)
        assert ml["confidence_after"] == pytest.approx(0.67, abs=0.01)

    def test_ml_disagree_halves_confidence(self):
        sm = self._make_strategy_manager()
        signal = self._make_signal(direction=SignalDirection.BUY, confidence=0.67)
        prediction = self._make_prediction(signal_class=SignalClass.SELL, confidence=0.72)
        prediction = PredictionResult(
            signal_class=SignalClass.SELL,
            signal_name="SELL",
            confidence=0.72,
            probabilities={"SELL": 0.72, "HOLD": 0.13, "BUY": 0.15},
        )
        sm._scalp_strategy.generate_signal.return_value = signal
        market_data = {"current_price": 2047.5, "atr": 16.8}

        result = sm._process_scalp(prediction, "XAUUSD", market_data)

        assert result.metadata["ml"]["agreement"] == "disagree"
        # ML disagree applies 0.5x — 0.67 * 0.5 = 0.335
        assert result.metadata["ml"]["confidence_after"] == pytest.approx(0.335, abs=0.01)

    def test_ml_neutral_halves_confidence(self):
        sm = self._make_strategy_manager()
        signal = self._make_signal(direction=SignalDirection.BUY, confidence=0.67)
        prediction = PredictionResult(
            signal_class=SignalClass.HOLD,
            signal_name="HOLD",
            confidence=0.50,
            probabilities={"SELL": 0.20, "HOLD": 0.50, "BUY": 0.30},
        )
        sm._scalp_strategy.generate_signal.return_value = signal
        market_data = {"current_price": 2047.5, "atr": 16.8}

        result = sm._process_scalp(prediction, "XAUUSD", market_data)

        assert result.metadata["ml"]["agreement"] == "neutral"
        # ML neutral applies 0.75x — 0.67 * 0.75 ≈ 0.5025
        assert result.metadata["ml"]["confidence_after"] == pytest.approx(0.5025, abs=0.01)
