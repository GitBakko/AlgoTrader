# MANTIS AI - Setup Guide

## Prerequisites

### System Requirements

- **Python**: 3.12+
- **Node.js**: 22+ (LTS recommended, tested with v25.2.1)
- **npm**: 10+
- **Docker**: 24+ with Docker Compose v2 (optional)
- **Git**: 2.40+

### Accounts Required

- **Capital.com**: Trading account (demo is sufficient to start)
  - Enable 2FA
  - Generate API key at Settings > API integrations

---

## Quick Start

### 1. Clone & Configure

```bash
git clone <repo-url> AlgoTrader
cd AlgoTrader

# Create environment file
cp .env.example .env
# Edit .env with your credentials (see Environment Variables below)
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/macOS)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend
uvicorn src.api.main:app --reload --port 8000
```

The backend starts with **graceful degradation**: PostgreSQL, Redis, and broker connection are all optional. Without them, the system falls back to in-memory storage and mock prices.

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server (port 4321)
npx ng serve

# Open browser at http://localhost:4321
```

### 4. Docker Setup (Alternative)

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f mantis-backend
```

---

## Environment Variables

Create `.env` in the project root:

```env
# ===== Capital.com API =====
CAPITAL_API_KEY=your_api_key_here
CAPITAL_API_PASSWORD=your_api_password_here
CAPITAL_EMAIL=your_email@example.com
CAPITAL_ENVIRONMENT=demo  # demo or live

# ===== Database (optional - falls back to in-memory) =====
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mantis
POSTGRES_USER=mantis
POSTGRES_PASSWORD=your_secure_password

# ===== Redis (optional - falls back to in-memory) =====
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# ===== ML Settings =====
ML_DEVICE=cpu  # cpu or cuda
ML_MODELS_DIR=./data/models

# ===== Risk Management =====
RISK_MAX_PER_TRADE=0.01        # 1% max risk per trade
RISK_MAX_TOTAL_EXPOSURE=0.10   # 10% max total exposure
RISK_MAX_DRAWDOWN=0.15         # 15% max drawdown before halt
RISK_DAILY_LOSS_LIMIT=0.03     # 3% daily loss circuit breaker

# ===== Logging =====
LOG_LEVEL=INFO
```

---

## Docker Compose

The `docker-compose.yml` at project root orchestrates all services:

```yaml
services:
  backend:
    container_name: mantis-backend
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend/data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/system/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    container_name: mantis-frontend
    build: ./frontend
    ports:
      - "4321:4321"
    depends_on:
      backend:
        condition: service_healthy

  postgres:
    container_name: mantis-postgres
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-mantis}
      POSTGRES_USER: ${POSTGRES_USER:-mantis}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-mantis}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-mantis}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    container_name: mantis-redis
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgadmin:
    container_name: mantis-pgadmin
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@mantis.local
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres

volumes:
  postgres_data:
  redis_data:

networks:
  default:
    name: mantis-network
```

---

## Data Download & Model Training

After setup, download historical data and train models:

```bash
cd backend

# Download data for all 9 assets (3 timeframes each)
.venv/Scripts/python.exe scripts/download_data.py

# Train XGBoost models with Optuna tuning
.venv/Scripts/python.exe scripts/train_models.py

# (Optional) Walk-forward backtest with Monte Carlo validation
.venv/Scripts/python.exe scripts/walk_forward_backtest.py --epic XAUUSD --tune --monte-carlo
```

### Supported Assets

| Asset     | Epic   | Capital.com Epic | Type      |
| --------- | ------ | ---------------- | --------- |
| Gold      | XAUUSD | GOLD             | Commodity |
| Silver    | XAGUSD | SILVER           | Commodity |
| Crude Oil | WTIUSD | OIL_CRUDE        | Commodity |
| Bitcoin   | BTCUSD | BTCUSD           | Crypto    |
| EUR/USD   | EURUSD | EURUSD           | Forex     |
| S&P 500   | US500  | US500            | Index     |
| DAX 40    | DE40   | DE40             | Index     |
| NVIDIA    | NVDA   | NVDA             | Stock CFD |
| Tesla     | TSLA   | TSLA             | Stock CFD |

> **Note**: EURUSD is excluded from active trading (ATR too small for reliable position sizing).

---

## Running Tests

### Backend Tests (865 tests, ~80% coverage)

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/ -v

# With coverage report
.venv/Scripts/python.exe -m pytest tests/ --cov=src --cov-report=term-missing
```

### Frontend Tests

```bash
cd frontend
npx ng test --watch=false
```

---

## Verification Checklist

After setup, verify each component:

- [ ] `.env` file configured with Capital.com credentials
- [ ] Backend starts on port 8000 (`/docs` shows Swagger UI)
- [ ] Capital.com demo session creates successfully
- [ ] Historical data downloaded (`backend/data/historical/` has parquet files)
- [ ] ML models trained (`backend/data/models/` has `.json` model files)
- [ ] Frontend builds and serves on port 4321
- [ ] Frontend can reach backend API (dashboard loads data)
- [ ] WebSocket connects (live prices appear in dashboard)
- [ ] Paper trading starts/stops from dashboard
