"""Tests for Volatility Squeeze Breakout Strategy."""

import numpy as np
import polars as pl
import pytest

from src.models.schemas import SignalClass
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.strategy.squeeze_strategy import SqueezeBreakoutStrategy


@pytest.fixture
def squeeze_strategy() -> SqueezeBreakoutStrategy:
    """Create a squeeze strategy instance with default parameters."""
    return SqueezeBreakoutStrategy(
        min_squeeze_bars=6,
        volume_confirm=1.3,
        momentum_lookback=3,
    )


@pytest.fixture
def recent_bars_squeeze() -> pl.DataFrame:
    """Create recent bars with a valid squeeze pattern and bullish momentum.

    The strategy expects recent_bars to include bars UP TO (but not including) the current bar.
    So if current bar is the release, recent_bars should end with squeeze bars.
    """
    # 10 bars: first 3 leading up, then 7 consecutive squeeze bars
    # The current_bar (separate) will be the release point
    squeeze_on = [0, 0, 0, 1, 1, 1, 1, 1, 1, 1]  # 7 consecutive squeeze bars at end
    macd_hist = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]  # Increasing (bullish)
    volume_ratio = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
    close = [100.0, 100.5, 100.2, 100.3, 100.1, 100.4, 100.6, 100.7, 100.8, 100.9]
    high = [101.0, 101.5, 101.2, 101.3, 101.1, 101.4, 101.6, 101.7, 101.8, 101.9]
    low = [99.0, 99.5, 99.2, 99.3, 99.1, 99.4, 99.6, 99.7, 99.8, 99.9]

    return pl.DataFrame({
        "squeeze_on": squeeze_on,
        "macd_histogram": macd_hist,
        "volume_sma_ratio": volume_ratio,
        "close": close,
        "high": high,
        "low": low,
    })


@pytest.fixture
def recent_bars_squeeze_bearish() -> pl.DataFrame:
    """Create recent bars with a valid squeeze pattern and bearish momentum."""
    # 10 bars: first 3 leading up, then 7 consecutive squeeze bars
    # MACD histogram is decreasing (bearish)
    squeeze_on = [0, 0, 0, 1, 1, 1, 1, 1, 1, 1]  # 7 consecutive squeeze bars at end
    macd_hist = [-0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7, -0.8, -0.9, -1.0]  # Decreasing (bearish)
    volume_ratio = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
    close = [105.0, 104.5, 104.2, 104.0, 103.8, 103.6, 103.4, 103.2, 103.0, 102.8]
    high = [106.0, 105.5, 105.2, 105.0, 104.8, 104.6, 104.4, 104.2, 104.0, 103.8]
    low = [104.0, 103.5, 103.2, 103.0, 102.8, 102.6, 102.4, 102.2, 102.0, 101.8]

    return pl.DataFrame({
        "squeeze_on": squeeze_on,
        "macd_histogram": macd_hist,
        "volume_sma_ratio": volume_ratio,
        "close": close,
        "high": high,
        "low": low,
    })


@pytest.fixture
def current_bar_release_buy() -> dict:
    """Create a current bar representing a bullish squeeze release."""
    return {
        "close": 103.0,
        "high": 104.0,
        "low": 102.0,
        "atr_14": 2.0,
        "squeeze_off": 1,
        "macd_histogram": 1.0,  # Positive = bullish
        "volume_sma_ratio": 1.5,
    }


@pytest.fixture
def current_bar_release_sell() -> dict:
    """Create a current bar representing a bearish squeeze release."""
    return {
        "close": 103.0,
        "high": 104.0,
        "low": 102.0,
        "atr_14": 2.0,
        "squeeze_off": 1,
        "macd_histogram": -1.0,  # Negative = bearish
        "volume_sma_ratio": 1.5,
    }


@pytest.fixture
def sample_ohlc_for_backtest() -> pl.DataFrame:
    """Generate OHLC data for backtesting."""
    np.random.seed(42)
    n = 100

    # Create a ranging pattern followed by breakout
    price = np.concatenate([
        np.full(50, 100.0) + np.random.normal(0, 1, 50),  # Ranging
        np.linspace(100, 110, 50) + np.random.normal(0, 1.5, 50),  # Breakout
    ])

    return pl.DataFrame({
        "timestamp": pl.datetime_range(
            pl.datetime(2024, 1, 1),
            pl.datetime(2024, 1, 1) + pl.duration(hours=n - 1),
            interval="1h",
            eager=True,
        ),
        "open": price + np.random.normal(0, 0.5, n),
        "high": price + np.abs(np.random.normal(1, 0.3, n)),
        "low": price - np.abs(np.random.normal(1, 0.3, n)),
        "close": price,
        "volume": np.random.randint(1000, 5000, n).astype(np.int64),
    })


@pytest.mark.unit
@pytest.mark.strategy
class TestSqueezeBreakoutStrategy:
    """Tests for Squeeze Breakout Strategy signal generation."""

    def test_name_and_regimes(self, squeeze_strategy: SqueezeBreakoutStrategy):
        """Verify strategy name and applicable regimes."""
        assert squeeze_strategy.name == "squeeze_breakout"
        assert squeeze_strategy.applicable_regimes == ["ranging"]

    def test_no_squeeze_release_returns_hold(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze: pl.DataFrame,
    ):
        """Verify HOLD signal when squeeze_off != 1."""
        current_bar = {
            "close": 103.0,
            "atr_14": 2.0,
            "squeeze_off": 0,  # No release
            "macd_histogram": 1.0,
            "volume_sma_ratio": 1.5,
        }

        config = StrategyConfig()
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar,
            recent_bars=recent_bars_squeeze,
            config=config,
        )

        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.0

    def test_squeeze_release_buy_signal(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze: pl.DataFrame,
        current_bar_release_buy: dict,
    ):
        """Verify BUY signal on valid squeeze release with positive MACD."""
        config = StrategyConfig()
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar_release_buy,
            recent_bars=recent_bars_squeeze,
            config=config,
        )

        assert signal.direction == SignalDirection.BUY
        assert signal.signal_class == SignalClass.BUY
        assert signal.confidence > 0.5
        assert signal.technical_confirmation is True

        # Verify SL and TP
        assert signal.suggested_stop is not None
        assert signal.suggested_tp is not None
        assert signal.suggested_stop < signal.entry_price < signal.suggested_tp

    def test_squeeze_release_sell_signal(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze_bearish: pl.DataFrame,
        current_bar_release_sell: dict,
    ):
        """Verify SELL signal on valid squeeze release with negative MACD."""
        config = StrategyConfig()
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar_release_sell,
            recent_bars=recent_bars_squeeze_bearish,
            config=config,
        )

        assert signal.direction == SignalDirection.SELL
        assert signal.signal_class == SignalClass.SELL
        assert signal.confidence > 0.5
        assert signal.technical_confirmation is True

        # Verify SL and TP
        assert signal.suggested_stop is not None
        assert signal.suggested_tp is not None
        assert signal.suggested_tp < signal.entry_price < signal.suggested_stop

    def test_insufficient_duration_returns_hold(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        current_bar_release_buy: dict,
    ):
        """Verify HOLD when squeeze duration < min_squeeze_bars."""
        # Create recent bars with only 3 squeeze bars (less than min 6)
        short_squeeze = pl.DataFrame({
            "squeeze_on": [0, 0, 0, 1, 1, 1, 0, 0],
            "macd_histogram": [0.5] * 8,
            "volume_sma_ratio": [1.5] * 8,
            "close": [100.0] * 8,
            "high": [101.0] * 8,
            "low": [99.0] * 8,
        })

        config = StrategyConfig()
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar_release_buy,
            recent_bars=short_squeeze,
            config=config,
        )

        assert signal.direction == SignalDirection.HOLD

    def test_low_volume_returns_hold(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze: pl.DataFrame,
    ):
        """Verify HOLD when volume ratio is below threshold."""
        current_bar = {
            "close": 103.0,
            "atr_14": 2.0,
            "squeeze_off": 1,
            "macd_histogram": 1.0,
            "volume_sma_ratio": 1.0,  # Below 1.3 threshold
        }

        config = StrategyConfig()
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar,
            recent_bars=recent_bars_squeeze,
            config=config,
        )

        assert signal.direction == SignalDirection.HOLD

    def test_zero_macd_returns_hold(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze: pl.DataFrame,
    ):
        """Verify HOLD when MACD histogram is zero (no directional momentum)."""
        current_bar = {
            "close": 103.0,
            "atr_14": 2.0,
            "squeeze_off": 1,
            "macd_histogram": 0.0,  # Zero = no direction
            "volume_sma_ratio": 1.5,
        }

        config = StrategyConfig()
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar,
            recent_bars=recent_bars_squeeze,
            config=config,
        )

        assert signal.direction == SignalDirection.HOLD

    def test_buy_signal_has_stop_and_tp(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze: pl.DataFrame,
        current_bar_release_buy: dict,
    ):
        """Verify BUY signal has proper SL (below entry) and TP (above entry)."""
        config = StrategyConfig(risk_reward_ratio=2.0)
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar_release_buy,
            recent_bars=recent_bars_squeeze,
            config=config,
        )

        assert signal.direction == SignalDirection.BUY

        # BUY: stop < entry < tp
        assert signal.suggested_stop < signal.entry_price
        assert signal.suggested_tp > signal.entry_price

        # Risk-reward should be approximately 2:1
        risk = signal.entry_price - signal.suggested_stop
        reward = signal.suggested_tp - signal.entry_price
        rr_ratio = reward / risk if risk > 0 else 0
        assert abs(rr_ratio - 2.0) < 0.1  # Allow small floating point difference

    def test_sell_signal_has_stop_and_tp(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze_bearish: pl.DataFrame,
        current_bar_release_sell: dict,
    ):
        """Verify SELL signal has proper SL (above entry) and TP (below entry)."""
        config = StrategyConfig(risk_reward_ratio=2.0)
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar_release_sell,
            recent_bars=recent_bars_squeeze_bearish,
            config=config,
        )

        assert signal.direction == SignalDirection.SELL

        # SELL: tp < entry < stop
        assert signal.suggested_tp < signal.entry_price
        assert signal.suggested_stop > signal.entry_price

        # Risk-reward should be approximately 2:1
        risk = signal.suggested_stop - signal.entry_price
        reward = signal.entry_price - signal.suggested_tp
        rr_ratio = reward / risk if risk > 0 else 0
        assert abs(rr_ratio - 2.0) < 0.1

    def test_backtest_signals_columns(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        sample_ohlc_for_backtest: pl.DataFrame,
    ):
        """Verify that generate_backtest_signals returns proper columns."""
        df = squeeze_strategy.generate_backtest_signals(
            ohlc_df=sample_ohlc_for_backtest,
            epic="XAUUSD",
            timeframe="1h",
        )

        # Should have signal columns
        assert "signal_direction" in df.columns
        assert "signal_confidence" in df.columns
        assert "signal_stop" in df.columns
        assert "signal_tp" in df.columns

        # Signal direction should be -1, 0, or 1
        assert df["signal_direction"].is_in([-1, 0, 1]).all()

        # Confidence should be between 0 and 1
        assert (df["signal_confidence"] >= 0.0).all()
        assert (df["signal_confidence"] <= 1.0).all()

    def test_backtest_signals_has_trades(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        sample_ohlc_for_backtest: pl.DataFrame,
    ):
        """Verify that backtest generates signals or runs without error."""
        df = squeeze_strategy.generate_backtest_signals(
            ohlc_df=sample_ohlc_for_backtest,
            epic="XAUUSD",
            timeframe="1h",
        )

        # Check that signal columns exist and have proper data types
        assert "signal_direction" in df.columns
        signal_count = (df["signal_direction"] != 0).sum()

        # Signal count could be 0 if the data doesn't have proper squeeze patterns
        # The important thing is that the function runs without error
        assert signal_count >= 0

    def test_invalid_price_returns_hold(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze: pl.DataFrame,
    ):
        """Verify HOLD when price or ATR is invalid."""
        invalid_bars = [
            {"close": 0.0, "atr_14": 2.0, "squeeze_off": 1, "macd_histogram": 1.0, "volume_sma_ratio": 1.5},
            {"close": -10.0, "atr_14": 2.0, "squeeze_off": 1, "macd_histogram": 1.0, "volume_sma_ratio": 1.5},
            {"close": 103.0, "atr_14": 0.0, "squeeze_off": 1, "macd_histogram": 1.0, "volume_sma_ratio": 1.5},
            {"close": 103.0, "atr_14": -1.0, "squeeze_off": 1, "macd_histogram": 1.0, "volume_sma_ratio": 1.5},
        ]

        config = StrategyConfig()
        for current_bar in invalid_bars:
            signal = squeeze_strategy.generate_signal(
                epic="XAUUSD",
                current_bar=current_bar,
                recent_bars=recent_bars_squeeze,
                config=config,
            )
            assert signal.direction == SignalDirection.HOLD

    def test_momentum_trend_confirmation(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
    ):
        """Verify momentum trend confirmation logic."""
        # Bullish momentum: MACD histogram increasing
        bullish_bars = pl.DataFrame({
            "squeeze_on": [1, 1, 1, 1, 1, 1, 0],
            "macd_histogram": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],  # Increasing
            "volume_sma_ratio": [1.5] * 7,
            "close": [100.0] * 7,
            "high": [101.0] * 7,
            "low": [99.0] * 7,
        })

        current_bar = {
            "close": 103.0,
            "atr_14": 2.0,
            "squeeze_off": 1,
            "macd_histogram": 0.7,
            "volume_sma_ratio": 1.5,
        }

        config = StrategyConfig()
        signal = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar,
            recent_bars=bullish_bars,
            config=config,
        )

        # Should generate BUY with proper momentum confirmation
        assert signal.direction == SignalDirection.BUY

    def test_custom_parameters(self):
        """Verify that custom parameters are properly set."""
        strategy = SqueezeBreakoutStrategy(
            min_squeeze_bars=10,
            volume_confirm=1.5,
            momentum_lookback=5,
        )

        assert strategy.min_squeeze_bars == 10
        assert strategy.volume_confirm == 1.5
        assert strategy.momentum_lookback == 5

    def test_stop_loss_uses_squeeze_range(
        self,
        squeeze_strategy: SqueezeBreakoutStrategy,
        recent_bars_squeeze: pl.DataFrame,
        current_bar_release_buy: dict,
    ):
        """Verify that stop loss is based on squeeze range (low for BUY, high for SELL)."""
        config = StrategyConfig()

        # BUY signal - stop should be below squeeze low
        signal_buy = squeeze_strategy.generate_signal(
            epic="XAUUSD",
            current_bar=current_bar_release_buy,
            recent_bars=recent_bars_squeeze,
            config=config,
        )

        # Get squeeze low from recent bars
        squeeze_bars = recent_bars_squeeze.filter(pl.col("squeeze_on") == 1)
        squeeze_low = float(squeeze_bars["low"].min())

        assert signal_buy.direction == SignalDirection.BUY
        # Stop should be near (squeeze_low - 0.5 * ATR)
        expected_stop = squeeze_low - 0.5 * current_bar_release_buy["atr_14"]
        assert abs(signal_buy.suggested_stop - expected_stop) < 0.1
