<p align="center">
  <img src="frontend/src/assets/favicon.svg" width="80" height="80" alt="MANTIS AI Logo">
</p>

<h1 align="center">MANTIS AI</h1>

<p align="center">
  <strong>Algorithmic Trading Platform powered by Machine Learning</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/angular-21-dd0031?logo=angular&logoColor=white" alt="Angular">
  <img src="https://img.shields.io/badge/tests-1136_passing-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/assets-21_instruments-blueviolet" alt="Assets">
  <img src="https://img.shields.io/badge/features-220+-9cf" alt="Features">
  <img src="https://img.shields.io/badge/broker-Capital.com-orange" alt="Broker">
</p>

---

## Overview

MANTIS AI is a full-stack algorithmic trading system that combines **XGBoost ML models** with advanced risk management to trade **21 financial instruments** on Capital.com. Like its namesake predator, the system is patient, precise, and strikes only with high confidence.

### Traded Instruments

| Forex | Crypto | Commodities | Indices | Stocks |
|-------|--------|-------------|---------|--------|
| EURUSD | BTCUSD | XAUUSD (Gold) | US500 (S&P 500) | NVDA |
| GBPUSD | ETHUSD | XAGUSD (Silver) | DE40 (DAX) | TSLA |
| USDJPY | SOLUSD | WTIUSD (Oil) | NAS100 (Nasdaq) | |
| | BNBUSD | NATGAS | | |
| | DOGUSD | COPPER | | |
| | DASHUSD | PLATINUM | | |
| | ICPUSD | | | |

### Key Capabilities

- **220+ ML Features**: Technical indicators, candlestick patterns, Fibonacci clusters, market structure, Keltner/VWAP bands, sentiment (news + equity), macro (VIX/DXY/10Y yield)
- **Regime-Adaptive**: ADX + EMA-50 slope classifies trending/ranging markets; strategies auto-switch
- **Per-Asset Thresholds**: Walk-forward OOS scorecard with KEEP/REVIEW/EXCLUDE decisions per asset
- **Multi-Tier Sentiment**: Tier 1 (stocks) = 5 features, Tier 2 (all others) = news sentiment
- **Macro Overlay**: VIX, DXY, 10Y yield via yfinance with daily asof-join to hourly bars
- **Real Trading**: Trades executed on Capital.com demo with real ML confidence scores, full position tracking and history

---

## Features

### ML Pipeline

- **XGBoost 3-class classifier** (BUY / HOLD / SELL) with Optuna hyperparameter tuning
- **220+ features**: technical indicators, candlestick patterns (8), Fibonacci clusters (7), market structure (3), Keltner channels, VWAP bands, sentiment (5), macro (6)
- **Walk-forward optimization** with train/val/test split, purge, and embargo
- **Isotonic confidence calibration** for reliable probability estimates
- **Batch OOS scorecard**: evaluates all 20 assets — Sharpe, win rate, max DD, Monte Carlo p-value, risk of ruin
- **Per-asset confidence thresholds**: `optimal_thresholds.json` loaded at startup
- **F1 macro**: 0.53-0.61 across assets

### Risk Management (TRADING MAGNA AI)

- **6 Circuit Breakers**: daily loss, consecutive losses, max positions, slippage anomaly, heartbeat timeout, volatility spike
- **4-Phase Trailing Stop**: Initial -> Breakeven -> TP1 Lock -> ATR Trailing
- **Multi-Target Exit**: TP1 (1xR) with 50% partial close, TP2 (2xR) full exit
- **Adaptive Kelly Position Sizing**: half-Kelly with 30-trade minimum, fixed-fractional fallback
- **Equity Curve Filter**: SMA(20 trades), 50% size reduction when underperforming
- **Correlation Guard**: prevents over-exposure to correlated assets

### Strategy Engine

- **Regime-based Strategy Router**: trending -> ML, ranging -> [Squeeze, VWAP, ML]
- **Volatility Squeeze Breakout**: BB-inside-KC detection with momentum/volume confirmation
- **VWAP Reversion**: mean-reversion at +/-2 SD bands in ranging markets
- **Pairs Trading**: Gold-BTC cointegration with z-score entry/exit (dollar-neutral)
- **Monte Carlo Validation**: permutation, bootstrap, sign-flip tests with confidence intervals

### Execution and Tracking

- **Paper + DEMO + LIVE modes**: seamless mode switching via `EXECUTION_MODE` env var
- **Position persistence**: all opens/closes saved to PostgreSQL with close reason normalization
- **Broker-closed detection**: positions closed by Capital.com (SL/TP) are automatically detected and persisted
- **State recovery**: PAPER from PostgreSQL, DEMO/LIVE from broker API + DB fallback
- **Partial close**: TP1 at 50%, DEMO/LIVE uses close-then-reopen pattern (Capital.com limitation)
- **Emergency kill switch**: stops loop + closes all positions + fires CRITICAL alert

### Dashboard

- **Angular 21 + CoreUI** with MANTIS AI dark theme (neon green `#39FF14` accents)
- **12 views**: Dashboard, Paper Trading, Backtest, Positions, Signals, Markets, News, Strategy, AI Models, Trade Journal, Settings, System Logs
- **Real-time**: WebSocket price streaming, live P&L updates
- **TradingView Lightweight Charts** for candlestick visualization
- **Positions history**: tab-based (Open/History), filters, close reason badges, KPI summary
- **Performance analytics**: win rate, profit factor, P&L by asset, equity curve
- **Mobile responsive**: Bottom nav, scroll strips, 44px touch targets
- **Auth**: JWT + RBAC (3 roles, 30+ permissions), avatar upload
- **Alerting**: Email, Slack, Telegram, Webhook channels (configurable, off by default)

---

## Architecture

```text
                    MANTIS AI - System Architecture

    +------------------+         +-------------------+
    |   Angular 21     |  REST   |   FastAPI Backend  |
    |   MANTIS Theme   | <-----> |   Python 3.12+     |
    |   CoreUI + LWC   |   WS    |   13 REST routers  |
    +------------------+         +--------+-----------+
                                          |
              +---------------------------+---------------------------+
              |              |            |            |              |
        +-----+----+  +-----+----+ +-----+----+ +----+-----+ +-----+----+
        |  Broker   |  |   Data   | | Features | |    ML    | | Strategy |
        | Capital   |  | Pipeline | |  Engine  | |  Models  | |  Router  |
        |  .com     |  | Parquet  | | 220+ ft  | | XGBoost  | |  Regime  |
        |  REST+WS  |  | DuckDB   | | Multi-TF | | Calibr.  | |  Based   |
        +-----------+  +----------+ +----------+ +----------+ +----------+
              |              |            |            |              |
        +-----+----+  +-----+----+ +-----+----+ +----+-----+       |
        | External  |  | Backtest | | Sentiment| |  Macro   |       |
        | Finnhub   |  | WF + MC  | | FinBERT  | |VIX/DXY  |       |
        | Marketaux |  | Scorecard| | Tiered   | |yfinance  |       |
        +-----------+  +----------+ +----------+ +----------+       |
                                                                     |
                            +-------------+-------------+            |
                            |        Risk Stack         |<-----------+
                            | CircuitBreakers -> Equity |
                            | -> Kelly -> TrailingStop  |
                            +---------------------------+
                                          |
                            +-------------+-------------+
                            |     Execution Engine      |
                            |  Paper + DEMO + Live      |
                            |  State Recovery + Persist |
                            +---------------------------+
```

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.12+, FastAPI, Pydantic v2, Loguru |
| **ML** | XGBoost, PyTorch (LSTM), scikit-learn, Optuna |
| **Data** | Polars, Parquet, DuckDB, Redis |
| **External** | Finnhub, Marketaux, yfinance (macro data) |
| **Database** | PostgreSQL, SQLAlchemy, Alembic |
| **Frontend** | Angular 21, CoreUI Free, TradingView LWC |
| **Broker** | Capital.com REST API + WebSocket |
| **Monitoring** | Prometheus, Grafana, JSON structured logging |
| **CI/CD** | GitHub Actions (lint, test, docker) |

All databases are optional — the app degrades gracefully without PostgreSQL, Redis, or DuckDB.

---

## Project Structure

```text
AlgoTrader/
├── backend/
│   ├── src/
│   │   ├── api/               # 13 REST routers + WebSocket + middleware
│   │   ├── auth/              # JWT + RBAC (3 roles, 30+ permissions)
│   │   ├── broker/            # Capital.com API wrapper (REST + WS)
│   │   ├── data/              # Parquet storage, DuckDB analytics
│   │   ├── external/          # Finnhub, Marketaux, yfinance clients
│   │   ├── features/          # 220+ features (Polars, pure numpy)
│   │   ├── models/            # XGBoost, LSTM, calibration, Optuna tuner
│   │   ├── strategy/          # ML, Squeeze, VWAP, Pairs, Router
│   │   ├── risk/              # Circuit breakers, Kelly, trailing stops
│   │   ├── execution/         # Paper + DEMO + live execution, state recovery
│   │   ├── backtest/          # Walk-forward, Monte Carlo, scorecard
│   │   ├── trading/           # Paper trading loop (21 assets)
│   │   ├── monitoring/        # Health, trade logger, alerting, metrics
│   │   └── utils/             # Config, constants, event bus
│   ├── tests/                 # 1136+ pytest tests
│   ├── scripts/               # download, train, backtest, scorecard
│   └── data/                  # Parquet files, saved models, logs
├── frontend/                  # Angular 21 MANTIS AI dashboard
│   ├── src/app/
│   │   ├── core/              # Services, guards, interceptors
│   │   ├── shared/            # Chart, avatar, epic-logo, loading-button
│   │   ├── views/             # 12 page components
│   │   └── layout/            # Sidebar, header, footer, bottom-nav
│   └── src/scss/              # MANTIS AI design system (6-level surfaces)
├── docs/
│   ├── architecture/          # System architecture, API reference, state recovery
│   ├── trading/               # ML strategy, Capital.com API, trading concepts
│   ├── guides/                # Setup guide, frontend guide
│   ├── planning/              # Development roadmap, next steps
│   └── archive/               # Historical research docs
└── docker-compose.yml
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Capital.com demo account

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your Capital.com demo credentials

# Download historical data (21 assets x 3 timeframes)
python scripts/download_data.py

# Train ML models (XGBoost with walk-forward + Optuna)
python scripts/train_models.py

# Run batch OOS scorecard (evaluates all 20 tradable assets)
python scripts/batch_oos_scorecard.py

# Start the server
uvicorn src.api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npx ng serve --port 4321
```

Open **http://localhost:4321** for the MANTIS AI dashboard.

### Paper Trading

```bash
# Via API (backend must be running)
curl -X POST http://localhost:8000/api/trading/start
curl http://localhost:8000/api/trading/status
curl -X POST http://localhost:8000/api/trading/stop
```

Or use the **Paper Trading** page in the dashboard.

---

## API Reference

| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/health` | System health + data freshness |
| POST | `/api/auth/login` | JWT authentication |
| GET | `/api/dashboard/overview` | Portfolio KPIs + realized P&L |
| GET | `/api/positions/paper` | Open paper positions |
| GET | `/api/positions/closed` | Closed positions history (paginated, filtered) |
| GET | `/api/signals/history` | Signal history |
| POST | `/api/signals/predict/{epic}` | Run ML prediction pipeline |
| GET | `/api/markets/candles/{epic}` | OHLC candle data |
| POST | `/api/backtest/run` | Run walk-forward backtest |
| POST | `/api/trading/start` | Start paper trading loop |
| POST | `/api/trading/stop` | Stop paper trading loop |
| GET | `/api/trading/status` | Paper trading status + regime distribution |
| GET | `/api/trading/performance` | Trading performance stats |
| POST | `/api/trading/emergency-stop` | Emergency kill switch |
| GET | `/api/strategy/` | Strategy configs per asset |
| GET | `/api/models/` | Loaded ML model info |
| WS | `/ws/prices` | Real-time price stream |
| WS | `/ws/trades` | Trade event stream |

Full interactive docs at **http://localhost:8000/docs** (Swagger UI).

---

## Testing

```bash
cd backend

# All tests
python -m pytest tests/ -v

# Quick run, stop on first failure
python -m pytest tests/ -x --no-cov -q

# Specific modules
python -m pytest tests/risk/ -v         # Risk management
python -m pytest tests/strategy/ -v     # Strategy engine
python -m pytest tests/features/ -v     # Feature engineering
python -m pytest tests/external/ -v     # External API clients
python -m pytest tests/backtest/ -v     # Backtesting + scorecard
python -m pytest tests/execution/ -v    # Execution + state recovery
```

**1136 tests** passing (Feb 2026) covering: broker integration, data pipeline, feature engineering, ML models, strategy engine, risk management, execution, API endpoints, external clients, backtest scorecard, paper trading, and alerting.

---

## Development Phases

| Phase | Status | Highlights |
|-------|--------|-----------|
| 1-5 | COMPLETE | Foundation, ML, trading engine, dashboard |
| 6 | COMPLETE | 3-class XGBoost, Optuna, calibration |
| 7-9 | COMPLETE | Paper trading UI, TRADING MAGNA AI (15 improvements), coverage |
| 10 | COMPLETE | MANTIS AI branding, dark theme, OnPush optimization |
| 11 | COMPLETE | 21-asset expansion, monitoring, smart polling |
| 12-13 | COMPLETE | Portfolio expansion (9 to 21), ML training (all assets) |
| 14-16 | COMPLETE | State recovery, UI/UX + avatar, best practices |
| **P0** | **COMPLETE** | Log cleanup, Kelly sizing, first real trading session |
| **P1** | **COMPLETE** | Regime detection, OOS scorecard, sentiment + macro features |
| **P2** | **COMPLETE** | Toast notifications, skeletons, token refresh, mobile UX |
| **P3** | **COMPLETE** | CI/CD, JSON logging, Prometheus/Grafana, security headers |
| **P4** | **COMPLETE** | DEMO readiness: partial close, Telegram alerts, kill switch |
| **Phase 18** | **COMPLETE** | Positions history, performance analytics, P&L fix |
| **Phase 18b-d** | **COMPLETE** | Bug fixes, LoadingButton, broker-closed detection |
| **P5** | **NEXT** | Live trading (2+ weeks demo validation first) |

---

## Documentation

```text
docs/
├── architecture/
│   ├── 01-ARCHITECTURE.md          # System architecture and data flow
│   ├── 08-API-REFERENCE.md         # REST API endpoint documentation
│   └── 14-STATE-RECOVERY.md        # State recovery system design
├── trading/
│   ├── 03-ML-STRATEGY.md           # ML pipeline and model strategy
│   ├── 04-CAPITAL-COM-API.md       # Capital.com broker integration
│   └── 07-TRADING-GURU-SYNTHESIS.md # Advanced trading concepts
├── guides/
│   ├── 05-FRONTEND-GUIDE.md        # Angular frontend development guide
│   └── 06-SETUP-GUIDE.md           # Environment setup instructions
├── planning/
│   ├── 02-DEVELOPMENT-ROADMAP.md   # Full development roadmap
│   └── ROADMAP-NEXT-STEPS.md       # Current status and next steps
└── archive/                         # Historical research docs
```

---

## Configuration

```ini
# .env file
CAPITAL_COM_API_KEY=your_api_key
CAPITAL_COM_EMAIL=your_email
CAPITAL_COM_PASSWORD=your_password
CAPITAL_COM_DEMO=true

# Optional services (system works without them)
DATABASE_URL=postgresql://user:pass@localhost:5432/mantis
REDIS_URL=redis://localhost:6379/0

# Execution mode
EXECUTION_MODE=PAPER  # PAPER, DEMO, or LIVE

# Alerting (off by default)
ALERTS_ENABLED=false
ALERT_TELEGRAM_ENABLED=false
```

---

## License

Private project - All rights reserved.

---

<p align="center">
  <sub>Built with precision by <strong>MANTIS AI</strong></sub>
</p>
