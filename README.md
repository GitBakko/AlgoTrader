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
  <img src="https://img.shields.io/badge/tests-865_passing-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-80%25-green" alt="Coverage">
  <img src="https://img.shields.io/badge/assets-9_instruments-blueviolet" alt="Assets">
  <img src="https://img.shields.io/badge/broker-Capital.com-orange" alt="Broker">
</p>

---

## Overview

MANTIS AI is a full-stack algorithmic trading system that combines **XGBoost ML models** with advanced risk management to trade 9 financial instruments on Capital.com. Like its namesake predator, the system is patient, precise, and strikes only with high confidence.

### Traded Instruments

| Forex | Commodities | Indices | Stocks |
|-------|------------|---------|--------|
| EURUSD | XAUUSD (Gold) | US500 (S&P 500) | NVDA |
| | XAGUSD (Silver) | DE40 (DAX) | TSLA |
| | WTIUSD (Oil) | | |

### Key Metrics (Walk-Forward Out-of-Sample)

| Asset | Return | Sharpe | Win Rate | Max DD | MC p-value |
|-------|--------|--------|----------|--------|------------|
| BTCUSD | +56.05% | 16.93 | 80.4% | 0.35% | 0.0000 |
| XAUUSD | +12.87% | 14.58 | 80.2% | 0.64% | 0.0000 |
| US500 | +5.95% | 18.03 | 78.3% | 0.11% | 0.0000 |

All results include realistic trading costs (spreads, slippage, overnight fees) and are validated via Monte Carlo simulation (10K permutations, sign-flip test).

---

## Features

### ML Pipeline
- **XGBoost 3-class classifier** (BUY / HOLD / SELL) with Optuna hyperparameter tuning
- **220 features**: technical indicators, candlestick patterns, Fibonacci clusters, market structure (BOS/CHoCH), Keltner channels, VWAP bands, multi-timeframe (1h + 4h + 1d)
- **Walk-forward optimization** with train/val/test split, purge, and embargo
- **Isotonic confidence calibration** for reliable probability estimates
- **F1 macro**: 0.53-0.61 across assets

### Risk Management (TRADING MAGNA AI)
- **6 Circuit Breakers**: daily loss, consecutive losses, max positions, slippage anomaly, heartbeat timeout, volatility spike
- **4-Phase Trailing Stop**: Initial -> Breakeven -> TP1 Lock -> ATR Trailing
- **Multi-Target Exit**: TP1 (1xR) with 50% partial close, TP2 (2xR) full exit
- **Adaptive Kelly Position Sizing**: half-Kelly with 30-trade minimum, fixed-fractional fallback
- **Equity Curve Filter**: SMA(20 trades), 50% size reduction when underperforming
- **ADX Pre-Signal Filter**: reject choppy markets (ADX < 20), boost trending (ADX > 25)

### Strategy Engine
- **Regime-based Strategy Router**: trending -> ML, ranging -> [Squeeze, VWAP, ML]
- **Volatility Squeeze Breakout**: BB-inside-KC detection with momentum/volume confirmation
- **VWAP Reversion**: mean-reversion at +/-2 SD bands in ranging markets
- **Pairs Trading**: Gold-BTC cointegration with z-score entry/exit (dollar-neutral)
- **Monte Carlo Validation**: permutation, bootstrap, sign-flip tests with confidence intervals

### Dashboard
- **Angular 21 + CoreUI** with MANTIS AI dark theme (neon green accents)
- **9 pages**: Dashboard, Paper Trading, Backtest, Positions, Signals, Markets, Strategy, AI Models, Settings
- **Real-time**: WebSocket price streaming, live P&L updates
- **TradingView Lightweight Charts** for candlestick visualization
- **OnPush change detection** + route preloading for optimal performance

---

## Architecture

```
                    MANTIS AI - System Architecture

    +------------------+         +-------------------+
    |   Angular 21     |  REST   |   FastAPI Backend  |
    |   MANTIS Theme   | <-----> |   Python 3.12+     |
    |   CoreUI + LWC   |   WS    |                    |
    +------------------+         +--------+-----------+
                                          |
              +---------------------------+---------------------------+
              |              |            |            |              |
        +-----+----+  +-----+----+ +-----+----+ +----+-----+ +-----+----+
        |  Broker   |  |   Data   | | Features | |    ML    | | Strategy |
        | Capital   |  | Pipeline | |  Engine  | |  Models  | |  Router  |
        |  .com     |  | Parquet  | | 220 feat | | XGBoost  | |  Regime  |
        |  REST+WS  |  | DuckDB   | | Multi-TF | | Calibr.  | |  Based   |
        +-----------+  +----------+ +----------+ +----------+ +----------+
              |              |            |            |              |
              +---------------------------+---------------------------+
                                          |
                            +-------------+-------------+
                            |        Risk Stack         |
                            | CircuitBreakers -> Equity |
                            | -> Kelly -> TrailingStop  |
                            +---------------------------+
                                          |
                            +-------------+-------------+
                            |     Execution Engine      |
                            |  Paper + Live + Partial   |
                            +---------------------------+
```

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.12+, FastAPI, Pydantic v2, Loguru |
| **ML** | XGBoost, PyTorch (LSTM), scikit-learn, Optuna |
| **Data** | Polars, Parquet, DuckDB, Redis |
| **Database** | PostgreSQL, SQLAlchemy |
| **Frontend** | Angular 21, CoreUI Free, TradingView LWC |
| **Broker** | Capital.com REST API + WebSocket |

---

## Project Structure

```
mantis-ai/
+-- backend/
|   +-- src/
|   |   +-- api/             # 8 REST routers + WebSocket
|   |   +-- broker/          # Capital.com API wrapper
|   |   +-- data/            # Parquet storage, DuckDB analytics
|   |   +-- features/        # 220 technical features (Polars)
|   |   +-- models/          # XGBoost, LSTM, calibration, Optuna
|   |   +-- strategy/        # ML, Squeeze, VWAP, Pairs strategies
|   |   +-- risk/            # Circuit breakers, Kelly, trailing stops
|   |   +-- execution/       # Paper + live execution, partial close
|   |   +-- backtest/        # Walk-forward engine, Monte Carlo
|   |   +-- trading/         # Paper trading loop
|   |   +-- utils/           # Config, event bus, logging
|   +-- tests/               # 865 tests (pytest, 80% coverage)
|   +-- scripts/             # download, train, backtest, verify
|   +-- data/                # Parquet files + saved models
+-- frontend/                # Angular 21 MANTIS AI dashboard
+-- docs/                    # Architecture, API, ML strategy docs
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

# Download historical data (9 assets x 3 timeframes)
python scripts/download_data.py

# Train ML models (XGBoost with Optuna tuning)
python scripts/train_models.py

# Start the server
python -m src.api.main
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

Or use the **Paper Trading** page in the dashboard for start/stop controls and live monitoring.

### Walk-Forward Backtest

```bash
cd backend

# Basic backtest
python scripts/walk_forward_backtest.py --epic XAUUSD

# With Optuna tuning + Monte Carlo validation
python scripts/walk_forward_backtest.py --epic BTCUSD --tune --monte-carlo

# Strategy router (regime-based switching)
python scripts/walk_forward_backtest.py --epic US500 --strategy router
```

---

## API Reference

| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/health` | System health + data freshness |
| GET | `/api/dashboard/overview` | Portfolio overview + P&L |
| GET | `/api/positions/` | Open positions |
| GET | `/api/signals/` | Active signals |
| POST | `/api/signals/predict/{epic}` | Run ML prediction pipeline |
| GET | `/api/markets/candles/{epic}` | OHLC candle data |
| POST | `/api/backtest/run` | Run walk-forward backtest |
| POST | `/api/trading/start` | Start paper trading loop |
| POST | `/api/trading/stop` | Stop paper trading loop |
| GET | `/api/trading/status` | Paper trading status + metrics |
| GET | `/api/strategy/` | Strategy configs per asset |
| GET | `/api/models/` | Loaded ML model info |
| GET | `/api/settings/system` | System settings + risk status |
| WS | `/ws/prices` | Real-time price stream |
| WS | `/ws/trades` | Trade event stream |

Full interactive docs at **http://localhost:8000/docs** (Swagger UI).

---

## Testing

```bash
cd backend

# All tests
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=src --cov-report=html

# Specific modules
python -m pytest tests/risk/ -v         # Risk management
python -m pytest tests/strategy/ -v     # Strategy engine
python -m pytest tests/models/ -v       # ML models
```

**865 tests** covering: broker integration, data pipeline, feature engineering, ML models, strategy engine, risk management, execution, API endpoints, integration flows, and paper trading.

---

## Development Phases

| Phase | Status | Highlights |
|-------|--------|-----------|
| 1. Foundation | COMPLETE | Broker integration, data pipeline, database |
| 2. Intelligence | COMPLETE | Feature engineering, XGBoost, backtesting |
| 3. Trading Engine | COMPLETE | Strategy, risk management, execution |
| 4. Dashboard | COMPLETE | Angular 21 + CoreUI, 8 pages |
| 5. Integration | COMPLETE | End-to-end wiring, paper trading loop |
| 6. ML Optimization | COMPLETE | 3-class, Optuna, multi-TF, calibration, 9 assets |
| 7. Paper Trading UI | COMPLETE | Live dashboard, KPI cards, signal history |
| 8. TRADING MAGNA AI | COMPLETE | 15 improvements: circuit breakers, trailing stops, Kelly, squeeze, VWAP, pairs, Monte Carlo |
| 9. Integration + Coverage | COMPLETE | Full wiring, 865 tests, 80% coverage |
| 10. MANTIS AI Branding | COMPLETE | Dark theme, neon green, SVG logo, OnPush optimization |
| 14. State Recovery | COMPLETE | Multi-source recovery, broker/DB fallback, auto-persistence, monitoring API, performance indexes |

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
```

---

## License

Private project - All rights reserved.

---

<p align="center">
  <sub>Built with precision by <strong>MANTIS AI</strong></sub>
</p>
