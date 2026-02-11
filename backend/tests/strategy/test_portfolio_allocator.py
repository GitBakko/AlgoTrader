"""Tests for portfolio allocator module."""

import pytest

from src.strategy.portfolio_allocator import PortfolioAllocator
from src.strategy.schemas import AllocationConfig


class TestPortfolioAllocator:
    def test_base_allocation(self):
        alloc = PortfolioAllocator.get_allocation()
        assert alloc["XAUUSD"] == pytest.approx(0.35)
        assert alloc["BTCUSD"] == pytest.approx(0.30)
        assert alloc["US500"] == pytest.approx(0.35)
        assert sum(alloc.values()) == pytest.approx(1.0)

    def test_bull_regime(self):
        alloc = PortfolioAllocator.get_allocation("bull")
        assert alloc["XAUUSD"] == pytest.approx(0.25)
        assert alloc["BTCUSD"] == pytest.approx(0.35)
        assert alloc["US500"] == pytest.approx(0.40)

    def test_bear_regime(self):
        alloc = PortfolioAllocator.get_allocation("bear")
        assert alloc["XAUUSD"] == pytest.approx(0.45)
        assert alloc["BTCUSD"] == pytest.approx(0.20)

    def test_high_vol_regime(self):
        alloc = PortfolioAllocator.get_allocation("high_vol")
        assert alloc["XAUUSD"] == pytest.approx(0.50)
        assert alloc["BTCUSD"] == pytest.approx(0.15)

    def test_unknown_regime_uses_base(self):
        alloc = PortfolioAllocator.get_allocation("alien_invasion")
        assert alloc == PortfolioAllocator.get_allocation(None)

    def test_max_capital_for_asset(self):
        cap = PortfolioAllocator.get_max_capital_for_asset("XAUUSD", 100000.0)
        assert cap == pytest.approx(35000.0)

    def test_max_capital_for_asset_bear(self):
        cap = PortfolioAllocator.get_max_capital_for_asset("XAUUSD", 100000.0, "bear")
        assert cap == pytest.approx(45000.0)

    def test_max_capital_unknown_asset(self):
        cap = PortfolioAllocator.get_max_capital_for_asset("EURUSD", 100000.0)
        assert cap == 0.0
