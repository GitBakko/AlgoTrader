# MANTIS-EVOLUTION: DRL Backtester
"""Backtester for validating DRL ensemble before deploy."""

from __future__ import annotations

import numpy as np
from loguru import logger

from src.drl.ensemble import MantisDRLEnsemble
from src.drl.performance_analyzer import MantisPerformanceAnalyzer
from src.drl.schemas import BacktestConfig, BacktestResult


class MantisDRLBacktester:
    """
    Backtester for DRL ensemble.
    Simulates trading on historical price data using the ensemble's signals.

    Position model:
      0  = flat
      1  = long
     -1  = short

    P&L is realised on close; commission and slippage are deducted from each
    round-trip as a fraction of the gross P&L.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()
        self.analyzer = MantisPerformanceAnalyzer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        prices: np.ndarray,
        ensemble: MantisDRLEnsemble,
        regimes: list[str] | None = None,
    ) -> BacktestResult:
        """
        Run backtest on historical prices.

        Args:
            prices: 1-D array of close prices (float64).
            ensemble: Trained DRL ensemble to generate signals.
            regimes: Optional per-bar regime labels; defaults to "UNKNOWN".

        Returns:
            BacktestResult with equity curve, trade log, and metrics.
        """
        n = len(prices)
        if n < 2:
            return BacktestResult(config=self.config)

        if regimes is None:
            regimes = ["UNKNOWN"] * n

        balance = self.config.initial_balance
        position = 0  # 0=flat, 1=long, -1=short
        entry_price = 0.0
        equity_curve: list[float] = [balance]
        trades: list[dict] = []

        for i in range(1, n):
            obs = self._build_observation(prices, i)
            signal = ensemble.predict(obs, current_regime=regimes[i])

            # ---- Action: BUY (1) ----
            if signal.action == 1 and position <= 0:
                if position == -1:  # Close existing short first
                    pnl = (entry_price - prices[i]) * self.config.max_position_size
                    pnl = self._apply_costs(pnl)
                    balance += pnl
                    trades.append({"type": "CLOSE_SHORT", "price": float(prices[i]), "pnl": pnl})
                # Open long
                position = 1
                entry_price = float(prices[i])

            # ---- Action: SELL (2) ----
            elif signal.action == 2 and position >= 0:
                if position == 1:  # Close existing long first
                    pnl = (prices[i] - entry_price) * self.config.max_position_size
                    pnl = self._apply_costs(pnl)
                    balance += pnl
                    trades.append({"type": "CLOSE_LONG", "price": float(prices[i]), "pnl": pnl})
                # Open short
                position = -1
                entry_price = float(prices[i])

            # ---- Mark-to-market ----
            mtm = self._mark_to_market(balance, position, entry_price, prices[i])
            equity_curve.append(mtm)

        # ---- Close any open position at end of data ----
        if position != 0:
            final_pnl = self._close_position(position, entry_price, prices[-1])
            trades.append(
                {
                    "type": f"CLOSE_{'LONG' if position == 1 else 'SHORT'}",
                    "price": float(prices[-1]),
                    "pnl": final_pnl,
                }
            )

        # ---- Metrics ----
        equity_arr = np.array(equity_curve, dtype=np.float64)
        returns = np.diff(equity_arr) / np.where(equity_arr[:-1] != 0, equity_arr[:-1], 1.0)
        pnl_values = (
            np.array([t["pnl"] for t in trades], dtype=np.float64) if trades else np.array([])
        )

        metrics = self.analyzer.generate_report(returns, equity_arr, pnl_values)

        benchmark_return = float((prices[-1] / prices[0]) - 1) if prices[0] != 0 else 0.0

        logger.debug(
            f"[MantisDRLBacktester] Completed: {len(trades)} trades, "
            f"sharpe={metrics.sharpe_ratio:.3f}, "
            f"benchmark={benchmark_return:.3%}"
        )

        return BacktestResult(
            config=self.config,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            benchmark_return=benchmark_return,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply_costs(self, gross_pnl: float) -> float:
        """Deduct commission + slippage from gross P&L."""
        cost = abs(gross_pnl) * (self.config.commission_pct + self.config.slippage_pct)
        return gross_pnl - cost

    def _mark_to_market(
        self,
        balance: float,
        position: int,
        entry_price: float,
        current_price: float,
    ) -> float:
        """Compute unrealised equity for the current bar."""
        if position == 1:
            return balance + (current_price - entry_price) * self.config.max_position_size
        if position == -1:
            return balance + (entry_price - current_price) * self.config.max_position_size
        return balance

    def _close_position(
        self,
        position: int,
        entry_price: float,
        close_price: float,
    ) -> float:
        """Calculate P&L for closing an open position."""
        if position == 1:
            gross = (close_price - entry_price) * self.config.max_position_size
        else:
            gross = (entry_price - close_price) * self.config.max_position_size
        return self._apply_costs(gross)

    def _build_observation(self, prices: np.ndarray, idx: int) -> np.ndarray:
        """
        Build a simple 6-element observation vector from a price window.

        Features:
          [0] last 1-bar return
          [1] mean return over window
          [2] std of returns over window (volatility)
          [3] 5-bar momentum
          [4] normalised time progress
          [5] placeholder (zeros)
        """
        window = min(10, idx)
        price_slice = prices[idx - window : idx + 1]
        if len(price_slice) < 2:
            return np.zeros(6, dtype=np.float32)

        returns = np.diff(price_slice) / np.where(price_slice[:-1] != 0, price_slice[:-1], 1.0)

        last_return = float(returns[-1]) if len(returns) > 0 else 0.0
        mean_return = float(np.mean(returns))
        vol = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
        momentum_5 = float(prices[idx] / prices[max(0, idx - 5)] - 1) if idx >= 5 else 0.0
        time_progress = min(idx / max(len(prices), 1), 1.0)

        return np.array(
            [last_return, mean_return, vol, momentum_5, time_progress, 0.0],
            dtype=np.float32,
        )
