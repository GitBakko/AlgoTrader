<p align="center">
  <img src="frontend/src/assets/favicon.svg" width="80" height="80" alt="MANTIS AI Logo">
</p>

<h1 align="center">MANTIS AI</h1>

<p align="center">
  <strong>AI-Powered Algorithmic Trading Platform</strong><br>
  <sub>21 instruments &bull; ML-Primary strategy &bull; Real-time risk management &bull; Capital.com broker</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/angular-21-dd0031?logo=angular&logoColor=white" alt="Angular">
  <img src="https://img.shields.io/badge/tests-2300+_passing-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/ML-XGBoost_220+_features-9cf" alt="ML">
  <img src="https://img.shields.io/badge/broker-Capital.com-orange" alt="Broker">
  <img src="https://img.shields.io/github/actions/workflow/status/GitBakko/AlgoTrader/ci.yml?label=CI&logo=github" alt="CI">
</p>

---

## What is MANTIS AI?

MANTIS AI is a full-stack algorithmic trading system that combines **XGBoost machine learning** with a 7-indicator technical quality gate to trade **21 financial instruments** across 5 asset classes. Like its namesake predator, the system is patient, precise, and strikes only with high confidence.

The platform runs on **Capital.com** (demo/live), features a professional Angular dashboard with real-time WebSocket updates, and includes a Telegram bot for remote monitoring and control.

### Traded Instruments

| Forex | Crypto | Commodities | Indices | Stocks |
|:-----:|:------:|:-----------:|:-------:|:------:|
| EURUSD | BTCUSD | XAUUSD (Gold) | US500 | NVDA |
| GBPUSD | ETHUSD | XAGUSD (Silver) | DE40 | TSLA |
| USDJPY | SOLUSD | WTIUSD (Oil) | NAS100 | |
| | BNBUSD | NATGAS | | |
| | DOGUSD | COPPER | | |
| | DASHUSD | PLATINUM | | |
| | ICPUSD | | | |

---

## Key Features

### ML-Primary Strategy Engine

- **ML decides direction** &mdash; XGBoost 3-class classifier (BUY/HOLD/SELL) with 220+ features is the primary decision maker
- **ScalpScore quality gate** &mdash; 7-vote technical indicator system (EMA, RSI, MACD, BB/Keltner, Volume, ADX, Sentiment) validates ML signals
- **Composite confidence** &mdash; `ML_confidence x technical_quality x gate_penalties` determines position sizing
- **Feature-flagged** &mdash; `ML_PRIMARY_ENABLED=true/false` for instant rollback to legacy ScalpScore mode
- **Per-asset models** &mdash; each of the 21 instruments has its own trained XGBoost model with Optuna-tuned hyperparameters

### Training Dashboard

- **In-app training management** &mdash; retrain all models or cherry-pick individual assets from the UI
- **Parallel training** &mdash; 2-3 concurrent jobs with real-time progress bar and WebSocket status updates
- **Extended historical data** &mdash; auto-download from yfinance (stocks/forex/commodities) and CryptoCompare (crypto) for multi-year training
- **Hot model reload** &mdash; new models go live automatically after training, no restart needed
- **P&L per asset table** &mdash; sorted worst-to-best with F1 scores and model info hover cards
- **Training notifications** &mdash; Telegram + in-app alerts for start/complete/fail events
- **Backtest integration** &mdash; launch backtest directly from completed training jobs

### Risk Management

| Layer | Description |
|-------|-------------|
| **Circuit Breakers** | 6 types: daily loss, consecutive losses, max positions, slippage anomaly, heartbeat timeout, volatility spike |
| **Epic SL Cooldown** | Progressive penalty after repeated SL hits: 1 SL = 0.70x, 2 SL = 0.40x, 3+ SL = blocked (2h window) |
| **Trailing Stops** | 4-phase: Initial &rarr; Breakeven &rarr; TP1 Lock &rarr; ATR Trailing |
| **Multi-Target Exit** | TP1 (1:1 R:R) with 50% partial close, TP2 (2:1) full exit |
| **Kelly Sizing** | Adaptive half-Kelly with fixed-fractional fallback (30-trade minimum) |
| **Equity Curve Filter** | SMA(20 trades), 50% size reduction when underperforming |
| **Correlation Guard** | Prevents over-exposure to correlated assets |
| **Smart SL/TP** | Auto-corrects broker-rejected stop levels, fallback to post-fill stop setting |

### Dashboard & Monitoring

- **13 views** &mdash; Dashboard, Paper Trading, Positions, Signals, Markets, News, Backtest, Strategy, AI Models + Training, Trade Journal, Settings, System Logs
- **Real-time data** &mdash; WebSocket price streaming, live P&L in header, instant trade notifications
- **TradingView charts** &mdash; Lightweight Charts v5.1+ with multi-timeframe support
- **Signal audit drawer** &mdash; click any signal/position to see full ML prediction breakdown, technical votes, risk check details, and live broker position data
- **Mobile responsive** &mdash; bottom nav, scroll strips, 44px touch targets
- **Dark + Light themes** &mdash; MANTIS AI design system with 6-level surface elevation
- **Auth** &mdash; JWT + RBAC (3 roles, 30+ permissions), avatar upload

### Telegram Bot

Interactive bot for remote monitoring and control:

| Command | Description |
|---------|-------------|
| `/status` | Live equity, P&L, positions, win rate, CB status, SL cooldowns |
| `/reset` | Reset all circuit breakers |
| `/stop` | Emergency stop (close all positions) |
| `/help` | Command reference |

Automatic alerts for: trade opened (with direction arrows), trade closed (with P&L), circuit breaker trips, epic cooldowns, training events.

---

## Architecture

```
                              MANTIS AI Architecture

  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐    ┌────────────┐
  │  Angular 21  │  REST   │   FastAPI     │         │ Capital.com  │    │  Telegram  │
  │  MANTIS UI   │◄───────►│  Python 3.12  │◄───────►│  REST + WS   │    │    Bot     │
  │  CoreUI+LWC  │   WS    │  15 Routers   │         │  21 Assets   │    │ /status    │
  └──────────────┘         └──────┬────────┘         └──────────────┘    └────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
  ┌─────┴──────┐  ┌──────────────┴┐  ┌──────────────┐  ┌──┴───────────┐  ┌────────────┐
  │ ML Models  │  │   Strategy    │  │  Risk Stack  │  │  Execution   │  │  Training  │
  │            │  │               │  │              │  │              │  │            │
  │ XGBoost    │  │ ML-Primary    │  │ 6 Circuit    │  │ Paper/DEMO   │  │ Parallel   │
  │ 220+ feat  │  │ ScalpScore QG │  │ Breakers     │  │ Live modes   │  │ Orchestr.  │
  │ Optuna     │  │ Regime Router │  │ SL Cooldown  │  │ State Recov. │  │ Hot Reload │
  │ Calibr.    │  │ Squeeze/VWAP  │  │ Kelly Sizing │  │ Smart SL/TP  │  │ yfinance   │
  └─────┬──────┘  └───────────────┘  │ Trailing 4ph │  │ Partial Close│  │ CryptoCmp  │
        │                             └──────────────┘  └──────────────┘  └────────────┘
  ┌─────┴──────┐  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐
  │ Data Layer │  │ Feature Eng.  │  │ External API │  │ Monitoring   │  │  Storage   │
  │            │  │               │  │              │  │              │  │            │
  │ Capital.com│  │ 220+ features │  │ Finnhub      │  │ Prometheus   │  │ PostgreSQL │
  │ yfinance   │  │ Technical     │  │ Marketaux    │  │ Grafana      │  │ Redis      │
  │ CryptoCmp  │  │ Sentiment SIL │  │ FRED/COT     │  │ JSON Logging │  │ DuckDB     │
  │ Parquet    │  │ Macro overlay │  │ Alpha Vant.  │  │ Trade Audit  │  │ Parquet    │
  └────────────┘  └───────────────┘  └──────────────┘  └──────────────┘  └────────────┘

  Signal Flow: Data → Features (220+) → ML Predict → ScalpScore QG → Risk → Execute → Track

  21 Instruments  ·  220+ ML Features  ·  2300+ Tests  ·  7 Risk Layers  ·  24/7 Crypto
```

---

## Tech Stack

| Layer | Technologies |
|:------|:------------|
| **Backend** | Python 3.12+, FastAPI, Pydantic v2, Loguru, asyncio |
| **ML** | XGBoost, PyTorch (LSTM), scikit-learn, Optuna, isotonic calibration |
| **Data** | Polars, Parquet, DuckDB, Redis, yfinance, CryptoCompare |
| **Database** | PostgreSQL 16, SQLAlchemy 2.0, Alembic (all optional, graceful degradation) |
| **Frontend** | Angular 21, CoreUI Free, TradingView Lightweight Charts, SCSS design system |
| **Broker** | Capital.com REST API + WebSocket (demo + live) |
| **Monitoring** | Prometheus + Grafana, Telegram Bot, JSON structured logging |
| **CI/CD** | GitHub Actions (ruff + black lint, 2300+ tests, frontend build, Docker build) |

---

## Quick Start

### Prerequisites

- Python 3.12+ &bull; Node.js 22+ &bull; Capital.com demo account

### Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate  # Windows
pip install -r requirements.txt

cp .env.example .env  # Configure credentials

python scripts/download_data.py     # Historical data (21 assets)
python scripts/train_models.py      # Train ML models
uvicorn src.api.main:app --port 8000
```

### Frontend

```bash
cd frontend
npm install
npx ng serve --port 4321
```

Open **http://localhost:4321** &mdash; the MANTIS AI dashboard.

### Start Trading

```bash
curl -X POST http://localhost:8000/api/trading/start
```

Or use the **Paper Trading** page in the dashboard.

---

## API Highlights

| Method | Endpoint | Description |
|:------:|:--------|:------------|
| `POST` | `/api/trading/start` | Start trading loop (DEMO/PAPER) |
| `GET` | `/api/trading/status` | Full status: positions, P&L, CB, regime |
| `POST` | `/api/trading/emergency-stop` | Kill switch: stop + close all |
| `GET` | `/api/dashboard/overview` | Equity, daily P&L, win rate |
| `POST` | `/api/models/training/start` | Retrain all/selected models |
| `GET` | `/api/models/training/status` | Training progress (WebSocket-enabled) |
| `POST` | `/api/models/training/start/{epic}` | Retrain single asset model |
| `POST` | `/api/models/data/download-extended/{epic}` | Download extended historical data |
| `GET` | `/api/signals/audit/{id}` | Full signal audit trail |
| `WS` | `/ws/prices` | Real-time price stream |
| `WS` | `/ws/trades` | Trade event stream |
| `WS` | `/ws/training` | Training status updates |

Full interactive docs at **http://localhost:8000/docs** (Swagger UI).

---

## Project Structure

```
AlgoTrader/
├── backend/
│   ├── src/
│   │   ├── api/               # 15 REST routers + WebSocket + middleware
│   │   ├── auth/              # JWT + RBAC (3 roles, 30+ permissions)
│   │   ├── broker/            # Capital.com API wrapper (REST + WS)
│   │   ├── data/              # Parquet storage, DuckDB, extended data providers
│   │   ├── external/          # Finnhub, Marketaux, yfinance, CryptoCompare clients
│   │   ├── features/          # 220+ features (Polars, pure numpy)
│   │   ├── models/            # XGBoost, LSTM, calibration, tuner, training orchestrator
│   │   ├── strategy/          # ML-Primary, ScalpScore, Squeeze, VWAP, Pairs, Router
│   │   ├── risk/              # Circuit breakers, Kelly, trailing stops, SL cooldown
│   │   ├── execution/         # Paper + DEMO + live, state recovery, smart SL/TP retry
│   │   ├── backtest/          # Walk-forward, Monte Carlo, scorecard
│   │   ├── trading/           # Paper trading loop (21 assets, 24/7 crypto)
│   │   ├── monitoring/        # Telegram bot, alerting, health, metrics
│   │   ├── agents/            # Multi-agent architecture (evolution)
│   │   ├── drl/               # Deep RL ensemble (evolution)
│   │   └── utils/             # Config, constants, event bus
│   ├── tests/                 # 2300+ pytest tests
│   └── data/                  # Parquet files, trained models, logs
├── frontend/                  # Angular 21 MANTIS AI dashboard
│   ├── src/app/
│   │   ├── core/              # Services, guards, interceptors
│   │   ├── shared/            # Chart, avatar, epic-logo, signal-audit-drawer
│   │   ├── views/             # 13 page components
│   │   └── layout/            # Sidebar, header (P&L pills), footer, bottom-nav
│   └── src/scss/              # MANTIS AI design system (dark + light themes)
├── infra/                     # Prometheus config, Grafana dashboards
├── docs/                      # Architecture, trading, guides, plans
└── docker-compose.yml         # Dev stack (PG, Redis, backend, frontend)
```

---

## Testing

```bash
cd backend
python -m pytest tests/ -v                    # Full suite (2300+ tests)
python -m pytest tests/ -x --no-cov -q        # Quick run, stop on first failure
python -m pytest tests/strategy/ -v            # Strategy engine only
python -m pytest tests/risk/ -v                # Risk management only
python -m pytest tests/models/ -v              # ML models + training orchestrator
```

---

## Configuration

```ini
# Core
EXECUTION_MODE=DEMO                    # PAPER, DEMO, or LIVE
ML_PRIMARY_ENABLED=true                # ML decides direction (vs ScalpScore legacy)
SCALP_MODE_ENABLED=true                # Enable ScalpScore quality gate

# Broker (Capital.com)
CAPITAL_DEMO_API_KEY=your_key
CAPITAL_DEMO_EMAIL=your_email
CAPITAL_DEMO_PASSWORD=your_password

# Optional services (graceful degradation)
DATABASE_URL=postgresql://...          # PostgreSQL for positions/trades
REDIS_URL=redis://localhost:6379       # Redis for caching

# Monitoring
ALERTS_ENABLED=true
ALERT_TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# External data (all free tier)
FINNHUB_API_KEY=your_key               # Equity data
MARKETAUX_API_KEY=your_key             # News sentiment
```

---

## License

Private project &mdash; All rights reserved.

---

<p align="center">
  <sub>Built with precision by <strong>MANTIS AI</strong> &bull; Powered by XGBoost &bull; Broker: Capital.com</sub>
</p>
