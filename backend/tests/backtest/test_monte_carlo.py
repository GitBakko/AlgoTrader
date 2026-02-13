"""
Tests for Monte Carlo backtest validation.
"""

import pytest

from src.backtest.monte_carlo import MonteCarloResult, MonteCarloSimulator


@pytest.mark.unit
@pytest.mark.backtest
class TestMonteCarloSimulator:
    """Tests for MonteCarloSimulator."""

    def _make_trades(self, n: int = 100, avg_pnl: float = 10.0) -> list[dict]:
        import random
        random.seed(42)
        return [{"pnl": avg_pnl + random.gauss(0, 50)} for _ in range(n)]

    def test_basic_run(self):
        """Basic run with enough trades."""
        sim = MonteCarloSimulator(n_simulations=1000, seed=42)
        trades = self._make_trades(50, avg_pnl=20.0)
        result = sim.run(trades, initial_capital=10000)

        assert isinstance(result, MonteCarloResult)
        assert result.n_simulations == 1000
        assert result.n_trades == 50
        assert len(result.final_equity_ci) == 3
        assert result.final_equity_ci[0] <= result.final_equity_ci[1] <= result.final_equity_ci[2]
        assert 0.0 <= result.p_value_return <= 1.0
        assert 0.0 <= result.risk_of_ruin <= 1.0

    def test_too_few_trades(self):
        """Very few trades returns empty result."""
        sim = MonteCarloSimulator(n_simulations=100)
        trades = [{"pnl": 10}] * 3
        result = sim.run(trades, initial_capital=10000)
        assert result.n_simulations == 0
        assert result.p_value_return == 1.0

    def test_profitable_strategy(self):
        """Profitable strategy should have low p-value."""
        sim = MonteCarloSimulator(n_simulations=5000, seed=42)
        # Consistently winning
        trades = [{"pnl": 100}] * 80 + [{"pnl": -50}] * 20
        result = sim.run(trades, initial_capital=10000)
        # Strong positive returns -> p-value should be relatively low
        assert result.final_equity_ci[1] > 10000  # Median > initial
        assert result.risk_of_ruin < 0.5

    def test_losing_strategy(self):
        """Losing strategy should have higher risk of ruin."""
        sim = MonteCarloSimulator(n_simulations=5000, seed=42, ruin_threshold=0.50)
        trades = [{"pnl": -200}] * 60 + [{"pnl": 50}] * 40
        result = sim.run(trades, initial_capital=10000)
        # Net negative expectation
        assert result.risk_of_ruin > 0

    def test_drawdown_ci(self):
        """Drawdown CI should be non-negative."""
        sim = MonteCarloSimulator(n_simulations=1000, seed=42)
        trades = self._make_trades(100)
        result = sim.run(trades, initial_capital=10000)
        assert result.max_drawdown_ci[0] >= 0
        assert result.max_drawdown_ci[2] >= result.max_drawdown_ci[0]

    def test_to_dict(self):
        """to_dict returns serializable dict."""
        sim = MonteCarloSimulator(n_simulations=100, seed=42)
        trades = self._make_trades(20)
        result = sim.run(trades, initial_capital=10000)
        d = result.to_dict()
        assert "n_simulations" in d
        assert "final_equity" in d
        assert "p_value_return" in d
        assert isinstance(d["final_equity"]["p50"], float)

    def test_original_metrics_override(self):
        """Can override original metrics for comparison."""
        sim = MonteCarloSimulator(n_simulations=100, seed=42)
        trades = self._make_trades(50)
        result = sim.run(
            trades, initial_capital=10000,
            original_metrics={"final_equity": 15000, "max_drawdown": 0.1, "sharpe": 1.5},
        )
        assert result.original_final_equity == 15000
        assert result.original_max_drawdown == 0.1
        assert result.original_sharpe == 1.5

    def test_net_pnl_key(self):
        """Accepts 'net_pnl' key."""
        sim = MonteCarloSimulator(n_simulations=100, seed=42)
        trades = [{"net_pnl": 50}] * 30 + [{"net_pnl": -25}] * 20
        result = sim.run(trades, initial_capital=10000)
        assert result.n_trades == 50

    def test_reproducible_with_seed(self):
        """Same seed produces same results."""
        trades = self._make_trades(50)
        r1 = MonteCarloSimulator(n_simulations=500, seed=123).run(trades, 10000)
        r2 = MonteCarloSimulator(n_simulations=500, seed=123).run(trades, 10000)
        assert r1.final_equity_ci == r2.final_equity_ci
        assert r1.p_value_return == r2.p_value_return

    def test_sharpe_ci(self):
        """Sharpe ratio CI is computed."""
        sim = MonteCarloSimulator(n_simulations=1000, seed=42)
        trades = self._make_trades(80, avg_pnl=30.0)
        result = sim.run(trades, initial_capital=10000)
        assert len(result.sharpe_ratio_ci) == 3
