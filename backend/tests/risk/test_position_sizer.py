"""Tests for position sizer module."""

import pytest

from src.risk.position_sizer import PositionSizer


class TestPositionSizer:
    def test_basic_sizing(self):
        """Basic position size calculation."""
        size = PositionSizer.calculate_size(
            equity=100000,
            risk_per_trade=0.02,
            entry_price=100,
            stop_loss=98,
            confidence=0.80,
            max_position_pct=0.50,
        )
        # risk_amount = 2000, stop_distance = 2, base_size = 1000
        # max_size = 100000 * 0.50 / 100 = 500 -> capped
        # Note: confidence scaling is now handled by RiskManager, not PositionSizer
        assert size > 0
        assert size == pytest.approx(500.0, rel=0.01)

    def test_confidence_no_longer_affects_size(self):
        """Confidence is now ignored by PositionSizer (handled by RiskManager)."""
        low = PositionSizer.calculate_size(
            equity=100000, risk_per_trade=0.001,
            entry_price=100, stop_loss=95, confidence=0.55,
        )
        high = PositionSizer.calculate_size(
            equity=100000, risk_per_trade=0.001,
            entry_price=100, stop_loss=95, confidence=0.95,
        )
        # Confidence no longer affects PositionSizer output
        assert low == pytest.approx(high, rel=1e-9)

    def test_max_position_cap(self):
        """Position should be capped at max_position_pct of equity."""
        # Very large base size that would exceed cap
        size = PositionSizer.calculate_size(
            equity=10000, risk_per_trade=0.10,
            entry_price=100, stop_loss=99, confidence=0.95,
            max_position_pct=0.05,
        )
        max_size = (10000 * 0.05) / 100  # = 5.0
        assert size <= max_size + 1e-6

    def test_zero_equity_returns_zero(self):
        size = PositionSizer.calculate_size(
            equity=0, risk_per_trade=0.02,
            entry_price=100, stop_loss=95, confidence=0.80,
        )
        assert size == 0.0

    def test_zero_stop_distance_returns_zero(self):
        size = PositionSizer.calculate_size(
            equity=10000, risk_per_trade=0.02,
            entry_price=100, stop_loss=100, confidence=0.80,
        )
        assert size == 0.0

    def test_negative_equity_returns_zero(self):
        size = PositionSizer.calculate_size(
            equity=-5000, risk_per_trade=0.02,
            entry_price=100, stop_loss=95, confidence=0.80,
        )
        assert size == 0.0

    def test_result_is_always_non_negative(self):
        size = PositionSizer.calculate_size(
            equity=10000, risk_per_trade=0.02,
            entry_price=100, stop_loss=95, confidence=0.50,
        )
        assert size >= 0.0
