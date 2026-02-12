"""
Portfolio tracker for backtesting.
Manages open positions, equity calculation, and trade lifecycle.
"""

from datetime import datetime

from loguru import logger

from src.backtest.costs import CostSimulator
from src.backtest.schemas import BacktestConfig, BacktestTrade, TradeDirection, TradeStatus
from src.data.utils import timeframe_to_minutes


class PortfolioTracker:
    """
    Tracks portfolio state during a backtest.
    Manages cash, open positions, equity curve, and trade lifecycle.
    """

    def __init__(self, config: BacktestConfig, cost_simulator: CostSimulator | None = None):
        self.config = config
        self.cost_simulator = cost_simulator or CostSimulator()

        self.cash = config.initial_capital
        self.equity = config.initial_capital
        self.open_positions: list[BacktestTrade] = []
        self.closed_trades: list[BacktestTrade] = []
        self.equity_history: list[dict] = []
        self._trade_counter = 0

    def open_position(
        self,
        direction: TradeDirection,
        entry_price: float,
        entry_time: datetime,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        atr_value: float | None = None,
    ) -> BacktestTrade | None:
        """
        Open a new position.

        Position size is calculated based on risk_per_trade and stop distance.

        Returns:
            BacktestTrade if opened, None if rejected (max positions reached)
        """
        # Check max positions
        if len(self.open_positions) >= self.config.max_positions:
            return None

        # Calculate stop loss from ATR if not provided
        if stop_loss is None and atr_value is not None:
            sl_distance = atr_value * self.config.atr_sl_multiplier
            if direction == TradeDirection.LONG:
                stop_loss = entry_price - sl_distance
            else:
                stop_loss = entry_price + sl_distance

        # Calculate take profit from ATR if not provided
        if take_profit is None and atr_value is not None:
            tp_distance = atr_value * self.config.atr_tp_multiplier
            if direction == TradeDirection.LONG:
                take_profit = entry_price + tp_distance
            else:
                take_profit = entry_price - tp_distance

        # Calculate position size based on risk
        size = self._calculate_position_size(entry_price, stop_loss)
        if size <= 0:
            return None

        self._trade_counter += 1
        trade = BacktestTrade(
            trade_id=self._trade_counter,
            epic=self.config.epic,
            direction=direction,
            entry_price=entry_price,
            entry_time=entry_time,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        self.open_positions.append(trade)
        return trade

    def check_exits(self, high: float, low: float, close: float, bar_time: datetime) -> list[BacktestTrade]:
        """
        Check if any open positions hit SL/TP.

        Args:
            high: Current bar high
            low: Current bar low
            close: Current bar close
            bar_time: Current bar timestamp

        Returns:
            List of trades that were closed
        """
        closed = []
        remaining = []

        for trade in self.open_positions:
            trade.bars_held += 1
            exit_price = None
            status = None

            if trade.direction == TradeDirection.LONG:
                # Check stop loss (hit if low <= SL)
                if trade.stop_loss is not None and low <= trade.stop_loss:
                    exit_price = trade.stop_loss
                    status = TradeStatus.CLOSED_SL
                # Check take profit (hit if high >= TP)
                elif trade.take_profit is not None and high >= trade.take_profit:
                    exit_price = trade.take_profit
                    status = TradeStatus.CLOSED_TP
            else:  # SHORT
                # Check stop loss (hit if high >= SL)
                if trade.stop_loss is not None and high >= trade.stop_loss:
                    exit_price = trade.stop_loss
                    status = TradeStatus.CLOSED_SL
                # Check take profit (hit if low <= TP)
                elif trade.take_profit is not None and low <= trade.take_profit:
                    exit_price = trade.take_profit
                    status = TradeStatus.CLOSED_TP

            if exit_price is not None:
                self._close_trade(trade, exit_price, bar_time, status)
                closed.append(trade)
            else:
                remaining.append(trade)

        self.open_positions = remaining
        return closed

    def close_all_positions(self, close_price: float, bar_time: datetime) -> list[BacktestTrade]:
        """Close all open positions at end of backtest."""
        closed = []
        for trade in self.open_positions:
            self._close_trade(trade, close_price, bar_time, TradeStatus.CLOSED_EOB)
            closed.append(trade)
        self.open_positions = []
        return closed

    def close_position_by_signal(
        self, trade: BacktestTrade, close_price: float, bar_time: datetime
    ) -> None:
        """Close a specific position due to a reverse signal."""
        self._close_trade(trade, close_price, bar_time, TradeStatus.CLOSED_SIGNAL)
        self.open_positions = [t for t in self.open_positions if t.trade_id != trade.trade_id]

    def update_equity(self, current_price: float, bar_time: datetime) -> None:
        """
        Update portfolio equity with current market price.
        Records equity point for the equity curve.
        """
        unrealized_pnl = 0.0
        for trade in self.open_positions:
            if trade.direction == TradeDirection.LONG:
                unrealized_pnl += (current_price - trade.entry_price) * trade.size
            else:
                unrealized_pnl += (trade.entry_price - current_price) * trade.size

        self.equity = self.cash + unrealized_pnl

        self.equity_history.append({
            "timestamp": bar_time,
            "equity": self.equity,
            "cash": self.cash,
            "unrealized_pnl": unrealized_pnl,
            "open_positions": len(self.open_positions),
        })

    @property
    def all_trades(self) -> list[BacktestTrade]:
        """All closed trades."""
        return self.closed_trades

    @property
    def current_drawdown(self) -> float:
        """Current drawdown as a fraction of peak equity."""
        if not self.equity_history:
            return 0.0
        peak = max(pt["equity"] for pt in self.equity_history)
        if peak <= 0:
            return 0.0
        return (peak - self.equity) / peak

    def _close_trade(
        self,
        trade: BacktestTrade,
        exit_price: float,
        exit_time: datetime,
        status: TradeStatus,
    ) -> None:
        """Close a trade and update cash."""
        # Calculate P&L
        if trade.direction == TradeDirection.LONG:
            pnl = (exit_price - trade.entry_price) * trade.size
        else:
            pnl = (trade.entry_price - exit_price) * trade.size

        # Calculate fees
        fees = 0.0
        if self.config.include_costs:
            tf_minutes = timeframe_to_minutes(self.config.timeframe)
            is_sl_exit = status == TradeStatus.CLOSED_SL
            fees = self.cost_simulator.calculate_total_cost(
                epic=trade.epic,
                size=trade.size,
                entry_price=trade.entry_price,
                direction=trade.direction,
                bars_held=trade.bars_held,
                timeframe_minutes=tf_minutes,
                is_sl_exit=is_sl_exit,
                entry_time=trade.entry_time,
            )

        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.status = status
        trade.pnl = pnl
        trade.fees = fees
        trade.net_pnl = pnl - fees

        self.cash += trade.net_pnl
        self.closed_trades.append(trade)

    def _calculate_position_size(
        self, entry_price: float, stop_loss: float | None
    ) -> float:
        """
        Calculate position size based on risk per trade.

        Risk amount = equity * risk_per_trade
        Position size = risk_amount / stop_distance
        """
        if stop_loss is None:
            # Without SL, use a conservative fixed fraction
            return (self.equity * self.config.risk_per_trade) / entry_price

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return 0.0

        risk_amount = self.equity * self.config.risk_per_trade
        size = risk_amount / stop_distance

        # Cap at 5% of equity
        max_size = (self.equity * 0.05) / entry_price
        return min(size, max_size)
