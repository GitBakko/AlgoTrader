"""
Pydantic models for risk management module.
Defines schemas for risk checks, limits, and drawdown state.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class RiskCheckResult(BaseModel):
    """Result of a risk check on a proposed trade."""

    approved: bool
    position_size: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    partial_close_pct: float = Field(default=0.50, ge=0.0, le=1.0)
    rejection_reason: str | None = None
    adjustments: list[str] = Field(default_factory=list)
    sizing_method: str = "fixed_fractional"
    circuit_breaker_details: dict | None = None
    audit: dict = Field(default_factory=dict)


class RiskLimits(BaseModel):
    """Configurable risk limits for the trading system."""

    max_risk_per_trade: float = Field(default=0.02, ge=0.001, le=0.10)
    max_daily_drawdown: float = Field(default=0.05, ge=0.01, le=0.50)
    max_total_drawdown: float = Field(default=0.15, ge=0.01, le=0.50)
    max_position_pct: float = Field(
        default=0.10,
        ge=0.01,
        le=1.0,
        description=(
            "Max per-position notional as fraction of equity. "
            "Phase 1 expansion 2026-05-23: lowered 0.20 → 0.10 to keep "
            "100% gross exposure ceiling at the new 10-slot cap."
        ),
    )
    max_total_open_positions: int = Field(
        default=10,
        ge=1,
        le=50,
        description=(
            "Maximum total open positions across all assets (hard cap). "
            "Phase 1 expansion 2026-05-23: raised 5 → 10 for 19-asset basket."
        ),
    )
    max_total_exposure: float = Field(
        default=1.0,
        ge=0.01,
        le=1.0,
        description="Maximum total exposure as fraction of equity (1.0 = 100% cap, enforced).",
    )


class DrawdownState(BaseModel):
    """Current drawdown tracking state."""

    peak_equity: float
    current_equity: float
    current_drawdown_pct: float = 0.0
    daily_pnl: float = 0.0
    daily_start_equity: float = 0.0
    circuit_breaker_active: bool = False
    circuit_breaker_reason: str | None = None
    last_reset: datetime = Field(default_factory=lambda: datetime.now(UTC))
