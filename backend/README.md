# AlgoTrader AI - Backend

Backend Python per il sistema di trading algoritmico AI.

## Setup

### Requisiti
- Python 3.12+
- Poetry
- PostgreSQL 16+
- Redis 7+
- Docker (opzionale)

### Installazione

1. Installa Poetry (se non già installato):
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Installa le dipendenze:
```bash
cd backend
poetry install
```

3. Crea il file `.env`:
```bash
cp .env.example .env
# Modifica .env con le tue credenziali
```

4. Avvia i servizi con Docker Compose:
```bash
docker-compose up -d
```

5. Esegui le migrazioni del database:
```bash
poetry run alembic upgrade head
```

6. Avvia il server di sviluppo:
```bash
poetry run uvicorn src.api.main:app --reload
```

## Sviluppo

### Code Quality

Formatta il codice con Black:
```bash
poetry run black src tests
```

Linting con Ruff:
```bash
poetry run ruff check src tests
```

Type checking con Mypy:
```bash
poetry run mypy src
```

### Testing

Esegui i test:
```bash
poetry run pytest
```

Con coverage:
```bash
poetry run pytest --cov=src --cov-report=html
```

### Pre-commit Hooks

Installa i pre-commit hooks:
```bash
poetry run pre-commit install
```

## Struttura

```
backend/
├── src/
│   ├── api/          # FastAPI endpoints
│   ├── broker/       # Capital.com integration
│   ├── data/         # Data pipeline
│   ├── features/     # Feature engineering
│   ├── models/       # ML models
│   ├── strategy/     # Trading strategies
│   ├── risk/         # Risk management
│   ├── execution/    # Order execution
│   ├── backtest/     # Backtesting engine
│   ├── monitoring/   # System monitoring
│   └── utils/        # Utilities
├── tests/            # Test suite
├── config/           # Configuration files
└── notebooks/        # Jupyter notebooks
```

## API Documentation

Una volta avviato il server, la documentazione Swagger è disponibile a:
- http://localhost:8000/docs (Swagger UI)
- http://localhost:8000/redoc (ReDoc)
