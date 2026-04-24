"""
API response schemas and DTOs.
Provides consistent envelope format for all API responses.
"""

from datetime import datetime

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Response helpers ──


def success_response(data) -> dict:
    """Wrap data in standard success envelope."""
    return {"success": True, "data": data}


def error_response(error: str, status_code: int = 400) -> JSONResponse:
    """Return standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": error},
    )


# ── Query params ──


class PaginationParams(BaseModel):
    """Common pagination parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


# ── Dashboard DTOs ──


class DashboardOverview(BaseModel):
    """Dashboard summary data."""

    equity: float = 0.0
    daily_pnl: float = 0.0
    today_realized_pnl: float = 0.0
    total_pnl: float = 0.0
    open_positions_count: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    circuit_breaker_active: bool = False
    trading_mode: str = "paper"


class EquityCurvePoint(BaseModel):
    """Single point on the equity curve."""

    date: str
    equity: float
    drawdown_pct: float = 0.0
    daily_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    cumulative_trades: int = 0
    cumulative_win_rate: float = 0.0


class TradeResponse(BaseModel):
    """Trade information for API responses."""

    deal_id: str
    epic: str
    direction: str
    size: float
    entry_price: float
    exit_price: float | None = None
    pnl: float | None = None
    timestamp: str


# ── Position DTOs ──


class PositionResponse(BaseModel):
    """Open position for API responses."""

    deal_id: str
    epic: str
    direction: str
    size: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    current_pnl: float = 0.0
    opened_at: str | None = None


class ClosedPositionResponse(BaseModel):
    """Closed position for API responses."""

    deal_id: str
    epic: str
    direction: str
    size: float
    entry_price: float
    exit_price: float | None = None
    profit_loss: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    close_reason: str | None = None
    opened_at: str | None = None
    closed_at: str | None = None
    duration_minutes: int | None = None


class ModifyStopsRequest(BaseModel):
    """Request to modify SL/TP levels."""

    stop_loss: float | None = None
    take_profit: float | None = None


class UpdateTradeNoteRequest(BaseModel):
    """Request to create/update a trade journal note."""

    epic: str
    signal_timestamp: str
    notes: str = Field(max_length=2000)


# ── Signal DTOs ──


class SignalResponse(BaseModel):
    """Trading signal for API responses."""

    id: int | None = None
    epic: str
    direction: str
    confidence: float
    signal_class: int
    entry_price: float
    suggested_stop: float | None = None
    suggested_tp: float | None = None
    regime: str | None = None
    timestamp: str
    status: str = "pending"


# ── Market DTOs ──


class MarketInfo(BaseModel):
    """Market summary information."""

    epic: str
    name: str
    bid: float | None = None
    offer: float | None = None
    high: float | None = None
    low: float | None = None
    change_pct: float | None = None


class OHLCResponse(BaseModel):
    """OHLC candle for API responses."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# ── Strategy DTOs ──


class StrategyConfigResponse(BaseModel):
    """Strategy configuration for API responses."""

    epic: str
    min_confidence: float
    counter_trend_penalty: float
    stop_multiplier: float
    risk_reward_ratio: float
    overbought_rsi: float
    oversold_rsi: float


class PerformanceDeltaResponse(BaseModel):
    """Win-rate delta (current vs previous retro-shifted period) for the Win Rate tile."""

    timeframe: str
    date_from: str
    date_to: str
    prev_from: str
    prev_to: str
    win_rate_current: float | None = None
    win_rate_previous: float | None = None
    delta_pp: float | None = None
    n_current: int = 0
    n_previous: int = 0
    wins_current: int = 0
    losses_current: int = 0
    source: str = "db"


class RiskLimitsResponse(BaseModel):
    """Risk limits for API responses."""

    max_risk_per_trade: float
    max_daily_drawdown: float
    max_total_drawdown: float
    max_position_pct: float
    max_correlated_exposure: float


class AllocationResponse(BaseModel):
    """Portfolio allocation for API responses."""

    weights: dict[str, float]
    regime: str | None = None


# ── Backtest DTOs ──


class BacktestRunRequest(BaseModel):
    """Request to start a backtest."""

    epic: str = "XAUUSD"
    timeframe: str = "1h"
    start_date: str | None = None
    end_date: str | None = None
    initial_equity: float = Field(default=10000.0, gt=0)
    risk_per_trade: float = Field(default=0.02, gt=0, le=0.10)
    strategy: str = "ml_ensemble"  # ml_ensemble, squeeze_breakout, vwap_reversion, auto


class BacktestRunResponse(BaseModel):
    """Backtest run summary."""

    id: str
    epic: str
    status: str  # "running", "completed", "failed"
    total_return_pct: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown_pct: float | None = None
    total_trades: int | None = None
    win_rate: float | None = None
    created_at: str


# ── System DTOs ──


class RiskStatusResponse(BaseModel):
    """Current risk management status."""

    peak_equity: float
    current_equity: float
    current_drawdown_pct: float
    daily_pnl: float
    circuit_breaker_active: bool
    circuit_breaker_reason: str | None = None


class SystemSettingsResponse(BaseModel):
    """Read-only system settings."""

    app_name: str
    app_version: str
    environment: str
    trading_enabled: bool
    paper_trading: bool
    use_demo: bool
    min_confidence_threshold: float
    max_risk_per_trade: float
    max_daily_drawdown: float
    max_total_drawdown: float


class RecoveryReportResponse(BaseModel):
    """State recovery report from system startup."""

    success: bool
    positions_recovered: int
    positions_source: str  # "broker", "database", "none"
    trailing_stops_restored: int
    trade_history_count: int
    risk_state_restored: bool
    warnings: list[str]
    errors: list[str]
    recovered_at: datetime
