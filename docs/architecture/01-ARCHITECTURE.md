# MANTIS AI - System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Angular 21 + CoreUI)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │Dashboard │ │ Charts   │ │ Backtest │ │ Strategy Manager  │  │
│  │Overview  │ │ & Prices │ │ Results  │ │ & Risk Settings   │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │
│                         │ HTTP + WebSocket                      │
└─────────────────────────┼───────────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────────┐
│                    BACKEND API (FastAPI)                         │
│  ┌──────────────────────┼──────────────────────────────────┐    │
│  │              REST API + WebSocket Server                 │    │
│  └──────────────────────┼──────────────────────────────────┘    │
│                         │                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  EVENT BUS (Redis Pub/Sub)               │    │
│  └───┬─────────┬──────────┬──────────┬──────────┬─────────┘    │
│      │         │          │          │          │               │
│  ┌───▼───┐ ┌──▼────┐ ┌───▼───┐ ┌───▼────┐ ┌──▼──────────┐   │
│  │ Data  │ │Feature│ │  ML   │ │Strategy│ │  Execution   │   │
│  │Pipeline│ │Engine │ │Models │ │ Engine │ │   Engine     │   │
│  └───┬───┘ └──┬────┘ └───┬───┘ └───┬────┘ └──┬──────────┘   │
│      │         │          │          │          │               │
│  ┌───▼─────────▼──────────▼──────────▼──────────▼───────────┐  │
│  │              RISK MANAGEMENT LAYER                        │  │
│  │  (Position Sizing | Stop Loss | Drawdown | Correlation)   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │  Backtesting  │  │  Monitoring   │  │  Model Training     │  │
│  │  Engine       │  │  & Alerts     │  │  Pipeline           │  │
│  └──────────────┘  └──────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────────┐
│                  EXTERNAL SERVICES                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │ Capital.com  │  │  FRED API    │  │  News/Sentiment     │   │
│  │ REST + WS    │  │  (Macro Data)│  │  APIs               │   │
│  └──────────────┘  └──────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────────┐
│                    DATA STORAGE                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │ PostgreSQL   │  │   DuckDB     │  │     Redis           │   │
│  │ (Trades,     │  │ (Market Data │  │ (Cache, Real-time   │   │
│  │  Accounts,   │  │  Analytics,  │  │  State, Events,     │   │
│  │  Configs)    │  │  Parquet)    │  │  Session Tokens)    │   │
│  └──────────────┘  └──────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Data Pipeline (`backend/src/data/`)

Responsible for collecting, cleaning, and storing market data.

**Sub-components:**
- `collector.py` - Fetches historical OHLC from Capital.com REST API
- `streamer.py` - Real-time WebSocket price streaming
- `cleaner.py` - Data validation, gap filling, outlier detection
- `storage.py` - Parquet file management + DuckDB interface
- `scheduler.py` - Scheduled data collection tasks (APScheduler)

**Data Flow:**
```
Capital.com API ──> Collector ──> Cleaner ──> Storage (Parquet/DuckDB)
Capital.com WS  ──> Streamer  ──> Redis (real-time) ──> Storage (periodic flush)
FRED API        ──> Collector ──> Storage
News APIs       ──> Collector ──> Storage
```

**Storage Strategy:**
- Historical OHLC: Parquet files partitioned by asset and timeframe
- Real-time ticks: Redis streams with periodic flush to Parquet
- Macro data: DuckDB tables
- Sentiment scores: DuckDB tables

### 2. Feature Engineering (`backend/src/features/`)

Transforms raw data into ML-ready features.

**Sub-components:**
- `technical.py` - Technical indicators (EMA, MACD, RSI, Bollinger, ATR, OBV)
- `sentiment.py` - FinBERT-based sentiment scoring from news feeds
- `macro.py` - Macroeconomic features from FRED (CPI, rates, GDP)
- `regime.py` - Market regime detection (bull/bear/sideways/volatile)
- `builder.py` - Feature pipeline orchestrator

**Feature Categories per Asset:**

| Category | Gold | Bitcoin | S&P 500 |
|----------|------|---------|---------|
| Price OHLCV | Yes | Yes | Yes |
| EMA (8,21,50,200) | Yes | Yes | Yes |
| MACD | Yes | Yes | Yes |
| RSI (14) | Yes | Yes | Yes |
| Bollinger Bands | Yes | Yes | Yes |
| ATR (14) | Yes | Yes | Yes |
| Volume indicators | Yes | Yes | Yes |
| Fed Funds Rate | High | Medium | High |
| CPI/Inflation | High | Medium | Medium |
| USD Index (DXY) | High | Medium | Medium |
| Gold Price | - | High | Low |
| BTC Blockchain metrics | No | High | No |
| News Sentiment | Medium | High | High |
| VIX | Medium | Low | High |

### 3. ML Models (`backend/src/models/`)

XGBoost 3-class classifier with 220 features per asset (21 assets supported).

**Sub-components:**
- `xgboost_model.py` - XGBoost gradient boosting classifier (3-class: BUY/HOLD/SELL)
- `lstm_model.py` - LSTM network (implemented, not in production — F1 ~0.17)
- `trainer.py` - Training pipeline with walk-forward optimization
- `tuner.py` - Optuna hyperparameter tuning (TPE sampler, 40 trials)
- `feature_selector.py` - Feature importance-based selection
- `calibration.py` - Isotonic + Platt confidence calibration, ECE metric
- `predictor.py` - Inference engine for real-time predictions

**Model Architecture (per asset):**
```
Raw OHLCV (1h, 4h, 1d)
         │
    ┌────▼─────────┐
    │   Feature     │
    │  Engineering  │
    │  (220 feats)  │
    └────┬─────────┘
         │
    ┌────▼─────────┐
    │   Optuna      │
    │   Tuning      │
    │  (40 trials)  │
    └────┬─────────┘
         │
    ┌────▼─────────┐
    │   XGBoost     │
    │  3-class      │
    │  Classifier   │
    └────┬─────────┘
         │
    ┌────▼─────────┐
    │  Isotonic     │
    │ Calibration   │
    └────┬─────────┘
         │
    ┌────▼─────────┐
    │   Signal      │
    │  BUY/SELL/    │
    │  HOLD +       │
    │  confidence   │
    └──────────────┘
```

**Training Strategy:**
- Walk-forward optimization with 252-day (1 year) training window
- 63-day (3 months) validation window
- Rolling forward 21 days (1 month) between retrains
- Purged cross-validation to prevent data leakage
- Optuna TPE tuning (40 trials per asset)
- Isotonic confidence calibration per fold
- Models saved with versioning in `data/models/`
- F1 macro: 0.53-0.61 depending on asset

### 4. Strategy Engine (`backend/src/strategy/`)

Converts ML predictions into actionable trading signals.

**Sub-components:**
- `signal_generator.py` - Combines model predictions with rules
- `regime_adapter.py` - Adjusts strategy parameters per market regime
- `portfolio_allocator.py` - Distributes capital across assets
- `strategy_manager.py` - Strategy lifecycle management

**Signal Generation Flow:**
```
ML Prediction (confidence score)
    + Technical Confirmation (RSI, MACD alignment)
    + Regime Filter (appropriate for current regime?)
    + Correlation Check (not over-exposed to correlated assets?)
    = Final Signal (BUY/SELL/HOLD + size + SL/TP levels)
```

### 5. Risk Management (`backend/src/risk/`)

The most critical component. Every trade must pass all risk checks.

**Sub-components:**
- `position_sizer.py` - Volatility-adjusted position sizing (ATR-based)
- `stop_manager.py` - Dynamic stop-loss (ATR-based trailing stops)
- `drawdown_monitor.py` - Account and per-strategy drawdown tracking
- `correlation_checker.py` - Cross-asset exposure management
- `circuit_breaker.py` - Emergency stop conditions

**Risk Rules:**
- Max risk per trade: 1-2% of account equity
- Max total exposure: 10% of account equity
- Max drawdown before halt: 15% account, 8% per strategy
- Trailing stop: 2x ATR for swing trades
- Circuit breaker: halt all trading if daily loss > 5%
- Correlation guard: reduce size if Gold+BTC positions align (they correlate)

### 6. Execution Engine (`backend/src/execution/`)

Manages order lifecycle with Capital.com API.

**Sub-components:**
- `order_manager.py` - Order creation, modification, cancellation
- `position_tracker.py` - Open position monitoring
- `fill_handler.py` - Trade confirmation processing
- `slippage_model.py` - Expected vs actual fill price tracking

### 7. Backtesting Engine (`backend/src/backtest/`)

Validates strategies on historical data before live deployment.

**Sub-components:**
- `engine.py` - Core backtesting loop (event-driven)
- `walk_forward.py` - Walk-forward optimization framework
- `metrics.py` - Performance metrics (Sharpe, Sortino, max drawdown, etc.)
- `reporter.py` - HTML/JSON report generation

### 7b. Trading Services (`backend/src/trading/`)

Trading loop and supporting services.

**Sub-components:**

- `paper_loop.py` - Paper/demo trading loop with iteration-based signal processing
- `market_spec_prefetch.py` - Pre-fetches minDealSize for all 21 assets at startup (batch parallel with DB persistence)

**MinDealSize Validation Flow:**

```text
Startup: DB load (instant) → Background broker fetch (3s) → seed_min_deal_sizes()
Per-trade: market_info_cache → min_deal_size_cache → None (broker will reject)
```

### 8. Monitoring (`backend/src/monitoring/`)

Real-time system health and performance tracking.

**Sub-components:**
- `health_checker.py` - System component health monitoring
- `pnl_tracker.py` - Real-time P&L calculation
- `trade_logger.py` - Structured trade event logging (signals, executions, risk)
- `log_analyzer.py` - Polars-based log analysis (signal accuracy, execution quality)
- `log_formatter.py` - JSON structured log formatting
- `metrics.py` - Performance metrics collection
- `alerting/` - Alert rules and notification system

### 9. Authentication & Security

**`backend/src/auth/`** - JWT-based authentication with RBAC:
- `models.py` - User, Role, Permission SQLAlchemy models
- `schemas.py` - Pydantic schemas (UserCreate, UserResponse, TokenResponse)
- `rbac.py` - Role-Based Access Control (VIEWER, TRADER, ADMIN roles)
- `jwt.py` - JWT token creation/validation (access + refresh tokens)

**`backend/src/security/`** - Security hardening:
- Input sanitization, rate limiting, CORS configuration
- JWT secret validation (fails startup if default key in production)

**`backend/src/audit/`** - Audit trail:
- System event logging for compliance

### 10. Backend API (`backend/src/api/`)

FastAPI server exposing REST + WebSocket for the frontend.

**Middleware:** GZipMiddleware (min 1000 bytes), CORS, rate limiting (slowapi)

**Key Endpoints:**
- `GET /api/dashboard` - Overview data (P&L, positions, signals)
- `GET /api/positions` - Current open positions
- `GET /api/positions/closed` - Closed positions history (paginated, filtered)
- `GET /api/trading/performance` - Trading performance stats (win rate, P&L by asset)
- `GET /api/signals` - Active trading signals
- `POST /api/backtest/run` - Run walk-forward backtest
- `POST /api/strategy/activate` - Enable/disable strategies
- `POST /api/trading/start|stop` - Paper trading control
- `GET /api/system/health` - Health check (data freshness, broker, DB)
- `GET /api/system/recovery-report` - State recovery status
- `POST /api/auth/login|register` - Authentication (rate-limited)
- `POST /api/auth/avatar/upload` - Avatar image upload
- `WS /ws/prices` - Real-time price streaming
- `WS /ws/trades` - Real-time trade updates

### 11. Frontend Dashboard (Angular 21 + CoreUI)

**MANTIS AI Theme:** Neon green `#39FF14`, dark bg `#0d1117`, surface `#161b22`

**Pages:**
- **Dashboard** - Full-width equity curve, 8-asset price grid, risk metric cards
- **Markets** - Real-time charts for 21 assets with TradingView Lightweight Charts
- **Signals** - ML signal history with confidence scores
- **Positions** - Open + closed positions (tab view), live P&L, history with filters
- **Paper Trading** - Start/stop trading, live signal monitor
- **Trade Journal** - Full signal history with filters and stats
- **Backtest** - Walk-forward backtest runner with equity curves
- **Strategy** - Strategy and risk configuration
- **Models** - ML model performance monitoring
- **Settings** - App settings, broker configuration
- **Login/Register** - Glassmorphism split-screen with animated gradients
- **User Profile** - Avatar upload, account info, permissions

### State Recovery System

**Purpose**: Restore trading state after backend restart (crash, deployment, maintenance)

**Components**:

- `StateRecoveryService` - Main orchestrator for state recovery
- `TrailingStopRepository` - Persist trailing stop phases and levels
- `RiskStateRepository` - Persist DrawdownMonitor, CircuitBreakers, EquityCurveFilter
- `TradeRepository.get_recent_for_kelly()` - Load trade history for Kelly sizing

**Recovery Flow (DEMO/LIVE mode)**:

1. Try Broker API → positions + equity
2. If broker fails → Try PostgreSQL
3. If both fail → Empty state + CRITICAL ERROR + circuit breaker trip

**Recovery Flow (PAPER mode)**:

1. Try PostgreSQL → positions + trailing stops + risk state
2. If DB fails → Empty state + WARNING

**Auto-Persistence Hooks**:

- After each trading iteration: Save risk state
- After position open: Save trailing stop state + persist position to DB
- After trailing stop update: Save updated state
- After position close: Persist position close to DB + save final risk state

**Monitoring**: `GET /api/system/recovery-report` endpoint provides recovery status and warnings

## Communication Patterns

### Event Types (Redis Pub/Sub)
```
EVENTS:
  market.tick.{asset}      - New price tick received
  market.ohlc.{asset}      - New OHLC bar completed
  signal.generated.{asset} - New trading signal
  order.placed.{id}        - Order sent to broker
  order.filled.{id}        - Order confirmed by broker
  position.opened.{id}     - New position opened
  position.closed.{id}     - Position closed
  risk.alert.{type}        - Risk threshold breached
  risk.circuit_breaker     - Emergency stop triggered
  model.prediction.{asset} - New ML prediction available
  system.health.{component}- Component health status
```

## Deployment Architecture

```
Docker Compose (Development)
├── backend      (FastAPI + all Python services)
├── frontend     (Angular dev server / nginx in prod)
├── postgres     (Trade/account data)
├── redis        (Cache, events, real-time state)
└── duckdb       (Embedded, runs within backend container)
```

## Security Considerations

- API keys stored in `.env` files, never in code
- Capital.com session tokens auto-refreshed before 10min expiry
- Frontend-to-backend auth via JWT tokens
- Rate limiting on all API endpoints
- Input validation on all user-facing endpoints (Pydantic)
- WebSocket connections authenticated on handshake
