# AlgoTrader AI - Capital.com API Reference

## Environments

| Environment | Base URL | Purpose |
|-------------|----------|---------|
| Demo | `https://demo-api-capital.backend-capital.com/` | Development, paper trading |
| Live | `https://api-capital.backend-capital.com/` | Real money trading |
| WebSocket | `wss://api-streaming-capital.backend-capital.com/connect` | Real-time streaming |

## Authentication Flow

### Step 1: Generate API Key
1. Login to Capital.com account
2. Enable 2FA (required)
3. Settings > API integrations > Generate new key
4. Set a custom password (separate from account password)
5. Store: email, API key, API password in `.env`

### Step 2: Create Session

```python
# Method 1: Unencrypted (simpler, OK for development)
POST /api/v1/session
Headers:
  X-CAP-API-KEY: <api_key>
Body:
  {
    "identifier": "<email>",
    "password": "<api_password>",
    "encryptedPassword": false
  }

# Response headers (SAVE THESE):
# CST: <authorization_token>
# X-SECURITY-TOKEN: <financial_account_token>
```

### Step 3: Use Session Tokens
All subsequent requests must include:
```
Headers:
  X-SECURITY-TOKEN: <from_session>
  CST: <from_session>
```

### Step 4: Keep-Alive
Tokens expire after 10 minutes of inactivity.
```
GET /api/v1/ping
Headers: CST + X-SECURITY-TOKEN
```

## Key Endpoints

### Market Data

```python
# Search markets (find epic codes)
GET /api/v1/markets?searchTerm=gold
GET /api/v1/markets?searchTerm=bitcoin
GET /api/v1/markets?searchTerm=US500

# Historical OHLC data
GET /api/v1/prices/{epic}
Params:
  resolution: MINUTE | MINUTE_5 | MINUTE_15 | MINUTE_30 | HOUR | HOUR_4 | DAY | WEEK
  max: <max_candles>
  from: YYYY-MM-DDTHH:MM:SS
  to: YYYY-MM-DDTHH:MM:SS

# Example: Get daily gold candles for last year
GET /api/v1/prices/GOLD?resolution=DAY&from=2025-01-01T00:00:00&to=2026-01-01T00:00:00

# Client sentiment
GET /api/v1/clientsentiment/{epic}
```

### Order Management

```python
# Open position (market order)
POST /api/v1/positions
Body:
  {
    "epic": "GOLD",
    "direction": "BUY",        # BUY or SELL
    "size": 0.5,               # Position size
    "guaranteedStop": false,
    "stopLevel": 2890.0,       # Optional stop loss price
    "profitLevel": 2950.0      # Optional take profit price
  }

# Close position
DELETE /api/v1/positions/{dealId}

# Modify position (update SL/TP)
PUT /api/v1/positions/{dealId}
Body:
  {
    "stopLevel": 2900.0,
    "profitLevel": 2960.0
  }

# List open positions
GET /api/v1/positions

# Create working order (limit/stop order)
POST /api/v1/workingorders
Body:
  {
    "epic": "GOLD",
    "direction": "BUY",
    "size": 0.5,
    "level": 2880.0,           # Trigger price
    "type": "LIMIT",           # LIMIT or STOP
    "goodTillDate": "2026-02-28T00:00:00"
  }

# Trade confirmation
GET /api/v1/confirms/{dealReference}
```

### Account

```python
# Account info + balance
GET /api/v1/accounts

# Transaction history
GET /api/v1/history/transactions
Params:
  from: YYYY-MM-DDTHH:MM:SS
  to: YYYY-MM-DDTHH:MM:SS
  type: ALL | ALL_DEAL | DEPOSIT | WITHDRAWAL

# Top up demo account
POST /api/v1/accounts/topUp
Body: { "amount": 10000 }
```

## WebSocket Streaming

### Connection

```python
import websocket
import json

ws = websocket.WebSocket()
ws.connect("wss://api-streaming-capital.backend-capital.com/connect")
```

### Subscribe to Real-Time Quotes

```python
# Subscribe
subscribe_msg = {
    "destination": "marketData.subscribe",
    "correlationId": "1",
    "cst": "<cst_token>",
    "securityToken": "<security_token>",
    "payload": {
        "epics": ["GOLD", "BITCOIN", "US500"]  # Max 40 instruments
    }
}
ws.send(json.dumps(subscribe_msg))

# Receive quote events
# {
#   "destination": "quote",
#   "payload": {
#     "epic": "GOLD",
#     "bid": 2920.50,
#     "ofr": 2921.10,     # (offer/ask)
#     "timestamp": "2026-02-10T12:00:00.000"
#   }
# }
```

### Subscribe to OHLC Candles

```python
ohlc_subscribe = {
    "destination": "OHLCMarketData.subscribe",
    "correlationId": "2",
    "cst": "<cst_token>",
    "securityToken": "<security_token>",
    "payload": {
        "epics": ["GOLD"],
        "resolutions": ["MINUTE_5", "HOUR"],
        "type": "classic"  # or "heikin-ashi"
    }
}
ws.send(json.dumps(ohlc_subscribe))

# Receive OHLC events
# {
#   "destination": "ohlc.event",
#   "payload": {
#     "epic": "GOLD",
#     "resolution": "MINUTE_5",
#     "t": 1707566400000,  # timestamp ms
#     "o": 2920.50,        # open
#     "h": 2921.30,        # high
#     "l": 2919.80,        # low
#     "c": 2920.90,        # close
#     "type": "classic",
#     "priceType": "mid"
#   }
# }
```

### Keep-Alive

```python
# Send ping every 5 minutes (before 10min timeout)
ping_msg = {
    "destination": "ping",
    "correlationId": "ping-1",
    "cst": "<cst_token>",
    "securityToken": "<security_token>"
}
ws.send(json.dumps(ping_msg))
```

## Rate Limits

| Operation | Limit |
|-----------|-------|
| General API requests | 10/second |
| Session creation | 1/second per API key |
| Position/order creation (demo) | 1,000/hour |
| Demo top-up | 10/second, 100/day |
| WebSocket subscriptions | Max 40 instruments |
| WebSocket session | 10 min timeout (use ping) |

## Asset Epic Codes

Verify exact epics at runtime via:
```
GET /api/v1/markets?searchTerm=<asset_name>
```

Expected epics (confirm via API):
- **Gold**: `GOLD` (XAUUSD CFD)
- **Bitcoin**: search for `bitcoin` or `BTCUSD`
- **S&P 500**: `US500`

## Error Handling

Common error responses:
```json
{
  "errorCode": "error.invalid.session"  // Session expired -> re-authenticate
}
{
  "errorCode": "error.exceeds.rate-limit"  // Rate limited -> back off
}
{
  "errorCode": "error.insufficient.funds"  // Not enough margin
}
```

## Implementation Notes for Our Wrapper

1. **Auto-refresh sessions**: Implement a background task that pings every 5 minutes
2. **Rate limiter**: Token bucket (10 tokens/sec, burst allowed)
3. **WebSocket reconnection**: Exponential backoff on disconnect (1s, 2s, 4s, 8s, max 60s)
4. **Historical data pagination**: API may limit candles per request; paginate with from/to
5. **Thread safety**: Use asyncio locks for session token access
6. **Error mapping**: Map Capital.com error codes to custom exceptions
7. **Logging**: Log every API call with timing for performance monitoring
