# AlgoTrader AI - Development Roadmap

## Phase Overview

| Phase | Name | Duration | Focus | Status |
|-------|------|----------|-------|--------|
| 1 | Foundation | 2-3 weeks | Project setup, data pipeline, broker connection | COMPLETE |
| 2 | Intelligence | 3-4 weeks | Feature engineering, ML models, backtesting | MVP COMPLETE |
| 3 | Trading Engine | 2-3 weeks | Strategy, risk management, execution | COMPLETE |
| 4 | Dashboard | 2-3 weeks | Angular frontend, real-time visualization | COMPLETE |
| 5 | Integration & Wiring | 2 weeks | End-to-end wiring, paper trading pipeline | COMPLETE |
| 6 | Optimization & Live | Ongoing | Performance tuning, live deployment | NEXT |

---

## Phase 1: Foundation [COMPLETE]

### 1.1 Project Setup [COMPLETE]
- [x] Initialize Python project with Poetry
- [x] Configure pyproject.toml with all dependencies
- [x] Setup pre-commit hooks (black, ruff, mypy)
- [x] Create .env.example with all required environment variables
- [x] Setup Docker Compose (backend, postgres, redis)
- [x] Initialize git repository with .gitignore
- [x] Create base FastAPI application with health endpoint

### 1.2 Capital.com Broker Integration [COMPLETE]
- [x] Implement session manager (auth, token refresh, keep-alive)
- [x] Implement encrypted password authentication (AES)
- [x] Build market data client (search, prices, OHLC history)
- [x] Build WebSocket streaming client (quotes, OHLC real-time)
- [x] Build order management client (positions, working orders)
- [x] Build account client (balance, history, preferences)
- [x] Handle rate limiting (10 req/sec) with token bucket
- [x] Implement automatic reconnection for WebSocket
- [x] Write comprehensive tests with mocked API responses (100 tests)
- [ ] Verify demo account connectivity with all 3 assets

### 1.3 Data Pipeline [COMPLETE]
- [x] Design Parquet storage schema for OHLC data
- [x] Implement historical data downloader (batch with pagination)
- [ ] Download initial historical data: Gold, BTC, S&P500 (all timeframes)
- [x] Implement real-time data streamer (WebSocket -> Redis -> Parquet)
- [x] Setup DuckDB for analytical queries on Parquet files
- [x] Implement data quality checks (gaps, outliers, consistency)
- [x] Setup APScheduler for scheduled data collection
- [x] Create data access layer (unified interface for historical + real-time)

### 1.4 Database Setup [COMPLETE]
- [x] Design PostgreSQL schema (trades, positions, signals, config)
- [x] Setup Alembic migrations
- [x] Create SQLAlchemy/SQLModel ORM models
- [x] Implement repository pattern for data access

---

## Phase 2: Intelligence [MVP COMPLETE]

### 2.1 Feature Engineering [COMPLETE]

- [x] Implement technical indicators module (EMA, MACD, RSI, BB, ATR, ADX, OBV) - pure Polars/numpy
- [x] Create feature builder pipeline (raw data -> feature matrix)
- [ ] Implement FRED API client for macro data (CPI, rates, GDP, DXY, VIX) → Phase 2B
- [ ] Implement sentiment analysis with FinBERT (news headlines) → Phase 2B
- [x] Build market regime detector (rule-based: ADX + EMA slope)
- [x] Create asset-specific feature sets (Gold, BTC, S&P500)
- [x] Implement feature normalization and scaling (rolling z-score, log transform, clip)
- [x] Handle missing data and alignment across timeframes (asof join)
- [ ] Create Jupyter notebooks for EDA and feature analysis → Phase 2B
- [ ] Validate feature importance with SHAP values → Phase 2B

### 2.2 ML Models [MVP COMPLETE]

- [ ] Implement LSTM model (PyTorch) for sequential price patterns → Phase 2B
- [ ] Implement Temporal Fusion Transformer (TFT) for multi-horizon prediction → Phase 2B
- [x] Implement XGBoost model for tabular features classification
- [ ] Build ensemble stacking meta-learner → Phase 2B (needs 2+ base models)
- [x] Create training pipeline with walk-forward optimization (purge + embargo)
- [x] Implement model versioning and artifact storage
- [x] Build prediction/inference engine (predict + predict_proba)
- [x] Create model evaluation metrics (accuracy, precision, recall, F1, confusion matrix)
- [ ] Implement model drift detection → Phase 2B
- [ ] Train initial models on historical data for all 3 assets → requires live data
- [ ] Document model performance baselines → requires live data

### 2.3 Backtesting Engine [COMPLETE]

- [x] Build event-driven backtesting loop
- [x] Implement walk-forward optimization framework (252d/63d/21d splits)
- [x] Create performance metrics calculator (Sharpe, Sortino, Calmar, max DD)
- [x] Implement transaction cost simulation (spread, slippage, overnight fees)
- [x] Build report generator (JSON reports with equity curves, trade lists)
- [ ] Backtest all 3 assets individually → requires live data
- [ ] Backtest portfolio-level strategy (all 3 combined) → Phase 3
- [x] Validate no look-ahead bias (strict temporal ordering in walk-forward)

---

## Phase 3: Trading Engine [COMPLETE]

### 3.1 Strategy Engine [COMPLETE]

- [x] Implement signal generator (ML prediction + technical confirmation + RSI filter)
- [x] Build regime-adaptive parameter system (trending_up/down, ranging)
- [x] Create portfolio allocation engine (base + regime-adjusted weights)
- [x] Implement signal filtering (confidence threshold, counter-trend penalty)
- [x] Build strategy manager orchestrator (prediction -> signal pipeline)
- [x] Create strategy schemas (TradingSignal, StrategyConfig, AllocationConfig)

### 3.2 Risk Management [COMPLETE]

- [x] Implement ATR-based position sizing with confidence scaling
- [x] Build dynamic stop-loss manager (ATR stops, take-profit, trailing stops)
- [x] Implement account-level drawdown monitor (high-water mark tracking)
- [x] Build circuit breaker system (daily loss limit 5%, total drawdown 15%)
- [x] Implement correlation-based exposure checker (Gold↔BTC 50%, BTC↔SP500 30%)
- [x] Build risk manager orchestrator (full pipeline: circuit breaker → drawdown → SL/TP → correlation → sizing)
- [x] Create risk schemas (RiskCheckResult, RiskLimits, DrawdownState)
- [x] Test all risk rules with edge cases (107 tests)

### 3.3 Execution Engine [COMPLETE]

- [x] Build order manager (create, modify, cancel with paper + live mode)
- [x] Implement position tracker (paper in-memory + broker sync ready)
- [x] Implement slippage tracking (expected vs actual per epic)
- [x] Build execution engine orchestrator (signal + risk → order → track)
- [x] Implement paper trading mode (identical pipeline, no broker calls)
- [x] Create execution schemas (ExecutionOrder, ExecutionResult, ExecutionMode)
- [x] Build trade repository for audit trail (CRUD + PnL summary)

---

## Phase 4: Dashboard (Angular 21 + CoreUI) [COMPLETE]

### 4.1 Project Setup [COMPLETE]
- [x] Initialize Angular 21 project
- [x] Install and configure CoreUI Free template
- [x] Setup routing structure for all pages
- [x] Configure HTTP interceptors (auth, error handling)
- [x] Setup WebSocket service for real-time data
- [x] Configure environment files (dev, staging, prod)
- [x] Setup dark mode as default theme

### 4.2 Core Pages [COMPLETE]
- [x] **Dashboard page**: P&L overview, equity curve chart, active positions summary, recent trades table, model confidence indicators
- [x] **Markets page**: Real-time candlestick charts (Chart.js), multi-timeframe view
- [x] **Signals page**: Active signals table with confidence, signal history, test signal generation
- [x] **Positions page**: Open positions with live P&L, SL/TP visualization, close/modify interface
- [x] **Backtest page**: Run new backtests, results viewer with equity curves
- [x] **Strategy page**: Strategy parameter editor, risk rule configuration, asset allocation
- [x] **Models page**: Model performance dashboard, training history, version list
- [x] **Settings page**: Broker connection config, system info, theme settings

### 4.3 Real-time Features [COMPLETE]
- [x] WebSocket integration for live price updates
- [x] Live P&L calculation on open positions
- [x] Real-time signal notifications (toast/badge)
- [x] Trade execution notifications
- [x] Risk alert indicators (circuit breaker status)

### 4.4 Backend API (REST + WebSocket) [COMPLETE]
- [x] 8 REST routers: dashboard, positions, signals, markets, backtest, strategy, models, system
- [x] WebSocket endpoints: /ws/prices (real-time quotes), /ws/trades (trade events)
- [x] 47 API unit tests passing
- [x] Consistent response envelope: `{ success, data, error? }`

---

## Phase 5: Integration & Wiring [COMPLETE]

### 5.1 Dependency Injection & Service Wiring [COMPLETE]

- [x] Expand FastAPI DI with typed providers for all services (broker, data, features, ML, DB repos)
- [x] Create `PredictionService` — real ML inference pipeline: DataAccess -> FeatureBuilder -> XGBoost -> PredictionResult
- [x] Initialize broker client at startup with graceful degradation (mock mode if offline)
- [x] Start background data pipeline (initial download + APScheduler for EOD updates)
- [x] All services accessible via `app.state` singletons, DB repos per-request via `Depends()`

### 5.2 Database Persistence (Dual-Mode Routers) [COMPLETE]

- [x] Wire `PositionRepository` into positions router (DB or in-memory engine fallback)
- [x] Wire `SignalRepository` into signals router (DB or in-memory list fallback)
- [x] Wire `TradeRepository` into dashboard router (DB P&L summary or placeholder)
- [x] Wire `ModelVersioning` into models router (filesystem metadata or static registry)
- [x] Create `ExecutionPersistence` — saves Position + Trade records after execution
- [x] New endpoint `POST /api/signals/predict/{epic}` — full ML pipeline with optional execution

### 5.3 Real-Time Streaming & Events [COMPLETE]

- [x] Broker WebSocket forwarding — fan-out pattern for multiple frontend clients
- [x] Redis `EventBus` singleton — fire-and-forget pub/sub (system works without Redis)
- [x] Event channels: `signal:{epic}`, `trade:{epic}`, `system:events`
- [x] Trade events published via Redis + WebSocket broadcast after execution

### 5.4 Integration Tests [COMPLETE]

- [x] 13 integration tests across 7 test classes (400 total tests passing)
- [x] `TestFeatureBuilderPipeline` — OHLC data -> feature matrix validation
- [x] `TestSignalGenerationPipeline` — prediction -> signal for BUY/HOLD/low-confidence
- [x] `TestRiskCheckPipeline` — risk approval + circuit breaker rejection
- [x] `TestExecutionPipeline` — paper execution end-to-end
- [x] `TestFullPipelineE2E` — complete chain: OHLC -> features -> prediction -> signal -> risk -> paper trade
- [x] `TestExecutionPersistence` — DB record creation with mock session
- [x] `TestGracefulDegradation` — app starts without broker/Redis/DB

### 5.5 Best Practices & Performance Review [COMPLETE]

- [x] Fix WebSocket handler overwrite bug (fan-out pattern for multi-client)
- [x] Fix `_broker_price_stream` timeout handling (heartbeat + retry loop)
- [x] Add background task error logging callbacks
- [x] Add type annotations on all DI providers (TYPE_CHECKING imports)
- [x] Refactor predict endpoint to use DI session (no manual session creation)
- [x] Cache candles between predict/get_market_data (avoid double query)
- [x] Skip request logging for /health and /ws (reduce log noise)
- [x] Optimize OHLC serialization (Polars `to_dicts()` instead of per-row Pydantic)

### 5.6 Remaining (Phase 5B — Paper Trading Validation)

- [ ] Deploy full system connected to Capital.com demo
- [ ] Run paper trading for minimum 2 weeks per asset
- [ ] Compare paper results with backtest predictions
- [ ] Verify risk management rules in live conditions
- [ ] Monitor system stability (memory, CPU, reconnections)
- [ ] Frontend E2E tests (Cypress or Playwright)
- [ ] Security audit (API keys, auth, input validation)

---

## Phase 6: Optimization & Live (Ongoing)

### 6.1 Performance Optimization
- [ ] Optimize model inference latency
- [ ] Implement Numba JIT for hot feature calculation paths
- [ ] Optimize Parquet read/write patterns
- [ ] Frontend bundle optimization
- [ ] Redis connection pooling tuning

### 6.2 Live Trading Preparation
- [ ] Switch from demo to live Capital.com API
- [ ] Start with minimal position sizes (0.5% risk per trade)
- [ ] Implement enhanced monitoring and alerting
- [ ] Setup daily performance reports
- [ ] Gradually increase position sizes based on performance

### 6.3 Continuous Improvement
- [ ] Implement automated model retraining pipeline
- [ ] Add new features based on model drift analysis
- [ ] Explore additional sentiment data sources
- [ ] A/B test strategy variations
- [ ] Build model performance leaderboard
