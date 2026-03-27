"""
Backtest report generator.
Produces structured reports from backtest results.
"""

from src.backtest.schemas import BacktestResult, BacktestTrade


class BacktestReporter:
    """
    Generates structured reports from backtest results.
    Output is JSON-serializable for frontend consumption.
    """

    @staticmethod
    def generate_report(result: BacktestResult) -> dict:
        """
        Generate a comprehensive backtest report.

        Args:
            result: BacktestResult from engine.run()

        Returns:
            Dict with summary, trades, equity curve, and detailed metrics
        """
        metrics = result.metrics

        report = {
            "summary": {
                "epic": result.config.epic,
                "timeframe": result.config.timeframe,
                "period": {
                    "start": result.config.start_date.isoformat(),
                    "end": result.config.end_date.isoformat(),
                },
                "initial_capital": result.config.initial_capital,
                "final_equity": result.end_equity,
                "total_return": metrics.get("total_return", 0.0),
                "total_pnl": metrics.get("total_pnl", 0.0),
                "total_bars": result.total_bars,
                "total_trades": result.total_trades,
            },
            "risk_metrics": {
                "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
                "sortino_ratio": metrics.get("sortino_ratio", 0.0),
                "calmar_ratio": metrics.get("calmar_ratio", 0.0),
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "max_drawdown_duration_bars": metrics.get("max_drawdown_duration_bars", 0),
                "volatility": metrics.get("volatility", 0.0),
                "annualized_return": metrics.get("annualized_return", 0.0),
            },
            "trade_metrics": {
                "total_trades": metrics.get("total_trades", 0),
                "winning_trades": metrics.get("winning_trades", 0),
                "losing_trades": metrics.get("losing_trades", 0),
                "win_rate": metrics.get("win_rate", 0.0),
                "avg_win": metrics.get("avg_win", 0.0),
                "avg_loss": metrics.get("avg_loss", 0.0),
                "profit_factor": metrics.get("profit_factor", 0.0),
                "avg_bars_held": metrics.get("avg_bars_held", 0.0),
                "max_consecutive_wins": metrics.get("max_consecutive_wins", 0),
                "max_consecutive_losses": metrics.get("max_consecutive_losses", 0),
                "total_fees": metrics.get("total_fees", 0.0),
            },
            "equity_curve": [
                {
                    "timestamp": (
                        pt["timestamp"].isoformat()
                        if hasattr(pt["timestamp"], "isoformat")
                        else str(pt["timestamp"])
                    ),
                    "equity": pt["equity"],
                }
                for pt in result.equity_curve
            ],
            "trades": [BacktestReporter._trade_to_dict(t) for t in result.trades],
            "generated_at": result.generated_at.isoformat(),
        }

        return report

    @staticmethod
    def summarize(result: BacktestResult) -> str:
        """
        Generate a human-readable text summary.

        Args:
            result: BacktestResult

        Returns:
            Formatted string summary
        """
        m = result.metrics
        lines = [
            f"=== Backtest Report: {result.config.epic}/{result.config.timeframe} ===",
            f"Period: {result.config.start_date:%Y-%m-%d} to {result.config.end_date:%Y-%m-%d}",
            f"Bars: {result.total_bars}",
            "",
            "--- Returns ---",
            f"Initial Capital: ${result.config.initial_capital:,.2f}",
            f"Final Equity:    ${result.end_equity:,.2f}",
            f"Total Return:    {m.get('total_return', 0):.2%}",
            f"Annualized:      {m.get('annualized_return', 0):.2%}",
            "",
            "--- Risk ---",
            f"Sharpe Ratio:    {m.get('sharpe_ratio', 0):.2f}",
            f"Sortino Ratio:   {m.get('sortino_ratio', 0):.2f}",
            f"Calmar Ratio:    {m.get('calmar_ratio', 0):.2f}",
            f"Max Drawdown:    {m.get('max_drawdown', 0):.2%}",
            f"Volatility:      {m.get('volatility', 0):.2%}",
            "",
            "--- Trades ---",
            f"Total Trades:    {m.get('total_trades', 0)}",
            f"Win Rate:        {m.get('win_rate', 0):.1%}",
            f"Profit Factor:   {m.get('profit_factor', 0):.2f}",
            f"Avg Win:         ${m.get('avg_win', 0):,.2f}",
            f"Avg Loss:        ${m.get('avg_loss', 0):,.2f}",
            f"Total Fees:      ${m.get('total_fees', 0):,.2f}",
        ]

        return "\n".join(lines)

    @staticmethod
    def _trade_to_dict(trade: BacktestTrade) -> dict:
        """Convert a trade to a JSON-serializable dict."""
        return {
            "trade_id": trade.trade_id,
            "epic": trade.epic,
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "entry_time": (
                trade.entry_time.isoformat()
                if hasattr(trade.entry_time, "isoformat")
                else str(trade.entry_time)
            ),
            "exit_price": trade.exit_price,
            "exit_time": (
                trade.exit_time.isoformat()
                if trade.exit_time and hasattr(trade.exit_time, "isoformat")
                else str(trade.exit_time) if trade.exit_time else None
            ),
            "size": trade.size,
            "status": trade.status,
            "pnl": trade.pnl,
            "fees": trade.fees,
            "net_pnl": trade.net_pnl,
            "bars_held": trade.bars_held,
        }
