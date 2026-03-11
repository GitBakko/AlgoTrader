"""Tests for ScalpScore decision audit trail metadata."""
import pytest
from src.strategy.schemas import TradingSignal, SignalDirection


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


from src.strategy.scalp_score_strategy import ScalpScoreStrategy


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
