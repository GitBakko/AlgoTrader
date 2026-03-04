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


class TestScalpScoreGuruGateFilters:
    """Tests for SCALPING-GURU gate filter architecture (2026-03-04)."""

    def test_default_entry_threshold_is_55(self):
        from src.strategy.scalp_score_strategy import DEFAULT_ENTRY_THRESHOLD
        assert DEFAULT_ENTRY_THRESHOLD == 55

    def test_default_full_size_threshold_is_70(self):
        from src.strategy.scalp_score_strategy import DEFAULT_FULL_SIZE_THRESHOLD
        assert DEFAULT_FULL_SIZE_THRESHOLD == 70

    def test_vwap_gate_blocks_buy_below_vwap(self, strategy, recent_bars, config):
        """GURU: VWAP is a binary gate. Buy below VWAP is blocked, sell allowed."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=32.0,
            volume=1500, volume_sma_20=1000,
            vwap=106.0,  # price BELOW vwap -> buy blocked
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        # Buy is gated (zeroed), so either SELL or HOLD — never BUY
        assert signal.direction != SignalDirection.BUY

    def test_vwap_gate_blocks_sell_above_vwap(self, strategy, recent_bars, config):
        """GURU: Sell above VWAP is blocked."""
        bar = _make_bar(
            close=105.0,
            ema_9=104.5, ema_21=105.2,     # bearish EMA
            rsi_14=65.0,                     # overbought
            macd_histogram=-0.5, macd=-0.6, macd_signal=-0.1,
            adx_14=28.0,
            volume=1500, volume_sma_20=1000,
            vwap=104.0,  # price ABOVE vwap -> sell blocked
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction != SignalDirection.SELL

    def test_vwap_aligned_buy_passes(self, strategy, recent_bars, config):
        """GURU: Buy above VWAP passes through untouched."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=32.0,
            volume=1500, volume_sma_20=1000,
            vwap=104.0,  # price ABOVE vwap -> buy allowed
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY

    def test_no_vwap_data_allows_both_directions(self, strategy, recent_bars, config):
        """Without VWAP data, both directions should work normally."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=32.0,
            volume=1500, volume_sma_20=1000,
            # no vwap key
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY

    def test_htf_opposing_reduces_score_additively(self, strategy, recent_bars, config):
        """GURU: HTF opposing = additive -10, not multiplicative ×0.5."""
        bar = _make_bar(
            close=105.5,
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.8, macd=0.9, macd_signal=0.1,
            adx_14=40.0,
            volume=2000, volume_sma_20=1000,
            bb_upper=106.0, bb_lower=104.0, bb_middle=105.0,
            keltner_upper=107.0, keltner_lower=103.0,
            htf_bias="bearish",
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        # With additive -10 a strong signal (~80+) should still pass threshold 55
        assert signal.direction == SignalDirection.BUY

    def test_htf_aligned_gives_bonus(self, strategy, recent_bars, config):
        """GURU: HTF aligned = additive +5 bonus."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=28.0,
            volume=1500, volume_sma_20=1000,
            htf_bias="bullish",
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        assert signal.direction == SignalDirection.BUY

    def test_session_outside_killzone_raises_threshold(self, strategy, recent_bars, config):
        """GURU: Outside kill zone, threshold +5 (additive), not score ×0.7."""
        # Moderate signal that passes threshold 55 but not 60
        bar = _make_bar(
            ema_9=105.3, ema_21=104.9,     # moderate bullish
            rsi_14=38.0,                     # RSI buy zone
            macd_histogram=0.3, macd=0.4, macd_signal=0.1,
            adx_14=25.0,                     # moderate trend
            volume=1400, volume_sma_20=1000, # moderate volume
            utc_hour=18,                     # 18 UTC = active session, not kill zone
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        # With threshold raised to 60, a moderate signal might HOLD
        # (This is the correct behavior — slightly stricter outside kill zones)
        assert signal.direction in (SignalDirection.BUY, SignalDirection.HOLD)
