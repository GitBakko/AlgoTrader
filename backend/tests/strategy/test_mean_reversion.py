"""Tests for MeanReversionStrategy signal generation."""

from unittest.mock import MagicMock, patch

import pytest

from src.strategy.mean_reversion_strategy import MeanReversionStrategy


def _make_market_data(**overrides) -> dict:
    """Return default market data dict, with optional overrides."""
    data = {
        "current_price": 100.0,
        "bb_pctb": 0.5,
        "rsi": 50.0,
        "adx": 20.0,
        "vwap_z_score": 0.0,
        "bb_middle": 100.0,
        "vwap": 100.0,
        "atr": 1.0,
    }
    data.update(overrides)
    return data


@pytest.fixture
def strategy():
    return MeanReversionStrategy()


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock get_settings to return default MR config values."""
    settings = MagicMock()
    settings.mr_z_entry = 2.0
    settings.mr_z_stop = 3.0
    settings.mr_adx_max = 30.0
    with patch("src.strategy.mean_reversion_strategy.get_settings", return_value=settings):
        yield settings


class TestSellSignal:
    def test_sell_signal_overbought(self, strategy):
        """z > 2, RSI > 70, ADX < 30 -> SELL with TP at mean."""
        data = _make_market_data(
            current_price=105.0,
            vwap_z_score=2.5,
            rsi=75.0,
            adx=20.0,
            vwap=100.0,
            atr=1.0,
        )
        sig = strategy.generate_signal(data)

        assert sig.direction == "SELL"
        assert sig.tp_level == 100.0  # TP at VWAP
        assert sig.stop_level is not None
        assert sig.stop_level > 105.0  # SL above entry
        assert sig.confidence >= 0.5
        assert "above mean" in sig.reason


class TestBuySignal:
    def test_buy_signal_oversold(self, strategy):
        """z < -2, RSI < 30, ADX < 30 -> BUY with TP at mean."""
        data = _make_market_data(
            current_price=95.0,
            vwap_z_score=-2.5,
            rsi=25.0,
            adx=20.0,
            vwap=100.0,
            atr=1.0,
        )
        sig = strategy.generate_signal(data)

        assert sig.direction == "BUY"
        assert sig.tp_level == 100.0  # TP at VWAP
        assert sig.stop_level is not None
        assert sig.stop_level < 95.0  # SL below entry
        assert sig.confidence >= 0.5
        assert "below mean" in sig.reason


class TestHoldSignals:
    def test_hold_trending(self, strategy):
        """ADX > 30 -> HOLD regardless of z-score."""
        data = _make_market_data(
            vwap_z_score=2.5,
            rsi=75.0,
            adx=35.0,
        )
        sig = strategy.generate_signal(data)

        assert sig.direction == "HOLD"
        assert "Trending" in sig.reason or "ADX" in sig.reason

    def test_hold_no_extreme(self, strategy):
        """z between -2 and 2 -> HOLD."""
        data = _make_market_data(
            vwap_z_score=1.0,
            rsi=50.0,
            adx=20.0,
        )
        sig = strategy.generate_signal(data)

        assert sig.direction == "HOLD"
        assert "No extreme" in sig.reason

    def test_sell_without_rsi_confirmation(self, strategy):
        """z > 2 but RSI < 70 -> SELL (RSI is now a confidence boost, not a hard gate)."""
        data = _make_market_data(
            vwap_z_score=2.5,
            rsi=60.0,  # Not overbought, but z-score is extreme
            adx=20.0,
        )
        sig = strategy.generate_signal(data)

        assert sig.direction == "SELL"
        # No RSI boost since RSI < 70
        assert sig.confidence < 0.95


class TestConfidence:
    def test_confidence_scales_with_zscore(self, strategy):
        """z=2.0 -> conf ~0.5, z=3.0 -> conf ~1.0."""
        # At z_entry boundary (z=2.0): confidence component = 0 -> 0.5
        data_low = _make_market_data(
            current_price=105.0,
            vwap_z_score=2.01,
            rsi=75.0,
            adx=20.0,
            atr=1.0,
        )
        sig_low = strategy.generate_signal(data_low)
        assert sig_low.direction == "SELL"
        # z=2.01 -> base 0.01, +0.2 RSI boost = 0.21, final = 0.5 + 0.21*0.5 = ~0.605
        assert sig_low.confidence == pytest.approx(0.605, abs=0.02)

        # At z_stop boundary (z=3.0): confidence component = 1 -> 1.0
        data_high = _make_market_data(
            current_price=110.0,
            vwap_z_score=3.0,
            rsi=80.0,
            adx=20.0,
            atr=1.0,
        )
        sig_high = strategy.generate_signal(data_high)
        assert sig_high.direction == "SELL"
        assert sig_high.confidence == pytest.approx(1.0, abs=0.02)

        assert sig_high.confidence > sig_low.confidence
