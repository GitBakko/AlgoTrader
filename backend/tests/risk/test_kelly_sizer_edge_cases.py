"""
Unit tests for KellySizer edge cases and critical bug fixes.

Tests:
- CRIT-1: Division by zero when payoff_ratio = 0
- Edge case: All winning trades (win_rate = 100%)
- Edge case: Very small payoff ratios
- Edge case: Insufficient trade history
"""

import pytest

from src.risk.kelly_sizer import AdaptiveKellySizer


class TestKellySizerDivisionByZero:
    """Test CRIT-1: Division by zero protection."""

    def test_zero_payoff_ratio_returns_none(self):
        """
        Test that zero payoff ratio is handled gracefully.

        Scenario: avg_win = 0 (should be impossible but test defensively)
        """
        sizer = AdaptiveKellySizer(min_trades=5)

        # Create trade history with zero wins (edge case)
        # In practice, this should never happen since wins are filtered as p > 0
        # But we test the defensive check
        trade_history = [
            {"pnl": -10.0},
            {"pnl": -5.0},
            {"pnl": -3.0},
            {"pnl": -8.0},
            {"pnl": -2.0},
        ]

        stats = sizer.compute_stats(trade_history)

        # Should return None since no wins
        assert stats is None

    def test_very_small_payoff_ratio(self):
        """
        Test that very small payoff ratios don't cause numerical issues.

        Scenario: avg_win = 0.01, avg_loss = 100 → payoff_ratio = 0.0001
        """
        sizer = AdaptiveKellySizer(min_trades=5)

        trade_history = [
            {"pnl": 0.01},  # Tiny win
            {"pnl": -100.0},  # Large loss
            {"pnl": -100.0},
            {"pnl": -100.0},
            {"pnl": -100.0},
        ]

        stats = sizer.compute_stats(trade_history)

        # Should compute stats successfully
        assert stats is not None
        assert stats.win_rate == 0.2  # 1 win, 4 losses
        assert stats.avg_win == 0.01
        assert stats.avg_loss == 100.0
        assert stats.kelly_fraction >= 0  # Should be capped at 0 (negative kelly)

    def test_all_winning_trades(self):
        """
        Test that 100% win rate is handled correctly.

        Scenario: win_rate = 1.0 → (1 - win_rate) = 0 → no division by payoff_ratio
        """
        sizer = AdaptiveKellySizer(min_trades=5)

        trade_history = [
            {"pnl": 10.0},
            {"pnl": 15.0},
            {"pnl": 20.0},
            {"pnl": 12.0},
            {"pnl": 8.0},
        ]

        stats = sizer.compute_stats(trade_history)

        # Should return None since no losses (can't compute payoff ratio)
        assert stats is None

    def test_negative_avg_win_impossible(self):
        """
        Test that negative avg_win can't occur (wins are filtered as p > 0).

        This is a sanity check - the filter on line 71 ensures wins are positive.
        """
        sizer = AdaptiveKellySizer(min_trades=5)

        trade_history = [
            {"pnl": 10.0},   # Positive
            {"pnl": -5.0},   # Negative
            {"pnl": 15.0},   # Positive
            {"pnl": -3.0},   # Negative
            {"pnl": 8.0},    # Positive
        ]

        stats = sizer.compute_stats(trade_history)

        assert stats is not None
        assert stats.avg_win > 0  # All wins are positive by definition
        assert stats.avg_loss > 0  # All losses are positive (absolute value)


class TestKellySizerEdgeCases:
    """Test other edge cases in Kelly sizing."""

    def test_insufficient_trade_history(self):
        """Test that insufficient trades return None."""
        sizer = AdaptiveKellySizer(min_trades=30)

        trade_history = [
            {"pnl": 10.0},
            {"pnl": -5.0},
            {"pnl": 8.0},
        ]

        stats = sizer.compute_stats(trade_history)
        assert stats is None

    def test_kelly_capped_at_max(self):
        """Test that Kelly fraction is capped at max_kelly."""
        sizer = AdaptiveKellySizer(min_trades=5, max_kelly=0.25)

        # Create highly profitable trade history → high Kelly
        trade_history = [
            {"pnl": 100.0},  # Large wins
            {"pnl": 100.0},
            {"pnl": 100.0},
            {"pnl": 100.0},
            {"pnl": -1.0},   # Tiny loss
        ]

        stats = sizer.compute_stats(trade_history)

        assert stats is not None
        # Kelly should be capped at max_kelly
        assert stats.kelly_fraction <= 0.25

    def test_half_kelly_reduces_variance(self):
        """Test that half-Kelly is exactly half of full Kelly."""
        sizer = AdaptiveKellySizer(min_trades=5, use_half_kelly=True)

        trade_history = [
            {"pnl": 10.0},
            {"pnl": -5.0},
            {"pnl": 12.0},
            {"pnl": -6.0},
            {"pnl": 8.0},
        ]

        stats = sizer.compute_stats(trade_history)

        assert stats is not None
        assert abs(stats.half_kelly - stats.kelly_fraction / 2) < 1e-10

    def test_calculate_size_with_zero_equity(self):
        """Test that zero equity returns 0 size."""
        sizer = AdaptiveKellySizer()

        size, method = sizer.calculate_size(
            equity=0.0,
            entry_price=100.0,
            stop_loss=95.0,
            confidence=0.65,
            trade_history=[],
        )

        assert size == 0.0
        assert method == "invalid"

    def test_calculate_size_with_zero_stop_distance(self):
        """Test that entry_price == stop_loss returns 0 size."""
        sizer = AdaptiveKellySizer()

        size, method = sizer.calculate_size(
            equity=10000.0,
            entry_price=100.0,
            stop_loss=100.0,  # Same as entry
            confidence=0.65,
            trade_history=[],
        )

        assert size == 0.0
        assert method == "invalid"

    def test_fallback_to_fixed_fractional(self):
        """Test that insufficient history triggers fixed-fractional fallback."""
        sizer = AdaptiveKellySizer(min_trades=30)

        # Only 5 trades (< min_trades)
        trade_history = [
            {"pnl": 10.0},
            {"pnl": -5.0},
            {"pnl": 8.0},
            {"pnl": -3.0},
            {"pnl": 12.0},
        ]

        size, method = sizer.calculate_size(
            equity=10000.0,
            entry_price=100.0,
            stop_loss=95.0,
            confidence=0.65,
            trade_history=trade_history,
        )

        assert size > 0
        assert method == "fixed_fractional"
