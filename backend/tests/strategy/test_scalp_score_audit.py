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
