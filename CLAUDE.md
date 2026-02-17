# MANTIS AI - Claude Code Instructions

## Project Overview
MANTIS AI is an AI-powered algorithmic trading platform for **21 assets** across Forex, Crypto, Commodities, Indices, and Stocks using Capital.com as broker (demo).

**Assets**: XAUUSD, BTCUSD, US500, WTIUSD, EURUSD, NVDA, TSLA, XAGUSD, DE40, SOLUSD, ETHUSD, BNBUSD, DOGUSD, DASHUSD, ICPUSD, NATGAS, COPPER, PLATINUM, GBPUSD, USDJPY, NAS100

## Tech Stack
- **Backend**: Python 3.12+ (FastAPI, PyTorch, XGBoost, Polars, numpy)
- **Frontend**: Angular 21 + CoreUI Free Template (Bootstrap 5, TradingView Lightweight Charts, dark mode)
- **Broker**: Capital.com REST API + WebSocket (demo mode)
- **Database**: PostgreSQL (trades, users, RBAC) + DuckDB (market data analytics)
- **Cache/Queue**: Redis (real-time state, pub/sub events) — all DBs optional, graceful degradation
- **ML Models**: XGBoost 3-class (F1 0.53-0.61), 220 features, Optuna tuning, isotonic calibration

## Project Structure
```
AlgoTrader/
├── backend/
│   ├── src/
│   │   ├── api/               # FastAPI endpoints + middleware (GZip, CORS, rate limiting)
│   │   ├── auth/              # Authentication (JWT, RBAC, models, schemas, dependencies)
│   │   ├── audit/             # Audit logging system
│   │   ├── broker/            # Capital.com API wrapper (REST + WebSocket)
│   │   ├── data/              # Data pipeline (collection, cleaning, storage)
│   │   ├── database/          # PostgreSQL session, repositories, backup manager
│   │   ├── features/          # Feature engineering (220 features: technical, candlestick, fibonacci, keltner, vwap, market structure)
│   │   ├── execution/         # Order execution engine + state recovery
│   │   ├── models/            # ML models (XGBoost, LSTM, calibration, tuner, versioning)
│   │   ├── monitoring/        # Health checks, trade logger, log analyzer, alerting, metrics
│   │   ├── risk/              # Risk management (circuit breakers, Kelly, trailing stops, equity curve filter)
│   │   ├── security/          # Encrypted secrets (Fernet), security models
│   │   ├── strategy/          # Strategies (ML, squeeze, VWAP, pairs, strategy router)
│   │   ├── trading/           # Paper trading loop
│   │   └── utils/             # Config, avatar handler, event bus, sanitization
│   ├── tests/                 # 1065+ pytest tests (69% coverage, 80%+ on critical modules)
│   ├── scripts/               # init_permissions.py, promote_user_to_god.py, train/download scripts
│   ├── alembic/               # Database migrations
│   └── data/                  # Local storage (historical, models, avatars, logs, backups)
├── frontend/                  # Angular 21 + CoreUI (MANTIS AI theme)
│   ├── src/app/
│   │   ├── core/              # Services (auth, trading, websocket, market-status, news, monitoring)
│   │   │   ├── guards/        # Auth guard, permission guard (RBAC)
│   │   │   ├── interceptors/  # Auth interceptor (JWT), error interceptor
│   │   │   └── services/      # All injectable services
│   │   ├── shared/            # Reusable components (avatar, avatar-upload, epic-logo, tv-chart, news-widget)
│   │   ├── views/             # Page components (dashboard, markets, positions, signals, backtest, etc.)
│   │   └── layout/            # Default layout with sidebar, header, user dropdown
│   └── src/scss/              # MANTIS AI theme (_custom.scss)
├── docs/                      # Architecture and development docs
└── docker-compose.yml
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
- Use **pip** (venv) for dependency management — NOT poetry
- Use `datetime.now(timezone.utc)` — NEVER `datetime.utcnow()` (deprecated)
- Technical indicators: pure **Polars/numpy** — no ta-lib dependency

### Angular (Frontend)
- Angular 21 with **standalone components** (no NgModules)
- CoreUI Free template as base, MANTIS AI theme (#39FF14 neon green, #0d1117 dark)
- **Strict TypeScript** mode enabled
- Use **Angular Signals** for reactive state management
- Use **Angular HttpClient** with `withFetch()` for API communication
- All components use `ChangeDetectionStrategy.OnPush`
- Use **RxJS** sparingly, prefer Signals where possible
- Fonts: Plus Jakarta Sans (UI), IBM Plex Mono (numbers/KPIs)
- No `console.log` in production code — use `console.error`/`console.warn` only for real errors

### Git Conventions
- Branch naming: `feature/`, `fix/`, `refactor/`, `docs/`
- Commit messages: conventional commits (feat:, fix:, refactor:, docs:, test:)
- Never commit: `.env`, `data/historical/`, `data/models/`, `__pycache__/`, `node_modules/`

### API Design
- Backend exposes REST API via FastAPI on port 8000
- Frontend on port 4321
- All API responses follow envelope: `{ success: bool, data: T, error?: string }`
- Auth: JWT tokens (Bearer), RBAC with roles (VIEWER, TRADER, ADMIN)
- Rate limiting: slowapi on auth endpoints (10/min login, 5/hour register)
- GZip compression on responses > 1KB
- WebSocket for real-time price streaming and trade updates

## Key Design Decisions
1. **Risk-first design** - Every trade must pass risk management checks before execution
2. **Regime detection** - Separate strategies for trending vs ranging markets (StrategyRouter)
3. **Walk-forward optimization** - Rolling window training to avoid overfitting
4. **Paper trading first** - Always validate on demo before live trading
5. **Graceful degradation** - App works without PostgreSQL, Redis, or DuckDB
6. **State recovery** - PAPER→PostgreSQL, DEMO/LIVE→Broker API+DB fallback

## Environment Setup
```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt  # Windows
# OR: py -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ -v  # Run tests

# Frontend
cd frontend
npm install
npx ng serve --port 4321

# Auth setup (after DB migration)
cd backend
.venv/Scripts/python.exe scripts/init_permissions.py   # Create RBAC roles/permissions
.venv/Scripts/python.exe scripts/promote_user_to_god.py # Promote user to ADMIN
```

## Capital.com API
- Demo: `https://demo-api-capital.backend-capital.com/`
- Live: `https://api-capital.backend-capital.com/`
- WebSocket: `wss://api-streaming-capital.backend-capital.com/connect`
- Auth: API key + email + password → CST + X-SECURITY-TOKEN (10min expiry)
- Epic mapping: XAUUSD→GOLD, XAGUSD→SILVER, WTIUSD→OIL_CRUDE
- OHLC prices: `{bid, ask}` dicts → use mid-price
- Rate limit: 10 req/sec, max 40 WebSocket subscriptions, 1000 orders/hour (demo)
