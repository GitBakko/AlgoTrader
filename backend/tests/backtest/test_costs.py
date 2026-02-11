"""Tests for backtest cost simulator."""

import pytest

from src.backtest.costs import CostSimulator, ASSET_SPREADS


class TestCostSimulator:
    def test_spread_cost_known_asset(self):
        sim = CostSimulator()
        cost = sim.calculate_spread_cost("XAUUSD", 1.0)
        # Round-trip: spread * size * 2
        assert cost == ASSET_SPREADS["XAUUSD"] * 1.0 * 2

    def test_spread_cost_scales_with_size(self):
        sim = CostSimulator()
        cost_1 = sim.calculate_spread_cost("XAUUSD", 1.0)
        cost_2 = sim.calculate_spread_cost("XAUUSD", 2.0)
        assert cost_2 == cost_1 * 2

    def test_slippage_positive(self):
        sim = CostSimulator(slippage_factor=0.1)
        slippage = sim.calculate_slippage("BTCUSD", 1.0)
        assert slippage > 0

    def test_overnight_fee(self):
        sim = CostSimulator()
        fee = sim.calculate_overnight_fee("XAUUSD", 10000.0, "LONG", 5)
        assert fee > 0

    def test_overnight_fee_zero_nights(self):
        sim = CostSimulator()
        fee = sim.calculate_overnight_fee("XAUUSD", 10000.0, "LONG", 0)
        assert fee == 0.0

    def test_total_cost_no_overnight(self):
        sim = CostSimulator()
        # 1 bar of 1h = 60 min, < 1 day => no overnight
        cost = sim.calculate_total_cost(
            epic="XAUUSD", size=1.0, entry_price=2000.0,
            direction="LONG", bars_held=1, timeframe_minutes=60,
        )
        assert cost > 0  # Should have spread + slippage
        # But no overnight since 1 bar of 60 min < 24h
        spread_slip = sim.calculate_spread_cost("XAUUSD", 1.0) + sim.calculate_slippage("XAUUSD", 1.0)
        assert cost == pytest.approx(spread_slip)

    def test_total_cost_with_overnight(self):
        sim = CostSimulator()
        # 48 bars of 1h = 48h = 2 nights
        cost = sim.calculate_total_cost(
            epic="XAUUSD", size=1.0, entry_price=2000.0,
            direction="LONG", bars_held=48, timeframe_minutes=60,
        )
        spread_slip = sim.calculate_spread_cost("XAUUSD", 1.0) + sim.calculate_slippage("XAUUSD", 1.0)
        assert cost > spread_slip  # Should include overnight fees
