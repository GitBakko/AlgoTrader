"""Tests for stop manager module."""

import pytest

from src.risk.stop_manager import StopManager


class TestStopManager:
    def test_stop_loss_buy(self):
        sl = StopManager.calculate_stop_loss("BUY", 2000.0, atr=20.0, multiplier=2.0)
        assert sl == pytest.approx(1960.0)

    def test_stop_loss_sell(self):
        sl = StopManager.calculate_stop_loss("SELL", 2000.0, atr=20.0, multiplier=2.0)
        assert sl == pytest.approx(2040.0)

    def test_take_profit_buy(self):
        tp = StopManager.calculate_take_profit(
            "BUY", 2000.0, atr=20.0, multiplier=2.0, risk_reward=2.0
        )
        # TP = 2000 + 20 * 2 * 2 = 2080
        assert tp == pytest.approx(2080.0)

    def test_take_profit_sell(self):
        tp = StopManager.calculate_take_profit(
            "SELL", 2000.0, atr=20.0, multiplier=2.0, risk_reward=2.0
        )
        # TP = 2000 - 20 * 2 * 2 = 1920
        assert tp == pytest.approx(1920.0)

    def test_trailing_stop_buy(self):
        ts = StopManager.calculate_trailing_stop("BUY", 2050.0, atr=20.0, multiplier=2.0)
        assert ts == pytest.approx(2010.0)

    def test_trailing_stop_sell(self):
        ts = StopManager.calculate_trailing_stop("SELL", 1950.0, atr=20.0, multiplier=2.0)
        assert ts == pytest.approx(1990.0)

    def test_different_multipliers(self):
        sl_tight = StopManager.calculate_stop_loss("BUY", 100.0, atr=5.0, multiplier=1.0)
        sl_wide = StopManager.calculate_stop_loss("BUY", 100.0, atr=5.0, multiplier=3.0)
        assert sl_tight > sl_wide  # Wider stop is further from entry

    def test_risk_reward_scaling(self):
        tp_low = StopManager.calculate_take_profit(
            "BUY", 100.0, atr=5.0, multiplier=2.0, risk_reward=1.0
        )
        tp_high = StopManager.calculate_take_profit(
            "BUY", 100.0, atr=5.0, multiplier=2.0, risk_reward=3.0
        )
        assert tp_high > tp_low
