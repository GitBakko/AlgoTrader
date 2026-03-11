"""Tests for ScalpScoreStrategy confluence voting model."""
import polars as pl
import pytest

from src.strategy.scalp_score_strategy import (
    ScalpScoreStrategy,
    DEFAULT_MIN_CONFLUENCE,
    KILLZONE_MIN_CONFLUENCE,
    OFF_KILLZONE_MIN_CONFLUENCE,
)
from src.strategy.schemas import SignalDirection, StrategyConfig


@pytest.fixture
def strategy() -> ScalpScoreStrategy:
    return ScalpScoreStrategy()


@pytest.fixture
def config() -> StrategyConfig:
    return StrategyConfig(
        epic="XAUUSD",
        stop_multiplier=1.0,
        risk_reward_ratio=2.0,
    )


@pytest.fixture
def recent_bars() -> pl.DataFrame:
    return pl.DataFrame({
        "close": [100.0 + i * 0.1 for i in range(20)],
        "high": [100.5 + i * 0.1 for i in range(20)],
        "low": [99.5 + i * 0.1 for i in range(20)],
        "volume": [1000 + i * 10 for i in range(20)],
    })


def _make_bar(**overrides) -> dict:
    """Create a current_bar dict with sensible defaults."""
    bar = {
        "close": 105.0,
        "high": 105.5,
        "low": 104.5,
        "open": 104.8,
        "volume": 1500,
        "atr_14": 1.0,
        "rsi_14": 40.0,
        "ema_9": 105.1,
        "ema_21": 104.8,
        "macd_histogram": 0.3,
        "macd": 0.5,
        "macd_signal": 0.2,
        "adx_14": 25.0,
        "volume_sma_20": 1200,
        "bb_upper": 106.0,
        "bb_lower": 104.0,
        "bb_middle": 105.0,
        "keltner_upper": 106.5,
        "keltner_lower": 103.5,
    }
    bar.update(overrides)
    return bar


class TestScalpScoreProperties:
    def test_name(self, strategy):
        assert strategy.name == "scalp_score"

    def test_applicable_regimes(self, strategy):
        regimes = strategy.applicable_regimes
        assert "trending_up" in regimes
        assert "trending_down" in regimes
        assert "ranging" in regimes

    def test_default_confluence_is_3(self):
        assert DEFAULT_MIN_CONFLUENCE == 3

    def test_killzone_confluence_is_3(self):
        assert KILLZONE_MIN_CONFLUENCE == 3

    def test_off_killzone_confluence_is_4(self):
        assert OFF_KILLZONE_MIN_CONFLUENCE == 4


class TestIndividualVotes:
    """Test each indicator vote function independently."""

    def test_ema_vote_bullish(self):
        value, _ = ScalpScoreStrategy._vote_ema(105.5, 104.8)
        assert value == 1

    def test_ema_vote_bearish(self):
        value, _ = ScalpScoreStrategy._vote_ema(104.5, 105.2)
        assert value == -1

    def test_ema_vote_neutral_when_close(self):
        value, _ = ScalpScoreStrategy._vote_ema(105.0, 105.0)
        assert value == 0

    def test_rsi_vote_buy_oversold(self):
        value, _ = ScalpScoreStrategy._vote_rsi(35.0)
        assert value == 1

    def test_rsi_vote_sell_overbought(self):
        value, _ = ScalpScoreStrategy._vote_rsi(65.0)
        assert value == -1

    def test_rsi_vote_neutral(self):
        value, _ = ScalpScoreStrategy._vote_rsi(50.0)
        assert value == 0

    def test_macd_vote_bullish(self):
        value, _ = ScalpScoreStrategy._vote_macd(0.5, 0.6, 0.1)
        assert value == 1

    def test_macd_vote_bearish(self):
        value, _ = ScalpScoreStrategy._vote_macd(-0.5, -0.6, -0.1)
        assert value == -1

    def test_volume_vote_strong(self):
        value, _ = ScalpScoreStrategy._vote_volume(1500, 1000)
        assert value == 1

    def test_volume_vote_weak(self):
        value, _ = ScalpScoreStrategy._vote_volume(900, 1000)
        assert value == 0

    def test_adx_vote_trending(self):
        value, _ = ScalpScoreStrategy._vote_adx(25.0)
        assert value == 1

    def test_adx_vote_no_trend(self):
        value, _ = ScalpScoreStrategy._vote_adx(15.0)
        assert value == 0

    def test_bb_vote_squeeze_up(self):
        # BB inside Keltner (squeeze), price above middle
        value, _ = ScalpScoreStrategy._vote_bb_squeeze(
            106.0, 104.0, 107.0, 103.0, 105.5, 105.0
        )
        assert value == 1

    def test_bb_vote_squeeze_down(self):
        value, _ = ScalpScoreStrategy._vote_bb_squeeze(
            106.0, 104.0, 107.0, 103.0, 104.5, 105.0
        )
        assert value == -1


class TestConfluenceHold:
    def test_hold_on_invalid_price(self, strategy, recent_bars, config):
        bar = _make_bar(close=0)
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD

    def test_hold_on_invalid_atr(self, strategy, recent_bars, config):
        bar = _make_bar(atr_14=0)
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD

    def test_hold_on_conflicting_signals(self, strategy, recent_bars, config):
        """Mixed indicators should not reach confluence."""
        bar = _make_bar(
            ema_9=105.1, ema_21=104.9,  # weak bullish
            rsi_14=50.0,                  # neutral
            macd_histogram=-0.1,          # bearish
            adx_14=12.0,                  # no trend
            volume=900, volume_sma_20=1000,  # weak volume
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD


class TestConfluenceBuy:
    def test_strong_buy_confluence(self, strategy, recent_bars, config):
        """All indicators aligned bullish -> BUY."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # BUY vote
            rsi_14=38.0,                     # BUY vote
            macd_histogram=0.5,              # BUY vote
            macd=0.6, macd_signal=0.1,
            adx_14=28.0,                     # confirms trend
            volume=1500, volume_sma_20=1000, # confirms volume
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence >= 0.5
        assert signal.suggested_stop < signal.entry_price < signal.suggested_tp

    def test_minimal_buy_confluence(self, strategy, recent_bars, config):
        """Just enough votes (3) should still produce BUY."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # BUY vote (1)
            rsi_14=38.0,                     # BUY vote (2)
            macd_histogram=0.5,              # BUY vote (3)
            macd=0.6, macd_signal=0.1,
            adx_14=15.0,                     # no confirmation
            volume=900, volume_sma_20=1000,  # no volume
            utc_hour=14,                     # NY kill zone
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY


class TestConfluenceSell:
    def test_strong_sell_confluence(self, strategy, recent_bars, config):
        """All indicators aligned bearish -> SELL."""
        bar = _make_bar(
            close=105.0,
            ema_9=104.5, ema_21=105.2,     # SELL vote
            rsi_14=65.0,                     # SELL vote
            macd_histogram=-0.5,             # SELL vote
            macd=-0.6, macd_signal=-0.1,
            adx_14=28.0,                     # confirms trend
            volume=1500, volume_sma_20=1000, # confirms volume
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence >= 0.5
        assert signal.suggested_tp < signal.entry_price < signal.suggested_stop


class TestVWAPGateFilter:
    def test_vwap_blocks_buy_below(self, strategy, recent_bars, config):
        """GURU: Cannot buy below VWAP."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=32.0,
            volume=1500, volume_sma_20=1000,
            vwap=106.0,  # price 105 < VWAP 106
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction != SignalDirection.BUY

    def test_vwap_blocks_sell_above(self, strategy, recent_bars, config):
        """GURU: Cannot sell above VWAP."""
        bar = _make_bar(
            close=105.0,
            ema_9=104.5, ema_21=105.2,
            rsi_14=65.0,
            macd_histogram=-0.5, macd=-0.6, macd_signal=-0.1,
            adx_14=28.0,
            volume=1500, volume_sma_20=1000,
            vwap=104.0,  # price 105 > VWAP 104
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction != SignalDirection.SELL

    def test_vwap_allows_buy_above(self, strategy, recent_bars, config):
        """Buy above VWAP should pass."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=28.0,
            volume=1500, volume_sma_20=1000,
            vwap=104.0,
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY

    def test_no_vwap_allows_both(self, strategy, recent_bars, config):
        """No VWAP data = no gating."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=28.0,
            volume=1500, volume_sma_20=1000,
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY


class TestHTFConfluence:
    def test_htf_bullish_boosts_buy(self, strategy, recent_bars, config):
        """HTF bullish adds 1 vote to buy, making a borderline signal pass."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # BUY (1)
            rsi_14=38.0,                     # BUY (2)
            macd_histogram=0.05,             # weak BUY (3)
            macd=0.1, macd_signal=0.05,
            adx_14=15.0,                     # no confirmation
            volume=900, volume_sma_20=1000,  # no volume
            htf_bias="bullish",              # +1 to buy
            utc_hour=14,                     # kill zone
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY

    def test_htf_opposing_can_block(self, strategy, recent_bars, config):
        """HTF opposing removes 1 buy vote, potentially blocking borderline signal."""
        bar = _make_bar(
            ema_9=105.3, ema_21=104.9,     # weak BUY (1)
            rsi_14=42.0,                     # BUY (2)
            macd_histogram=0.2,              # BUY (3)
            macd=0.3, macd_signal=0.1,
            adx_14=15.0,                     # no confirmation
            volume=900, volume_sma_20=1000,  # no volume
            htf_bias="bearish",              # -1 from buy
            utc_hour=14,                     # kill zone
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        # With HTF bearish: buy_count goes from 3 to 2, below min 3
        assert signal.direction == SignalDirection.HOLD


class TestSessionFilter:
    def test_off_killzone_needs_more_confluence(self, strategy, recent_bars, config):
        """Outside kill zones, need 4 votes instead of 3."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # BUY (1)
            rsi_14=38.0,                     # BUY (2)
            macd_histogram=0.5,              # BUY (3)
            macd=0.6, macd_signal=0.1,
            adx_14=15.0,                     # no confirmation
            volume=900, volume_sma_20=1000,  # no volume
            utc_hour=18,                     # outside kill zone (session_mult < 1.0)
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        # 3 directional BUY votes, but off-killzone needs 4 -> HOLD
        assert signal.direction == SignalDirection.HOLD

    def test_killzone_accepts_3_votes(self, strategy, recent_bars, config):
        """During kill zone, 3 votes are enough."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # BUY (1)
            rsi_14=38.0,                     # BUY (2)
            macd_histogram=0.5,              # BUY (3)
            macd=0.6, macd_signal=0.1,
            adx_14=15.0,
            volume=900, volume_sma_20=1000,
            utc_hour=14,                     # NY kill zone
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY


class TestBacktest:
    def test_backtest_adds_columns(self, strategy):
        df = pl.DataFrame({
            "close": [100.0, 101.0, 102.0, 103.0, 104.0] * 10,
            "high": [100.5, 101.5, 102.5, 103.5, 104.5] * 10,
            "low": [99.5, 100.5, 101.5, 102.5, 103.5] * 10,
            "open": [99.8, 100.8, 101.8, 102.8, 103.8] * 10,
            "volume": [1000] * 50,
            "atr_14": [1.0] * 50,
            "rsi_14": [50.0] * 50,
            "ema_9": [101.0] * 50,
            "ema_21": [100.5] * 50,
            "macd_histogram": [0.1] * 50,
            "macd": [0.2] * 50,
            "macd_signal": [0.1] * 50,
            "adx_14": [25.0] * 50,
            "volume_sma_20": [1000] * 50,
            "bb_upper": [103.0] * 50,
            "bb_lower": [97.0] * 50,
            "bb_middle": [100.0] * 50,
            "keltner_upper": [104.0] * 50,
            "keltner_lower": [96.0] * 50,
        })
        result = strategy.generate_backtest_signals(df, "XAUUSD", "15min")
        assert "signal_direction" in result.columns
        assert "signal_confidence" in result.columns
        assert len(result) == len(df)
