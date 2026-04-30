"""
SQLModel ORM models for AlgoTrader AI PostgreSQL database.
Based on schema design in schema_design.md.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Column,
    ForeignKey,
    MetaData,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# MetaData object for Alembic migrations
metadata = MetaData()


class Account(SQLModel, table=True):
    """
    Capital.com account state snapshots over time.
    Tracks balance, equity, and margin for P&L analysis.
    """

    __tablename__ = "accounts"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    account_id: str = Field(max_length=100, nullable=False, index=True)
    account_type: str = Field(max_length=50, nullable=False)  # DEMO, LIVE
    balance: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    equity: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    available: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    margin_used: Decimal | None = Field(default=None, max_digits=15, decimal_places=2)
    profit_loss: Decimal | None = Field(default=None, max_digits=15, decimal_places=2)
    currency: str = Field(default="USD", max_length=3, nullable=False)
    snapshot_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Position(SQLModel, table=True):
    """
    Open and closed trading positions.
    Links to strategies and signals for performance tracking.
    """

    __tablename__ = "positions"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    deal_id: str = Field(max_length=100, nullable=False, unique=True, index=True)
    deal_reference: str | None = Field(default=None, max_length=100, nullable=True)
    epic: str = Field(max_length=50, nullable=False, index=True)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL
    size: Decimal = Field(max_digits=10, decimal_places=4, nullable=False)
    entry_price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    current_price: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    stop_loss: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    take_profit: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    profit_loss: Decimal | None = Field(default=None, max_digits=15, decimal_places=2)
    status: str = Field(max_length=20, nullable=False, index=True)  # OPEN, CLOSED, CANCELLED
    opened_at: datetime = Field(nullable=False, index=True)
    closed_at: datetime | None = None
    close_reason: str | None = Field(default=None, max_length=50)  # SL, TP, MANUAL, EXPIRED
    strategy_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("strategies.id"), index=True)
    )
    signal_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("signals.id"))
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class Order(SQLModel, table=True):
    """
    Working orders (limit/stop orders not yet filled).
    """

    __tablename__ = "orders"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    deal_id: str = Field(max_length=100, nullable=False, unique=True, index=True)
    epic: str = Field(max_length=50, nullable=False, index=True)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL
    order_type: str = Field(max_length=10, nullable=False)  # LIMIT, STOP
    size: Decimal = Field(max_digits=10, decimal_places=4, nullable=False)
    trigger_price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    stop_loss: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    take_profit: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    status: str = Field(
        max_length=20, nullable=False, index=True
    )  # PENDING, FILLED, CANCELLED, EXPIRED
    good_till_date: datetime | None = None
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None
    strategy_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("strategies.id"))
    )
    signal_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("signals.id"))
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        index=True,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class Trade(SQLModel, table=True):
    """
    Historical trade executions (immutable audit trail).
    Records every trade action: OPEN, CLOSE, MODIFY.
    """

    __tablename__ = "trades"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    position_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("positions.id"), nullable=False, index=True)
    )
    deal_reference: str | None = Field(default=None, max_length=100)
    # 20 chars holds BREAKEVEN / TP1_LOCK / TRAIL_UPD / TP1_HIT trailing
    # transition codes alongside the legacy OPEN / CLOSE / MODIFY.
    trade_type: str = Field(max_length=20, nullable=False)
    epic: str = Field(max_length=50, nullable=False)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL
    size: Decimal = Field(max_digits=10, decimal_places=4, nullable=False)
    price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    profit_loss: Decimal | None = Field(default=None, max_digits=15, decimal_places=2)
    commission: Decimal | None = Field(default=None, max_digits=10, decimal_places=4)
    # Free-form audit note. Used by the trailing-stop manager to record the
    # reason for a phase transition ("TP1 hit at 1973.37 → SL → 1964.40 BE").
    # Surfaced verbatim in the position-detail-drawer History tab tooltip.
    notes: str | None = Field(default=None, max_length=255)
    executed_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Signal(SQLModel, table=True):
    """
    ML model predictions and trading signals.
    Links predictions to models and tracks execution.
    """

    __tablename__ = "signals"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    timeframe: str = Field(max_length=10, nullable=False)  # 1h, 4h, 1d
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL, HOLD
    confidence: Decimal = Field(max_digits=5, decimal_places=4, nullable=False, index=True)
    predicted_price: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    stop_loss_price: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    take_profit_price: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    model_version: str = Field(max_length=50, nullable=False)
    model_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("models.id"))
    )
    features: dict | None = Field(default=None, sa_column=Column(JSONB))
    strategy_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("strategies.id"))
    )
    position_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("positions.id"))
    )
    status: str = Field(
        max_length=20, nullable=False, index=True
    )  # PENDING, EXECUTED, REJECTED, EXPIRED
    generated_at: datetime = Field(nullable=False, index=True)
    expires_at: datetime | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Strategy(SQLModel, table=True):
    """
    Trading strategy configurations.
    Each strategy targets a specific asset/timeframe with ML models.
    """

    __tablename__ = "strategies"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(max_length=100, nullable=False, unique=True, index=True)
    description: str | None = None
    epic: str = Field(max_length=50, nullable=False, index=True)
    timeframe: str = Field(max_length=10, nullable=False)
    is_active: bool = Field(default=False, nullable=False, index=True)
    model_ids: list[int] | None = Field(
        default=None, sa_column=Column(ARRAY(BigInteger))
    )  # Array of model IDs
    parameters: dict = Field(sa_column=Column(JSONB, nullable=False))
    risk_params: dict = Field(sa_column=Column(JSONB, nullable=False))
    performance_metrics: dict | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None


class Model(SQLModel, table=True):
    """
    ML model metadata and versioning.
    Tracks model performance, hyperparameters, and active status.
    """

    __tablename__ = "models"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(max_length=100, nullable=False)  # lstm, transformer, xgboost, ensemble
    version: str = Field(max_length=50, nullable=False)
    epic: str = Field(max_length=50, nullable=False, index=True)
    model_type: str = Field(max_length=50, nullable=False)  # LSTM, TFT, XGBOOST, ENSEMBLE
    file_path: str = Field(max_length=255, nullable=False)
    hyperparameters: dict = Field(sa_column=Column(JSONB, nullable=False))
    training_metrics: dict | None = Field(default=None, sa_column=Column(JSONB))
    validation_metrics: dict | None = Field(default=None, sa_column=Column(JSONB))
    feature_importance: dict | None = Field(default=None, sa_column=Column(JSONB))
    trained_at: datetime = Field(nullable=False, index=True)
    train_start_date: date = Field(nullable=False)
    train_end_date: date = Field(nullable=False)
    is_active: bool = Field(default=False, nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class MarketDataSnapshot(SQLModel, table=True):
    """
    Periodic snapshots of market state.
    Used for regime detection and sentiment analysis.
    Main OHLC data stored in Parquet files.
    """

    __tablename__ = "market_data_snapshots"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    timeframe: str = Field(max_length=10, nullable=False)
    open: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    high: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    low: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    close: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    volume: int | None = Field(default=None, sa_column=Column(BigInteger))
    bid: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    ask: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    spread: Decimal | None = Field(default=None, max_digits=10, decimal_places=4)
    client_sentiment_long: Decimal | None = Field(
        default=None, max_digits=5, decimal_places=2
    )  # % long
    client_sentiment_short: Decimal | None = Field(
        default=None, max_digits=5, decimal_places=2
    )  # % short
    snapshot_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class SystemEvent(SQLModel, table=True):
    """
    System events, errors, warnings for monitoring.
    Centralized logging for debugging and alerts.
    """

    __tablename__ = "system_events"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    event_type: str = Field(
        max_length=50, nullable=False, index=True
    )  # ERROR, WARNING, INFO, TRADE, SIGNAL
    severity: str = Field(max_length=20, nullable=False, index=True)  # CRITICAL, HIGH, MEDIUM, LOW
    component: str = Field(max_length=100, nullable=False, index=True)
    message: str = Field(nullable=False)
    details: dict | None = Field(default=None, sa_column=Column(JSONB))
    related_position_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("positions.id"))
    )
    related_signal_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("signals.id"))
    )
    occurred_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class BacktestRun(SQLModel, table=True):
    """
    Backtest execution metadata and results.
    Tracks strategy performance over historical data.
    """

    __tablename__ = "backtest_runs"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(max_length=200, nullable=False)
    strategy_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("strategies.id"), nullable=False, index=True)
    )
    epic: str = Field(max_length=50, nullable=False)
    start_date: date = Field(nullable=False)
    end_date: date = Field(nullable=False)
    initial_capital: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    final_capital: Decimal | None = Field(default=None, max_digits=15, decimal_places=2)
    total_trades: int | None = None
    winning_trades: int | None = None
    losing_trades: int | None = None
    win_rate: Decimal | None = Field(default=None, max_digits=5, decimal_places=4)
    sharpe_ratio: Decimal | None = Field(default=None, max_digits=10, decimal_places=6)
    sortino_ratio: Decimal | None = Field(default=None, max_digits=10, decimal_places=6)
    max_drawdown: Decimal | None = Field(default=None, max_digits=5, decimal_places=4)
    calmar_ratio: Decimal | None = Field(default=None, max_digits=10, decimal_places=6)
    metrics: dict | None = Field(default=None, sa_column=Column(JSONB))
    parameters: dict | None = Field(default=None, sa_column=Column(JSONB))
    status: str = Field(max_length=20, nullable=False)  # RUNNING, COMPLETED, FAILED
    started_at: datetime = Field(nullable=False, index=True)
    completed_at: datetime | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class TrailingStopState(SQLModel, table=True):
    """
    Persistent state for trailing stops.
    Enables recovery of trailing stop phase and price levels after restart.
    """

    __tablename__ = "trailing_stop_states"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    deal_id: str = Field(max_length=100, nullable=False, unique=True, index=True)
    epic: str = Field(max_length=50, nullable=False)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL

    # Price levels
    entry_price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    current_stop: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    tp1_level: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    tp2_level: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)

    # Tracking state
    phase: int = Field(default=1, nullable=False)  # 1-4
    highest_price: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)
    lowest_price: Decimal | None = Field(default=None, max_digits=15, decimal_places=4)

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class TradeJournalNote(SQLModel, table=True):
    """
    User notes/annotations for trade journal entries (signals).
    Keyed by the signal's natural identifier (epic + timestamp).
    """

    __tablename__ = "trade_journal_notes"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    signal_timestamp: str = Field(max_length=50, nullable=False)
    notes: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class RiskStateSnapshot(SQLModel, table=True):
    """
    Periodic snapshots of RiskManager internal state.
    Enables recovery of risk monitoring state after restart.
    """

    __tablename__ = "risk_state_snapshots"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))

    # DrawdownMonitor state
    peak_equity: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    daily_start_equity: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    current_equity: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)

    # CircuitBreakerManager state
    consecutive_losses: int = Field(default=0, nullable=False)
    tripped_breakers: dict = Field(
        default={}, sa_column=Column(JSONB, nullable=False)
    )  # {epic: timestamp_iso}

    # EquityCurveFilter state
    equity_curve_points: list = Field(
        default=[], sa_column=Column(JSONB, nullable=False)
    )  # Last 50 equity points

    # Metadata
    snapshot_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        index=True,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class MarketSpec(SQLModel, table=True):
    """
    Cached market specifications from Capital.com broker.
    Stores dealing rules (minDealSize, etc.) per asset per environment.
    Survives restarts so the trading loop can validate sizes immediately.
    """

    __tablename__ = "market_specs"
    __table_args__ = (UniqueConstraint("epic", "environment", name="uq_market_spec_epic_env"),)

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    environment: str = Field(max_length=10, nullable=False)  # DEMO | LIVE
    min_deal_size: Decimal = Field(sa_column=Column(Numeric(15, 6), nullable=False))
    min_deal_size_unit: str = Field(default="UNITS", max_length=20, nullable=False)
    max_deal_size: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(15, 6), nullable=True)
    )
    market_name: str | None = Field(default=None, max_length=200, nullable=True)
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Notification(SQLModel, table=True):
    """
    In-app notifications persisted from AlertManager.
    Each alert generates one notification row for the UI notification center.
    """

    __tablename__ = "notifications"

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    alert_type: str = Field(max_length=50, nullable=False, index=True)
    severity: str = Field(max_length=20, nullable=False, index=True)
    title: str = Field(max_length=300, nullable=False)
    message: str = Field(nullable=False)
    epic: str | None = Field(default=None, max_length=50, index=True)
    details: dict | None = Field(default=None, sa_column=Column(JSONB))
    is_read: bool = Field(default=False, nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class PendingCloseDetection(SQLModel, table=True):
    """Persisted state for close-detection reconciliation retries.

    Mirrors the in-memory ``PaperTradingLoop._pending_close_detections``
    dict so the retry counter and ``first_seen`` timestamp survive
    backend restarts. Without this, a pending close whose broker activity
    / transaction is slow to materialize is silently reset to retry 0 /
    first_seen=now on every process restart, and the 10-minute
    reconciliation window never fires — the exact silent failure that
    caused tonight's DE40 TP close to land UNRECONCILED after a restart.

    Rows are created by CloseDetector when a position disappears from the
    broker without an immediate match, and deleted once reconciliation
    succeeds (Tier 1 / Tier 2) or the UNRECONCILED timeout fires (Tier 3).

    See migration ``a910f5d6e7b2`` and plan calm-questing-quail.md.
    """

    __tablename__ = "pending_close_detections"

    deal_id: str = Field(max_length=100, primary_key=True)
    deal_reference: str | None = Field(default=None, max_length=100, nullable=True)
    epic: str = Field(max_length=32, nullable=False, index=True)
    direction: str = Field(max_length=8, nullable=False)
    size: Decimal = Field(max_digits=20, decimal_places=8, nullable=False)
    entry_price: Decimal = Field(max_digits=20, decimal_places=8, nullable=False)
    prev_pos: dict = Field(sa_column=Column(JSONB, nullable=False))
    first_seen: datetime = Field(nullable=False, index=True)
    retry_count: int = Field(default=0, nullable=False)
    last_activity_snapshot: dict | None = Field(default=None, sa_column=Column(JSONB))
    last_transaction_snapshot: dict | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class SwapDailySnapshot(SQLModel, table=True):
    """Daily snapshot of overnight-swap state per epic.

    Captures broker overnightFee long/short rate (pct per interval) and
    aggregate net notional of OPEN positions on the epic at snapshot time,
    by direction. Enables Dashboard v2 /swap-accum to render last N days
    of realized funding exposure from stored rows instead of extrapolating
    today's rate across historical days (Phase 4 MINIMAL).

    Upsert key (epic, snapshot_date) — one row per epic-day.
    """

    __tablename__ = "swap_daily_snapshots"
    __table_args__ = (
        UniqueConstraint("epic", "snapshot_date", name="uq_swap_daily_epic_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    epic: str = Field(max_length=32, nullable=False, index=True)
    snapshot_date: date = Field(nullable=False, index=True)
    long_rate_pct: float | None = Field(default=None, nullable=True)
    short_rate_pct: float | None = Field(default=None, nullable=True)
    currency: str | None = Field(default=None, max_length=8, nullable=True)
    source: str = Field(max_length=16, nullable=False)
    direction: str = Field(max_length=8, nullable=False)
    notional: float = Field(default=0.0, nullable=False)
    swap_realized: float | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class PaperPnlSnapshot(SQLModel, table=True):
    """60s-tick snapshot of the global Paper Trading P&L state.

    Powers the Paper Trading v2 KPI strip (P&L Open / P&L Today
    sparklines) with real history. One row per scheduler tick.
    See migration ``c3d8e9f0a1b2``.
    """

    __tablename__ = "paper_pnl_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    captured_at: datetime = Field(nullable=False, index=True)
    pnl_open: float = Field(default=0.0, nullable=False)
    pnl_today: float = Field(default=0.0, nullable=False)
    equity: float | None = Field(default=None, nullable=True)
    open_count: int = Field(default=0, nullable=False)
    currency: str | None = Field(default=None, max_length=8, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class PositionPnlSnapshot(SQLModel, table=True):
    """60s-tick snapshot of a single open position's P&L.

    Powers the position-card price chart with real history per deal.
    One row per scheduler tick PER open position. Unbounded growth is
    fine because positions live for at most a few days; the rows are
    addressed via ``(deal_id, captured_at)`` and clean up automatically
    once the position is closed and a TTL job prunes old rows.
    See migration ``c3d8e9f0a1b2``.
    """

    __tablename__ = "position_pnl_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    deal_id: str = Field(nullable=False, max_length=64)
    epic: str = Field(nullable=False, max_length=32)
    captured_at: datetime = Field(nullable=False, index=True)
    pnl: float = Field(default=0.0, nullable=False)
    pnl_pct: float = Field(default=0.0, nullable=False)
    current_price: float = Field(default=0.0, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
