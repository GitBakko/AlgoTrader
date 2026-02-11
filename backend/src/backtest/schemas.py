"""
Pydantic models for backtesting module.
Defines schemas for backtest configuration, trades, positions, and results.
"""

from datetime import datetime, timezone
from enum import Enum

import polars as pl
from pydantic import BaseModel, ConfigDict, Field


class TradeDirection(str, Enum):
    """Trade direction."""

    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(str, Enum):
    """Trade lifecycle status."""

    OPEN = "open"
    CLOSED_TP = "closed_tp"  # Take profit hit
    CLOSED_SL = "closed_sl"  # Stop loss hit
    CLOSED_SIGNAL = "closed_signal"  # Reverse signal
    CLOSED_EOB = "closed_eob"  # End of backtest


class BacktestConfig(BaseModel):
    """Configuration for a backtest run."""

    epic: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10_000.0
    risk_per_trade: float = 0.02  # 2% risk per trade
    max_positions: int = 1  # Max simultaneous positions per asset
    atr_sl_multiplier: float = 2.0  # ATR-based stop loss multiplier
    atr_tp_multiplier: float = 3.0  # ATR-based take profit multiplier
    include_costs: bool = True


class BacktestTrade(BaseModel):
    """A single trade in a backtest."""

    model_config = ConfigDict(use_enum_values=True)

    trade_id: int
    epic: str
    direction: TradeDirection
    entry_price: float
    entry_time: datetime
    exit_price: float | None = None
    exit_time: datetime | None = None
    size: float = 1.0  # Position size in units
    stop_loss: float | None = None
    take_profit: float | None = None
    status: TradeStatus = TradeStatus.OPEN
    pnl: float = 0.0  # Realized P&L
    fees: float = 0.0  # Total transaction costs
    net_pnl: float = 0.0  # PnL after fees
    bars_held: int = 0


class BacktestResult(BaseModel):
    """Complete backtest result."""

    config: BacktestConfig
    trades: list[BacktestTrade] = Field(default_factory=list)
    equity_curve: list[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    total_bars: int = 0
    total_trades: int = 0
    start_equity: float = 0.0
    end_equity: float = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
