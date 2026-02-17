# MANTIS AI - Development Roadmap

## Phase Overview

| Phase | Name | Focus | Status |
|-------|------|-------|--------|
| 1 | Foundation | Project setup, data pipeline, broker connection | COMPLETE |
| 2 | Intelligence | Feature engineering, ML models, backtesting | COMPLETE |
| 3 | Trading Engine | Strategy, risk management, execution | COMPLETE |
| 4 | Dashboard | Angular frontend, real-time visualization | COMPLETE |
| 5 | Integration & Wiring | End-to-end wiring, paper trading pipeline | COMPLETE |
| 5B | Paper Trading Validation | Scripts, paper loop, health monitoring | COMPLETE |
| 6A | Trading Guru ML Upgrades | 3-class migration, calibration, LSTM, features | COMPLETE |
| 6B | ML Optimization + Backtest Realism | Optuna, feature selection, cost model, backtest API | COMPLETE |
| 6B.2 | Optuna Production Re-training | 8 models tuned, multi-asset expansion (9 assets) | COMPLETE |
| 7 | Paper Trading Dashboard | Frontend paper trading page, signal history, live P&L | COMPLETE |
| 8 | TRADING MAGNA AI | 15 improvements: risk, features, strategies, pairs | COMPLETE |
| 9 | Integration & Coverage | Paper loop wiring, backtest router, coverage 80% | COMPLETE |
| 10 | MANTIS AI Branding | Rebrand, Angular optimization, OnPush, withFetch | COMPLETE |
| 11 | Production Quick Wins | Max positions, rate limiting, graceful shutdown, 21 assets | COMPLETE |
| 14 | State Recovery | Multi-source recovery, auto-persistence, backoff retry | COMPLETE |
| 15 | UI/UX + Avatar System | Auth redesign, dashboard layout, avatar upload | COMPLETE |
| 16 | Best Practices & Docs | Security, performance, memory leaks, documentation | COMPLETE |

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

### 6A.7 Code Review & Performance Optimization [COMPLETE]

**Code Best Practices:**

- [x] Fix broken cache check in `PredictionService.predict()` (condizione sempre True, query ridondante)
- [x] Fix double walk-forward iteration in `ModelTrainer` (ricalcolava tutti i fold per prendere l'ultimo)
- [x] Fix temp directory leak in `ModelTrainer` (tempfile.mkdtemp mai pulito → shutil.rmtree)
- [x] Aggiungere safety assertions per y_aligned nel trainer (protezione bug silenti)
- [x] Rimuovere import inutilizzati (`OrderManager`, `PositionTracker` in test_paper_loop)
- [x] Import `shutil` a livello di modulo (evita inline import)

**Performance Optimization:**

- [x] Cache TTL su `DataAccessLayer.get_candles()` — 3600x speedup (38ms → 11μs)
  - Cache in-memory con TTL configurabile (default 5 min)
  - Cache key: epic + timeframe + date range
  - `invalidate_cache()` per asset o globale
- [x] Fondere `clip_outliers` + `rolling_zscore` in singolo passo (`clip_and_zscore`)
  - Rolling mean/std calcolati una volta sola per colonna (era 2x)
  - ~50% meno computazione nel normalizer
- [x] 456 test passati dopo tutte le ottimizzazioni

---

## Phase 6B: ML Optimization + Backtest Realism [COMPLETE]

### 6B.1 Walk-Forward Upgrades [COMPLETE]

- [x] Multi-timeframe features in walk-forward (41→121 features)
- [x] Optuna hyperparameter tuning (`src/models/tuner.py` — TPE sampler, 40 trials)
- [x] Feature selection by importance (`src/models/feature_selector.py` — drop bottom N%)
- [x] Confidence calibration per fold (isotonic auto-fit on validation set)
- [x] Script: `scripts/walk_forward_backtest.py` with `--tune`, `--prune-pct`, `--sweep-threshold`

### 6B.2 Backtest Cost Model [COMPLETE]

- [x] Realistic spreads per asset (Gold 3.5 pips, BTC 50 pips, etc.)
- [x] SL slippage: 50% of spread added to stop distance
- [x] Weekend overnight: 3x normal overnight rate
- [x] Sharpe fix: daily returns (not per-bar) — industry standard
- [x] Engine performance: column-based iteration, signal_map via zip()

### 6B.3 Backtest API + Frontend [COMPLETE]

- [x] `POST /api/backtest/run` endpoint with full parameter control
- [x] Frontend backtest page with equity curve, trade list, metrics
- [x] Signal generator: `src/backtest/signal_generator.py` for batch ML inference

### 6B.4 Multi-Asset Expansion (3→9 assets) [COMPLETE]

- [x] 6 new assets: WTIUSD, EURUSD, NVDA, TSLA, XAGUSD, DE40
- [x] 84,017 candles downloaded (6 assets x 3 timeframes)
- [x] Walk-forward adaptive for stock CFDs (NVDA/TSLA scale=10)
- [x] Portfolio allocator, correlation guard, 9-asset configs
- [x] EURUSD excluded (tiny ATR → massive sizing → -99% OOS)

### 6B.5 Optuna Production Re-training [COMPLETE]

- [x] 8 models re-trained with Optuna tuning (40 trials/asset)
- [x] Params saved in `data/tuned_params/{EPIC}_1h.json`
- [x] WF OOS: BTCUSD +57%, TSLA +46%, NVDA +23%, XAUUSD +14%, DE40 +7%, US500 +5%

---

## Phase 7: Paper Trading Dashboard [COMPLETE]

- [x] Frontend page: control panel, KPI cards, signals, positions, activity
- [x] Signal history: `deque(maxlen=200)`, live P&L from WebSocket, 12s polling
- [x] Frontend port: 4321 (angular.json + CORS updated)
- [x] Code review + hardening: assert→ValueError, NaN threshold, error counting

---

## Phase 8: TRADING MAGNA AI [COMPLETE]

> 15 miglioramenti basati su `docs/TRADING_MAGNA_AI_OPTIMIZED.md` — 20 nuovi file, 221 nuovi test

### A — Risk Management [COMPLETE]

- [x] **A1 Circuit Breakers** (6 tipi): daily_loss, consecutive_losses, max_positions, slippage, heartbeat, volatility
- [x] **A2 ADX Pre-Signal Filter**: ADX<20 reject choppy, ADX>25 boost confidence (+0.05)
- [x] **A3 Step Trailing Stop** (4 fasi): INITIAL→BREAKEVEN→TP1_LOCK→TRAILING (ATR ratchet)
- [x] **A4 Equity Curve Filter**: SMA(20 trades), 50% size reduction when below

### B — Feature Engineering + Exit Management [COMPLETE]

- [x] **B5 Multi-Target Exit**: TP1(1xR)/TP2(2xR), partial_close(50%) in ExecutionEngine
- [x] **B6 MACD+Volume**: verified already present in feature pipeline
- [x] **B7 Candlestick Patterns**: 8 binary features (hammer, engulfing, doji, stars, pin_bar)
- [x] **B8 Fibonacci Clusters**: 5 ATR-normalized distance features + nearest + cluster_strength

### C — Execution + Validation [COMPLETE]

- [x] **C9 Market Structure BOS/CHoCH**: swing pivots HH/HL/LH/LL, structural breaks
- [x] **C10 Monte Carlo Validation**: 10K shuffles, equity/DD/Sharpe CIs, p-value, ruin risk
- [x] **C11 Volatility Squeeze**: BB-inside-KC detection, momentum+volume breakout entry
- [x] **C12 Adaptive Kelly**: half-Kelly sizing, fallback to fixed-fractional when <30 trades

### D — Strategic Vision [COMPLETE]

- [x] **D13 Strategy Router**: regime-based switching (trending→ML, ranging→[squeeze, vwap, ML])
- [x] **D14 VWAP Reversion**: ±2SD entry, VWAP center TP, 3SD SL, ADX/RSI filters
- [x] **D15 Pairs Trading Gold-BTC**: Engle-Granger cointegration, z-score entry/exit, dollar-neutral

---

## Phase 9: Integration & Coverage [COMPLETE]

- [x] **Paper Loop Wiring**: TrailingStop 4-phase, CircuitBreaker heartbeat/record, EquityCurveFilter, Kelly trade_history, TP1 partial_close — all connected in paper_loop.py
- [x] **Backtest StrategyRouter**: `--strategy` flag in walk_forward_backtest.py, strategy param in API
- [x] **Pairs backtest script**: `scripts/pairs_backtest.py` — Gold-BTC cointegration with Monte Carlo
- [x] **Pydantic v2 bug fix**: ModifyPositionRequest missing `populate_by_name=True`
- [x] **Coverage**: 75.6% → 80.14% (+168 tests, 865 total)
- [x] **Retraining**: 121→220 features, F1 macro stabile (~0.53-0.60)

---

## Phase 10: MANTIS AI Branding + Angular Optimization [COMPLETE]

- [x] Rebrand from "AlgoTrader AI" to "MANTIS AI"
- [x] Neon green theme (`#39FF14`) with dark backgrounds (`#0d1117`)
- [x] SVG mantis logo (favicon, sidebar, footer)
- [x] CoreUI CSS variable overrides in `_custom.scss`
- [x] All 9 components migrated to `ChangeDetectionStrategy.OnPush`
- [x] `app.config.ts`: `withFetch()` + `withPreloading(PreloadAllModules)`
- [x] TradingView Lightweight Charts with mantis green palette
- [x] Plus Jakarta Sans + IBM Plex Mono fonts

---

## Phase 11: Production Readiness Quick Wins [COMPLETE]

- [x] Max positions limit per asset (configurable)
- [x] API rate limiting (token bucket)
- [x] Graceful shutdown with signal handlers
- [x] Enhanced health checks (data freshness, broker connectivity)
- [x] 21-asset expansion: XAUUSD, BTCUSD, US500, WTIUSD, EURUSD, NVDA, TSLA, XAGUSD, DE40, SOLUSD, ETHUSD, BNBUSD, DOGUSD, DASHUSD, ICPUSD, NATGAS, COPPER, PLATINUM, GBPUSD, USDJPY, NAS100
- [x] Paper trading verified: 21 assets configured, 4 trades executed, 0 errors
- [x] WF OOS results: BTCUSD +56%, XAUUSD +13%, US500 +6% (all MC p=0.0000)

---

## Phase 15: UI/UX Improvements & Avatar System [COMPLETE]

### API Endpoint Fixes

- [x] Positions page: switched to `trading.paperPositions` + `loadPaperPositions()` (was using broker API)
- [x] Signals page: switched to `trading.paperSignals` + `loadPaperSignals()` (was using broker API)
- [x] WebSocket integration for live P&L calculation in positions table

### Dashboard Redesign

- [x] Full-width equity curve card (12 cols, 360px height)
- [x] 8 core assets in 4-column responsive grid (XAUUSD, BTCUSD, US500, WTIUSD, NVDA, TSLA, XAGUSD, DE40)
- [x] 4 horizontal risk metric cards (Circuit Breaker, Drawdown, Daily P&L, Peak Equity)

### Auth Pages Redesign

- [x] Split-screen layout (hero section left + form section right)
- [x] Glassmorphism: `backdrop-filter: blur(20px)`, rgba backgrounds, border glows
- [x] Animated gradients, floating blobs, neon green focus states
- [x] Registration: password strength meter (weak/medium/strong) with visual bars

### Avatar System (End-to-End)

- [x] Backend: `avatar_handler.py` — validate, resize (Pillow 256x256), save to `data/avatars/`
- [x] Migration: `avatar_url`, `avatar_storage_path` columns on `users` table
- [x] Endpoints: POST `/api/auth/avatar/upload`, GET `/api/auth/avatar/{user_id}`, DELETE `/api/auth/avatar`
- [x] Frontend: `AvatarComponent` (display + initials fallback), `AvatarUploadComponent` (drag-drop, 5MB max)
- [x] Integration: user dropdown, profile page, auth service methods

### Critical Fixes

- [x] CoreUI icons: removed non-existent `cilBrain`, `cilX`; added `cilBolt`, `cilBook`, `cilChartLine`
- [x] RBAC: `init_permissions.py` script, `settings:write` added to ADMIN role
- [x] SASS deprecation: replaced `lighten()` with `color.adjust()` (sass:color module)

### Build Status

- Frontend: **0 errors, 0 warnings** (bundle: 2.81 MB)

---

## Phase 16: Best Practices, Performance & Documentation [COMPLETE]

### S1 — Backend Fixes

- [x] Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)` across backend
- [x] Add LIMIT to unbounded repository queries
- [x] Fix HTTP client resource leak (`_http_client.aclose()` in broker)
- [x] Add GZipMiddleware (minimum_size=1000)
- [x] Rate limiting on auth endpoints (5/min login, 3/hour register)
- [x] JWT secret validation (fail startup if default secret in production)
- [x] Debug mode default changed to `False`
- [x] **1065 tests passing, 0 failures**

### S2 — Frontend Fixes

- [x] Fix memory leak: uncleared `setInterval` in dashboard (news timer)
- [x] Remove `console.log` from production code (kept `console.error`)
- [x] WebSocket exponential backoff: `min(1000 * 2^attempts, 60000)`
- [x] Add error handlers to all 13 TradingService `.subscribe()` calls
- [x] **Frontend build: 0 errors, 0 warnings**

### S3 — Documentation Overhaul

- [x] Rewrite CLAUDE.md (MANTIS AI, 21 assets, new modules)
- [x] Update all docs (01-ARCHITECTURE through 06-SETUP-GUIDE)
- [x] Fix 03-ML-STRATEGY (5-class ensemble → 3-class XGBoost)
- [x] Create 08-API-REFERENCE.md

### S4 — Roadmap

- [x] Create ROADMAP-NEXT-STEPS.md with Phases 17-20+

---

## Phase 14: State Recovery System [COMPLETE]

**Objective**: Restore trading state after backend restart from database and/or broker API

**Key Deliverables**:

- [x] Database schema (TrailingStopState, RiskStateSnapshot tables)
- [x] Repository layer (TrailingStopRepository, RiskStateRepository)
- [x] Auto-persistence hooks in PaperTradingLoop
- [x] StateRecoveryService with multi-source recovery
- [x] Startup integration in main.py
- [x] Graceful degradation with exponential backoff retry
- [x] Comprehensive testing (40 unit tests)
- [x] Monitoring API endpoint (GET /api/system/recovery-report)
- [x] Performance optimizations (N+1 fixes, indexes, deque)

**Recovery Architecture**:

- PAPER mode: PostgreSQL → Empty state + WARNING
- DEMO/LIVE mode: Broker API → PostgreSQL → Empty state + ERROR

**Key Features**:

- Multi-source recovery with broker/database fallback chain
- Position reconciliation (broker data wins, auto-close stale positions)
- Trailing stop state restoration with phase tracking
- Trade history restoration for Kelly sizing (200 trades)
- Risk manager state restoration (drawdown monitor, circuit breakers, equity curve)
- Exponential backoff retry (3 attempts: 1s, 2s, 4s)
- Structured logging events (RECOVERY_START, RECOVERY_COMPLETE, etc.)

**Performance**: <5s recovery time for 100 positions, indexed queries, bulk operations
