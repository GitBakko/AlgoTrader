"""Tests for backtest cost simulator."""

from datetime import datetime

import pytest

from src.backtest.costs import (
    ASSET_SPREADS,
    SPREAD_FALLBACK_PCT,
    CostSimulator,
    resolve_spread,
)


class TestCostSimulator:
    def test_spread_cost_known_asset(self):
        sim = CostSimulator()
        cost = sim.calculate_spread_cost("XAUUSD", 1.0)
        # Full spread × size (no ×2, spread is already full bid-ask)
        assert cost == ASSET_SPREADS["XAUUSD"] * 1.0

    def test_spread_cost_scales_with_size(self):
        sim = CostSimulator()
        cost_1 = sim.calculate_spread_cost("XAUUSD", 1.0)
        cost_2 = sim.calculate_spread_cost("XAUUSD", 2.0)
        assert cost_2 == cost_1 * 2

    def test_slippage_positive(self):
        sim = CostSimulator(slippage_factor=0.1)
        slippage = sim.calculate_slippage("BTCUSD", 1.0)
        assert slippage > 0

    def test_sl_slippage_higher_than_normal(self):
        """SL fills should have higher slippage than normal exits."""
        sim = CostSimulator(slippage_factor=0.1)
        normal = sim.calculate_slippage("XAUUSD", 10.0)
        sl_extra = sim.calculate_sl_slippage("XAUUSD", 10.0)
        assert sl_extra > normal  # SL_SLIPPAGE_FACTOR=0.5 > slippage_factor=0.1

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
            epic="XAUUSD",
            size=1.0,
            entry_price=2000.0,
            direction="LONG",
            bars_held=1,
            timeframe_minutes=60,
        )
        assert cost > 0  # Should have spread + slippage
        # No overnight since 1h < 24h
        spread_slip = sim.calculate_spread_cost("XAUUSD", 1.0) + sim.calculate_slippage(
            "XAUUSD", 1.0
        )
        assert cost == pytest.approx(spread_slip)

    def test_total_cost_with_overnight(self):
        sim = CostSimulator()
        # 48 bars of 1h = 48h = 2 nights
        cost = sim.calculate_total_cost(
            epic="XAUUSD",
            size=1.0,
            entry_price=2000.0,
            direction="LONG",
            bars_held=48,
            timeframe_minutes=60,
        )
        spread_slip = sim.calculate_spread_cost("XAUUSD", 1.0) + sim.calculate_slippage(
            "XAUUSD", 1.0
        )
        assert cost > spread_slip  # Should include overnight fees

    def test_sl_exit_costs_more(self):
        """SL exit should cost more than normal exit."""
        sim = CostSimulator()
        normal_cost = sim.calculate_total_cost(
            epic="XAUUSD",
            size=10.0,
            entry_price=2000.0,
            direction="LONG",
            bars_held=5,
            timeframe_minutes=60,
            is_sl_exit=False,
        )
        sl_cost = sim.calculate_total_cost(
            epic="XAUUSD",
            size=10.0,
            entry_price=2000.0,
            direction="LONG",
            bars_held=5,
            timeframe_minutes=60,
            is_sl_exit=True,
        )
        assert sl_cost > normal_cost

    def test_weekend_nights_counted(self):
        """Weekend nights should be identified correctly."""
        sim = CostSimulator()
        # Friday 2025-01-10 (weekday=4)
        friday = datetime(2025, 1, 10, 18, 0, 0)
        weekday, weekend = sim._count_weekend_nights(friday, 3)
        # Fri night (4) → weekend, Sat night (5) → weekend, Sun night (6) → weekday
        assert weekend == 2
        assert weekday == 1

    def test_listed_epic_ignores_price_fallback(self):
        """Listed epics use the measured spread regardless of price arg."""
        sim = CostSimulator()
        assert sim.calculate_spread_cost("XAUUSD", 1.0, price=2000.0) == ASSET_SPREADS["XAUUSD"]
        # resolve_spread returns the measured value, not a proportional one
        assert resolve_spread("XAUUSD", price=2000.0) == ASSET_SPREADS["XAUUSD"]

    def test_unlisted_epic_uses_proportional_fallback(self):
        """Unlisted epics fall back to a fraction of price, not the flat 0.5."""
        assert "DOGUSD" not in ASSET_SPREADS  # guards the premise of this test
        spread = resolve_spread("DOGUSD", price=0.10)
        assert spread == pytest.approx(0.10 * SPREAD_FALLBACK_PCT)

    def test_unlisted_epic_not_catastrophic(self):
        """The legacy flat-0.5 default produced a 500% spread on $0.10 DOGUSD.

        Regression guard: spread cost must be a tiny fraction of notional, not
        dominate it.
        """
        sim = CostSimulator()
        size, price = 1000.0, 0.10
        notional = size * price  # $100
        cost = sim.calculate_spread_cost("DOGUSD", size, price=price)
        assert cost < notional * 0.05  # << old 0.5*1000 = $500 (5x notional)

    def test_unlisted_epic_no_price_uses_flat_fallback(self):
        """Without a reference price we cannot go proportional — flat fallback."""
        # premise: epic not listed
        assert "ZZZUSD" not in ASSET_SPREADS
        assert resolve_spread("ZZZUSD", price=None) == 0.5

    def test_weekend_multiplier_increases_overnight(self):
        """Trades spanning weekends should have higher overnight fees."""
        sim = CostSimulator()
        # Monday entry, 2 nights (Mon-Tue, Tue-Wed) = 2 weekday nights
        monday = datetime(2025, 1, 6, 10, 0, 0)  # Monday
        cost_weekday = sim.calculate_total_cost(
            epic="XAUUSD",
            size=1.0,
            entry_price=2000.0,
            direction="LONG",
            bars_held=48,
            timeframe_minutes=60,
            entry_time=monday,
        )
        # Friday entry, 2 nights (Fri-Sat, Sat-Sun) = 2 weekend nights (3x each)
        friday = datetime(2025, 1, 10, 10, 0, 0)  # Friday
        cost_weekend = sim.calculate_total_cost(
            epic="XAUUSD",
            size=1.0,
            entry_price=2000.0,
            direction="LONG",
            bars_held=48,
            timeframe_minutes=60,
            entry_time=friday,
        )
        assert cost_weekend > cost_weekday
