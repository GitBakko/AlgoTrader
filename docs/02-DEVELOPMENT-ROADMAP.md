# AlgoTrader AI - Development Roadmap

## Phase Overview

| Phase | Name | Duration | Focus | Status |
|-------|------|----------|-------|--------|
| 1 | Foundation | 2-3 weeks | Project setup, data pipeline, broker connection | COMPLETE |
| 2 | Intelligence | 3-4 weeks | Feature engineering, ML models, backtesting | MVP COMPLETE |
| 3 | Trading Engine | 2-3 weeks | Strategy, risk management, execution | COMPLETE |
| 4 | Dashboard | 2-3 weeks | Angular frontend, real-time visualization | COMPLETE |
| 5 | Integration & Wiring | 2 weeks | End-to-end wiring, paper trading pipeline | COMPLETE |
| 5B | Paper Trading Validation | 1 week | Scripts, paper loop, health monitoring | COMPLETE |
| 6A | Trading Guru ML Upgrades | 1 week | 3-class migration, calibration, LSTM, features | COMPLETE |
| 6A.6 | Validation | 1 day | Re-training, LSTM comparison, paper trading test | COMPLETE |
| 6B | Ensemble & Advanced | TBD | TFT, stacking, hyperopt | NEXT |
| 7 | Optimization & Live | Ongoing | Performance tuning, live deployment | FUTURE |

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

### 5.6 Phase 5B — Paper Trading Validation [COMPLETE]

**Infrastructure & Scripts:**

- [x] Fix DataScheduler bug (missing `data_access` parameter in startup)
- [x] Create `scripts/download_data.py` — CLI tool for batch historical data download
- [x] Create `scripts/train_models.py` — CLI tool for walk-forward XGBoost training

**Paper Trading Loop:**

- [x] Create `PaperTradingLoop` class — controllable background asyncio task
- [x] Pipeline: PredictionService → StrategyManager → RiskManager → ExecutionEngine (paper)
- [x] REST API: `POST /api/trading/start`, `POST /api/trading/stop`, `GET /api/trading/status`
- [x] Dashboard integration — paper trading status in overview response

**Monitoring & Health:**

- [x] Add `check_data_freshness()` to HealthChecker (last candle age per epic)
- [x] Optimized data freshness check (reads only timestamp column, parallel health checks)
- [x] Add `get_latest_timestamp()` and `get_bar_count()` to ParquetStorageManager

**Best Practices & Performance:**

- [x] Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)` (8 occurrences, 5 files)
- [x] Add `get_paper_positions_sync()` to PositionTracker (avoid double private attr access)
- [x] Add `last_signals` property to PaperTradingLoop (public API)
- [x] Fix timezone mismatch bug in data freshness check
- [x] Parallelize health checks with `asyncio.gather()`

**Testing:**

- [x] 15 new tests: PaperTradingLoop (10) + Trading API endpoints (5)
- [x] Updated integration tests for graceful degradation
- [x] 415 total tests passing

**Operational Steps (completed manually):**

- [x] Download historical data from Capital.com demo (53,890 candles, 3 assets x 3 TF)
- [x] Fix epic mapping (XAUUSD→GOLD) and bid/ask price parsing
- [x] Fix walk-forward window scaling for hourly data (x24)
- [x] Train XGBoost models per asset (baseline F1 ~0.20-0.24)
- [x] Test paper trading loop end-to-end (backend starts, loads 3 models, runs predictions)
- [ ] Run paper trading for minimum 2 weeks per asset
- [ ] Compare paper results with backtest predictions
- [ ] Frontend E2E tests (Cypress or Playwright)
- [ ] Security audit (API keys, auth, input validation)

---

## Phase 6A: Trading Guru ML Upgrades [COMPLETE]

> Basata sull'analisi di `docs/addestramento.md` e sintesi in `docs/07-TRADING-GURU-SYNTHESIS.md`

### 6A.1 Migrazione 5→3 Classi [COMPLETE]

- [x] Aggiornare `SignalClass` enum: SELL=0, HOLD=1, BUY=2
- [x] Aggiornare `TargetBuilder`: soglia singola 0.5 ATR
- [x] Aggiornare `XGBoostClassifier`: n_classes=3
- [x] Aggiornare `ModelEvaluator`: labels a 3 classi
- [x] Aggiornare `SignalGenerator`: semplificare mapping
- [x] Aggiornare `PredictionService`: supporto 3 classi
- [x] Aggiornare tutti i test (20+ file, 456 test)

### 6A.2 Confidence Calibration [COMPLETE]

- [x] Creare `src/models/calibration.py` — isotonic + Platt scaling, ECE metric
- [x] Integrare calibrazione nel training pipeline (auto-fit su ultimo fold val)
- [x] Integrare nella prediction pipeline (PredictionService auto-load)
- [x] Save/load calibratore con modello

### 6A.3 Nuove Feature Tecniche [COMPLETE]

- [x] Stochastic RSI (%K, %D)
- [x] Bollinger Squeeze detection (binary + duration)
- [x] RSI Divergence detection (bullish=+1, bearish=-1)
- [x] VWAP + distance from VWAP
- [x] Session features (cyclical hour_sin/cos, dow_sin/cos)
- [x] Integrato in FeatureBuilder + add_all_indicators

### 6A.4 LSTM Model [COMPLETE]

- [x] Creare `src/models/lstm_model.py` (PyTorch, extends BaseMLModel)
- [x] Sequence reshaping per input LSTM (batch x seq_len x features)
- [x] 2-layer LSTM, dropout 0.3, linear head → 3 classi
- [x] Early stopping, AdamW, class-weighted loss, grad clipping
- [x] Save/load completo (weights + params)

### 6A.5 Multi-Timeframe Features [COMPLETE]

- [x] `additional_timeframes: ["4h", "1d"]` già configurati nell'asset config
- [x] `TimeframeAligner` funzionante (asof join, forward-fill)
- [x] `ModelTrainer.train(multi_timeframe=True)` abilitato
- [x] `PredictionService` auto-detect multi-TF features
- [x] `scripts/train_models.py` usa multi_timeframe=True di default

### 6A.6 Re-Training e Validazione [COMPLETE]

- [x] Re-train XGBoost con 3 classi → F1 macro 0.54 (target era 0.35, +184% vs 5 classi)
- [x] Verificare che il paper trading generi segnali (rate > 0%) → US500 BUY eseguito
- [x] Train LSTM → confrontare con XGBoost → LSTM F1 ~0.17 (vicino a random), XGBoost vince
- [x] min_confidence abbassato 0.50 → 0.40 (appropriato per 3 classi)
- [x] PredictionService fix: filtra per modelli XGBoost (ignora LSTM)
- [x] ModelTrainer fix: alignment output per modelli a sequenza (LSTM)
- [ ] Monitorare paper trading per 2+ settimane

---

## Phase 6B: Ensemble & Advanced (Future)

### 6B.1 TFT Model

- [ ] Implementare Temporal Fusion Transformer (PyTorch)
- [ ] Variable selection network per feature importance automatica
- [ ] Multi-horizon prediction (4h, 1d, 1w)

### 6B.2 Ensemble Stacking

- [ ] Meta-learner XGBoost su output di LSTM + TFT + XGBoost
- [ ] Model agreement voting (2-of-3 per trade)
- [ ] Weighted averaging basato su performance recente

### 6B.3 Advanced Features

- [ ] FRED API client per macro data (CPI, rates, GDP, DXY, VIX)
- [ ] Cross-asset correlation features (Gold-DXY, BTC-Gold, VIX-S&P)
- [ ] FinBERT sentiment analysis (news headlines)
- [ ] SHAP feature importance dashboard

### 6B.4 Hyperparameter Optimization

- [ ] Optuna integration con walk-forward framework
- [ ] TPE sampler per efficient search
- [ ] Obiettivo: risk-adjusted return (Sharpe), non solo F1

---

## Phase 7: Live Trading (Future)

### 7.1 Performance Optimization

- [ ] Optimize model inference latency
- [ ] Frontend bundle optimization
- [ ] Redis connection pooling tuning

### 7.2 Live Trading Preparation

- [ ] Switch from demo to live Capital.com API
- [ ] Start with minimal position sizes (0.5% risk per trade)
- [ ] Implement enhanced monitoring and alerting
- [ ] Setup daily performance reports
- [ ] Gradually increase position sizes based on performance

### 7.3 Continuous Improvement

- [ ] Implement automated model retraining pipeline
- [ ] Model drift detection and alerts
- [ ] A/B test strategy variations
- [ ] Build model performance leaderboard
