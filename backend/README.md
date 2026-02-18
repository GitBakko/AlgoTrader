# MANTIS AI - Backend

Backend Python per la piattaforma di trading algoritmico MANTIS AI.

## Setup

### Requisiti

- Python 3.12+
- Capital.com demo account
- PostgreSQL (opzionale — graceful degradation)
- Redis (opzionale — graceful degradation)

### Installazione

```bash
cd backend

# Crea virtual environment
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# Installa le dipendenze
pip install -r requirements.txt

# Crea il file .env
cp .env.example .env
# Modifica .env con le tue credenziali Capital.com
```

### Download dati e training

```bash
# Download dati storici (21 asset x 3 timeframe)
python scripts/download_data.py

# Training modelli XGBoost (walk-forward + Optuna)
python scripts/train_models.py

# Batch OOS scorecard (valuta tutti i 20 asset tradabili)
python scripts/batch_oos_scorecard.py
```

### Avvio server

```bash
uvicorn src.api.main:app --reload
```

## Testing

```bash
# Tutti i test (1110 test)
python -m pytest tests/ -v

# Quick run, stop al primo fallimento
python -m pytest tests/ -x --no-cov -q

# Moduli specifici
python -m pytest tests/risk/ -v         # Risk management
python -m pytest tests/strategy/ -v     # Strategy engine
python -m pytest tests/features/ -v     # Feature engineering
python -m pytest tests/external/ -v     # External API clients
python -m pytest tests/backtest/ -v     # Backtesting + scorecard
```

## Struttura

```text
backend/
├── src/
│   ├── api/               # 13 REST routers + WebSocket + middleware
│   ├── auth/              # JWT + RBAC (3 ruoli, 30+ permessi)
│   ├── audit/             # Audit logging
│   ├── broker/            # Capital.com API wrapper (REST + WS)
│   ├── data/              # Data pipeline (Parquet, DuckDB)
│   ├── database/          # PostgreSQL session, repositories
│   ├── execution/         # Order execution + state recovery
│   ├── external/          # Finnhub, Marketaux, yfinance clients
│   ├── features/          # 220+ features (technical, sentiment, macro)
│   ├── models/            # XGBoost, LSTM, calibration, Optuna tuner
│   ├── monitoring/        # Health checks, trade logger, alerting
│   ├── risk/              # Circuit breakers, Kelly, trailing stops
│   ├── security/          # Encrypted secrets (Fernet)
│   ├── strategy/          # ML, Squeeze, VWAP, Pairs, Router
│   ├── trading/           # Paper trading loop (21 asset)
│   └── utils/             # Config, constants, event bus
├── tests/                 # 1110 pytest test
├── scripts/               # download, train, backtest, scorecard
├── data/                  # Parquet, modelli, avatar, log
└── alembic/               # Database migrations
```

## API Documentation

Con il server avviato, la documentazione Swagger e disponibile a:

- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/redoc` (ReDoc)
