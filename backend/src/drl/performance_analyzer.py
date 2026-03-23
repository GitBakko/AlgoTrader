# MANTIS-EVOLUTION: DRL Performance Analyzer
"""Professional performance metrics for DRL agents."""
from __future__ import annotations

import numpy as np
from loguru import logger

from src.drl.schemas import PerformanceMetrics


class MantisPerformanceAnalyzer:
    """Calculates professional trading performance metrics.

    All calculations are pure numpy — no external financial libraries required.
    Metrics follow industry-standard definitions used by hedge funds and CTAs.
    """

    ANNUALIZATION_FACTOR = 252  # Trading days per year
    RISK_FREE_RATE = 0.02  # 2% annual risk-free rate

    def sharpe_ratio(
        self, returns: np.ndarray, risk_free_rate: float | None = None
    ) -> float:
        """Annualized Sharpe ratio.

        Args:
            returns: Array of daily (or per-bar) returns.
            risk_free_rate: Annual risk-free rate (default 2%).

        Returns:
            Annualized Sharpe ratio, or 0.0 when undefined.
        """
        if len(returns) < 2:
            return 0.0
        rfr = risk_free_rate if risk_free_rate is not None else self.RISK_FREE_RATE
        daily_rf = rfr / self.ANNUALIZATION_FACTOR
        excess = returns - daily_rf
        std = np.std(excess, ddof=1)
        if std < 1e-10:
            return 0.0
        return float(np.mean(excess) / std * np.sqrt(self.ANNUALIZATION_FACTOR))

    def sortino_ratio(
        self, returns: np.ndarray, risk_free_rate: float | None = None
    ) -> float:
        """Annualized Sortino ratio (penalises only downside volatility).

        Args:
            returns: Array of daily returns.
            risk_free_rate: Annual risk-free rate (default 2%).

        Returns:
            Annualized Sortino ratio.  Returns inf when there is no downside
            and mean excess return is positive.
        """
        if len(returns) < 2:
            return 0.0
        rfr = risk_free_rate if risk_free_rate is not None else self.RISK_FREE_RATE
        daily_rf = rfr / self.ANNUALIZATION_FACTOR
        excess = returns - daily_rf
        downside = excess[excess < 0]
        if len(downside) == 0:
            return float("inf") if np.mean(excess) > 0 else 0.0
        downside_std = np.std(downside, ddof=1)
        if downside_std < 1e-10:
            return 0.0
        return float(np.mean(excess) / downside_std * np.sqrt(self.ANNUALIZATION_FACTOR))

    def calmar_ratio(
        self, returns: np.ndarray, period_years: float = 1.0
    ) -> float:
        """Calmar ratio = annualized return / maximum drawdown.

        Args:
            returns: Array of daily returns.
            period_years: Length of the period in years (used to annualise).

        Returns:
            Calmar ratio.  Returns inf when max drawdown is zero and the
            annualised return is positive.
        """
        if len(returns) < 2:
            return 0.0
        total_return = float(np.prod(1 + returns) - 1)
        ann_return = total_return / period_years if period_years > 0 else total_return
        mdd = self.max_drawdown(np.cumprod(1 + returns))
        if mdd == 0:
            return float("inf") if ann_return > 0 else 0.0
        return float(ann_return / mdd)

    def max_drawdown(self, equity_curve: np.ndarray) -> float:
        """Maximum drawdown from peak as a positive fraction (e.g., 0.15 = 15%).

        Args:
            equity_curve: Array of equity values (not returns).

        Returns:
            Maximum drawdown fraction in [0, 1].
        """
        if len(equity_curve) < 2:
            return 0.0
        peak = np.maximum.accumulate(equity_curve)
        drawdowns = (peak - equity_curve) / np.where(peak > 0, peak, 1.0)
        return float(np.max(drawdowns))

    def profit_factor(self, pnl_values: np.ndarray) -> float:
        """Profit factor = gross profit / gross loss.

        Args:
            pnl_values: Array of per-trade P&L values.

        Returns:
            Profit factor.  Returns inf when there are no losses and some
            profit.  Returns 0.0 when there are no winning trades.
        """
        if len(pnl_values) == 0:
            return 0.0
        gains = pnl_values[pnl_values > 0]
        losses = pnl_values[pnl_values < 0]
        gross_profit = float(np.sum(gains)) if len(gains) > 0 else 0.0
        gross_loss = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def win_rate(self, pnl_values: np.ndarray) -> float:
        """Win rate = number of winning trades / total trades.

        Args:
            pnl_values: Array of per-trade P&L values.

        Returns:
            Win rate in [0, 1].
        """
        if len(pnl_values) == 0:
            return 0.0
        return float(np.sum(pnl_values > 0) / len(pnl_values))

    def generate_report(
        self,
        returns: np.ndarray,
        equity_curve: np.ndarray | None = None,
        pnl_values: np.ndarray | None = None,
    ) -> PerformanceMetrics:
        """Generate a complete performance report.

        Args:
            returns: Array of daily returns.
            equity_curve: Optional equity curve array.  If None it is computed
                          from returns assuming a 10,000 starting balance.
            pnl_values: Optional per-trade P&L array for trade-level metrics.

        Returns:
            Populated :class:`PerformanceMetrics` instance.
        """
        if equity_curve is None:
            equity_curve = np.cumprod(1 + returns) * 10_000.0

        metrics = PerformanceMetrics(
            sharpe_ratio=self.sharpe_ratio(returns),
            sortino_ratio=self.sortino_ratio(returns),
            calmar_ratio=self.calmar_ratio(returns),
            max_drawdown=self.max_drawdown(equity_curve),
            total_return=float(np.prod(1 + returns) - 1) if len(returns) > 0 else 0.0,
        )

        if pnl_values is not None and len(pnl_values) > 0:
            metrics.win_rate = self.win_rate(pnl_values)
            metrics.profit_factor = self.profit_factor(pnl_values)
            metrics.num_trades = len(pnl_values)

        logger.debug(
            "PerformanceAnalyzer report: sharpe={:.3f} sortino={:.3f} "
            "calmar={:.3f} max_dd={:.3%} total_return={:.3%}",
            metrics.sharpe_ratio,
            metrics.sortino_ratio,
            metrics.calmar_ratio,
            metrics.max_drawdown,
            metrics.total_return,
        )
        return metrics
