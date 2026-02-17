# MANTIS AI - API Reference

## Base URL

- **Development**: `http://localhost:8000`
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Response Envelope

All REST endpoints return responses in this format:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

On error:

```json
{
  "success": false,
  "data": null,
  "error": "Error description"
}
```

## Middleware

- **GZip**: Responses > 1000 bytes are compressed
- **CORS**: Configured for frontend origin
- **Rate Limiting**: Auth endpoints are rate-limited (see below)

---

## Authentication (`/api/auth`)

### POST `/api/auth/login`

Login with username and password. Rate limited: **5 requests/minute**.

**Request:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "data": {
    "access_token": "string (JWT)",
    "token_type": "bearer",
    "user": {
      "id": 1,
      "username": "string",
      "email": "string",
      "role_name": "VIEWER|TRADER|ADMIN",
      "avatar_url": "string|null",
      "permissions": ["dashboard:read", "trading:read", ...]
    }
  }
}
```

### POST `/api/auth/register`

Register a new user. Rate limited: **3 requests/hour**.

**Request:**
```json
{
  "username": "string (3-50 chars)",
  "email": "string",
  "password": "string (min 6 chars, requires upper+lower+number)",
  "role_name": "VIEWER|TRADER|ADMIN"
}
```

**Response (201):**
```json
{
  "data": {
    "id": 1,
    "username": "string",
    "email": "string",
    "role_name": "VIEWER"
  }
}
```

### GET `/api/auth/me`

Get current authenticated user profile.

**Headers:** `Authorization: Bearer <token>`

### GET `/api/auth/permissions`

Get permissions for current user's role.

### POST `/api/auth/avatar/upload`

Upload user avatar image. Accepts `multipart/form-data`.

- Max file size: 5MB
- Accepted types: JPEG, PNG, GIF, WEBP
- Backend resizes to 256x256 pixels

**Request:** `multipart/form-data` with `file` field

### GET `/api/auth/avatar/{user_id}`

Get avatar image for a specific user. Returns image bytes.

### DELETE `/api/auth/avatar`

Delete current user's avatar.

---

## Dashboard (`/api/dashboard`)

### GET `/api/dashboard/overview`

Main dashboard data: account equity, P&L, active positions count, recent signals.

**Response:**
```json
{
  "data": {
    "account_equity": 10000.0,
    "daily_pnl": 150.50,
    "total_pnl": 1250.00,
    "open_positions_count": 3,
    "active_signals_count": 5,
    "paper_trading_active": true,
    "circuit_breaker_active": false,
    "recent_signals": [...],
    "live_positions": [...]
  }
}
```

### GET `/api/dashboard/equity-curve`

Historical equity curve data for charting.

### GET `/api/dashboard/recent-trades`

List of recently executed trades.

---

## Positions (`/api/positions`)

### GET `/api/positions/`

List all open positions from broker.

### GET `/api/positions/{deal_id}`

Get details for a specific position.

### POST `/api/positions/close/{deal_id}`

Close an open position.

### PUT `/api/positions/{deal_id}/stops`

Modify stop-loss and take-profit for a position.

**Request:**
```json
{
  "stop_loss": 2900.00,
  "take_profit": 3100.00
}
```

---

## Signals (`/api/signals`)

### GET `/api/signals/`

List recent ML trading signals.

### GET `/api/signals/generate`

Generate signals for all configured assets (on-demand).

### POST `/api/signals/predict/{epic}`

Run ML prediction pipeline for a specific asset.

**Parameters:**
- `epic` (path): Asset identifier (e.g., `XAUUSD`, `BTCUSD`)
- `execute` (query, optional): If `true`, execute the signal as a paper trade

**Response:**
```json
{
  "data": {
    "epic": "XAUUSD",
    "direction": "BUY",
    "confidence": 0.72,
    "signal_class": 2,
    "entry_price": 2950.00,
    "stop_loss": 2920.00,
    "take_profit_1": 2980.00,
    "take_profit_2": 3010.00,
    "strategy": "ml_strategy",
    "regime": "trending_up"
  }
}
```

---

## Markets (`/api/markets`)

### GET `/api/markets/search`

Search Capital.com markets.

**Query Parameters:**
- `searchTerm` (string): Search query

### GET `/api/markets/{epic}/info`

Get market info (name, symbol, trading hours).

### GET `/api/markets/{epic}/prices`

Get OHLC price data for an asset.

**Query Parameters:**
- `timeframe` (string): `1h`, `4h`, `1d` (default: `1h`)
- `limit` (int): Number of bars (default: 100, max: 1000)

### GET `/api/markets/status/{epic}`

Get market open/closed status and session info.

---

## News (`/api/news`)

### GET `/api/news/{epic}`

Get recent news articles for an asset.

**Query Parameters:**
- `limit` (int): Max articles (default: 10)
- `days` (int): Look-back window in days (default: 7)

### GET `/api/news/insider/{epic}`

Get insider trading data for stock CFDs.

### GET `/api/news/sentiment/{epic}`

Get aggregated sentiment analysis for an asset.

---

## Trading (`/api/trading`)

### POST `/api/trading/start`

Start the paper trading loop.

### POST `/api/trading/stop`

Stop the paper trading loop.

### GET `/api/trading/status`

Get paper trading status (running, last iteration, errors).

**Response:**
```json
{
  "data": {
    "running": true,
    "mode": "PAPER",
    "iteration_count": 42,
    "last_iteration": "2026-02-16T10:30:00Z",
    "errors_count": 0,
    "assets_configured": 21
  }
}
```

### GET `/api/trading/positions`

Get current paper trading positions (with live P&L).

### GET `/api/trading/signals`

Get recent paper trading signals.

---

## Backtest (`/api/backtest`)

### POST `/api/backtest/run`

Run a walk-forward backtest.

**Request:**
```json
{
  "epic": "XAUUSD",
  "timeframe": "1h",
  "strategy": "ml_strategy",
  "start_date": "2024-01-01",
  "end_date": "2025-01-01",
  "initial_capital": 10000,
  "tune": false,
  "monte_carlo": true,
  "monte_carlo_runs": 10000
}
```

**Response:** Backtest results including equity curve, trade list, metrics (Sharpe, Sortino, max DD, etc.).

### GET `/api/backtest/runs`

List previous backtest runs.

### GET `/api/backtest/runs/{run_id}`

Get detailed results for a specific backtest run.

---

## Strategy (`/api/strategy`)

### GET `/api/strategy/config`

Get current strategy configuration.

### PUT `/api/strategy/config`

Update strategy configuration.

### GET `/api/strategy/allocation`

Get portfolio allocation weights across assets.

### GET `/api/strategy/risk-limits`

Get current risk management limits.

### PUT `/api/strategy/risk-limits`

Update risk management limits.

**Request:**
```json
{
  "max_risk_per_trade": 0.01,
  "max_total_exposure": 0.10,
  "max_drawdown": 0.15,
  "daily_loss_limit": 0.03,
  "max_positions_per_asset": 2
}
```

---

## Models (`/api/models`)

### GET `/api/models/`

List all trained ML models with metadata.

### GET `/api/models/{model_id}/metrics`

Get performance metrics for a specific model (F1, accuracy, confusion matrix).

### GET `/api/models/{model_id}/versions`

List version history for a model.

---

## System (`/api/system`)

### GET `/api/system/settings`

Get system settings and configuration.

### GET `/api/system/risk-status`

Get current risk management state (circuit breakers, drawdown, equity curve filter).

### GET `/api/system/events`

Get recent system events.

### GET `/api/system/recovery-report`

Get state recovery status from last startup.

**Response:**
```json
{
  "data": {
    "success": true,
    "positions_recovered": 3,
    "positions_source": "database",
    "trailing_stops_restored": 2,
    "trade_history_count": 150,
    "risk_state_restored": true,
    "warnings": [],
    "errors": [],
    "recovered_at": "2026-02-16T10:30:00Z"
  }
}
```

---

## Monitoring (`/api`)

### GET `/api/logs/signals`

Get signal log analysis (accuracy, distribution, per-asset stats).

**Query Parameters:**
- `start_date` (string): ISO date
- `end_date` (string): ISO date
- `epic` (string, optional): Filter by asset

### GET `/api/logs/executions`

Get execution log analysis (fill quality, slippage stats).

### GET `/api/logs/risk-events`

Get risk event log analysis (circuit breaker triggers, drawdown alerts).

### GET `/api/stats/performance`

Get aggregated performance statistics.

---

## WebSocket Endpoints

### WS `/ws/prices`

Real-time price streaming for all subscribed assets.

**Connection:** `ws://localhost:8000/ws/prices`

**Message format (server → client):**
```json
{
  "type": "price",
  "epic": "XAUUSD",
  "bid": 2950.10,
  "ask": 2950.45,
  "timestamp": "2026-02-16T10:30:00.123Z"
}
```

### WS `/ws/trades`

Real-time trade event notifications.

**Connection:** `ws://localhost:8000/ws/trades`

**Message format (server → client):**
```json
{
  "type": "trade",
  "epic": "BTCUSD",
  "direction": "BUY",
  "size": 0.1,
  "entry_price": 95000.00,
  "stop_loss": 93000.00,
  "take_profit": 98000.00,
  "timestamp": "2026-02-16T10:30:00Z"
}
```

---

## Health Check

### GET `/api/system/health`

System health endpoint (used by Docker healthcheck).

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "broker": "connected",
    "database": "connected",
    "redis": "connected",
    "data_freshness": {
      "XAUUSD": "2m ago",
      "BTCUSD": "1m ago"
    }
  }
}
```
