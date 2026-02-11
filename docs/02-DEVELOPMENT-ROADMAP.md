# AlgoTrader AI - Development Roadmap

## Phase Overview

| Phase | Name | Duration | Focus |
|-------|------|----------|-------|
| 1 | Foundation | 2-3 weeks | Project setup, data pipeline, broker connection |
| 2 | Intelligence | 3-4 weeks | Feature engineering, ML models, backtesting |
| 3 | Trading Engine | 2-3 weeks | Strategy, risk management, execution |
| 4 | Dashboard | 2-3 weeks | Angular frontend, real-time visualization |
| 5 | Integration & Testing | 2 weeks | End-to-end testing, paper trading |
| 6 | Optimization & Live | Ongoing | Performance tuning, live deployment |

---

## Phase 1: Foundation

### 1.1 Project Setup
- [ ] Initialize Python project with Poetry
- [ ] Configure pyproject.toml with all dependencies
- [ ] Setup pre-commit hooks (black, ruff, mypy)
- [ ] Create .env.example with all required environment variables
- [ ] Setup Docker Compose (backend, postgres, redis)
- [ ] Initialize git repository with .gitignore
- [ ] Create base FastAPI application with health endpoint

### 1.2 Capital.com Broker Integration
- [ ] Implement session manager (auth, token refresh, keep-alive)
- [ ] Implement encrypted password authentication (AES)
- [ ] Build market data client (search, prices, OHLC history)
- [ ] Build WebSocket streaming client (quotes, OHLC real-time)
- [ ] Build order management client (positions, working orders)
- [ ] Build account client (balance, history, preferences)
- [ ] Handle rate limiting (10 req/sec) with token bucket
- [ ] Implement automatic reconnection for WebSocket
- [ ] Write comprehensive tests with mocked API responses
- [ ] Verify demo account connectivity with all 3 assets

### 1.3 Data Pipeline
- [ ] Design Parquet storage schema for OHLC data
- [ ] Implement historical data downloader (batch with pagination)
- [ ] Download initial historical data: Gold, BTC, S&P500 (all timeframes)
- [ ] Implement real-time data streamer (WebSocket -> Redis -> Parquet)
- [ ] Setup DuckDB for analytical queries on Parquet files
- [ ] Implement data quality checks (gaps, outliers, consistency)
- [ ] Setup APScheduler for scheduled data collection
- [ ] Create data access layer (unified interface for historical + real-time)

### 1.4 Database Setup
- [ ] Design PostgreSQL schema (trades, positions, signals, config)
- [ ] Setup Alembic migrations
- [ ] Create SQLAlchemy/SQLModel ORM models
- [ ] Implement repository pattern for data access

---

## Phase 2: Intelligence

### 2.1 Feature Engineering
- [ ] Implement technical indicators module (EMA, MACD, RSI, BB, ATR, OBV)
- [ ] Create feature builder pipeline (raw data -> feature matrix)
- [ ] Implement FRED API client for macro data (CPI, rates, GDP, DXY, VIX)
- [ ] Implement sentiment analysis with FinBERT (news headlines)
- [ ] Build market regime detector (HMM or rule-based)
- [ ] Create asset-specific feature sets (Gold, BTC, S&P500)
- [ ] Implement feature normalization and scaling
- [ ] Handle missing data and alignment across timeframes
- [ ] Create Jupyter notebooks for EDA and feature analysis
- [ ] Validate feature importance with SHAP values

### 2.2 ML Models
- [ ] Implement LSTM model (PyTorch) for sequential price patterns
- [ ] Implement Temporal Fusion Transformer (TFT) for multi-horizon prediction
- [ ] Implement XGBoost model for tabular features classification
- [ ] Build ensemble stacking meta-learner
- [ ] Create training pipeline with walk-forward optimization
- [ ] Implement model versioning and artifact storage
- [ ] Build prediction/inference engine
- [ ] Create model evaluation metrics (accuracy, precision, recall, F1)
- [ ] Implement model drift detection
- [ ] Train initial models on historical data for all 3 assets
- [ ] Document model performance baselines

### 2.3 Backtesting Engine
- [ ] Build event-driven backtesting loop
- [ ] Implement walk-forward optimization framework
- [ ] Create performance metrics calculator (Sharpe, Sortino, Calmar, max DD)
- [ ] Implement transaction cost simulation (spread, slippage)
- [ ] Build report generator (HTML reports with equity curves, drawdowns)
- [ ] Backtest all 3 assets individually
- [ ] Backtest portfolio-level strategy (all 3 combined)
- [ ] Validate no look-ahead bias (strict temporal ordering)

---

## Phase 3: Trading Engine

### 3.1 Strategy Engine
- [ ] Implement signal generator (ML prediction + technical confirmation)
- [ ] Build regime-adaptive parameter system
- [ ] Create portfolio allocation engine (distribute capital across assets)
- [ ] Implement signal filtering (confidence threshold, regime filter)
- [ ] Build strategy activation/deactivation manager
- [ ] Create strategy parameter configuration system

### 3.2 Risk Management
- [ ] Implement ATR-based position sizing
- [ ] Build dynamic stop-loss manager (ATR trailing stops)
- [ ] Implement account-level drawdown monitor
- [ ] Build per-strategy drawdown tracker
- [ ] Implement correlation-based exposure checker
- [ ] Build circuit breaker system (daily loss limit, emergency stop)
- [ ] Create risk parameter configuration interface
- [ ] Test all risk rules with edge cases

### 3.3 Execution Engine
- [ ] Build order lifecycle manager (create, modify, cancel, confirm)
- [ ] Implement position tracker (sync with Capital.com)
- [ ] Build fill confirmation handler
- [ ] Implement slippage tracking (expected vs actual)
- [ ] Create order queue with priority management
- [ ] Handle API errors and retry logic
- [ ] Build execution log for audit trail

---

## Phase 4: Dashboard (Angular 21 + CoreUI)

### 4.1 Project Setup
- [ ] Initialize Angular 21 project
- [ ] Install and configure CoreUI Free template
- [ ] Setup routing structure for all pages
- [ ] Configure HTTP interceptors (auth, error handling)
- [ ] Setup WebSocket service for real-time data
- [ ] Configure environment files (dev, staging, prod)
- [ ] Setup dark mode as default theme

### 4.2 Core Pages
- [ ] **Dashboard page**: P&L overview, equity curve chart, active positions summary, recent trades table, model confidence indicators
- [ ] **Markets page**: Real-time candlestick charts (Chart.js or lightweight-charts), price alerts, multi-timeframe view, technical indicators overlay
- [ ] **Signals page**: Active signals table with confidence, ML model breakdown, signal history, signal-to-trade correlation
- [ ] **Positions page**: Open positions with live P&L, SL/TP visualization, position modification interface, history
- [ ] **Backtest page**: Run new backtests, results viewer with equity curves, parameter optimization grid, compare strategies
- [ ] **Strategy page**: Strategy parameter editor, activate/deactivate strategies, risk rule configuration, asset allocation sliders
- [ ] **Models page**: Model performance dashboard, training history, drift indicators, retrain trigger
- [ ] **Settings page**: Broker connection config, notification preferences, API key management, theme settings

### 4.3 Real-time Features
- [ ] WebSocket integration for live price updates
- [ ] Live P&L calculation on open positions
- [ ] Real-time signal notifications (toast/badge)
- [ ] Trade execution notifications
- [ ] Risk alert indicators (circuit breaker status)

---

## Phase 5: Integration & Testing

### 5.1 End-to-End Integration
- [ ] Connect all backend components via Redis events
- [ ] Connect frontend to backend API (all endpoints)
- [ ] Test complete flow: data -> features -> model -> signal -> risk -> execution
- [ ] Verify WebSocket streaming pipeline (Capital.com -> backend -> frontend)
- [ ] Load testing on API endpoints

### 5.2 Paper Trading Validation
- [ ] Deploy full system connected to Capital.com demo
- [ ] Run paper trading for minimum 2 weeks per asset
- [ ] Compare paper results with backtest predictions
- [ ] Verify risk management rules in live conditions
- [ ] Monitor system stability (memory, CPU, reconnections)
- [ ] Fix issues discovered during paper trading

### 5.3 Quality Assurance
- [ ] Backend unit tests (min 80% coverage on critical paths)
- [ ] Integration tests (API, broker, data pipeline)
- [ ] Frontend E2E tests (Cypress or Playwright)
- [ ] Security audit (API keys, auth, input validation)
- [ ] Performance profiling and optimization

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
