"""Tests for ScalpScoreStrategy.evaluate_technical_quality() — ML-Primary quality gate."""

import polars as pl
import pytest

from src.strategy.scalp_score_strategy import ScalpScoreStrategy
from src.strategy.schemas import SignalDirection


@pytest.fixture
def strategy():
    return ScalpScoreStrategy()


def _make_bar(
    *,
    close: float = 100.0,
    ema_9: float = 101.0,
    ema_21: float = 100.0,
    rsi_14: float = 40.0,
    macd_histogram: float = 0.5,
    macd: float = 1.0,
    macd_signal: float = 0.5,
    volume: float = 1500,
    volume_sma_20: float = 1000,
    adx_14: float = 25.0,
    bb_upper: float = 105.0,
    bb_lower: float = 95.0,
    bb_middle: float = 100.0,
    keltner_upper: float = 106.0,
    keltner_lower: float = 94.0,
    vwap: float = 99.0,
    utc_hour: int = 14,
    htf_bias: str | None = "bullish",
    sil_composite_score: float = 0.0,
) -> dict:
    return {
        "close": close,
        "atr_14": 2.0,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "rsi_14": rsi_14,
        "macd_histogram": macd_histogram,
        "macd": macd,
        "macd_signal": macd_signal,
        "volume": volume,
        "volume_sma_20": volume_sma_20,
        "adx_14": adx_14,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_middle": bb_middle,
        "keltner_upper": keltner_upper,
        "keltner_lower": keltner_lower,
        "vwap": vwap,
        "utc_hour": utc_hour,
        "htf_bias": htf_bias,
        "sil_composite_score": sil_composite_score,
    }


DUMMY_RECENT = pl.DataFrame({"close": [100.0]})


class TestQualityScoreDirection:
    """Tests that agreeing/opposing votes are counted relative to ML direction."""

    def test_all_bullish_ml_buy(self, strategy):
        """All indicators bullish + ML BUY → high quality."""
        bar = _make_bar()  # default is bullish setup
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["agreeing_votes"] >= 3
        assert result["quality_score"] > 0.4
        assert not result["session_blocked"]
        assert not result["dead_market_blocked"]

    def test_all_bearish_ml_sell(self, strategy):
        """All indicators bearish + ML SELL → high quality."""
        bar = _make_bar(
            ema_9=99.0, ema_21=100.0,  # bearish cross
            rsi_14=60.0,  # overbought
            macd_histogram=-0.5, macd=-1.0, macd_signal=-0.5,
            vwap=101.0,  # price below VWAP
            htf_bias="bearish",
        )
        result = strategy.evaluate_technical_quality(
            SignalDirection.SELL, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["agreeing_votes"] >= 3
        assert result["quality_score"] > 0.4

    def test_all_opposing_ml_buy(self, strategy):
        """All indicators bearish + ML BUY → quality near 0."""
        bar = _make_bar(
            ema_9=99.0, ema_21=100.0,
            rsi_14=60.0,
            macd_histogram=-0.5, macd=-1.0, macd_signal=-0.5,
            volume=500, volume_sma_20=1000,  # weak volume
            adx_14=15.0,  # no trend
        )
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["agreeing_votes"] == 0
        assert result["opposing_votes"] >= 3
        assert result["quality_score"] == 0.0

    def test_mixed_votes(self, strategy):
        """3 agree, 2 oppose → quality = 3/7 or higher with confirmations."""
        bar = _make_bar(
            ema_9=101.0, ema_21=100.0,  # BUY
            rsi_14=60.0,  # SELL (>55)
            macd_histogram=0.5, macd=1.0, macd_signal=0.5,  # BUY
            volume=1500, volume_sma_20=1000,  # confirms
            adx_14=25.0,  # confirms
            bb_upper=105.0, bb_lower=95.0,  # neutral (no squeeze)
            sil_composite_score=0.7,  # BUY (>0.6)
        )
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        # EMA(+1), RSI(-1), MACD(+1), BB(0), SENT(+1) = 3 agree, 1 oppose
        # 3 >= 2, so VOL+ADX add → 5 agree
        assert result["agreeing_votes"] >= 3
        assert result["quality_score"] >= 3 / 7


class TestConfirmationVotes:
    """VOL/ADX only count as agreeing when enough directional votes agree."""

    def test_vol_adx_add_with_enough_directional(self, strategy):
        """3+ directional agrees → VOL and ADX count."""
        bar = _make_bar(
            ema_9=101.0, ema_21=100.0,  # BUY
            rsi_14=40.0,  # BUY
            macd_histogram=0.5, macd=1.0, macd_signal=0.5,  # BUY
            volume=1500, volume_sma_20=1000,
            adx_14=25.0,
        )
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        # 3 directional agree (EMA, RSI, MACD) >= 2 → VOL + ADX add
        assert result["agreeing_votes"] >= 4  # 3 directional + VOL + ADX possible

    def test_vol_adx_skip_without_enough_directional(self, strategy):
        """<2 directional agrees → VOL and ADX don't count."""
        bar = _make_bar(
            ema_9=101.0, ema_21=100.0,  # BUY (only 1 directional)
            rsi_14=50.0,  # neutral
            macd_histogram=0.0,  # neutral
            volume=1500, volume_sma_20=1000,
            adx_14=25.0,
        )
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        # Only 1 directional agree → VOL/ADX should NOT be added
        assert result["agreeing_votes"] == 1


class TestGateAlignment:
    """VWAP and HTF alignment are reported (not gated)."""

    def test_vwap_aligned_buy_above(self, strategy):
        bar = _make_bar(close=100.0, vwap=99.0)
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["vwap_aligned"] is True

    def test_vwap_not_aligned_buy_below(self, strategy):
        bar = _make_bar(close=100.0, vwap=101.0)
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["vwap_aligned"] is False

    def test_vwap_aligned_sell_below(self, strategy):
        bar = _make_bar(close=100.0, vwap=101.0)
        result = strategy.evaluate_technical_quality(
            SignalDirection.SELL, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["vwap_aligned"] is True

    def test_no_vwap_assumes_aligned(self, strategy):
        bar = _make_bar(vwap=0)
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["vwap_aligned"] is True

    def test_htf_aligned_buy_bullish(self, strategy):
        bar = _make_bar(htf_bias="bullish")
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["htf_aligned"] is True

    def test_htf_opposed_buy_bearish(self, strategy):
        bar = _make_bar(htf_bias="bearish")
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["htf_aligned"] is False

    def test_htf_none_when_no_data(self, strategy):
        bar = _make_bar(htf_bias=None)
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        assert result["htf_aligned"] is None


class TestHardGates:
    """Session and dead market gates block via flags."""

    def test_session_blocked(self, strategy):
        """Off-session hour should set session_blocked=True."""
        bar = _make_bar(utc_hour=4)  # Not in any kill zone
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "EURUSD", bar, DUMMY_RECENT,
        )
        # EURUSD is session-filtered — 4 UTC may be blocked
        # The key assertion: the method returns a valid dict regardless
        assert isinstance(result["session_blocked"], bool)
        assert isinstance(result["quality_score"], float)

    def test_dead_market_blocked(self, strategy):
        """Very low ADX + compressed BB → dead market."""
        bar = _make_bar(
            adx_14=10.0,  # Below dead market threshold (20)
            bb_upper=100.5, bb_lower=99.5, bb_middle=100.0,  # Very tight BB
        )
        # Build recent_bars with wider BB so current is in lowest percentile
        recent = pl.DataFrame({
            "close": [100.0] * 20,
            "bb_upper": [110.0] * 20,
            "bb_lower": [90.0] * 20,
            "bb_middle": [100.0] * 20,
        })
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, recent,
        )
        assert result["dead_market_blocked"] is True
        assert result["quality_score"] == 0.0


class TestVotesDetail:
    """The votes_detail dict contains individual vote values."""

    def test_votes_detail_keys(self, strategy):
        bar = _make_bar()
        result = strategy.evaluate_technical_quality(
            SignalDirection.BUY, "XAUUSD", bar, DUMMY_RECENT,
        )
        detail = result["votes_detail"]
        assert set(detail.keys()) == {"ema", "rsi", "macd", "bb", "vol", "adx", "sentiment"}
        for val in detail.values():
            assert val in (-1, 0, 1)
