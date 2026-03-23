# MANTIS-EVOLUTION: DRL Performance Analyzer Tests
"""Tests for MantisPerformanceAnalyzer — pure numpy performance metrics."""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.drl.performance_analyzer import MantisPerformanceAnalyzer
from src.drl.schemas import PerformanceMetrics


@pytest.fixture
def analyzer() -> MantisPerformanceAnalyzer:
    return MantisPerformanceAnalyzer()


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------

class TestSharpeRatio:
    def test_sharpe_ratio_positive(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Known positive daily returns should yield a positive annualised Sharpe."""
        returns = np.array([0.01, 0.02, 0.015, 0.005, 0.012])
        result = analyzer.sharpe_ratio(returns)
        assert result > 0.0

    def test_sharpe_ratio_zero_std(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Constant returns (zero standard deviation) should return 0.0."""
        returns = np.full(10, 0.01)
        result = analyzer.sharpe_ratio(returns)
        assert result == 0.0

    def test_sharpe_ratio_empty(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Empty array should return 0.0."""
        result = analyzer.sharpe_ratio(np.array([]))
        assert result == 0.0

    def test_sharpe_ratio_single_element(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Single element (< 2) should return 0.0."""
        result = analyzer.sharpe_ratio(np.array([0.05]))
        assert result == 0.0


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------

class TestSortinoRatio:
    def test_sortino_ratio_no_downside(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """All positive returns — no downside — should return inf."""
        returns = np.array([0.01, 0.02, 0.03, 0.015])
        result = analyzer.sortino_ratio(returns)
        assert math.isinf(result)

    def test_sortino_ratio_with_losses(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Mixed returns: Sortino should be positive and > Sharpe (downside only)."""
        # Skewed returns: many small gains, rare large losses
        rng = np.random.default_rng(42)
        returns = np.concatenate([
            rng.normal(0.01, 0.005, 80),   # mostly positive
            rng.normal(-0.02, 0.005, 20),   # occasional losses
        ])
        sharpe = analyzer.sharpe_ratio(returns)
        sortino = analyzer.sortino_ratio(returns)
        assert sortino > 0.0
        assert sortino > sharpe

    def test_sortino_ratio_empty(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Empty array should return 0.0."""
        result = analyzer.sortino_ratio(np.array([]))
        assert result == 0.0


# ---------------------------------------------------------------------------
# calmar_ratio
# ---------------------------------------------------------------------------

class TestCalmarRatio:
    def test_calmar_ratio_basic(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Known returns and a clear drawdown → calmar should be positive."""
        # +10% total over 1 year, equity goes peak→trough by ~9%
        returns = np.array([0.02, 0.03, -0.05, 0.04, 0.03, 0.02, 0.01])
        result = analyzer.calmar_ratio(returns, period_years=1.0)
        assert result > 0.0

    def test_calmar_ratio_zero_drawdown(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Monotonically increasing equity → max drawdown = 0 → inf."""
        returns = np.array([0.01, 0.02, 0.01, 0.015])
        result = analyzer.calmar_ratio(returns)
        assert math.isinf(result)

    def test_calmar_ratio_empty(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Less than 2 returns should give 0.0."""
        result = analyzer.calmar_ratio(np.array([0.05]))
        assert result == 0.0


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_max_drawdown_known(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Equity [100, 110, 90, 95] → max dd from 110 to 90 = 20/110 ≈ 0.1818."""
        equity = np.array([100.0, 110.0, 90.0, 95.0])
        result = analyzer.max_drawdown(equity)
        expected = (110.0 - 90.0) / 110.0
        assert abs(result - expected) < 1e-6

    def test_max_drawdown_no_drawdown(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Monotonically increasing equity → drawdown = 0.0."""
        equity = np.array([100.0, 105.0, 110.0, 120.0])
        result = analyzer.max_drawdown(equity)
        assert result == 0.0

    def test_max_drawdown_empty(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Less than 2 points should return 0.0."""
        assert analyzer.max_drawdown(np.array([])) == 0.0
        assert analyzer.max_drawdown(np.array([100.0])) == 0.0

    def test_max_drawdown_full_loss(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Equity dropping to zero → drawdown = 1.0 (100%)."""
        equity = np.array([100.0, 50.0, 0.0])
        result = analyzer.max_drawdown(equity)
        assert result == 1.0


# ---------------------------------------------------------------------------
# profit_factor
# ---------------------------------------------------------------------------

class TestProfitFactor:
    def test_profit_factor_basic(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """[10, 20, -5, -10] → gross profit 30, gross loss 15 → pf = 2.0."""
        pnl = np.array([10.0, 20.0, -5.0, -10.0])
        result = analyzer.profit_factor(pnl)
        assert abs(result - 2.0) < 1e-9

    def test_profit_factor_no_losses(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """All positive trades → profit factor = inf."""
        pnl = np.array([10.0, 5.0, 20.0])
        result = analyzer.profit_factor(pnl)
        assert math.isinf(result)

    def test_profit_factor_no_gains(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """All losing trades → profit factor = 0.0."""
        pnl = np.array([-10.0, -5.0, -20.0])
        result = analyzer.profit_factor(pnl)
        assert result == 0.0

    def test_profit_factor_empty(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Empty PnL array → 0.0."""
        result = analyzer.profit_factor(np.array([]))
        assert result == 0.0


# ---------------------------------------------------------------------------
# win_rate
# ---------------------------------------------------------------------------

class TestWinRate:
    def test_win_rate_basic(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """[10, -5, 20, -3] → 2 wins out of 4 = 0.5."""
        pnl = np.array([10.0, -5.0, 20.0, -3.0])
        result = analyzer.win_rate(pnl)
        assert abs(result - 0.5) < 1e-9

    def test_win_rate_empty(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Empty array → 0.0."""
        result = analyzer.win_rate(np.array([]))
        assert result == 0.0

    def test_win_rate_all_wins(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """All positive → 1.0."""
        pnl = np.array([1.0, 2.0, 3.0])
        result = analyzer.win_rate(pnl)
        assert result == 1.0

    def test_win_rate_all_losses(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """All negative → 0.0."""
        pnl = np.array([-1.0, -2.0])
        result = analyzer.win_rate(pnl)
        assert result == 0.0


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_generate_report_complete(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Returns + pnl_values → PerformanceMetrics with all fields populated."""
        rng = np.random.default_rng(0)
        returns = rng.normal(0.001, 0.01, 100)
        equity = np.cumprod(1 + returns) * 10000
        pnl = rng.normal(50, 200, 30)

        report = analyzer.generate_report(returns, equity_curve=equity, pnl_values=pnl)

        assert isinstance(report, PerformanceMetrics)
        assert report.num_trades == 30
        assert 0.0 <= report.win_rate <= 1.0
        assert report.profit_factor >= 0.0
        assert report.max_drawdown >= 0.0

    def test_generate_report_returns_only(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """Just returns (no equity_curve, no pnl) → core metrics populated, trades = 0."""
        returns = np.array([0.01, -0.005, 0.02, 0.008, -0.003])
        report = analyzer.generate_report(returns)

        assert isinstance(report, PerformanceMetrics)
        # Sharpe / Sortino / Calmar are real numbers
        assert isinstance(report.sharpe_ratio, float)
        assert isinstance(report.sortino_ratio, float)
        assert isinstance(report.calmar_ratio, float)
        assert report.max_drawdown >= 0.0
        assert report.num_trades == 0

    def test_generate_report_equity_auto_computed(self, analyzer: MantisPerformanceAnalyzer) -> None:
        """When equity_curve is None it is auto-computed from returns; max_dd must be >= 0."""
        returns = np.array([0.05, -0.10, 0.03])
        report = analyzer.generate_report(returns)
        assert report.max_drawdown >= 0.0
        # total_return should match compound product
        expected_total = float(np.prod(1 + returns) - 1)
        assert abs(report.total_return - expected_total) < 1e-9
