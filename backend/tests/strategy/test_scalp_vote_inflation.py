"""Test that confirmation votes don't inflate weak directional signals."""
import polars as pl
import pytest

from src.strategy.scalp_score_strategy import ScalpScoreStrategy
from src.strategy.base_strategy import StrategyConfig


def _make_bar(overrides: dict) -> dict:
    """Create a minimal current_bar for generate_signal."""
    bar = {
        "close": 100.0,
        "atr_14": 1.0,
        "utc_hour": 14,
        "ema_9": 100.0,
        "ema_21": 100.0,
        "rsi_14": 50.0,
        "macd_histogram": 0.0,
        "macd_signal": 0.0,
        "bb_upper": 102.0,
        "bb_lower": 98.0,
        "bb_middle": 100.0,
        "adx_14": 25.0,
        "volume": 1500,
        "volume_sma_20": 1000,
        "keltner_upper": 101.5,
        "keltner_lower": 98.5,
        "vwap": 0,
        "htf_bias": None,
        "sil_composite_score": 0.0,
    }
    bar.update(overrides)
    return bar


def _make_config() -> StrategyConfig:
    return StrategyConfig(
        stop_multiplier=1.0,
        risk_reward_ratio=2.0,
    )


def test_weak_directional_not_inflated_to_buy():
    """2/5 directional BUY should NOT be inflated to >= min_confluence by VOL+ADX."""
    strategy = ScalpScoreStrategy()
    # 2 directional BUY: MACD=+1, BB=+1 (squeeze breakout up)
    # 0 directional SELL
    # 3 neutral: EMA=0, RSI=0, SENT=0
    # Confirmations: VOL=+1, ADX=+1
    # OLD behavior: buy_count = 2 + 1 + 1 = 4 >= 3 → BUY signal (WRONG!)
    # NEW behavior: buy_dir=2 < 3 → confirmations NOT added → buy_count=2 < 3 → HOLD
    bar = _make_bar({
        "ema_9": 100.0, "ema_21": 100.0,  # neutral
        "rsi_14": 50.0,  # neutral
        "macd_histogram": 0.5,  # BUY
        "bb_upper": 101.0, "bb_lower": 99.0,
        "keltner_upper": 102.0, "keltner_lower": 98.0,  # BB outside Keltner → breakout up
        "adx_14": 25.0,  # active
        "volume": 1500, "volume_sma_20": 1000,  # active
        "sil_composite_score": 0.0,
    })
    recent = pl.DataFrame({"close": [99.0, 100.0]})

    signal = strategy.generate_signal("TEST", bar, recent, _make_config())
    assert signal.direction.value == "HOLD", (
        f"Expected HOLD with only 2 directional BUY votes, got {signal.direction.value}"
    )


def test_strong_directional_still_gets_confirmations():
    """3/5 directional BUY should still get VOL+ADX boost."""
    strategy = ScalpScoreStrategy()
    # 3 directional BUY: EMA=+1, MACD=+1, BB=+1 (squeeze, price > bb_mid)
    # 1 directional SELL: RSI=-1 (overbought)
    # 1 neutral: SENT=0
    # Confirmations: VOL=+1, ADX=+1
    # buy_dir=3 >= 3 → confirmations added → buy_count = 3+1+1 = 5
    bar = _make_bar({
        "close": 100.5,  # above bb_middle → BB bullish in squeeze
        "ema_9": 100.5, "ema_21": 99.5,  # EMA bullish
        "rsi_14": 72.0,  # RSI overbought → SELL vote
        "macd_histogram": 0.5,  # BUY
        "bb_upper": 101.0, "bb_lower": 99.0, "bb_middle": 100.0,
        "keltner_upper": 102.0, "keltner_lower": 98.0,  # BB inside KC → squeeze
        "adx_14": 25.0,
        "volume": 1500, "volume_sma_20": 1000,
        "sil_composite_score": 0.0,
    })
    recent = pl.DataFrame({"close": [99.0, 100.0]})

    signal = strategy.generate_signal("TEST", bar, recent, _make_config())
    # With 3 directional + 2 confirmations = 5/7, should be BUY
    assert signal.direction.value == "BUY", (
        f"Expected BUY with 3+ directional votes, got {signal.direction.value}"
    )
    assert signal.confidence == pytest.approx(5 / 7, abs=0.01)
