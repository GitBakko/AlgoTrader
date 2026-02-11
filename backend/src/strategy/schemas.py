"""
Pydantic models for strategy module.
Defines schemas for trading signals, strategy configuration, and portfolio allocation.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class SignalDirection(str, Enum):
    """Direction of a trading signal."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradingSignal(BaseModel):
    """
    Actionable trading signal generated from ML prediction + technical confirmation.
    This is the output of the strategy module, consumed by risk and execution.
    """

    epic: str
    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    signal_class: int = Field(ge=0, le=2)  # SignalClass value (0=SELL, 1=HOLD, 2=BUY)
    regime: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    technical_confirmation: bool = True
    entry_price: float
    suggested_stop: float | None = None
    suggested_tp: float | None = None


class StrategyConfig(BaseModel):
    """Per-asset strategy configuration with tunable parameters."""

    epic: str = ""
    timeframe: str = "1h"
    min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    counter_trend_penalty: float = Field(default=0.5, ge=0.0, le=1.0)
    overbought_rsi: float = Field(default=80.0, ge=50.0, le=100.0)
    oversold_rsi: float = Field(default=20.0, ge=0.0, le=50.0)
    stop_multiplier: float = Field(default=2.0, ge=0.5, le=5.0)
    risk_reward_ratio: float = Field(default=2.0, ge=0.5, le=5.0)


class AllocationConfig(BaseModel):
    """Portfolio allocation configuration with regime adjustments."""

    base_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "XAUUSD": 0.35,
            "BTCUSD": 0.30,
            "US500": 0.35,
        }
    )
    regime_adjustments: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "bull": {"XAUUSD": 0.25, "BTCUSD": 0.35, "US500": 0.40},
            "bear": {"XAUUSD": 0.45, "BTCUSD": 0.20, "US500": 0.35},
            "high_vol": {"XAUUSD": 0.50, "BTCUSD": 0.15, "US500": 0.35},
        }
    )
