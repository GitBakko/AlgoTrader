"""
Monte Carlo simulation for backtest validation.
Shuffles trade P&L to generate confidence intervals for key metrics
and estimate the probability that results are due to skill vs luck.
"""

from dataclasses import dataclass

import numpy as np
from loguru import logger


@dataclass
class MonteCarloResult:
    """Results of Monte Carlo simulation."""

    n_simulations: int
    n_trades: int
    # Confidence intervals (5th, 50th, 95th percentile)
    final_equity_ci: tuple[float, float, float]
    max_drawdown_ci: tuple[float, float, float]
    sharpe_ratio_ci: tuple[float, float, float]
    # Statistical significance
    p_value_return: float
    risk_of_ruin: float
    # Original metrics for comparison
    original_final_equity: float
    original_max_drawdown: float
    original_sharpe: float

    def to_dict(self) -> dict:
        """Serialize for API response."""
        return {
            "n_simulations": self.n_simulations,
            "n_trades": self.n_trades,
            "final_equity": {
                "p5": self.final_equity_ci[0],
                "p50": self.final_equity_ci[1],
                "p95": self.final_equity_ci[2],
                "original": self.original_final_equity,
            },
            "max_drawdown": {
                "p5": self.max_drawdown_ci[0],
                "p50": self.max_drawdown_ci[1],
                "p95": self.max_drawdown_ci[2],
                "original": self.original_max_drawdown,
            },
            "sharpe_ratio": {
                "p5": self.sharpe_ratio_ci[0],
                "p50": self.sharpe_ratio_ci[1],
                "p95": self.sharpe_ratio_ci[2],
                "original": self.original_sharpe,
            },
            "p_value_return": self.p_value_return,
            "risk_of_ruin": self.risk_of_ruin,
        }


class MonteCarloSimulator:
    """
    Monte Carlo simulation for backtest validation.

    Shuffles trade P&L vectors N times and computes equity curves,
    drawdowns, and Sharpe ratios to generate confidence intervals.
    """

    def __init__(
        self,
        n_simulations: int = 10_000,
        ruin_threshold: float = 0.50,
        seed: int | None = 42,
    ):
        """
        Args:
            n_simulations: Number of random shuffles
            ruin_threshold: Equity drop fraction considered "ruin" (0.5 = 50% loss)
            seed: Random seed for reproducibility (None = random)
        """
        self.n_simulations = n_simulations
        self.ruin_threshold = ruin_threshold
        self.seed = seed

    def run(
        self,
        trades: list[dict],
        initial_capital: float,
        original_metrics: dict | None = None,
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation on trade results.

        Args:
            trades: List of trade dicts with 'pnl' or 'net_pnl' key
            initial_capital: Starting capital
            original_metrics: Dict with optional keys: 'final_equity', 'max_drawdown', 'sharpe'

        Returns:
            MonteCarloResult with confidence intervals and p-values
        """
        # Extract P&L array
        pnls = np.array([t.get("pnl", t.get("net_pnl", 0.0)) for t in trades], dtype=np.float64)

        n_trades = len(pnls)
        if n_trades < 5:
            logger.warning(f"Too few trades ({n_trades}) for Monte Carlo")
            return self._empty_result(initial_capital, n_trades)

        original_metrics = original_metrics or {}
        rng = np.random.default_rng(self.seed)

        # Compute original metrics if not provided
        orig_equity_curve = initial_capital + np.cumsum(pnls)
        orig_final = float(orig_equity_curve[-1])
        orig_dd = self._max_drawdown(orig_equity_curve, initial_capital)
        orig_sharpe = self._compute_sharpe(pnls)

        orig_final = original_metrics.get("final_equity", orig_final)
        orig_dd = original_metrics.get("max_drawdown", orig_dd)
        orig_sharpe = original_metrics.get("sharpe", orig_sharpe)

        # --- Permutation test: shuffle trade ORDER for drawdown CI ---
        max_drawdowns = np.empty(self.n_simulations)
        ruin_count = 0

        for i in range(self.n_simulations):
            shuffled = rng.permutation(pnls)
            equity_curve = initial_capital + np.cumsum(shuffled)
            max_drawdowns[i] = self._max_drawdown(equity_curve, initial_capital)

            min_equity = float(np.min(equity_curve))
            if min_equity <= initial_capital * (1 - self.ruin_threshold):
                ruin_count += 1

        # --- Bootstrap: resample WITH replacement for equity/Sharpe CI ---
        final_equities = np.empty(self.n_simulations)
        sharpe_ratios = np.empty(self.n_simulations)

        for i in range(self.n_simulations):
            boot_idx = rng.integers(0, n_trades, size=n_trades)
            boot_pnls = pnls[boot_idx]
            final_equities[i] = initial_capital + float(np.sum(boot_pnls))
            sharpe_ratios[i] = self._compute_sharpe(boot_pnls)

        # --- Sign-flip test for p-value (null: direction is random) ---
        better_return_count = 0
        n_sign_tests = min(self.n_simulations, 10_000)

        for i in range(n_sign_tests):
            signs = rng.choice([-1.0, 1.0], size=n_trades)
            random_return = float(np.sum(pnls * signs))
            if random_return >= float(np.sum(pnls)):
                better_return_count += 1

        # Compute confidence intervals (5th, 50th, 95th)
        final_ci = tuple(float(x) for x in np.percentile(final_equities, [5, 50, 95]))
        dd_ci = tuple(float(x) for x in np.percentile(max_drawdowns, [5, 50, 95]))
        sharpe_ci = tuple(float(x) for x in np.percentile(sharpe_ratios, [5, 50, 95]))

        # P-value from sign-flip test
        p_value = better_return_count / n_sign_tests

        # Risk of ruin from permutation test
        risk_of_ruin = ruin_count / self.n_simulations

        logger.info(
            f"Monte Carlo ({self.n_simulations} sims, {n_trades} trades): "
            f"equity CI=[{final_ci[0]:.0f}, {final_ci[2]:.0f}], "
            f"p-value={p_value:.4f}, ruin={risk_of_ruin:.4f}"
        )

        return MonteCarloResult(
            n_simulations=self.n_simulations,
            n_trades=n_trades,
            final_equity_ci=final_ci,
            max_drawdown_ci=dd_ci,
            sharpe_ratio_ci=sharpe_ci,
            p_value_return=p_value,
            risk_of_ruin=risk_of_ruin,
            original_final_equity=orig_final,
            original_max_drawdown=orig_dd,
            original_sharpe=orig_sharpe,
        )

    @staticmethod
    def _max_drawdown(equity_curve: np.ndarray, initial_capital: float) -> float:
        """Compute maximum drawdown percentage from equity curve."""
        peak = initial_capital
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (peak - eq) / peak
                if dd > max_dd:
                    max_dd = dd
        return max_dd

    @staticmethod
    def _compute_sharpe(pnls: np.ndarray, risk_free: float = 0.0) -> float:
        """Compute Sharpe ratio from per-trade P&L array (no annualization)."""
        if len(pnls) < 2:
            return 0.0
        mean_ret = float(np.mean(pnls))
        std_ret = float(np.std(pnls, ddof=1))
        if std_ret < 1e-10:
            return 0.0
        # Raw mean/std ratio — annualization omitted because trade frequency
        # is not fixed (not daily returns). CI comparison is unaffected.
        return (mean_ret - risk_free) / std_ret

    def _empty_result(self, initial_capital: float, n_trades: int) -> MonteCarloResult:
        """Return empty result for insufficient data."""
        return MonteCarloResult(
            n_simulations=0,
            n_trades=n_trades,
            final_equity_ci=(initial_capital, initial_capital, initial_capital),
            max_drawdown_ci=(0.0, 0.0, 0.0),
            sharpe_ratio_ci=(0.0, 0.0, 0.0),
            p_value_return=1.0,
            risk_of_ruin=0.0,
            original_final_equity=initial_capital,
            original_max_drawdown=0.0,
            original_sharpe=0.0,
        )
