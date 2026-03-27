"""
Backtest engine.
Event-driven backtesting loop that simulates trading on historical data.
"""

from datetime import datetime

import polars as pl
from loguru import logger

from src.backtest.costs import CostSimulator
from src.backtest.metrics import MetricsCalculator
from src.backtest.portfolio import PortfolioTracker
from src.backtest.schemas import (
    BacktestConfig,
    BacktestResult,
    TradeDirection,
)
from src.data.utils import timeframe_to_minutes
from src.models.schemas import SignalClass


class BacktestEngine:
    """
    Event-driven backtesting engine.

    For each bar:
    1. Update current prices
    2. Check SL/TP on open positions
    3. Process signal (open/close positions)
    4. Record equity
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.cost_simulator = CostSimulator()
        self.portfolio = PortfolioTracker(config, self.cost_simulator)

    def run(
        self,
        ohlc_df: pl.DataFrame,
        signals_df: pl.DataFrame,
    ) -> BacktestResult:
        """
        Run a backtest on historical data with pre-computed signals.

        Args:
            ohlc_df: OHLC DataFrame with columns: timestamp, open, high, low, close, volume
            signals_df: Signals DataFrame with columns: timestamp, signal (int, SignalClass values)
                        Optional columns: atr (for position sizing)

        Returns:
            BacktestResult with trades, equity curve, and metrics
        """
        if ohlc_df.is_empty():
            raise ValueError("OHLC DataFrame is empty.")

        # Ensure sorted by timestamp
        ohlc_df = ohlc_df.sort("timestamp")
        signals_df = signals_df.sort("timestamp")

        # Create signal lookup by timestamp (column-based for speed)
        sig_ts = signals_df["timestamp"].to_list()
        sig_vals = signals_df["signal"].to_list()
        signal_map = dict(zip(sig_ts, sig_vals))
        atr_map = (
            dict(zip(sig_ts, signals_df["atr"].to_list())) if "atr" in signals_df.columns else {}
        )

        total_bars = len(ohlc_df)
        logger.info(
            f"Starting backtest: {self.config.epic}/{self.config.timeframe}, "
            f"{total_bars} bars, capital={self.config.initial_capital}"
        )

        # Pre-extract columns as lists for fast iteration (avoids per-row dict allocation)
        ts_col = ohlc_df["timestamp"].to_list()
        high_col = ohlc_df["high"].to_list()
        low_col = ohlc_df["low"].to_list()
        close_col = ohlc_df["close"].to_list()

        # Main loop: iterate over each bar
        for i in range(total_bars):
            ts = ts_col[i]
            high = high_col[i]
            low = low_col[i]
            close = close_col[i]

            # Step 1: Check SL/TP exits on open positions
            self.portfolio.check_exits(high, low, close, ts)

            # Step 2: Process signal
            signal = signal_map.get(ts)
            if signal is not None:
                atr = atr_map.get(ts)
                self._process_signal(signal, close, ts, atr)

            # Step 3: Update equity
            self.portfolio.update_equity(close, ts)

        # Close any remaining positions at end
        if total_bars > 0:
            self.portfolio.close_all_positions(close_col[-1], ts_col[-1])

        # Calculate metrics
        tf_minutes = timeframe_to_minutes(self.config.timeframe)
        bars_per_day = (24 * 60) / tf_minutes  # Approximate

        metrics = MetricsCalculator.calculate_all(
            equity_curve=self.portfolio.equity_history,
            trades=self.portfolio.closed_trades,
            initial_capital=self.config.initial_capital,
            bars_per_day=bars_per_day,
        )

        result = BacktestResult(
            config=self.config,
            trades=self.portfolio.closed_trades,
            equity_curve=self.portfolio.equity_history,
            metrics=metrics,
            total_bars=total_bars,
            total_trades=len(self.portfolio.closed_trades),
            start_equity=self.config.initial_capital,
            end_equity=self.portfolio.equity,
        )

        logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"return={metrics.get('total_return', 0):.2%}, "
            f"sharpe={metrics.get('sharpe_ratio', 0):.2f}"
        )

        return result

    def _process_signal(
        self,
        signal: int,
        current_price: float,
        bar_time: datetime,
        atr: float | None = None,
    ) -> None:
        """Process a signal: close existing positions if needed, open new ones."""
        # Map signal to direction
        if signal == SignalClass.BUY:
            desired_direction = TradeDirection.LONG
        elif signal == SignalClass.SELL:
            desired_direction = TradeDirection.SHORT
        else:
            # HOLD: do nothing
            return

        # Close positions in opposite direction
        for trade in list(self.portfolio.open_positions):
            if trade.direction != desired_direction:
                self.portfolio.close_position_by_signal(trade, current_price, bar_time)

        # Open new position if none in desired direction
        has_position = any(t.direction == desired_direction for t in self.portfolio.open_positions)

        if not has_position:
            self.portfolio.open_position(
                direction=desired_direction,
                entry_price=current_price,
                entry_time=bar_time,
                atr_value=atr,
            )
