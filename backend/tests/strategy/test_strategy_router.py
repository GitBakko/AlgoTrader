"""Tests for Strategy Router."""

import polars as pl
import pytest

from src.models.schemas import SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal
from src.strategy.strategy_router import StrategyRouter


class MockHoldStrategy(BaseStrategy):
    """Mock strategy that always returns HOLD."""

    @property
    def name(self) -> str:
        return "mock_hold"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["ranging"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        return TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=SignalClass.HOLD,
            entry_price=100.0,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        return ohlc_df.with_columns([
            pl.lit(0).alias("signal_direction"),
            pl.lit(0.0).alias("signal_confidence"),
        ])


class MockBuyStrategy(BaseStrategy):
    """Mock strategy that always returns BUY."""

    @property
    def name(self) -> str:
        return "mock_buy"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["ranging", "trending_up"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        return TradingSignal(
            epic=epic,
            direction=SignalDirection.BUY,
            confidence=0.70,
            signal_class=SignalClass.BUY,
            entry_price=100.0,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        return ohlc_df.with_columns([
            pl.lit(1).alias("signal_direction"),
            pl.lit(0.70).alias("signal_confidence"),
        ])


class MockSellStrategy(BaseStrategy):
    """Mock strategy that always returns SELL."""

    @property
    def name(self) -> str:
        return "mock_sell"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_down"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        return TradingSignal(
            epic=epic,
            direction=SignalDirection.SELL,
            confidence=0.65,
            signal_class=SignalClass.SELL,
            entry_price=100.0,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        return ohlc_df.with_columns([
            pl.lit(-1).alias("signal_direction"),
            pl.lit(0.65).alias("signal_confidence"),
        ])


class MockErrorStrategy(BaseStrategy):
    """Mock strategy that always raises an exception."""

    @property
    def name(self) -> str:
        return "mock_error"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["ranging"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        raise ValueError("Mock strategy error")

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        raise ValueError("Mock strategy error")


@pytest.fixture
def router() -> StrategyRouter:
    """Create a strategy router with default configuration."""
    return StrategyRouter()


@pytest.fixture
def config() -> StrategyConfig:
    """Create a default strategy config."""
    return StrategyConfig(epic="XAUUSD", timeframe="1h")


@pytest.fixture
def current_bar() -> dict:
    """Create a simple current bar."""
    return {"close": 100.0}


@pytest.fixture
def recent_bars() -> pl.DataFrame:
    """Create a minimal recent bars DataFrame."""
    return pl.DataFrame({"close": [100.0]})


@pytest.mark.unit
@pytest.mark.strategy
def test_register_strategy(router: StrategyRouter):
    """Test that registered strategy appears in registered_strategies."""
    mock_strategy = MockBuyStrategy()
    router.register_strategy(mock_strategy)

    assert "mock_buy" in router.registered_strategies
    assert router.get_strategy("mock_buy") is mock_strategy


@pytest.mark.unit
@pytest.mark.strategy
def test_select_strategy_trending(router: StrategyRouter):
    """Test strategy selection for trending_up regime returns ml_ensemble-type."""
    # Register strategies
    router.register_strategy(MockBuyStrategy())
    router.register_strategy(MockHoldStrategy())

    # trending_up should select ml_ensemble (but we don't have it registered)
    # So it should fallback to all registered strategies
    strategies = router.select_strategy(regime="trending_up", epic="XAUUSD")

    # Since ml_ensemble is not registered, fallback to all
    assert len(strategies) == 2


@pytest.mark.unit
@pytest.mark.strategy
def test_select_strategy_ranging(router: StrategyRouter):
    """Test strategy selection for ranging regime returns ordered list."""
    # Register strategies
    mock_hold = MockHoldStrategy()
    mock_buy = MockBuyStrategy()
    router.register_strategy(mock_hold)
    router.register_strategy(mock_buy)

    # ranging should try: squeeze_breakout, vwap_reversion, ml_ensemble
    # None are registered, so fallback to all
    strategies = router.select_strategy(regime="ranging", epic="XAUUSD")

    assert len(strategies) == 2
    assert mock_hold in strategies or mock_buy in strategies


@pytest.mark.unit
@pytest.mark.strategy
def test_select_strategy_unknown_regime(router: StrategyRouter):
    """Test strategy selection for unknown regime falls back to all registered."""
    mock_hold = MockHoldStrategy()
    mock_buy = MockBuyStrategy()
    router.register_strategy(mock_hold)
    router.register_strategy(mock_buy)

    # Unknown regime should fall back to all registered
    strategies = router.select_strategy(regime="unknown_regime", epic="XAUUSD")

    # Since "unknown_regime" not in DEFAULT_REGIME_MAP, uses default ["ml_ensemble"]
    # ml_ensemble not registered, so fallback to all
    assert len(strategies) == 2


@pytest.mark.unit
@pytest.mark.strategy
def test_generate_signal_first_strategy_wins(
    router: StrategyRouter,
    config: StrategyConfig,
    current_bar: dict,
    recent_bars: pl.DataFrame,
):
    """Test that first non-HOLD strategy wins."""
    # Register BUY strategy first
    mock_buy = MockBuyStrategy()
    router.register_strategy(mock_buy)

    # Custom regime map that uses mock_buy
    router._regime_map = {"test": ["mock_buy"]}

    signal = router.generate_signal(
        epic="XAUUSD",
        regime="test",
        current_bar=current_bar,
        recent_bars=recent_bars,
        config=config,
    )

    assert signal.direction == SignalDirection.BUY
    assert signal.confidence == 0.70
    assert signal.strategy_name == "mock_buy"


@pytest.mark.unit
@pytest.mark.strategy
def test_generate_signal_fallthrough(
    router: StrategyRouter,
    config: StrategyConfig,
    current_bar: dict,
    recent_bars: pl.DataFrame,
):
    """Test that first HOLD falls through to second BUY strategy."""
    # Register HOLD first, then BUY
    router.register_strategy(MockHoldStrategy())
    router.register_strategy(MockBuyStrategy())

    # Custom regime map with both strategies
    router._regime_map = {"test": ["mock_hold", "mock_buy"]}

    signal = router.generate_signal(
        epic="XAUUSD",
        regime="test",
        current_bar=current_bar,
        recent_bars=recent_bars,
        config=config,
    )

    # Should skip mock_hold (returns HOLD) and use mock_buy (returns BUY)
    assert signal.direction == SignalDirection.BUY
    assert signal.strategy_name == "mock_buy"


@pytest.mark.unit
@pytest.mark.strategy
def test_generate_signal_all_hold(
    router: StrategyRouter,
    config: StrategyConfig,
    current_bar: dict,
    recent_bars: pl.DataFrame,
):
    """Test that all HOLD strategies result in HOLD signal."""
    # Register only HOLD strategies
    router.register_strategy(MockHoldStrategy())

    router._regime_map = {"test": ["mock_hold"]}

    signal = router.generate_signal(
        epic="XAUUSD",
        regime="test",
        current_bar=current_bar,
        recent_bars=recent_bars,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.0
    assert signal.strategy_name is None


@pytest.mark.unit
@pytest.mark.strategy
def test_signal_has_strategy_name(
    router: StrategyRouter,
    config: StrategyConfig,
    current_bar: dict,
    recent_bars: pl.DataFrame,
):
    """Test that winning signal is tagged with strategy name."""
    mock_sell = MockSellStrategy()
    router.register_strategy(mock_sell)

    router._regime_map = {"test": ["mock_sell"]}

    signal = router.generate_signal(
        epic="XAUUSD",
        regime="test",
        current_bar=current_bar,
        recent_bars=recent_bars,
        config=config,
    )

    assert signal.direction == SignalDirection.SELL
    assert signal.strategy_name == "mock_sell"


@pytest.mark.unit
@pytest.mark.strategy
def test_custom_regime_map():
    """Test that custom regime map is used."""
    custom_map = {
        "bull": ["mock_buy"],
        "bear": ["mock_sell"],
    }
    router = StrategyRouter(regime_map=custom_map)

    router.register_strategy(MockBuyStrategy())
    router.register_strategy(MockSellStrategy())

    # Test bull regime
    strategies = router.select_strategy(regime="bull", epic="XAUUSD")
    assert len(strategies) == 1
    assert strategies[0].name == "mock_buy"

    # Test bear regime
    strategies = router.select_strategy(regime="bear", epic="XAUUSD")
    assert len(strategies) == 1
    assert strategies[0].name == "mock_sell"


@pytest.mark.unit
@pytest.mark.strategy
def test_strategy_error_handled(
    router: StrategyRouter,
    config: StrategyConfig,
    current_bar: dict,
    recent_bars: pl.DataFrame,
):
    """Test that if strategy raises an exception, router skips to next."""
    # Register error strategy first, then working strategy
    router.register_strategy(MockErrorStrategy())
    router.register_strategy(MockBuyStrategy())

    router._regime_map = {"test": ["mock_error", "mock_buy"]}

    signal = router.generate_signal(
        epic="XAUUSD",
        regime="test",
        current_bar=current_bar,
        recent_bars=recent_bars,
        config=config,
    )

    # Should skip mock_error (raises exception) and use mock_buy
    assert signal.direction == SignalDirection.BUY
    assert signal.strategy_name == "mock_buy"


@pytest.mark.unit
@pytest.mark.strategy
def test_get_strategy_returns_none_for_unknown():
    """Test that get_strategy returns None for unregistered strategy."""
    router = StrategyRouter()
    assert router.get_strategy("nonexistent") is None


@pytest.mark.unit
@pytest.mark.strategy
def test_generate_backtest_signals(router: StrategyRouter):
    """Test batch signal generation for backtesting uses first strategy."""
    router.register_strategy(MockBuyStrategy())
    router.register_strategy(MockHoldStrategy())

    router._regime_map = {"test": ["mock_buy", "mock_hold"]}

    df = pl.DataFrame({
        "close": [100.0, 101.0, 102.0],
    })

    result = router.generate_backtest_signals(
        ohlc_df=df,
        epic="XAUUSD",
        timeframe="1h",
        regime="test",
    )

    # Should use mock_buy (first strategy)
    assert "signal_direction" in result.columns
    assert "signal_confidence" in result.columns
    assert result["signal_direction"][0] == 1  # BUY
    assert result["signal_confidence"][0] == 0.70


@pytest.mark.unit
@pytest.mark.strategy
def test_generate_backtest_signals_no_strategies():
    """Test batch signal generation returns zeros when no strategies registered."""
    router = StrategyRouter()

    df = pl.DataFrame({
        "close": [100.0, 101.0, 102.0],
    })

    result = router.generate_backtest_signals(
        ohlc_df=df,
        epic="XAUUSD",
        timeframe="1h",
        regime="unknown",
    )

    # Should return zeros
    assert "signal_direction" in result.columns
    assert "signal_confidence" in result.columns
    assert result["signal_direction"].sum() == 0
    assert result["signal_confidence"].sum() == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_default_regime_map_structure():
    """Test that DEFAULT_REGIME_MAP has expected structure."""
    assert "trending_up" in StrategyRouter.DEFAULT_REGIME_MAP
    assert "trending_down" in StrategyRouter.DEFAULT_REGIME_MAP
    assert "ranging" in StrategyRouter.DEFAULT_REGIME_MAP

    # Check ranging has multiple strategies
    ranging_strategies = StrategyRouter.DEFAULT_REGIME_MAP["ranging"]
    assert len(ranging_strategies) >= 2
    assert "ml_ensemble" in ranging_strategies


@pytest.mark.unit
@pytest.mark.strategy
def test_none_regime_defaults_to_ranging(
    router: StrategyRouter,
    config: StrategyConfig,
    current_bar: dict,
    recent_bars: pl.DataFrame,
):
    """Test that None regime defaults to ranging behavior."""
    router.register_strategy(MockBuyStrategy())

    # Use default regime map but register strategy that's not in it
    # This will trigger fallback to all registered
    strategies = router.select_strategy(regime=None, epic="XAUUSD")

    # None should default to "ranging" regime
    # Since mock_buy not in ranging's default list, fallback to all registered
    assert len(strategies) >= 1
