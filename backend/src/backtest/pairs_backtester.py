"""
Pairs backtester for dual-asset strategies.
Separate from BacktestEngine to avoid modifying single-asset backtest logic.
"""

import numpy as np
from loguru import logger
from pydantic import BaseModel, Field

from src.strategy.pairs.cointegration import CointegrationAnalyzer
from src.strategy.pairs.pairs_strategy import PairsConfig, PairsTradingStrategy


class PairsBacktestResult(BaseModel):
    """Result of a pairs backtest run."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    avg_hold_bars: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    final_equity: float = 0.0
    trades: list[dict] = Field(default_factory=list)


class PairsBacktester:
    """
    Backtester specialized for pairs trading strategies.

    Runs the PairsTradingStrategy on historical price data for two assets,
    with periodic recalibration of the hedge ratio.
    """

    def __init__(self, config: PairsConfig | None = None):
        self.config = config or PairsConfig()

    def run(
        self,
        prices_a: np.ndarray,
        prices_b: np.ndarray,
        initial_equity: float = 10000.0,
        transaction_cost_pct: float = 0.001,
    ) -> PairsBacktestResult:
        """
        Run pairs backtest.

        Args:
            prices_a: Full price series for asset A (Gold)
            prices_b: Full price series for asset B (Bitcoin)
            initial_equity: Starting equity
            transaction_cost_pct: Transaction cost per leg as percentage

        Returns:
            PairsBacktestResult
        """
        n = len(prices_a)
        if n != len(prices_b) or n < self.config.min_cointegration_period + 50:
            logger.warning("Insufficient data for pairs backtest")
            return PairsBacktestResult(final_equity=initial_equity)

        strategy = PairsTradingStrategy(self.config)
        equity = initial_equity
        peak_equity = initial_equity
        max_dd = 0.0
        trades: list[dict] = []
        daily_returns: list[float] = []
        last_equity = equity

        # Start after minimum calibration period
        start_idx = self.config.min_cointegration_period
        calibration_interval = self.config.recalibration_window

        current_entry_a = 0.0
        current_entry_b = 0.0
        current_signal = None

        for i in range(start_idx, n):
            # Periodic recalibration
            if (i - start_idx) % calibration_interval == 0:
                cal_start = max(0, i - self.config.min_cointegration_period)
                strategy.calibrate(
                    prices_a[cal_start:i],
                    prices_b[cal_start:i],
                )

            if not strategy.is_cointegrated:
                daily_returns.append(0.0)
                continue

            # Generate signal
            lookback = self.config.zscore_lookback + 10
            lb_start = max(0, i - lookback)
            signal = strategy.generate_signal(
                prices_a=prices_a[lb_start:i + 1],
                prices_b=prices_b[lb_start:i + 1],
                current_price_a=float(prices_a[i]),
                current_price_b=float(prices_b[i]),
            )

            # Track P&L
            if signal.action in ("LONG_SPREAD", "SHORT_SPREAD") and current_signal is None:
                # Opening trade
                current_signal = signal
                current_entry_a = float(prices_a[i])
                current_entry_b = float(prices_b[i])
                # Transaction cost
                cost = (signal.size_a * current_entry_a + signal.size_b * current_entry_b) * transaction_cost_pct
                equity -= cost

            elif signal.action == "CLOSE" and current_signal is not None:
                # Closing trade
                pnl = self._compute_trade_pnl(
                    current_signal,
                    current_entry_a, current_entry_b,
                    float(prices_a[i]), float(prices_b[i]),
                )
                # Transaction cost on close
                cost = (current_signal.size_a * float(prices_a[i]) +
                        current_signal.size_b * float(prices_b[i])) * transaction_cost_pct
                pnl -= cost

                equity += pnl
                trades.append({
                    "action": current_signal.action,
                    "entry_price_a": current_entry_a,
                    "entry_price_b": current_entry_b,
                    "exit_price_a": float(prices_a[i]),
                    "exit_price_b": float(prices_b[i]),
                    "pnl": pnl,
                    "bars_held": strategy._bars_in_trade,
                    "exit_reason": signal.reason,
                })

                current_signal = None

            # Track drawdown
            peak_equity = max(peak_equity, equity)
            if peak_equity > 0:
                dd = (peak_equity - equity) / peak_equity
                max_dd = max(max_dd, dd)

            # Daily return
            ret = (equity - last_equity) / last_equity if last_equity > 0 else 0.0
            daily_returns.append(ret)
            last_equity = equity

        # Compute metrics
        total_trades = len(trades)
        winning = [t for t in trades if t["pnl"] > 0]
        losing = [t for t in trades if t["pnl"] <= 0]

        win_rate = len(winning) / total_trades if total_trades > 0 else 0.0
        avg_win = np.mean([t["pnl"] for t in winning]) if winning else 0.0
        avg_loss = np.mean([t["pnl"] for t in losing]) if losing else 0.0
        avg_hold = np.mean([t["bars_held"] for t in trades]) if trades else 0.0
        total_pnl = sum(t["pnl"] for t in trades)

        # Sharpe ratio (annualized, assuming hourly bars)
        if daily_returns:
            ret_arr = np.array(daily_returns)
            if ret_arr.std() > 0:
                sharpe = (ret_arr.mean() / ret_arr.std()) * np.sqrt(252 * 24)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        return PairsBacktestResult(
            total_trades=total_trades,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            total_pnl=float(total_pnl),
            max_drawdown_pct=float(max_dd),
            sharpe_ratio=float(sharpe),
            avg_hold_bars=float(avg_hold),
            avg_win=float(avg_win),
            avg_loss=float(avg_loss),
            final_equity=float(equity),
            trades=trades,
        )

    @staticmethod
    def _compute_trade_pnl(
        signal,
        entry_a: float,
        entry_b: float,
        exit_a: float,
        exit_b: float,
    ) -> float:
        """Compute P&L for a pairs trade."""
        if signal.action == "LONG_SPREAD":
            # Long A, Short B
            pnl_a = signal.size_a * (exit_a - entry_a)
            pnl_b = signal.size_b * (entry_b - exit_b)
        elif signal.action == "SHORT_SPREAD":
            # Short A, Long B
            pnl_a = signal.size_a * (entry_a - exit_a)
            pnl_b = signal.size_b * (exit_b - entry_b)
        else:
            return 0.0

        return pnl_a + pnl_b
