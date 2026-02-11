# AlgoTrader AI - Claude Code Instructions

## Project Overview
AlgoTrader AI is an AI-powered algorithmic trading system specialized for **Gold (XAUUSD)**, **Bitcoin (BTCUSD)**, and **S&P 500 (US500)** using Capital.com as broker.

## Tech Stack
- **Backend**: Python 3.12+ (FastAPI, PyTorch, scikit-learn, pandas, numpy)
- **Frontend**: Angular 21 + CoreUI Free Template (Bootstrap 5, Chart.js, dark mode)
- **Broker**: Capital.com REST API + WebSocket (demo first, then live)
- **Database**: PostgreSQL (trades/account data) + DuckDB (market data analytics)
- **Cache/Queue**: Redis (real-time state, pub/sub events)
- **ML Models**: LSTM, Transformer (TFT), XGBoost/LightGBM ensemble

## Project Structure
```
AlgoTrader/
├── backend/                    # Python backend
│   ├── src/
│   │   ├── api/               # FastAPI endpoints (REST API for frontend)
│   │   ├── broker/            # Capital.com API wrapper (REST + WebSocket)
│   │   ├── data/              # Data pipeline (collection, cleaning, storage)
│   │   ├── features/          # Feature engineering (technical, sentiment, macro)
│   │   ├── models/            # ML models (LSTM, Transformer, XGBoost, ensemble)
│   │   ├── strategy/          # Trading strategies and signal generation
│   │   ├── risk/              # Risk management (position sizing, stops, drawdown)
│   │   ├── execution/         # Order execution engine
│   │   ├── backtest/          # Backtesting engine with walk-forward optimization
│   │   ├── monitoring/        # System health, P&L tracking, alerts
│   │   └── utils/             # Shared utilities and helpers
│   ├── tests/                 # pytest test suite
│   ├── data/                  # Local data storage
│   │   ├── historical/        # Historical OHLC data (parquet files)
│   │   ├── models/            # Saved ML model weights
│   │   └── cache/             # Temporary cache files
│   ├── notebooks/             # Jupyter notebooks for research/EDA
│   └── config/                # Configuration files
├── frontend/                  # Angular 21 + CoreUI dashboard
├── docs/                      # Architecture and development docs
├── scripts/                   # Utility scripts (setup, data download, etc.)
└── docker-compose.yml         # Container orchestration
```

## Development Conventions

### Python (Backend)
- Use **Python 3.12+** with type hints everywhere
- Follow **PEP 8** with max line length 100
- Use **async/await** for I/O-bound operations (API calls, WebSocket, DB)
- Use **Pydantic v2** models for all data validation and serialization
- Use **pytest** for testing with minimum 80% coverage on critical paths
- Use **loguru** for structured logging
- Configuration via **pydantic-settings** with `.env` files (never commit secrets)
- Use **poetry** for dependency management

### Angular (Frontend)
- Angular 21 with **standalone components** (no NgModules)
- CoreUI Free template as base
- **Strict TypeScript** mode enabled
- Use **Angular Signals** for reactive state management
- Use **Angular HttpClient** with interceptors for API communication
- Follow Angular style guide (feature-based folder structure)
- Use **RxJS** sparingly, prefer Signals where possible

### Git Conventions
- Branch naming: `feature/`, `fix/`, `refactor/`, `docs/`
- Commit messages: conventional commits (feat:, fix:, refactor:, docs:, test:)
- Never commit: `.env`, `data/historical/`, `data/models/`, `__pycache__/`, `node_modules/`

### API Design
- Backend exposes REST API via FastAPI on port 8000
- Frontend communicates with backend via HTTP + WebSocket
- All API responses follow a consistent envelope: `{ success: bool, data: T, error?: string }`
- Use WebSocket for real-time price streaming and trade updates

## Key Design Decisions
1. **Event-driven architecture** - Components communicate via Redis pub/sub events
2. **Ensemble ML approach** - LSTM + Transformer + XGBoost stacking for each asset
3. **Walk-forward optimization** - Rolling window training to avoid overfitting
4. **Paper trading first** - Always validate on demo before live trading
5. **Risk-first design** - Every trade must pass risk management checks before execution
6. **Regime detection** - Separate models/parameters for different market regimes

## Asset-Specific Notes
- **Gold (XAUUSD)**: Driven by macro factors (inflation, rates, geopolitics). Include FRED data.
- **Bitcoin (BTCUSD)**: High volatility (~2.3% daily). Gold price is top predictor. Include blockchain metrics.
- **S&P 500 (US500)**: Benefits from stacking ensembles. Include earnings/sentiment data.

## Capital.com API
- Demo: `https://demo-api-capital.backend-capital.com/`
- Live: `https://api-capital.backend-capital.com/`
- WebSocket: `wss://api-streaming-capital.backend-capital.com/connect`
- Auth: API key + session tokens (CST + X-SECURITY-TOKEN), 10min expiry
- Rate limit: 10 req/sec, max 40 WebSocket subscriptions
- Epics: search via `GET /api/v1/markets?searchTerm=...`
