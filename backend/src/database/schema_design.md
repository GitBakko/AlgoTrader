# AlgoTrader AI - Database Schema Design

## Overview

PostgreSQL database schema for AlgoTrader AI trading system.

**Naming Conventions**:
- Tables: `snake_case`, plural (e.g., `positions`, `trades`)
- Primary keys: `id` (BigInt, auto-increment)
- Foreign keys: `{table}_id` (e.g., `position_id`, `strategy_id`)
- Timestamps: `created_at`, `updated_at` (auto-managed)
- Soft deletes: `deleted_at` (nullable)

---

## Tables

### 1. `accounts`
Tracks Capital.com account state over time.

```sql
CREATE TABLE accounts (
    id BIGSERIAL PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL,  -- Capital.com account ID
    account_type VARCHAR(50) NOT NULL, -- DEMO, LIVE
    balance DECIMAL(15, 2) NOT NULL,
    equity DECIMAL(15, 2) NOT NULL,
    available DECIMAL(15, 2) NOT NULL,
    margin_used DECIMAL(15, 2),
    profit_loss DECIMAL(15, 2),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    snapshot_at TIMESTAMP NOT NULL,    -- When this snapshot was taken
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_accounts_snapshot_at (snapshot_at DESC),
    INDEX idx_accounts_account_id (account_id)
);
```

**Purpose**: Historical tracking of account balance/equity for P&L analysis.

---

### 2. `positions`
Open and closed trading positions.

```sql
CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    deal_id VARCHAR(100) UNIQUE NOT NULL,     -- Capital.com deal ID
    epic VARCHAR(50) NOT NULL,                -- GOLD, BTCUSD, US500
    direction VARCHAR(4) NOT NULL,            -- BUY, SELL
    size DECIMAL(10, 4) NOT NULL,
    entry_price DECIMAL(15, 4) NOT NULL,
    current_price DECIMAL(15, 4),
    stop_loss DECIMAL(15, 4),
    take_profit DECIMAL(15, 4),
    profit_loss DECIMAL(15, 2),
    status VARCHAR(20) NOT NULL,              -- OPEN, CLOSED, CANCELLED
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    close_reason VARCHAR(50),                 -- SL, TP, MANUAL, EXPIRED
    strategy_id BIGINT,                       -- Link to strategy
    signal_id BIGINT,                         -- Link to ML signal
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_positions_deal_id (deal_id),
    INDEX idx_positions_epic (epic),
    INDEX idx_positions_status (status),
    INDEX idx_positions_opened_at (opened_at DESC),
    INDEX idx_positions_strategy_id (strategy_id)
);
```

**Purpose**: Track all positions with P&L, entry/exit, SL/TP.

---

### 3. `orders`
Working orders (limit/stop orders not yet filled).

```sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    deal_id VARCHAR(100) UNIQUE NOT NULL,
    epic VARCHAR(50) NOT NULL,
    direction VARCHAR(4) NOT NULL,
    order_type VARCHAR(10) NOT NULL,          -- LIMIT, STOP
    size DECIMAL(10, 4) NOT NULL,
    trigger_price DECIMAL(15, 4) NOT NULL,
    stop_loss DECIMAL(15, 4),
    take_profit DECIMAL(15, 4),
    status VARCHAR(20) NOT NULL,              -- PENDING, FILLED, CANCELLED, EXPIRED
    good_till_date TIMESTAMP,
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    strategy_id BIGINT,
    signal_id BIGINT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_orders_deal_id (deal_id),
    INDEX idx_orders_epic (epic),
    INDEX idx_orders_status (status),
    INDEX idx_orders_created_at (created_at DESC)
);
```

**Purpose**: Track pending orders before they become positions.

---

### 4. `trades`
Historical trade executions (audit trail).

```sql
CREATE TABLE trades (
    id BIGSERIAL PRIMARY KEY,
    position_id BIGINT NOT NULL,
    deal_reference VARCHAR(100),
    trade_type VARCHAR(10) NOT NULL,          -- OPEN, CLOSE, MODIFY
    epic VARCHAR(50) NOT NULL,
    direction VARCHAR(4) NOT NULL,
    size DECIMAL(10, 4) NOT NULL,
    price DECIMAL(15, 4) NOT NULL,
    profit_loss DECIMAL(15, 2),
    commission DECIMAL(10, 4),
    executed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
    INDEX idx_trades_position_id (position_id),
    INDEX idx_trades_executed_at (executed_at DESC)
);
```

**Purpose**: Immutable audit trail of all trade executions.

---

### 5. `signals`
ML model predictions and trading signals.

```sql
CREATE TABLE signals (
    id BIGSERIAL PRIMARY KEY,
    epic VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,           -- 1h, 4h, 1d
    direction VARCHAR(4) NOT NULL,            -- BUY, SELL, HOLD
    confidence DECIMAL(5, 4) NOT NULL,        -- 0.0000 to 1.0000
    predicted_price DECIMAL(15, 4),
    stop_loss_price DECIMAL(15, 4),
    take_profit_price DECIMAL(15, 4),
    model_version VARCHAR(50) NOT NULL,       -- e.g., "lstm-v1.2.3"
    model_id BIGINT,
    features JSONB,                           -- Feature values used for prediction
    strategy_id BIGINT,
    position_id BIGINT,                       -- If signal resulted in position
    status VARCHAR(20) NOT NULL,              -- PENDING, EXECUTED, REJECTED, EXPIRED
    generated_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE SET NULL,
    INDEX idx_signals_epic (epic),
    INDEX idx_signals_status (status),
    INDEX idx_signals_generated_at (generated_at DESC),
    INDEX idx_signals_confidence (confidence DESC)
);
```

**Purpose**: Store all ML signals for backtesting analysis and tracking.

---

### 6. `strategies`
Trading strategy configurations.

```sql
CREATE TABLE strategies (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    epic VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    model_ids BIGINT[],                       -- Array of model IDs used
    parameters JSONB NOT NULL,                -- Strategy parameters
    risk_params JSONB NOT NULL,               -- Risk management params
    performance_metrics JSONB,                -- Sharpe, Sortino, Win Rate, etc.
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMP,
    deactivated_at TIMESTAMP,

    INDEX idx_strategies_name (name),
    INDEX idx_strategies_epic (epic),
    INDEX idx_strategies_is_active (is_active)
);
```

**Purpose**: Manage multiple trading strategies with different configs.

---

### 7. `models`
ML model metadata and versioning.

```sql
CREATE TABLE models (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,               -- lstm, transformer, xgboost, ensemble
    version VARCHAR(50) NOT NULL,             -- Semantic version
    epic VARCHAR(50) NOT NULL,
    model_type VARCHAR(50) NOT NULL,          -- LSTM, TFT, XGBOOST, ENSEMBLE
    file_path VARCHAR(255) NOT NULL,          -- Path to model weights
    hyperparameters JSONB NOT NULL,
    training_metrics JSONB,                   -- Accuracy, F1, etc.
    validation_metrics JSONB,
    feature_importance JSONB,
    trained_at TIMESTAMP NOT NULL,
    train_start_date DATE NOT NULL,
    train_end_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (name, version, epic),
    INDEX idx_models_epic (epic),
    INDEX idx_models_is_active (is_active),
    INDEX idx_models_trained_at (trained_at DESC)
);
```

**Purpose**: Track ML model versions, performance, and active models.

---

### 8. `market_data_snapshots`
Periodic snapshots of market state (for regime detection, sentiment).

```sql
CREATE TABLE market_data_snapshots (
    id BIGSERIAL PRIMARY KEY,
    epic VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open DECIMAL(15, 4) NOT NULL,
    high DECIMAL(15, 4) NOT NULL,
    low DECIMAL(15, 4) NOT NULL,
    close DECIMAL(15, 4) NOT NULL,
    volume BIGINT,
    bid DECIMAL(15, 4),
    ask DECIMAL(15, 4),
    spread DECIMAL(10, 4),
    client_sentiment_long DECIMAL(5, 2),      -- % long positions
    client_sentiment_short DECIMAL(5, 2),     -- % short positions
    snapshot_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_snapshots_epic_time (epic, snapshot_at DESC),
    INDEX idx_snapshots_snapshot_at (snapshot_at DESC)
);
```

**Purpose**: Store periodic market snapshots for analysis (not full OHLC data, which is in Parquet).

---

### 9. `system_events`
System events, errors, warnings for monitoring.

```sql
CREATE TABLE system_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,          -- ERROR, WARNING, INFO, TRADE, SIGNAL
    severity VARCHAR(20) NOT NULL,            -- CRITICAL, HIGH, MEDIUM, LOW
    component VARCHAR(100) NOT NULL,          -- broker, ml_engine, risk_manager, etc.
    message TEXT NOT NULL,
    details JSONB,                            -- Additional context
    related_position_id BIGINT,
    related_signal_id BIGINT,
    occurred_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_events_event_type (event_type),
    INDEX idx_events_severity (severity),
    INDEX idx_events_occurred_at (occurred_at DESC),
    INDEX idx_events_component (component)
);
```

**Purpose**: Centralized logging for system events and debugging.

---

### 10. `backtest_runs`
Backtest execution metadata.

```sql
CREATE TABLE backtest_runs (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    strategy_id BIGINT NOT NULL,
    epic VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(15, 2) NOT NULL,
    final_capital DECIMAL(15, 2),
    total_trades INT,
    winning_trades INT,
    losing_trades INT,
    win_rate DECIMAL(5, 4),
    sharpe_ratio DECIMAL(10, 6),
    sortino_ratio DECIMAL(10, 6),
    max_drawdown DECIMAL(5, 4),
    calmar_ratio DECIMAL(10, 6),
    metrics JSONB,                            -- Full metrics JSON
    parameters JSONB,                         -- Strategy params used
    status VARCHAR(20) NOT NULL,              -- RUNNING, COMPLETED, FAILED
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    INDEX idx_backtest_runs_strategy_id (strategy_id),
    INDEX idx_backtest_runs_started_at (started_at DESC)
);
```

**Purpose**: Store backtest results for strategy evaluation.

---

### 11. `trailing_stop_states` (Phase 14)

Trailing stop manager state for position recovery.

```sql
CREATE TABLE trailing_stop_states (
    id BIGSERIAL PRIMARY KEY,
    deal_id VARCHAR(100) UNIQUE NOT NULL,     -- Position identifier
    epic VARCHAR(50) NOT NULL,                -- Asset symbol
    direction VARCHAR(10) NOT NULL,           -- BUY, SELL
    entry_price DECIMAL(20, 5) NOT NULL,
    current_stop DECIMAL(20, 5) NOT NULL,
    phase INTEGER NOT NULL,                   -- Trailing stop phase (1-4)
    tp1_level DECIMAL(20, 5),                 -- First take profit level
    tp2_level DECIMAL(20, 5),                 -- Second take profit level
    highest_price DECIMAL(20, 5),             -- Highest price reached (longs)
    lowest_price DECIMAL(20, 5),              -- Lowest price reached (shorts)
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_trailing_stop_states_deal_id (deal_id)
);
```

**Purpose**: Persist trailing stop state for recovery after backend restart.

---

### 12. `risk_state_snapshots` (Phase 14)

Risk manager internal state snapshots.

```sql
CREATE TABLE risk_state_snapshots (
    id BIGSERIAL PRIMARY KEY,
    peak_equity DECIMAL(20, 2) NOT NULL,
    daily_start_equity DECIMAL(20, 2) NOT NULL,
    current_equity DECIMAL(20, 2) NOT NULL,
    consecutive_losses INTEGER DEFAULT 0,
    tripped_breakers JSONB DEFAULT '{}',       -- {epic: iso_timestamp}
    equity_curve_points JSONB DEFAULT '[]',    -- Last 50 equity points
    snapshot_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_risk_state_snapshots_snapshot_at (snapshot_at DESC)
);
```

**Purpose**: Persist risk manager state (DrawdownMonitor, CircuitBreakers, EquityCurveFilter) for recovery.

---

## Relationships

```
strategies (1) ──> (N) positions
strategies (1) ──> (N) signals
strategies (1) ──> (N) orders
strategies (1) ──> (N) backtest_runs

signals (1) ──> (0..1) positions

positions (1) ──> (N) trades

models (N) ──<──> (N) strategies  (via model_ids array)
```

---

## Indexes Summary

**Critical indexes for performance**:
- `positions.deal_id` (unique lookups)
- `positions.status` (filtering open positions)
- `signals.generated_at DESC` (recent signals)
- `trades.executed_at DESC` (recent trades)
- `system_events.occurred_at DESC` (monitoring)
- All timestamp fields with DESC for time-series queries

---

## Data Retention

| Table | Retention Policy |
|-------|------------------|
| `accounts` | Keep all (for P&L history) |
| `positions` | Keep all |
| `orders` | Keep all |
| `trades` | Keep all (audit trail) |
| `signals` | Archive after 1 year |
| `market_data_snapshots` | Archive after 6 months (main data in Parquet) |
| `system_events` | Archive after 90 days |
| `backtest_runs` | Keep all (metadata only) |

---

## Migration Strategy

1. **Initial migration**: Create all tables
2. **Seed data**: Insert default strategy configs
3. **Future migrations**: Use Alembic for schema changes

---

_Last updated: 2026-02-10_
