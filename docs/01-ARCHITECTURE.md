# AlgoTrader AI - System Architecture

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

Ensemble approach with asset-specific model configurations.

**Sub-components:**
- `lstm_model.py` - LSTM network for temporal patterns
- `transformer_model.py` - Temporal Fusion Transformer (TFT)
- `xgboost_model.py` - XGBoost/LightGBM gradient boosting
- `ensemble.py` - Stacking meta-learner
- `trainer.py` - Training pipeline with walk-forward optimization
- `predictor.py` - Inference engine for real-time predictions

**Model Architecture (per asset):**
```
                    ┌─────────────┐
Raw Features ──────>│   Feature   │
                    │  Selection  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼────┐ ┌────▼────┐ ┌────▼─────┐
         │  LSTM   │ │Transformer│ │ XGBoost  │
         │ (seq)   │ │  (TFT)   │ │(tabular) │
         └────┬────┘ └────┬─────┘ └────┬─────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼──────┐
                    │   Stacking  │
                    │ Meta-Learner│
                    │  (XGBoost)  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Signal    │
                    │  (BUY/SELL/ │
                    │   HOLD +    │
                    │ confidence) │
                    └─────────────┘
```

**Training Strategy:**
- Walk-forward optimization with 252-day (1 year) training window
- 63-day (3 months) validation window
- Rolling forward 21 days (1 month) between retrains
- Purged cross-validation to prevent data leakage
- Models saved with versioning in `data/models/`

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

### 8. Monitoring (`backend/src/monitoring/`)

Real-time system health and performance tracking.

**Sub-components:**
- `health_checker.py` - System component health monitoring
- `pnl_tracker.py` - Real-time P&L calculation
- `model_monitor.py` - ML model drift detection
- `alerter.py` - Alert system (email, webhook notifications)

### 9. Backend API (`backend/src/api/`)

FastAPI server exposing REST + WebSocket for the frontend.

**Key Endpoints:**
- `GET /api/dashboard` - Overview data (P&L, positions, signals)
- `GET /api/positions` - Current open positions
- `GET /api/signals` - Active trading signals
- `GET /api/backtest/{id}` - Backtest results
- `POST /api/strategy/activate` - Enable/disable strategies
- `WS /ws/prices` - Real-time price streaming
- `WS /ws/trades` - Real-time trade updates

### 10. Frontend Dashboard (Angular 21 + CoreUI)

**Pages:**
- **Dashboard** - P&L overview, equity curve, active positions, recent trades
- **Markets** - Real-time charts for Gold, BTC, S&P 500 with indicators
- **Signals** - Current ML signals with confidence scores and reasoning
- **Positions** - Open positions manager with SL/TP visualization
- **Backtest** - Run and review backtests, compare strategies
- **Strategy** - Configure strategy parameters, risk settings
- **Models** - ML model performance, training history, drift alerts
- **Settings** - Broker connection, API keys, notification preferences

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
