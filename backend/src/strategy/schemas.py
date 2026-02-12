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
    min_confidence: float = Field(default=0.40, ge=0.0, le=1.0)
    counter_trend_penalty: float = Field(default=0.5, ge=0.0, le=1.0)
    overbought_rsi: float = Field(default=80.0, ge=50.0, le=100.0)
    oversold_rsi: float = Field(default=20.0, ge=0.0, le=50.0)
    stop_multiplier: float = Field(default=2.0, ge=0.5, le=5.0)
    risk_reward_ratio: float = Field(default=2.0, ge=0.5, le=5.0)


class AllocationConfig(BaseModel):
    """Portfolio allocation configuration with regime adjustments."""

    base_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "XAUUSD": 0.14,
            "BTCUSD": 0.10,
            "US500": 0.13,
            "WTIUSD": 0.10,
            "EURUSD": 0.10,
            "NVDA": 0.10,
            "TSLA": 0.08,
            "XAGUSD": 0.11,
            "DE40": 0.14,
        }
    )
    regime_adjustments: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "bull": {
                "XAUUSD": 0.08, "BTCUSD": 0.12, "US500": 0.15,
                "WTIUSD": 0.12, "EURUSD": 0.06, "NVDA": 0.14,
                "TSLA": 0.11, "XAGUSD": 0.07, "DE40": 0.15,
            },
            "bear": {
                "XAUUSD": 0.18, "BTCUSD": 0.06, "US500": 0.10,
                "WTIUSD": 0.08, "EURUSD": 0.16, "NVDA": 0.06,
                "TSLA": 0.04, "XAGUSD": 0.16, "DE40": 0.16,
            },
            "high_vol": {
                "XAUUSD": 0.18, "BTCUSD": 0.05, "US500": 0.12,
                "WTIUSD": 0.08, "EURUSD": 0.15, "NVDA": 0.06,
                "TSLA": 0.04, "XAGUSD": 0.14, "DE40": 0.18,
            },
        }
    )
