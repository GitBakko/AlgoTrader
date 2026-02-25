"""Tests for trend-following strategy with ML confirmation."""

import polars as pl
import pytest

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.strategy.trend_following_strategy import TrendFollowingStrategy


@pytest.fixture
def strategy() -> TrendFollowingStrategy:
    """Create a trend-following strategy instance."""
    return TrendFollowingStrategy()


@pytest.fixture
def empty_recent_bars() -> pl.DataFrame:
    """Minimal recent bars DataFrame (not used by trend strategy)."""
    return pl.DataFrame({"close": [100.0]})


@pytest.fixture
def default_config() -> StrategyConfig:
    """Default strategy configuration."""
    return StrategyConfig()


def _make_prediction(
    signal_class: int = SignalClass.BUY,
    confidence: float = 0.65,
) -> PredictionResult:
    """Helper to create a PredictionResult for testing."""
    return PredictionResult(
        signal_class=signal_class,
        signal_name=SignalClass(signal_class).name,
        confidence=confidence,
        probabilities={"SELL": 0.10, "HOLD": 0.25, "BUY": confidence},
    )


class TestTrendFollowingSignal:
    """Tests for TrendFollowingStrategy signal generation."""

    def _make_bar(self, **overrides) -> dict:
        """Create a default bar with all conditions for a BUY signal."""
        bar = {
            "epic": "XAUUSD",
            "close": 110.0,
            "sma_50": 105.0,
            "ema_8": 109.0,
            "ema_21": 108.0,
            "ema_8_prev": 107.0,
            "ema_21_prev": 108.0,
            "adx": 30.0,
            "atr_14": 2.0,
            "prediction": _make_prediction(
                signal_class=SignalClass.BUY, confidence=0.65,
            ),
        }
        bar.update(overrides)
        return bar

    def test_name_and_regimes(self, strategy: TrendFollowingStrategy):
        """Verify strategy name and applicable regimes."""
        assert strategy.name == "trend_following"
        assert "trending_up" in strategy.applicable_regimes
        assert "trending_down" in strategy.applicable_regimes

    def test_buy_signal_all_conditions_met(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """BUY when price > SMA50, EMA8 crosses EMA21, ADX > 20, ML agrees."""
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=self._make_bar(),
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence > 0.5
        assert signal.strategy_name == "trend_following"

    def test_sell_signal_all_conditions_met(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """SELL when price < SMA50, EMA8 crosses below EMA21, ADX > 20, ML agrees."""
        bar = self._make_bar(
            close=100.0,
            sma_50=105.0,
            ema_8=101.0,
            ema_21=102.0,
            ema_8_prev=103.0,
            ema_21_prev=102.0,
            prediction=_make_prediction(
                signal_class=SignalClass.SELL, confidence=0.70,
            ),
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence > 0.5

    def test_hold_when_ml_disagrees(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when macro says BUY but ML says SELL."""
        bar = self._make_bar(
            prediction=_make_prediction(
                signal_class=SignalClass.SELL, confidence=0.70,
            ),
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_hold_when_adx_low(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when ADX < 20 (no trend strength)."""
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=self._make_bar(adx=15.0),
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_hold_when_ema_not_crossed(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when EMAs haven't crossed in the trend direction."""
        bar = self._make_bar(
            ema_8=107.0,
            ema_21=108.0,  # ema_8 still below ema_21
            ema_8_prev=106.0,
            ema_21_prev=108.0,  # no crossover
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_hold_when_no_prediction(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when ML prediction is missing."""
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=self._make_bar(prediction=None),
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_hold_when_missing_data(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when required data fields are None."""
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=self._make_bar(sma_50=None),
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_hold_when_atr_zero(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when ATR is zero."""
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=self._make_bar(atr_14=0.0),
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_continuation_buy_ema_already_crossed(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """BUY when EMAs already crossed (continuation, not fresh crossover)."""
        bar = self._make_bar(
            ema_8=109.0,
            ema_21=108.0,  # ema_8 > ema_21
            ema_8_prev=108.5,
            ema_21_prev=108.0,  # already crossed previously
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.BUY

    def test_confidence_blending(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """Confidence should blend ADX factor and ML confidence."""
        bar = self._make_bar(adx=25.0)  # ADX factor = 25/50 = 0.5
        bar["prediction"] = _make_prediction(
            signal_class=SignalClass.BUY, confidence=0.80,
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        # blended = 0.4 * 0.5 + 0.6 * 0.80 = 0.2 + 0.48 = 0.68
        assert abs(signal.confidence - 0.68) < 0.01

    def test_hold_when_ml_says_hold(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when ML predicts HOLD (not BUY or SELL)."""
        bar = self._make_bar(
            prediction=_make_prediction(
                signal_class=SignalClass.HOLD, confidence=0.50,
            ),
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_hold_when_price_equals_sma(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """HOLD when price equals SMA50 (no clear trend direction)."""
        bar = self._make_bar(close=105.0, sma_50=105.0)
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.HOLD

    def test_sell_continuation_ema_already_crossed(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """SELL when EMAs already crossed down (continuation)."""
        bar = self._make_bar(
            close=100.0,
            sma_50=105.0,
            ema_8=101.0,
            ema_21=102.0,  # ema_8 < ema_21
            ema_8_prev=101.5,
            ema_21_prev=102.0,  # already crossed down
            prediction=_make_prediction(
                signal_class=SignalClass.SELL, confidence=0.70,
            ),
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        assert signal.direction == SignalDirection.SELL

    def test_adx_capped_at_50_for_confidence(
        self,
        strategy: TrendFollowingStrategy,
        empty_recent_bars: pl.DataFrame,
        default_config: StrategyConfig,
    ):
        """ADX factor should be capped at 1.0 (ADX 50+)."""
        bar = self._make_bar(adx=80.0)  # ADX > 50
        bar["prediction"] = _make_prediction(
            signal_class=SignalClass.BUY, confidence=0.65,
        )
        signal = strategy.generate_signal(
            epic="XAUUSD",
            current_bar=bar,
            recent_bars=empty_recent_bars,
            config=default_config,
        )
        # blended = 0.4 * 1.0 + 0.6 * 0.65 = 0.4 + 0.39 = 0.79
        assert abs(signal.confidence - 0.79) < 0.01


@pytest.mark.unit
@pytest.mark.strategy
class TestTrendFollowingBacktest:
    """Tests for trend-following backtest signal generation."""

    def test_backtest_signals_columns(
        self,
        strategy: TrendFollowingStrategy,
    ):
        """Verify that generate_backtest_signals returns proper columns."""
        df = pl.DataFrame({
            "close": [110.0, 112.0, 108.0],
            "sma_50": [105.0, 105.0, 105.0],
            "ema_8": [109.0, 111.0, 107.0],
            "ema_21": [108.0, 110.0, 108.0],
            "adx": [30.0, 35.0, 25.0],
        })

        result = strategy.generate_backtest_signals(df, "XAUUSD", "1h")

        assert "signal_direction" in result.columns
        assert "signal_confidence" in result.columns
        assert result["signal_direction"].is_in([-1, 0, 1]).all()

    def test_backtest_missing_columns_returns_zeros(
        self,
        strategy: TrendFollowingStrategy,
    ):
        """Verify that missing columns result in zero signals."""
        df = pl.DataFrame({
            "close": [110.0, 112.0],
            # Missing sma_50, ema_8, etc.
        })

        result = strategy.generate_backtest_signals(df, "XAUUSD", "1h")

        assert "signal_direction" in result.columns
        assert result["signal_direction"].sum() == 0


@pytest.mark.unit
@pytest.mark.strategy
class TestStrategyRouterIntegration:
    """Tests for trend-following integration with strategy router."""

    def test_trend_following_in_default_regime_map(self):
        """Verify trend_following is in DEFAULT_REGIME_MAP for trending regimes."""
        from src.strategy.strategy_router import StrategyRouter

        regime_map = StrategyRouter.DEFAULT_REGIME_MAP

        assert "trend_following" in regime_map["trending_up"]
        assert "trend_following" in regime_map["trending_down"]
        # Should be first (primary) strategy
        assert regime_map["trending_up"][0] == "trend_following"
        assert regime_map["trending_down"][0] == "trend_following"

    def test_trend_following_not_in_ranging(self):
        """Verify trend_following is NOT in ranging regime."""
        from src.strategy.strategy_router import StrategyRouter

        regime_map = StrategyRouter.DEFAULT_REGIME_MAP
        assert "trend_following" not in regime_map["ranging"]

    def test_router_selects_trend_following_for_trending(self):
        """Verify router selects trend_following strategy for trending regime."""
        from src.strategy.strategy_router import StrategyRouter

        router = StrategyRouter()
        strat = TrendFollowingStrategy()
        router.register_strategy(strat)

        strategies = router.select_strategy("trending_up", "XAUUSD")
        assert strat in strategies
        assert strategies[0] is strat  # Should be first
