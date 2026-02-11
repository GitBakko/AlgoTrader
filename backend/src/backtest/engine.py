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

        # Create signal lookup by timestamp
        signal_map = {}
        atr_map = {}
        for row in signals_df.iter_rows(named=True):
            signal_map[row["timestamp"]] = row["signal"]
            if "atr" in row:
                atr_map[row["timestamp"]] = row["atr"]

        total_bars = len(ohlc_df)
        logger.info(
            f"Starting backtest: {self.config.epic}/{self.config.timeframe}, "
            f"{total_bars} bars, capital={self.config.initial_capital}"
        )

        # Main loop: iterate over each bar
        for row in ohlc_df.iter_rows(named=True):
            ts = row["timestamp"]
            high = row["high"]
            low = row["low"]
            close = row["close"]

            # Step 1: Check SL/TP exits on open positions
            closed = self.portfolio.check_exits(high, low, close, ts)

            # Step 2: Process signal
            signal = signal_map.get(ts)
            if signal is not None:
                atr = atr_map.get(ts)
                self._process_signal(signal, close, ts, atr)

            # Step 3: Update equity
            self.portfolio.update_equity(close, ts)

        # Close any remaining positions at end
        if ohlc_df.height > 0:
            last_row = ohlc_df.row(-1, named=True)
            self.portfolio.close_all_positions(last_row["close"], last_row["timestamp"])

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
        if signal in (SignalClass.BUY, SignalClass.STRONG_BUY):
            desired_direction = TradeDirection.LONG
        elif signal in (SignalClass.SELL, SignalClass.STRONG_SELL):
            desired_direction = TradeDirection.SHORT
        else:
            # HOLD: do nothing
            return

        # Close positions in opposite direction
        for trade in list(self.portfolio.open_positions):
            if trade.direction != desired_direction:
                self.portfolio.close_position_by_signal(trade, current_price, bar_time)

        # Open new position if none in desired direction
        has_position = any(
            t.direction == desired_direction for t in self.portfolio.open_positions
        )

        if not has_position:
            self.portfolio.open_position(
                direction=desired_direction,
                entry_price=current_price,
                entry_time=bar_time,
                atr_value=atr,
            )
