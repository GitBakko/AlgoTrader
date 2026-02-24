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


class TestDynamicMultiplier:
    """Tests for volatility-scaled dynamic stop multiplier."""

    def test_normal_volatility_returns_base(self):
        """ratio=1.0 → multiplier unchanged."""
        result = StopManager.dynamic_multiplier(3.0, current_atr=10.0, baseline_atr=10.0)
        assert result == pytest.approx(3.0)

    def test_high_volatility_widens_stops(self):
        """ratio=2.0 → multiplier increases."""
        result = StopManager.dynamic_multiplier(3.0, current_atr=20.0, baseline_atr=10.0)
        # scaled = 3.0 * (0.5 + 0.5 * 2.0) = 3.0 * 1.5 = 4.5
        assert result == pytest.approx(4.5)

    def test_low_volatility_tightens_stops(self):
        """ratio=0.5 → multiplier decreases."""
        result = StopManager.dynamic_multiplier(3.0, current_atr=5.0, baseline_atr=10.0)
        # scaled = 3.0 * (0.5 + 0.5 * 0.5) = 3.0 * 0.75 = 2.25
        assert result == pytest.approx(2.25)

    def test_clamped_to_max(self):
        """Very high volatility clamped to max_multiplier."""
        result = StopManager.dynamic_multiplier(3.0, current_atr=100.0, baseline_atr=10.0)
        assert result == 5.0  # default max

    def test_clamped_to_min(self):
        """Very low volatility clamped to min_multiplier."""
        result = StopManager.dynamic_multiplier(3.0, current_atr=0.1, baseline_atr=10.0)
        assert result == 2.0  # default min

    def test_none_baseline_returns_base(self):
        """No baseline ATR → return base multiplier (no scaling)."""
        result = StopManager.dynamic_multiplier(3.0, current_atr=10.0, baseline_atr=None)
        assert result == 3.0

    def test_zero_baseline_returns_base(self):
        """Zero baseline ATR → return base multiplier (no scaling)."""
        result = StopManager.dynamic_multiplier(3.0, current_atr=10.0, baseline_atr=0.0)
        assert result == 3.0

    def test_custom_min_max(self):
        """Custom min/max boundaries respected."""
        result = StopManager.dynamic_multiplier(
            3.0, current_atr=100.0, baseline_atr=10.0,
            min_multiplier=1.0, max_multiplier=10.0,
        )
        # scaled = 3.0 * (0.5 + 0.5 * 10) = 3.0 * 5.5 = 16.5 → clamped to 10.0
        assert result == 10.0
