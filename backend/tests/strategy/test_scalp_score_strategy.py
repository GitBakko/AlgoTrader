"""Tests for ScalpScoreStrategy multi-indicator scoring."""
import polars as pl
import pytest

from src.strategy.scalp_score_strategy import ScalpScoreStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.models.schemas import SignalClass


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
    """Minimal recent bars for lookback (20 rows)."""
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


class TestScalpScoreStrategyProperties:
    def test_name(self, strategy):
        assert strategy.name == "scalp_score"

    def test_applicable_regimes(self, strategy):
        regimes = strategy.applicable_regimes
        assert "trending_up" in regimes
        assert "trending_down" in regimes
        assert "ranging" in regimes


class TestScalpScoreHold:
    def test_hold_on_invalid_price(self, strategy, recent_bars, config):
        bar = _make_bar(close=0)
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD

    def test_hold_on_invalid_atr(self, strategy, recent_bars, config):
        bar = _make_bar(atr_14=0)
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD

    def test_hold_on_low_score(self, strategy, recent_bars, config):
        """Conflicting signals should produce low score -> HOLD."""
        bar = _make_bar(
            ema_9=104.5, ema_21=105.2,  # bearish EMA
            rsi_14=50.0,                  # neutral RSI
            macd_histogram=-0.1,          # weak bearish MACD
            adx_14=12.0,                  # no trend
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.HOLD


class TestScalpScoreBuy:
    def test_strong_buy_signal(self, strategy, recent_bars, config):
        """All indicators aligned bullish -> strong BUY."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # bullish cross
            rsi_14=38.0,                     # oversold bounce
            macd_histogram=0.5,              # strong bullish
            macd=0.6, macd_signal=0.1,       # recent crossover
            adx_14=28.0,                     # strong trend
            volume=1500, volume_sma_20=1000, # high volume
            bb_upper=106.0, bb_lower=104.0,  # normal BB
            keltner_upper=106.5, keltner_lower=103.5,
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence > 0.6
        assert signal.suggested_stop is not None
        assert signal.suggested_tp is not None
        assert signal.suggested_stop < signal.entry_price < signal.suggested_tp

    def test_buy_stop_loss_distance(self, strategy, recent_bars, config):
        """SL should be ~1.0 ATR below entry for BUY."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=38.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=28.0,
            volume=1500, volume_sma_20=1000,
            atr_14=2.0,
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        if signal.direction == SignalDirection.BUY:
            sl_distance = signal.entry_price - signal.suggested_stop
            assert 1.5 <= sl_distance <= 2.5  # ~1.0 * ATR(2.0)


class TestScalpScoreSell:
    def test_strong_sell_signal(self, strategy, recent_bars, config):
        """All indicators aligned bearish -> strong SELL."""
        bar = _make_bar(
            close=105.0,
            ema_9=104.5, ema_21=105.2,     # bearish cross
            rsi_14=65.0,                     # overbought area
            macd_histogram=-0.5,             # strong bearish
            macd=-0.6, macd_signal=-0.1,     # recent bearish crossover
            adx_14=28.0,                     # strong trend
            volume=1500, volume_sma_20=1000, # high volume
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence > 0.6
        assert signal.suggested_stop is not None
        assert signal.suggested_tp is not None
        assert signal.suggested_tp < signal.entry_price < signal.suggested_stop


class TestScalpScoreBacktest:
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
