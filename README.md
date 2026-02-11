# AlgoTrader AI

AI-powered algorithmic trading system for **Gold (XAUUSD)**, **Bitcoin (BTCUSD)**, and **S&P 500 (US500)** using machine learning and Capital.com as broker.

## Features

- **ML-Driven Signals** -- XGBoost classifier with walk-forward optimization, confidence calibration, and multi-timeframe features (1h + 4h + 1d)
- **3-Class Prediction** -- SELL / HOLD / BUY with ATR-relative thresholds and isotonic confidence calibration (F1 macro ~0.54)
- **Risk Management** -- ATR-based position sizing, dynamic stop-loss/take-profit, drawdown circuit breaker (5% daily / 15% total), correlation exposure limits
- **Paper Trading Loop** -- Continuous background pipeline: ML prediction -> strategy signal -> risk check -> paper execution
- **Real-Time Dashboard** -- Angular 21 + CoreUI with live prices, positions, signals, equity curves, and model performance
- **Event-Driven Architecture** -- Redis pub/sub for real-time events, PostgreSQL for persistence, DuckDB for analytics
- **Graceful Degradation** -- System runs without broker, Redis, or PostgreSQL (in-memory fallback for all services)

## Architecture

```
Frontend (Angular 21 + CoreUI)
    |
    | REST API + WebSocket
    v
FastAPI Backend (Python 3.12+)
    |
    +-- Broker Integration (Capital.com REST + WS)
    +-- Data Pipeline (Parquet + DuckDB + Redis)
    +-- Feature Engineering (60+ technical indicators)
    +-- ML Models (XGBoost, LSTM, Calibration)
    +-- Strategy Engine (Signal generation + regime adaptation)
    +-- Risk Management (Position sizing + circuit breakers)
    +-- Execution Engine (Paper + Live modes)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, Pydantic v2 |
| ML | XGBoost, PyTorch (LSTM), scikit-learn |
| Data | Polars, Parquet, DuckDB, Redis |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Frontend | Angular 21, CoreUI Free, Chart.js |
| Broker | Capital.com REST API + WebSocket |

## Project Structure

```
AlgoTrader/
+-- backend/
|   +-- src/
|   |   +-- api/           # FastAPI REST + WebSocket endpoints
|   |   +-- broker/        # Capital.com API wrapper
|   |   +-- data/          # Parquet storage, DuckDB, data pipeline
|   |   +-- features/      # Technical indicators, normalization
|   |   +-- models/        # XGBoost, LSTM, calibration, training
|   |   +-- strategy/      # Signal generation, regime adaptation
|   |   +-- risk/          # Position sizing, stops, circuit breaker
|   |   +-- execution/     # Order management, paper/live execution
|   |   +-- backtest/      # Walk-forward backtesting engine
|   |   +-- monitoring/    # Health checks, system monitoring
|   |   +-- trading/       # Paper trading loop
|   |   +-- utils/         # Config, logging, event bus
|   +-- tests/             # 456 tests (pytest)
|   +-- scripts/           # CLI tools (download, train, verify)
|   +-- data/              # Parquet files + saved models
+-- frontend/              # Angular 21 dashboard
+-- docs/                  # Architecture, roadmap, API reference
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+ (for frontend)
- Capital.com demo account

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Capital.com credentials

# Download historical data
python scripts/download_data.py

# Train ML models
python scripts/train_models.py

# Start the server
python -m src.api.main
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npx ng serve
```

Open http://localhost:4200 for the dashboard.

### Paper Trading

```bash
# Start backend (auto-loads trained models)
cd backend && python -m src.api.main

# Start paper trading via API
curl -X POST http://localhost:8000/api/trading/start

# Check status
curl http://localhost:8000/api/trading/status

# Stop
curl -X POST http://localhost:8000/api/trading/stop
```

## ML Pipeline

| Stage | Description |
|-------|------------|
| Data | Parquet storage with monthly partitioning, 60+ technical indicators |
| Features | Multi-timeframe (1h/4h/1d), rolling z-score normalization, regime detection |
| Target | 3-class ATR-relative: SELL (<-0.5 ATR), HOLD, BUY (>+0.5 ATR) |
| Training | Walk-forward optimization (252d train / 63d val / 21d test, purge + embargo) |
| Model | XGBoost (F1 ~0.54), with isotonic confidence calibration |
| Inference | Cached data access (3600x speedup), feature build, predict, calibrate |

## API Endpoints

| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/health` | System health + data freshness |
| GET | `/api/dashboard/overview` | Portfolio overview + P&L |
| GET | `/api/positions/` | Open positions |
| GET | `/api/signals/` | Active signals |
| POST | `/api/signals/predict/{epic}` | Run ML prediction |
| GET | `/api/markets/candles/{epic}` | OHLC candles |
| POST | `/api/trading/start` | Start paper trading |
| POST | `/api/trading/stop` | Stop paper trading |
| GET | `/api/trading/status` | Paper trading status |
| WS | `/ws/prices` | Real-time price stream |

Full API docs at http://localhost:8000/docs (Swagger UI).

## Testing

```bash
cd backend

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html

# Run specific module
python -m pytest tests/models/ -v
```

456 tests covering broker integration, data pipeline, features, ML models, strategy, risk, execution, API endpoints, and integration flows.

## Development Status

| Phase | Status | Key Deliverables |
|-------|--------|-----------------|
| 1. Foundation | COMPLETE | Broker integration, data pipeline, database |
| 2. Intelligence | COMPLETE | Features, XGBoost, backtesting |
| 3. Trading Engine | COMPLETE | Strategy, risk management, execution |
| 4. Dashboard | COMPLETE | Angular 21 + CoreUI, 8 pages |
| 5. Integration | COMPLETE | End-to-end wiring, paper trading |
| 6A. ML Upgrades | COMPLETE | 3-class migration, calibration, LSTM, multi-TF |
| 6B. Ensemble | NEXT | TFT, stacking, hyperopt |
| 7. Live Trading | FUTURE | Performance tuning, live deployment |

## Configuration

Key environment variables (`.env`):

```ini
# Capital.com
CAPITAL_COM_API_KEY=your_api_key
CAPITAL_COM_EMAIL=your_email
CAPITAL_COM_PASSWORD=your_password
CAPITAL_COM_DEMO=true

# Database (optional - system works without)
DATABASE_URL=postgresql://user:pass@localhost:5432/algotrader

# Redis (optional - system works without)
REDIS_URL=redis://localhost:6379/0
```

## License

Private project -- all rights reserved.
