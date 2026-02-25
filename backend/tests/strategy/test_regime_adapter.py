"""Tests for regime adapter module."""

import pytest

from src.strategy.regime_adapter import RegimeAdapter
from src.strategy.schemas import StrategyConfig


class TestRegimeAdapter:
    def test_trending_up_lowers_confidence(self):
        base = StrategyConfig(min_confidence=0.55)
        adapted = RegimeAdapter.adapt_params("trending_up", base)
        assert adapted.min_confidence == 0.50

    def test_trending_down_adjusts_confidence(self):
        base = StrategyConfig(min_confidence=0.55)
        adapted = RegimeAdapter.adapt_params("trending_down", base)
        assert adapted.min_confidence == 0.50

    def test_ranging_adjusts_confidence(self):
        base = StrategyConfig(min_confidence=0.55)
        adapted = RegimeAdapter.adapt_params("ranging", base)
        assert adapted.min_confidence == 0.52

    def test_none_regime_no_change(self):
        base = StrategyConfig(min_confidence=0.50, stop_multiplier=2.0)
        adapted = RegimeAdapter.adapt_params(None, base)
        assert adapted.min_confidence == 0.50
        assert adapted.stop_multiplier == 2.0

    def test_unknown_regime_no_change(self):
        base = StrategyConfig(min_confidence=0.50)
        adapted = RegimeAdapter.adapt_params("unknown_regime", base)
        assert adapted.min_confidence == 0.50

    def test_stop_multiplier_trending_up(self):
        assert RegimeAdapter.get_stop_multiplier("trending_up") == 2.5

    def test_stop_multiplier_trending_down(self):
        assert RegimeAdapter.get_stop_multiplier("trending_down") == 2.0

    def test_stop_multiplier_default(self):
        assert RegimeAdapter.get_stop_multiplier(None) == 2.0

    def test_is_counter_trend_sell_in_uptrend(self):
        assert RegimeAdapter.is_counter_trend("SELL", "trending_up") is True

    def test_is_counter_trend_buy_in_downtrend(self):
        assert RegimeAdapter.is_counter_trend("BUY", "trending_down") is True

    def test_not_counter_trend_buy_in_uptrend(self):
        assert RegimeAdapter.is_counter_trend("BUY", "trending_up") is False

    def test_not_counter_trend_none_regime(self):
        assert RegimeAdapter.is_counter_trend("BUY", None) is False
