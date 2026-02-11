"""
Pydantic models for execution module.
Defines schemas for orders, execution results, and execution modes.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """Execution mode: paper trading or live."""

    PAPER = "PAPER"
    LIVE = "LIVE"


class ExecutionOrder(BaseModel):
    """Order ready for execution after risk approval."""

    epic: str
    direction: str  # "BUY" or "SELL"
    size: float = Field(gt=0.0)
    entry_price: float = Field(gt=0.0)
    stop_loss: float | None = None
    take_profit: float | None = None
    signal_id: int | None = None
    strategy_id: int | None = None
    order_type: str = "MARKET"


class ExecutionResult(BaseModel):
    """Result of an order execution attempt."""

    success: bool
    deal_id: str | None = None
    fill_price: float | None = None
    slippage: float = 0.0
    error: str | None = None
    execution_time_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
