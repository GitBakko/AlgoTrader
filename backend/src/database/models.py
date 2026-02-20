"""
SQLModel ORM models for AlgoTrader AI PostgreSQL database.
Based on schema design in schema_design.md.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import ARRAY, BigInteger, Column, ForeignKey, MetaData, Numeric, String, UniqueConstraint, text
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

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    account_id: str = Field(max_length=100, nullable=False, index=True)
    account_type: str = Field(max_length=50, nullable=False)  # DEMO, LIVE
    balance: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    equity: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    available: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    margin_used: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=2)
    profit_loss: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=2)
    currency: str = Field(default="USD", max_length=3, nullable=False)
    snapshot_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Position(SQLModel, table=True):
    """
    Open and closed trading positions.
    Links to strategies and signals for performance tracking.
    """

    __tablename__ = "positions"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    deal_id: str = Field(max_length=100, nullable=False, unique=True, index=True)
    epic: str = Field(max_length=50, nullable=False, index=True)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL
    size: Decimal = Field(max_digits=10, decimal_places=4, nullable=False)
    entry_price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    current_price: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    stop_loss: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    take_profit: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    profit_loss: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=2)
    status: str = Field(max_length=20, nullable=False, index=True)  # OPEN, CLOSED, CANCELLED
    opened_at: datetime = Field(nullable=False, index=True)
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = Field(default=None, max_length=50)  # SL, TP, MANUAL, EXPIRED
    strategy_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("strategies.id"), index=True)
    )
    signal_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("signals.id"))
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class Order(SQLModel, table=True):
    """
    Working orders (limit/stop orders not yet filled).
    """

    __tablename__ = "orders"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    deal_id: str = Field(max_length=100, nullable=False, unique=True, index=True)
    epic: str = Field(max_length=50, nullable=False, index=True)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL
    order_type: str = Field(max_length=10, nullable=False)  # LIMIT, STOP
    size: Decimal = Field(max_digits=10, decimal_places=4, nullable=False)
    trigger_price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    stop_loss: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    take_profit: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    status: str = Field(
        max_length=20, nullable=False, index=True
    )  # PENDING, FILLED, CANCELLED, EXPIRED
    good_till_date: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    strategy_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("strategies.id"))
    )
    signal_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("signals.id"))
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        index=True,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class Trade(SQLModel, table=True):
    """
    Historical trade executions (immutable audit trail).
    Records every trade action: OPEN, CLOSE, MODIFY.
    """

    __tablename__ = "trades"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    position_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("positions.id"), nullable=False, index=True)
    )
    deal_reference: Optional[str] = Field(default=None, max_length=100)
    trade_type: str = Field(max_length=10, nullable=False)  # OPEN, CLOSE, MODIFY
    epic: str = Field(max_length=50, nullable=False)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL
    size: Decimal = Field(max_digits=10, decimal_places=4, nullable=False)
    price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    profit_loss: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=2)
    commission: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=4)
    executed_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Signal(SQLModel, table=True):
    """
    ML model predictions and trading signals.
    Links predictions to models and tracks execution.
    """

    __tablename__ = "signals"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    timeframe: str = Field(max_length=10, nullable=False)  # 1h, 4h, 1d
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL, HOLD
    confidence: Decimal = Field(max_digits=5, decimal_places=4, nullable=False, index=True)
    predicted_price: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    stop_loss_price: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    take_profit_price: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    model_version: str = Field(max_length=50, nullable=False)
    model_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("models.id"))
    )
    features: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    strategy_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("strategies.id"))
    )
    position_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("positions.id"))
    )
    status: str = Field(
        max_length=20, nullable=False, index=True
    )  # PENDING, EXECUTED, REJECTED, EXPIRED
    generated_at: datetime = Field(nullable=False, index=True)
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Strategy(SQLModel, table=True):
    """
    Trading strategy configurations.
    Each strategy targets a specific asset/timeframe with ML models.
    """

    __tablename__ = "strategies"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(max_length=100, nullable=False, unique=True, index=True)
    description: Optional[str] = None
    epic: str = Field(max_length=50, nullable=False, index=True)
    timeframe: str = Field(max_length=10, nullable=False)
    is_active: bool = Field(default=False, nullable=False, index=True)
    model_ids: Optional[list[int]] = Field(
        default=None, sa_column=Column(ARRAY(BigInteger))
    )  # Array of model IDs
    parameters: dict = Field(sa_column=Column(JSONB, nullable=False))
    risk_params: dict = Field(sa_column=Column(JSONB, nullable=False))
    performance_metrics: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )
    activated_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None


class Model(SQLModel, table=True):
    """
    ML model metadata and versioning.
    Tracks model performance, hyperparameters, and active status.
    """

    __tablename__ = "models"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(max_length=100, nullable=False)  # lstm, transformer, xgboost, ensemble
    version: str = Field(max_length=50, nullable=False)
    epic: str = Field(max_length=50, nullable=False, index=True)
    model_type: str = Field(max_length=50, nullable=False)  # LSTM, TFT, XGBOOST, ENSEMBLE
    file_path: str = Field(max_length=255, nullable=False)
    hyperparameters: dict = Field(sa_column=Column(JSONB, nullable=False))
    training_metrics: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    validation_metrics: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    feature_importance: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    trained_at: datetime = Field(nullable=False, index=True)
    train_start_date: date = Field(nullable=False)
    train_end_date: date = Field(nullable=False)
    is_active: bool = Field(default=False, nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    timeframe: str = Field(max_length=10, nullable=False)
    open: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    high: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    low: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    close: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    volume: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    bid: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    ask: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    spread: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=4)
    client_sentiment_long: Optional[Decimal] = Field(
        default=None, max_digits=5, decimal_places=2
    )  # % long
    client_sentiment_short: Optional[Decimal] = Field(
        default=None, max_digits=5, decimal_places=2
    )  # % short
    snapshot_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class SystemEvent(SQLModel, table=True):
    """
    System events, errors, warnings for monitoring.
    Centralized logging for debugging and alerts.
    """

    __tablename__ = "system_events"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    event_type: str = Field(
        max_length=50, nullable=False, index=True
    )  # ERROR, WARNING, INFO, TRADE, SIGNAL
    severity: str = Field(max_length=20, nullable=False, index=True)  # CRITICAL, HIGH, MEDIUM, LOW
    component: str = Field(max_length=100, nullable=False, index=True)
    message: str = Field(nullable=False)
    details: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    related_position_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("positions.id"))
    )
    related_signal_id: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("signals.id"))
    )
    occurred_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class BacktestRun(SQLModel, table=True):
    """
    Backtest execution metadata and results.
    Tracks strategy performance over historical data.
    """

    __tablename__ = "backtest_runs"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    name: str = Field(max_length=200, nullable=False)
    strategy_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("strategies.id"), nullable=False, index=True)
    )
    epic: str = Field(max_length=50, nullable=False)
    start_date: date = Field(nullable=False)
    end_date: date = Field(nullable=False)
    initial_capital: Decimal = Field(max_digits=15, decimal_places=2, nullable=False)
    final_capital: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=2)
    total_trades: Optional[int] = None
    winning_trades: Optional[int] = None
    losing_trades: Optional[int] = None
    win_rate: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=4)
    sharpe_ratio: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=6)
    sortino_ratio: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=6)
    max_drawdown: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=4)
    calmar_ratio: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=6)
    metrics: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    parameters: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    status: str = Field(max_length=20, nullable=False)  # RUNNING, COMPLETED, FAILED
    started_at: datetime = Field(nullable=False, index=True)
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class TrailingStopState(SQLModel, table=True):
    """
    Persistent state for trailing stops.
    Enables recovery of trailing stop phase and price levels after restart.
    """

    __tablename__ = "trailing_stop_states"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    deal_id: str = Field(max_length=100, nullable=False, unique=True, index=True)
    epic: str = Field(max_length=50, nullable=False)
    direction: str = Field(max_length=4, nullable=False)  # BUY, SELL

    # Price levels
    entry_price: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    current_stop: Decimal = Field(max_digits=15, decimal_places=4, nullable=False)
    tp1_level: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    tp2_level: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)

    # Tracking state
    phase: int = Field(default=1, nullable=False)  # 1-4
    highest_price: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)
    lowest_price: Optional[Decimal] = Field(default=None, max_digits=15, decimal_places=4)

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class TradeJournalNote(SQLModel, table=True):
    """
    User notes/annotations for trade journal entries (signals).
    Keyed by the signal's natural identifier (epic + timestamp).
    """

    __tablename__ = "trade_journal_notes"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    signal_timestamp: str = Field(max_length=50, nullable=False)
    notes: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()"), "onupdate": text("NOW()")},
    )


class RiskStateSnapshot(SQLModel, table=True):
    """
    Periodic snapshots of RiskManager internal state.
    Enables recovery of risk monitoring state after restart.
    """

    __tablename__ = "risk_state_snapshots"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))

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
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
    __table_args__ = (
        UniqueConstraint("epic", "environment", name="uq_market_spec_epic_env"),
    )

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    epic: str = Field(max_length=50, nullable=False, index=True)
    environment: str = Field(max_length=10, nullable=False)  # DEMO | LIVE
    min_deal_size: Decimal = Field(sa_column=Column(Numeric(15, 6), nullable=False))
    min_deal_size_unit: str = Field(default="UNITS", max_length=20, nullable=False)
    max_deal_size: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(15, 6), nullable=True)
    )
    market_name: Optional[str] = Field(default=None, max_length=200, nullable=True)
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class Notification(SQLModel, table=True):
    """
    In-app notifications persisted from AlertManager.
    Each alert generates one notification row for the UI notification center.
    """

    __tablename__ = "notifications"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    alert_type: str = Field(max_length=50, nullable=False, index=True)
    severity: str = Field(max_length=20, nullable=False, index=True)
    title: str = Field(max_length=300, nullable=False)
    message: str = Field(nullable=False)
    epic: Optional[str] = Field(default=None, max_length=50, index=True)
    details: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    is_read: bool = Field(default=False, nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
