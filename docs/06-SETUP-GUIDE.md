# AlgoTrader AI - Setup Guide

## Prerequisites

### System Requirements
- **Python**: 3.12+
- **Node.js**: 20.19+ or 22.12+ (LTS recommended)
- **npm**: 10+
- **Docker**: 24+ with Docker Compose v2
- **Git**: 2.40+
- **GPU** (optional): NVIDIA CUDA-compatible for ML training acceleration

### Accounts Required
- **Capital.com**: Trading account (demo is sufficient to start)
  - Enable 2FA
  - Generate API key at Settings > API integrations
- **FRED API** (optional, for macro data): Free key at https://fred.stlouisfed.org/docs/api/api_key.html

---

## Quick Start

### 1. Clone & Configure

```bash
cd D:\Develop\AI\_ClaudeCode\AlgoTrader

# Create environment file from template
cp .env.example .env

# Edit .env with your credentials
# (see Environment Variables section below)
```

### 2. Backend Setup

```bash
cd backend

# Install Poetry (if not installed)
pip install poetry

# Install dependencies
poetry install

# Activate virtual environment
poetry shell

# Run database migrations
alembic upgrade head

# Verify broker connection
python -m src.broker.test_connection

# Start backend
uvicorn src.api.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
ng serve --port 4200

# Open browser at http://localhost:4200
```

### 4. Docker Setup (Alternative)

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
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

# ===== Database =====
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=algotrader
POSTGRES_USER=algotrader
POSTGRES_PASSWORD=your_secure_password

# ===== Redis =====
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# ===== FRED API (Macro Data) =====
FRED_API_KEY=your_fred_api_key

# ===== ML Settings =====
ML_DEVICE=cpu  # cpu or cuda
ML_MODELS_DIR=./data/models
ML_TRAINING_WORKERS=4

# ===== Risk Management =====
RISK_MAX_PER_TRADE=0.01        # 1% max risk per trade
RISK_MAX_TOTAL_EXPOSURE=0.10   # 10% max total exposure
RISK_MAX_DRAWDOWN=0.15         # 15% max drawdown before halt
RISK_DAILY_LOSS_LIMIT=0.05     # 5% daily loss circuit breaker

# ===== Logging =====
LOG_LEVEL=INFO
LOG_FILE=./logs/algotrader.log

# ===== Frontend =====
API_BASE_URL=http://localhost:8000
WS_BASE_URL=ws://localhost:8000

# ===== Security =====
JWT_SECRET=generate_a_secure_random_string_here
JWT_EXPIRY_HOURS=24
```

---

## Python Dependencies (pyproject.toml)

```toml
[tool.poetry]
name = "algotrader-backend"
version = "0.1.0"
description = "AI-powered algorithmic trading system"
python = "^3.12"

[tool.poetry.dependencies]
# Core
python = "^3.12"
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.34"}
pydantic = "^2.10"
pydantic-settings = "^2.7"

# Database
sqlalchemy = "^2.0"
sqlmodel = "^0.0.22"
alembic = "^1.14"
asyncpg = "^0.30"             # PostgreSQL async driver
duckdb = "^1.2"               # Analytical queries

# Data & ML
pandas = "^2.2"
numpy = "^2.1"
polars = "^1.20"              # Fast dataframe operations
scikit-learn = "^1.6"
torch = "^2.5"                # PyTorch for LSTM/Transformer
xgboost = "^2.1"
lightgbm = "^4.5"
optuna = "^4.1"               # Hyperparameter optimization
ta = "^0.11"                  # Technical analysis indicators
transformers = "^4.47"        # FinBERT for sentiment

# Broker & Networking
httpx = "^0.28"               # Async HTTP client
websockets = "^14.1"          # WebSocket client
aiohttp = "^3.11"             # Alternative async HTTP

# Infrastructure
redis = {extras = ["hiredis"], version = "^5.2"}
apscheduler = "^3.10"         # Task scheduling
celery = "^5.4"               # Distributed tasks (optional)

# Storage
pyarrow = "^18.1"             # Parquet file support

# Logging & Monitoring
loguru = "^0.7"
rich = "^13.9"                # Beautiful terminal output

# Utilities
python-dotenv = "^1.0"
pyjwt = "^2.10"               # JWT auth

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"
pytest-cov = "^6.0"
black = "^24.10"
ruff = "^0.8"
mypy = "^1.13"
pre-commit = "^4.0"
httpx = "^0.28"                # For testing FastAPI
jupyter = "^1.1"
matplotlib = "^3.10"
seaborn = "^0.13"
ipywidgets = "^8.1"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.black]
line-length = 100
target-version = ["py312"]

[tool.mypy]
python_version = "3.12"
strict = true
```

---

## Docker Compose

```yaml
# docker-compose.yml
version: '3.9'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend/data:/app/data
      - ./backend/logs:/app/logs

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "4200:80"
    depends_on:
      - backend

volumes:
  postgres_data:
  redis_data:
```

---

## Initial Data Download

After setup, download historical data for all assets:

```bash
cd backend
poetry run python scripts/download_historical_data.py

# This will download:
# - Gold (XAUUSD): DAY, HOUR_4, HOUR, MINUTE_15 (last 2-5 years)
# - Bitcoin (BTCUSD): DAY, HOUR_4, HOUR, MINUTE_15 (last 2-5 years)
# - S&P 500 (US500): DAY, HOUR_4, HOUR, MINUTE_15 (last 2-5 years)
# Data saved as Parquet files in data/historical/
```

---

## Verification Checklist

After setup, verify each component:

- [ ] `.env` file configured with all required variables
- [ ] `poetry install` completes without errors
- [ ] PostgreSQL is running and accessible
- [ ] Redis is running and accessible
- [ ] Capital.com demo session creates successfully
- [ ] Can fetch Gold, BTC, S&P500 prices from API
- [ ] WebSocket connects and receives price ticks
- [ ] FastAPI starts on port 8000 (`/docs` shows Swagger UI)
- [ ] Angular builds and serves on port 4200
- [ ] Frontend can reach backend API
