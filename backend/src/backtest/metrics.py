"""
Performance metrics calculator for backtesting.
Computes Sharpe, Sortino, Calmar, max drawdown, win rate, and more.
"""

import math

import numpy as np

from src.backtest.schemas import BacktestTrade


class MetricsCalculator:
    """
    Calculates performance metrics from backtest results.
    All ratios are annualized assuming 252 trading days.
    """

    TRADING_DAYS_PER_YEAR = 252
    RISK_FREE_RATE = 0.0  # Assume 0 for simplicity

    @staticmethod
    def calculate_all(
        equity_curve: list[dict],
        trades: list[BacktestTrade],
        initial_capital: float,
        bars_per_day: float = 6.0,
    ) -> dict:
        """
        Calculate all performance metrics.

        Args:
            equity_curve: List of equity points (dict with 'equity' key)
            trades: List of closed trades
            initial_capital: Starting capital
            bars_per_day: Average bars per trading day (for annualization)

        Returns:
            Dict with all metrics
        """
        mc = MetricsCalculator

        if not equity_curve:
            return mc._empty_metrics()

        equities = np.array([pt["equity"] for pt in equity_curve], dtype=np.float64)

        if len(equities) < 2:
            return mc._empty_metrics()

        # Returns
        returns = np.diff(equities) / equities[:-1]
        returns = returns[np.isfinite(returns)]

        if len(returns) == 0:
            return mc._empty_metrics()

        # Annualization factor
        ann_factor = bars_per_day * mc.TRADING_DAYS_PER_YEAR

        metrics = {}

        # ===== Return Metrics =====
        metrics["total_return"] = float((equities[-1] - initial_capital) / initial_capital)
        metrics["total_pnl"] = float(equities[-1] - initial_capital)
        metrics["end_equity"] = float(equities[-1])

        n_bars = len(equities)
        if n_bars > 1 and equities[-1] > 0 and initial_capital > 0:
            years = n_bars / ann_factor
            if years > 0:
                metrics["annualized_return"] = float(
                    (equities[-1] / initial_capital) ** (1 / years) - 1
                )
            else:
                metrics["annualized_return"] = 0.0
        else:
            metrics["annualized_return"] = 0.0

        # ===== Risk Metrics =====
        # Max drawdown
        dd_result = mc._calculate_max_drawdown(equities)
        metrics["max_drawdown"] = dd_result["max_drawdown"]
        metrics["max_drawdown_duration_bars"] = dd_result["max_drawdown_duration_bars"]

        # Volatility (annualized)
        metrics["volatility"] = float(np.std(returns) * math.sqrt(ann_factor))

        # ===== Risk-Adjusted Returns =====
        # Sharpe Ratio
        if metrics["volatility"] > 0:
            mean_return = float(np.mean(returns))
            metrics["sharpe_ratio"] = float(
                (mean_return * ann_factor - mc.RISK_FREE_RATE) / metrics["volatility"]
            )
        else:
            metrics["sharpe_ratio"] = 0.0

        # Sortino Ratio (downside deviation only)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = float(np.std(downside_returns) * math.sqrt(ann_factor))
            if downside_std > 0:
                metrics["sortino_ratio"] = float(
                    (np.mean(returns) * ann_factor - mc.RISK_FREE_RATE) / downside_std
                )
            else:
                metrics["sortino_ratio"] = 0.0
        else:
            metrics["sortino_ratio"] = float("inf") if metrics["total_return"] > 0 else 0.0

        # Calmar Ratio (annualized return / max drawdown)
        if metrics["max_drawdown"] > 0:
            metrics["calmar_ratio"] = float(
                metrics["annualized_return"] / metrics["max_drawdown"]
            )
        else:
            metrics["calmar_ratio"] = float("inf") if metrics["annualized_return"] > 0 else 0.0

        # ===== Trade Metrics =====
        trade_metrics = mc._calculate_trade_metrics(trades)
        metrics.update(trade_metrics)

        return metrics

    @staticmethod
    def _calculate_max_drawdown(equities: np.ndarray) -> dict:
        """Calculate maximum drawdown and its duration."""
        peak = equities[0]
        max_dd = 0.0
        max_dd_duration = 0
        current_dd_start = 0
        peak_idx = 0

        for i, eq in enumerate(equities):
            if eq > peak:
                peak = eq
                peak_idx = i
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_duration = i - peak_idx

        return {
            "max_drawdown": float(max_dd),
            "max_drawdown_duration_bars": int(max_dd_duration),
        }

    @staticmethod
    def _calculate_trade_metrics(trades: list[BacktestTrade]) -> dict:
        """Calculate trade-level metrics."""
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "avg_bars_held": 0.0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
            }

        pnls = [t.net_pnl for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_wins = sum(wins) if wins else 0.0
        total_losses = abs(sum(losses)) if losses else 0.0

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        current_wins = 0
        current_losses = 0

        for pnl in pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consec_wins = max(max_consec_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consec_losses = max(max_consec_losses, current_losses)

        return {
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(trades) if trades else 0.0,
            "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(losses) / len(losses) if losses else 0.0,
            "profit_factor": total_wins / total_losses if total_losses > 0 else float("inf"),
            "avg_bars_held": sum(t.bars_held for t in trades) / len(trades),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "total_fees": sum(t.fees for t in trades),
        }

    @staticmethod
    def _empty_metrics() -> dict:
        """Return empty metrics dict."""
        return {
            "total_return": 0.0,
            "total_pnl": 0.0,
            "end_equity": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_duration_bars": 0,
            "volatility": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "avg_bars_held": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
        }
