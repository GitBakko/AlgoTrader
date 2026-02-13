"""
Tests for adaptive Kelly criterion position sizing.
"""

import pytest

from src.risk.kelly_sizer import AdaptiveKellySizer, KellyStats


@pytest.mark.unit
@pytest.mark.risk
class TestAdaptiveKellySizer:
    """Tests for AdaptiveKellySizer."""

    def _make_trades(self, wins: int, losses: int, avg_win: float = 100, avg_loss: float = 50) -> list[dict]:
        trades = []
        for _ in range(wins):
            trades.append({"pnl": avg_win})
        for _ in range(losses):
            trades.append({"pnl": -avg_loss})
        return trades

    def test_insufficient_history_fallback(self):
        """Falls back to fixed-fractional with < min_trades."""
        sizer = AdaptiveKellySizer(min_trades=30)
        trades = self._make_trades(10, 5)
        size, method = sizer.calculate_size(
            equity=10000, entry_price=100, stop_loss=95,
            confidence=0.7, trade_history=trades,
        )
        assert method == "fixed_fractional"
        assert size > 0

    def test_kelly_with_enough_history(self):
        """Uses Kelly with sufficient trade history."""
        sizer = AdaptiveKellySizer(min_trades=10)
        trades = self._make_trades(25, 10, avg_win=200, avg_loss=100)
        size, method = sizer.calculate_size(
            equity=10000, entry_price=100, stop_loss=95,
            confidence=0.7, trade_history=trades,
        )
        assert method == "kelly"
        assert size > 0

    def test_compute_stats(self):
        """compute_stats returns correct Kelly statistics."""
        sizer = AdaptiveKellySizer(min_trades=5)
        # 60% win rate, 2:1 payoff
        trades = self._make_trades(30, 20, avg_win=200, avg_loss=100)
        stats = sizer.compute_stats(trades)
        assert stats is not None
        assert stats.win_rate == pytest.approx(0.6, abs=0.01)
        assert stats.avg_win == pytest.approx(200.0)
        assert stats.avg_loss == pytest.approx(100.0)
        # kelly = 0.6 - 0.4/2.0 = 0.6 - 0.2 = 0.4 -> capped at 0.25
        assert stats.kelly_fraction == pytest.approx(0.25)
        assert stats.half_kelly == pytest.approx(0.125)

    def test_compute_stats_none_insufficient(self):
        """compute_stats returns None with insufficient data."""
        sizer = AdaptiveKellySizer(min_trades=30)
        trades = self._make_trades(5, 5)
        assert sizer.compute_stats(trades) is None

    def test_compute_stats_no_losses(self):
        """compute_stats returns None if no losses."""
        sizer = AdaptiveKellySizer(min_trades=5)
        trades = [{"pnl": 100}] * 10
        assert sizer.compute_stats(trades) is None

    def test_compute_stats_no_wins(self):
        """compute_stats returns None if no wins."""
        sizer = AdaptiveKellySizer(min_trades=5)
        trades = [{"pnl": -50}] * 10
        assert sizer.compute_stats(trades) is None

    def test_kelly_zero_fraction(self):
        """Bad stats -> kelly_zero method."""
        sizer = AdaptiveKellySizer(min_trades=5)
        # 20% win rate, 1:1 payoff -> kelly = 0.2 - 0.8/1 = -0.6 -> 0
        trades = self._make_trades(2, 8, avg_win=100, avg_loss=100)
        size, method = sizer.calculate_size(
            equity=10000, entry_price=100, stop_loss=95,
            confidence=0.7, trade_history=trades,
        )
        assert method == "kelly_zero"
        assert size == 0.0

    def test_max_position_cap(self):
        """Position capped at max_position_pct."""
        sizer = AdaptiveKellySizer(min_trades=5)
        # Very profitable -> high Kelly fraction
        trades = self._make_trades(45, 5, avg_win=500, avg_loss=10)
        size, method = sizer.calculate_size(
            equity=10000, entry_price=100, stop_loss=99,
            confidence=0.95, trade_history=trades,
            max_position_pct=0.01,  # 1% cap
        )
        # Max size = (10000 * 0.01) / 100 = 1.0
        assert size <= 1.0 + 1e-6

    def test_invalid_inputs(self):
        """Zero/negative inputs return zero."""
        sizer = AdaptiveKellySizer()
        size, method = sizer.calculate_size(
            equity=0, entry_price=100, stop_loss=95,
            confidence=0.7, trade_history=[],
        )
        assert size == 0.0

    def test_half_kelly_flag(self):
        """Half-Kelly vs full Kelly."""
        trades = self._make_trades(25, 10, avg_win=200, avg_loss=100)
        half = AdaptiveKellySizer(min_trades=10, use_half_kelly=True)
        full = AdaptiveKellySizer(min_trades=10, use_half_kelly=False)
        stats_half = half.compute_stats(trades)
        stats_full = full.compute_stats(trades)
        assert stats_half.half_kelly < stats_full.kelly_fraction

    def test_net_pnl_key(self):
        """Accepts 'net_pnl' key as well as 'pnl'."""
        sizer = AdaptiveKellySizer(min_trades=5)
        trades = [{"net_pnl": 100}] * 7 + [{"net_pnl": -50}] * 3
        stats = sizer.compute_stats(trades)
        assert stats is not None
        assert stats.win_rate == pytest.approx(0.7, abs=0.01)
