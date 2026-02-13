"""Tests for VWAP Standard Deviation Reversion Strategy."""

import polars as pl
import pytest

from src.models.schemas import SignalClass
from src.strategy.schemas import SignalDirection, StrategyConfig
from src.strategy.vwap_strategy import VWAPReversionStrategy


@pytest.fixture
def vwap_strategy() -> VWAPReversionStrategy:
    """Create a VWAP reversion strategy instance with default parameters."""
    return VWAPReversionStrategy(
        entry_sd=2.0,
        stop_sd=3.0,
        max_adx=25.0,
        rsi_oversold=30.0,
        rsi_overbought=70.0,
        max_volume_ratio=2.0,
    )


@pytest.fixture
def config() -> StrategyConfig:
    """Create a default strategy config."""
    return StrategyConfig(epic="XAUUSD", timeframe="1h")


@pytest.fixture
def recent_bars_minimal() -> pl.DataFrame:
    """Create minimal recent bars DataFrame."""
    return pl.DataFrame({
        "close": [100.0, 100.5, 100.2],
        "high": [101.0, 101.5, 101.2],
        "low": [99.0, 99.5, 99.2],
    })


@pytest.mark.unit
@pytest.mark.strategy
def test_name_and_regimes(vwap_strategy: VWAPReversionStrategy):
    """Test that strategy name and applicable regimes are correct."""
    assert vwap_strategy.name == "vwap_reversion"
    assert vwap_strategy.applicable_regimes == ["ranging"]


@pytest.mark.unit
@pytest.mark.strategy
def test_buy_signal_below_lower_band(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test BUY signal when price is below VWAP - 2*SD and RSI is oversold."""
    current_bar = {
        "close": 95.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": -2.5,  # Below -2.0 threshold
        "adx": 20.0,  # Below max_adx
        "rsi_14": 25.0,  # Oversold (< 30)
        "volume_sma_ratio": 1.5,  # Below max_volume_ratio
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.BUY
    assert signal.signal_class == SignalClass.BUY
    assert signal.confidence > 0.5
    assert signal.technical_confirmation is True
    assert signal.strategy_name == "vwap_reversion"
    # SL should be below entry (3*SD below VWAP)
    assert signal.suggested_stop < current_bar["close"]
    # TP should be VWAP center
    assert signal.suggested_tp == current_bar["vwap_rolling"]


@pytest.mark.unit
@pytest.mark.strategy
def test_sell_signal_above_upper_band(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test SELL signal when price is above VWAP + 2*SD and RSI is overbought."""
    current_bar = {
        "close": 105.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": 2.5,  # Above 2.0 threshold
        "adx": 20.0,  # Below max_adx
        "rsi_14": 75.0,  # Overbought (> 70)
        "volume_sma_ratio": 1.5,  # Below max_volume_ratio
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.SELL
    assert signal.signal_class == SignalClass.SELL
    assert signal.confidence > 0.5
    assert signal.technical_confirmation is True
    assert signal.strategy_name == "vwap_reversion"
    # SL should be above entry (3*SD above VWAP)
    assert signal.suggested_stop > current_bar["close"]
    # TP should be VWAP center
    assert signal.suggested_tp == current_bar["vwap_rolling"]


@pytest.mark.unit
@pytest.mark.strategy
def test_hold_when_z_score_within_bands(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test HOLD when z-score is within the entry bands."""
    current_bar = {
        "close": 101.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": 0.5,  # Within [-2, 2] range
        "adx": 20.0,
        "rsi_14": 50.0,
        "volume_sma_ratio": 1.0,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.signal_class == SignalClass.HOLD
    assert signal.confidence == 0.0
    assert signal.technical_confirmation is False


@pytest.mark.unit
@pytest.mark.strategy
def test_hold_when_adx_too_high(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test HOLD when ADX exceeds max_adx (trending market filter)."""
    current_bar = {
        "close": 95.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": -2.5,
        "adx": 30.0,  # Above max_adx=25
        "rsi_14": 25.0,
        "volume_sma_ratio": 1.5,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_hold_when_volume_too_high(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test HOLD when volume ratio exceeds max_volume_ratio (high-volume breakout filter)."""
    current_bar = {
        "close": 95.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": -2.5,
        "adx": 20.0,
        "rsi_14": 25.0,
        "volume_sma_ratio": 3.0,  # Above max_volume_ratio=2.0
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_hold_when_rsi_not_confirmed_buy(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test HOLD when z-score signals BUY but RSI is not oversold."""
    current_bar = {
        "close": 95.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": -2.5,
        "adx": 20.0,
        "rsi_14": 50.0,  # Not oversold (> 30)
        "volume_sma_ratio": 1.5,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_hold_when_rsi_not_confirmed_sell(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test HOLD when z-score signals SELL but RSI is not overbought."""
    current_bar = {
        "close": 105.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": 2.5,
        "adx": 20.0,
        "rsi_14": 50.0,  # Not overbought (< 70)
        "volume_sma_ratio": 1.5,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_buy_stop_and_tp(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test BUY signal stop loss and take profit levels."""
    vwap = 100.0
    vwap_sd = 2.0
    entry_price = 95.0  # VWAP - 2.5*SD

    current_bar = {
        "close": entry_price,
        "vwap_rolling": vwap,
        "vwap_sd": vwap_sd,
        "vwap_z_score": -2.5,
        "adx": 20.0,
        "rsi_14": 25.0,
        "volume_sma_ratio": 1.5,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    # SL should be VWAP - 3*SD (stop_sd)
    expected_stop = vwap - vwap_strategy.stop_sd * vwap_sd
    assert signal.suggested_stop == expected_stop
    assert signal.suggested_stop < entry_price  # SL below entry for BUY

    # TP should be VWAP center
    assert signal.suggested_tp == vwap
    assert signal.suggested_tp > entry_price  # TP above entry for BUY


@pytest.mark.unit
@pytest.mark.strategy
def test_sell_stop_and_tp(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test SELL signal stop loss and take profit levels."""
    vwap = 100.0
    vwap_sd = 2.0
    entry_price = 105.0  # VWAP + 2.5*SD

    current_bar = {
        "close": entry_price,
        "vwap_rolling": vwap,
        "vwap_sd": vwap_sd,
        "vwap_z_score": 2.5,
        "adx": 20.0,
        "rsi_14": 75.0,
        "volume_sma_ratio": 1.5,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    # SL should be VWAP + 3*SD (stop_sd)
    expected_stop = vwap + vwap_strategy.stop_sd * vwap_sd
    assert signal.suggested_stop == expected_stop
    assert signal.suggested_stop > entry_price  # SL above entry for SELL

    # TP should be VWAP center
    assert signal.suggested_tp == vwap
    assert signal.suggested_tp < entry_price  # TP below entry for SELL


@pytest.mark.unit
@pytest.mark.strategy
def test_hold_when_vwap_data_missing(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test HOLD when VWAP indicators are missing."""
    current_bar = {
        "close": 100.0,
        # Missing: vwap_rolling, vwap_sd, vwap_z_score
        "adx": 20.0,
        "rsi_14": 50.0,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_hold_when_price_invalid(
    vwap_strategy: VWAPReversionStrategy,
    config: StrategyConfig,
    recent_bars_minimal: pl.DataFrame,
):
    """Test HOLD when price is zero or negative."""
    current_bar = {
        "close": 0.0,
        "vwap_rolling": 100.0,
        "vwap_sd": 2.0,
        "vwap_z_score": -2.5,
        "adx": 20.0,
        "rsi_14": 25.0,
    }

    signal = vwap_strategy.generate_signal(
        epic="XAUUSD",
        current_bar=current_bar,
        recent_bars=recent_bars_minimal,
        config=config,
    )

    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_generate_backtest_signals(vwap_strategy: VWAPReversionStrategy):
    """Test batch signal generation for backtesting."""
    # Create OHLC data with VWAP indicators
    df = pl.DataFrame({
        "timestamp": pl.datetime_range(
            start=pl.datetime(2024, 1, 1),
            end=pl.datetime(2024, 1, 10),
            interval="1h",
            eager=True,
        )[:10],
        "open": [100.0] * 10,
        "high": [101.0] * 10,
        "low": [99.0] * 10,
        "close": [95.0, 105.0, 100.0, 95.0, 105.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "volume": [1000.0] * 10,
        "vwap_rolling": [100.0] * 10,
        "vwap_sd": [2.0] * 10,
        "vwap_z_score": [-2.5, 2.5, 0.0, -2.5, 2.5, 0.0, 0.0, 0.0, 0.0, 0.0],
        "adx": [20.0] * 10,
        "rsi_14": [25.0, 75.0, 50.0, 25.0, 75.0, 50.0, 50.0, 50.0, 50.0, 50.0],
        "volume_sma_ratio": [1.5] * 10,
    })

    result = vwap_strategy.generate_backtest_signals(df, epic="XAUUSD", timeframe="1h")

    assert "signal_direction" in result.columns
    assert "signal_confidence" in result.columns

    # First bar: BUY (z=-2.5, rsi=25)
    assert result["signal_direction"][0] == 1
    assert result["signal_confidence"][0] > 0.0

    # Second bar: SELL (z=2.5, rsi=75)
    assert result["signal_direction"][1] == -1
    assert result["signal_confidence"][1] > 0.0

    # Third bar: HOLD (z=0.0)
    assert result["signal_direction"][2] == 0
    assert result["signal_confidence"][2] == 0.0


@pytest.mark.unit
@pytest.mark.strategy
def test_custom_parameters():
    """Test strategy with custom parameters."""
    strategy = VWAPReversionStrategy(
        entry_sd=1.5,
        stop_sd=2.5,
        max_adx=30.0,
        rsi_oversold=25.0,
        rsi_overbought=75.0,
        max_volume_ratio=3.0,
    )

    assert strategy.entry_sd == 1.5
    assert strategy.stop_sd == 2.5
    assert strategy.max_adx == 30.0
    assert strategy.rsi_oversold == 25.0
    assert strategy.rsi_overbought == 75.0
    assert strategy.max_volume_ratio == 3.0
