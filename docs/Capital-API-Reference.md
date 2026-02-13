# Capital.com Public API - Complete Reference Guide

API Version: **1.0.0**

## Overview

The Capital.com API provides direct access to the latest version of the trading engine, enabling:
- Access to real-time market data
- Position and order management
- Trading operations execution
- Account and settings monitoring

---

## General Information

### Base URLs
- **Production**: `https://api-capital.backend-capital.com/`
- **Demo**: `https://demo-api-capital.backend-capital.com/`

### Key Features
- Endpoints require an active session via `POST /session`
- Sessions are active for **10 minutes**. Inactivity beyond this period will cause errors on the next request
- API covers the full range of available instruments, licenses, and trading functionality

### Rate Limits
- **POST /session**: 1 request per second
- **POST /positions** and **POST /workingorders**: 1000 requests per hour (Demo environment)

---

## Getting Started

Follow these steps to use the API:

### 1. Create a Trading Account
You can use a demo account for testing.

### 2. Enable Two-Factor Authentication (2FA)
2FA **must be enabled** before API key generation.
[2FA enablement instructions](https://capital.com/en-eu/trading-platforms/api-development-guide)

### 3. Generate an API Key
1. Navigate to: **Settings > API integrations > Generate new key**
2. Enter the key label
3. Set a custom password
4. (Optional) Set expiration date
5. Enter 2FA code

### 4. You're Ready!
You can now use the API with your credentials.

---

## Authentication

### How to Start a New Session

There are **2 methods** to start a session:

#### Method 1: API Key + Login + Password
Use the `POST /session` endpoint with:
- **Header**: `X-CAP-API-KEY` (your generated API key)
- **Body Parameters**:
  - `identifier`: your login
  - `password`: your password
  - `encryptedPassword`: must be `false`

#### Method 2: API Key + Login + Encrypted Password
1. First call `GET /session/encryptionKey` with `X-CAP-API-KEY` header
2. Response contains `encryptionKey` and `timeStamp`
3. Encrypt your password using AES encryption method:

```java
// Encryption example (Java)
public static String encryptPassword(String encryptionKey, Long timestamp, String password) {
    try {
        byte[] input = stringToBytes(password + "|" + timestamp);
        input = Base64.encodeBase64(input);
        KeyFactory keyFactory = KeyFactory.getInstance("RSA_ALGORITHM");
        PublicKey publicKey = keyFactory.generatePublic(new X509EncodedKeySpec(Base64.decodeBase64(stringToBytes(encryptionKey))));
        Cipher cipher = Cipher.getInstance("PKCS1_PADDING_TRANSFORMATION");
        cipher.init(Cipher.ENCRYPT_MODE, publicKey);
        byte[] output = cipher.doFinal(input);
        output = Base64.encodeBase64(output);
        return bytesToString(output);
    } catch (Exception e) {
        throw new RuntimeException(e);
    }
}
```

4. Use `POST /session` endpoint with:
   - **Header**: `X-CAP-API-KEY`
   - **Body**: `identifier`, `password` (encrypted), `encryptedPassword: true`

### After Starting the Session

When starting a session, you receive two parameters in **response headers**:
- **CST**: Authorization token
- **X-SECURITY-TOKEN**: Indicates which financial account is used for trading operations

**Important**: Both tokens must be passed as **headers** in all subsequent API requests. Both tokens are valid for **10 minutes** from last use.

---

## Symbology

### Financial Accounts
- **accountId**: Your financial account ID. Each account has a unique ID.
- View complete list of available accounts: `GET /accounts`
- Discover which accountId is used for trading operations: `GET /session`
- Change financial account: `PUT /session`

### Epic
- **Epic**: The name of the market pair.
- Use `GET /markets/?searchTerm=` endpoint to find market pairs of interest.
- Example: to search for "Bitcoin" or "BTC", use `searchTerm` parameter to receive full list of associated market pairs.
- The `GET /marketnavigation` endpoint returns asset group names. These names can be used in `GET /marketnavigation/{node}` to get the list of market pairs belonging to that group.

---

## Available Functionality

### Market Data
- Receive real-time prices for the entire range of available assets
- Search and filter instruments
- Access market details

### Trading Functionality
- Open positions
- Set stop and limit orders
- Set stop loss and take profit levels
- Review and modify financial account settings (trading modes, leverage sizes)
- Review trade and order history

---

## REST API Endpoints

### General

#### GET /api/v1/time
**Description**: Get server time
**Authentication**: Not required
**Response**:
```json
{
  "serverTime": 1649259764171
}
```

#### GET /api/v1/ping
**Description**: Ping the service to keep a trading session alive
**Required Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Response**:
```json
{
  "status": "OK"
}
```

### Session

#### POST /api/v1/session
**Description**: Create a new trading session
**Headers**:
- `X-CAP-API-KEY`: Your API key
- `Content-Type`: application/json

**Body** (Method 1 - Plain password):
```json
{
  "identifier": "your_login",
  "password": "your_password",
  "encryptedPassword": false
}
```

**Body** (Method 2 - Encrypted password):
```json
{
  "identifier": "your_login",
  "password": "encrypted_password_here",
  "encryptedPassword": true
}
```

**Response Headers**:
- `CST`: Access token
- `X-SECURITY-TOKEN`: Account token

#### GET /api/v1/session/encryptionKey
**Description**: Get encryption key to encrypt password
**Headers**:
- `X-CAP-API-KEY`: Your API key

**Response**:
```json
{
  "encryptionKey": "MIIBIjANB...",
  "timeStamp": 1647405281941
}
```

#### GET /api/v1/session
**Description**: Get current session details
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Response**: Information about current account and session

#### PUT /api/v1/session
**Description**: Change active financial account
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Body**:
```json
{
  "accountId": "target_account_id"
}
```

#### DELETE /api/v1/session
**Description**: Close current session
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

### Accounts

#### GET /api/v1/accounts
**Description**: Returns list of all available accounts
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Response**: List of accounts with details (accountId, accountName, balance, etc.)

#### PUT /api/v1/accounts/topUp
**Description**: Top up Demo account balance
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Body**:
```json
{
  "amount": 10000
}
```

### Markets

#### GET /api/v1/markets
**Description**: Search markets using search terms
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Query Parameters**:
- `searchTerm`: Search term (e.g., "BTC", "EUR/USD")

**Response**: List of markets matching the search

#### GET /api/v1/markets/{epic}
**Description**: Get details of a specific market
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Path Parameter**:
- `epic`: Market identifier

#### GET /api/v1/marketnavigation
**Description**: Get market navigation nodes
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Response**: Tree structure of market groups

#### GET /api/v1/marketnavigation/{node}
**Description**: Get markets belonging to a specific node
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Path Parameter**:
- `node`: Navigation node ID

### Trading - Positions

#### GET /api/v1/positions
**Description**: Returns all open positions
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Response**: List of open positions with details

#### POST /api/v1/positions
**Description**: Create a new position
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Body**:
```json
{
  "epic": "BTCUSD",
  "direction": "BUY",
  "size": 1,
  "guaranteedStop": false,
  "stopLevel": 45000,
  "profitLevel": 55000
}
```

**Parameters**:
- `epic`: Market identifier
- `direction`: "BUY" or "SELL"
- `size`: Position size
- `guaranteedStop`: true/false
- `stopLevel`: Stop loss level (optional)
- `profitLevel`: Take profit level (optional)

#### PUT /api/v1/positions/{dealId}
**Description**: Modify an existing position
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Path Parameter**:
- `dealId`: Position ID

**Body**:
```json
{
  "stopLevel": 46000,
  "profitLevel": 54000
}
```

#### DELETE /api/v1/positions/{dealId}
**Description**: Close a position
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Path Parameter**:
- `dealId`: Position ID to close

### Trading - Working Orders

#### GET /api/v1/workingorders
**Description**: Returns all pending orders
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

#### POST /api/v1/workingorders
**Description**: Create a new pending order
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Body**:
```json
{
  "epic": "BTCUSD",
  "direction": "BUY",
  "size": 1,
  "level": 48000,
  "type": "LIMIT",
  "guaranteedStop": false,
  "stopLevel": 45000,
  "profitLevel": 55000
}
```

**Parameters**:
- `type`: "LIMIT" or "STOP"
- `level`: Price at which order will be executed

#### DELETE /api/v1/workingorders/{dealId}
**Description**: Delete a pending order
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

### History

#### GET /api/v1/history/activity
**Description**: Get account activity history
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Query Parameters**:
- `from`: Start date (timestamp or ISO format)
- `to`: End date
- `lastPeriod`: Period (e.g., "1", max interval 1 day)

#### GET /api/v1/history/transactions
**Description**: Get transaction history
**Headers**:
- `X-SECURITY-TOKEN`: Account token
- `CST`: Access token

**Query Parameters**:
- `from`: Start date
- `to`: End date

---

## WebSocket API

Capital.com provides a **WebSocket API** for real-time updates on:
- Market prices
- Position updates
- Order status

**WebSocket URL**: Refer to official documentation for WebSocket endpoint details.

---

## Examples and Collections

### Postman Collection
Capital.com provides a complete Postman collection for easy testing of all endpoints:
- **Repository**: https://github.com/capital-com-sv/capital-api-postman

### Sample Trading Bot
Example trading bot based on RSI indicator:
- **Repository**: https://github.com/capital-com-sv/api-java-samples

---

## Changelog

### November 28, 2023
- Added ability to adjust Demo account balance using `POST /accounts/topUp` endpoint

### October 05, 2023
- Set limit of 1 request per second for `POST /session` endpoint

### August 04, 2023
- Added ability to view entire list of available markets using `GET /markets` endpoint

### July 04, 2023
- Set maximum date range for `from`, `to`, `lastPeriod` parameters to 1 day for `GET /history/activity`

### March 23, 2022
- Set limit of 1000 requests per hour for `POST /positions` and `POST /workingorders` in Demo

### March 16, 2022
- First public API release

---

## Best Practices for Claude Code

### 1. Session Management
```python
# Python example for creating and maintaining a session
import requests
import time

class CapitalAPIClient:
    def __init__(self, api_key, identifier, password, is_demo=True):
        self.api_key = api_key
        self.identifier = identifier
        self.password = password
        self.base_url = "https://demo-api-capital.backend-capital.com/" if is_demo else "https://api-capital.backend-capital.com/"
        self.cst = None
        self.security_token = None
        self.last_request_time = 0

    def create_session(self):
        """Create a new trading session"""
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        body = {
            "identifier": self.identifier,
            "password": self.password,
            "encryptedPassword": False
        }
        response = requests.post(
            f"{self.base_url}api/v1/session",
            headers=headers,
            json=body
        )

        if response.status_code == 200:
            self.cst = response.headers.get("CST")
            self.security_token = response.headers.get("X-SECURITY-TOKEN")
            self.last_request_time = time.time()
            return True
        return False

    def get_headers(self):
        """Get headers for authenticated requests, auto-refresh if needed"""
        # Refresh session if more than 8 minutes have passed
        if time.time() - self.last_request_time > 480:  # 8 minutes
            self.ping()

        return {
            "X-SECURITY-TOKEN": self.security_token,
            "CST": self.cst,
            "Content-Type": "application/json"
        }

    def ping(self):
        """Keep session alive"""
        response = requests.get(
            f"{self.base_url}api/v1/ping",
            headers=self.get_headers()
        )
        self.last_request_time = time.time()
        return response.status_code == 200
```

### 2. Market Search
```python
def search_market(self, search_term):
    """Search for markets by term"""
    params = {"searchTerm": search_term}
    response = requests.get(
        f"{self.base_url}api/v1/markets",
        headers=self.get_headers(),
        params=params
    )
    return response.json()

def get_market_details(self, epic):
    """Get detailed information about a specific market"""
    response = requests.get(
        f"{self.base_url}api/v1/markets/{epic}",
        headers=self.get_headers()
    )
    return response.json()
```

### 3. Position Management
```python
def open_position(self, epic, direction, size, stop_level=None, profit_level=None):
    """Open a new trading position"""
    body = {
        "epic": epic,
        "direction": direction,  # "BUY" or "SELL"
        "size": size,
        "guaranteedStop": False
    }

    if stop_level:
        body["stopLevel"] = stop_level
    if profit_level:
        body["profitLevel"] = profit_level

    response = requests.post(
        f"{self.base_url}api/v1/positions",
        headers=self.get_headers(),
        json=body
    )
    return response.json()

def get_open_positions(self):
    """Get all open positions"""
    response = requests.get(
        f"{self.base_url}api/v1/positions",
        headers=self.get_headers()
    )
    return response.json()

def close_position(self, deal_id):
    """Close an existing position"""
    response = requests.delete(
        f"{self.base_url}api/v1/positions/{deal_id}",
        headers=self.get_headers()
    )
    return response.json()

def update_position(self, deal_id, stop_level=None, profit_level=None):
    """Update stop loss and take profit levels"""
    body = {}
    if stop_level:
        body["stopLevel"] = stop_level
    if profit_level:
        body["profitLevel"] = profit_level

    response = requests.put(
        f"{self.base_url}api/v1/positions/{deal_id}",
        headers=self.get_headers(),
        json=body
    )
    return response.json()
```

### 4. Working Orders
```python
def create_working_order(self, epic, direction, size, level, order_type="LIMIT",
                        stop_level=None, profit_level=None):
    """Create a pending order (LIMIT or STOP)"""
    body = {
        "epic": epic,
        "direction": direction,
        "size": size,
        "level": level,
        "type": order_type,  # "LIMIT" or "STOP"
        "guaranteedStop": False
    }

    if stop_level:
        body["stopLevel"] = stop_level
    if profit_level:
        body["profitLevel"] = profit_level

    response = requests.post(
        f"{self.base_url}api/v1/workingorders",
        headers=self.get_headers(),
        json=body
    )
    return response.json()

def get_working_orders(self):
    """Get all pending orders"""
    response = requests.get(
        f"{self.base_url}api/v1/workingorders",
        headers=self.get_headers()
    )
    return response.json()

def cancel_working_order(self, deal_id):
    """Cancel a pending order"""
    response = requests.delete(
        f"{self.base_url}api/v1/workingorders/{deal_id}",
        headers=self.get_headers()
    )
    return response.json()
```

### 5. Account Management
```python
def get_accounts(self):
    """Get all available accounts"""
    response = requests.get(
        f"{self.base_url}api/v1/accounts",
        headers=self.get_headers()
    )
    return response.json()

def switch_account(self, account_id):
    """Switch to a different trading account"""
    body = {"accountId": account_id}
    response = requests.put(
        f"{self.base_url}api/v1/session",
        headers=self.get_headers(),
        json=body
    )
    return response.json()

def top_up_demo_account(self, amount=10000):
    """Add funds to demo account"""
    body = {"amount": amount}
    response = requests.put(
        f"{self.base_url}api/v1/accounts/topUp",
        headers=self.get_headers(),
        json=body
    )
    return response.json()
```

### 6. Error Handling
```python
def make_request(self, method, endpoint, **kwargs):
    """Make API request with automatic session refresh on auth failure"""
    try:
        response = requests.request(
            method,
            f"{self.base_url}{endpoint}",
            **kwargs
        )

        # If session expired, recreate and retry
        if response.status_code == 401:
            print("Session expired, recreating...")
            self.create_session()
            response = requests.request(
                method,
                f"{self.base_url}{endpoint}",
                **kwargs
            )

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
```

### 7. Rate Limiting
Remember to respect rate limits:
- `POST /session`: max 1 req/second
- `POST /positions` and `POST /workingorders`: max 1000 req/hour (Demo)

```python
import time
from functools import wraps

def rate_limit(max_per_second=1):
    """Decorator to enforce rate limiting"""
    min_interval = 1.0 / max_per_second
    def decorator(func):
        last_called = [0.0]
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

@rate_limit(max_per_second=1)
def create_session_rate_limited(self):
    """Create session with rate limiting"""
    return self.create_session()
```

### 8. Complete Usage Example
```python
# Initialize client
client = CapitalAPIClient(
    api_key="YOUR_API_KEY",
    identifier="your_login",
    password="your_password",
    is_demo=True  # Use demo environment
)

# Create session
if client.create_session():
    print("Session created successfully")

    # Search for Bitcoin markets
    btc_markets = client.search_market("BTC")
    print(f"Found {len(btc_markets)} BTC markets")

    # Get current open positions
    positions = client.get_open_positions()
    print(f"Open positions: {len(positions)}")

    # Open a new position
    new_position = client.open_position(
        epic="BTCUSD",
        direction="BUY",
        size=0.1,
        stop_level=45000,
        profit_level=55000
    )
    print(f"Position opened: {new_position}")

    # Create a limit order
    limit_order = client.create_working_order(
        epic="ETHUSD",
        direction="BUY",
        size=0.5,
        level=3000,
        order_type="LIMIT",
        stop_level=2800,
        profit_level=3500
    )
    print(f"Limit order created: {limit_order}")

else:
    print("Failed to create session")
```

---

## Common Patterns and Use Cases

### Pattern 1: Monitor and Auto-Close Positions
```python
def monitor_positions(client, profit_threshold=0.05):
    """Close positions that have reached profit threshold"""
    positions = client.get_open_positions()

    for position in positions['positions']:
        profit_pct = position['profit'] / position['size']

        if profit_pct >= profit_threshold:
            print(f"Closing profitable position: {position['dealId']}")
            client.close_position(position['dealId'])
```

### Pattern 2: Batch Market Data Fetching
```python
def get_multiple_market_details(client, epics):
    """Fetch details for multiple markets"""
    results = {}
    for epic in epics:
        try:
            results[epic] = client.get_market_details(epic)
            time.sleep(0.1)  # Small delay to avoid rate limits
        except Exception as e:
            print(f"Error fetching {epic}: {e}")
    return results
```

### Pattern 3: Smart Order Placement with Validation
```python
def place_validated_order(client, epic, direction, size, current_price):
    """Place order with price validation"""
    # Calculate stop loss and take profit based on current price
    if direction == "BUY":
        stop_level = current_price * 0.98  # 2% below
        profit_level = current_price * 1.05  # 5% above
    else:
        stop_level = current_price * 1.02  # 2% above
        profit_level = current_price * 0.95  # 5% below

    return client.open_position(
        epic=epic,
        direction=direction,
        size=size,
        stop_level=stop_level,
        profit_level=profit_level
    )
```

---

## Troubleshooting

### Common Issues

**Issue**: Session expires too quickly
- **Solution**: Implement automatic session refresh using `ping()` every 8 minutes

**Issue**: Rate limit exceeded
- **Solution**: Implement rate limiting decorators and request queuing

**Issue**: Position not opening
- **Solution**: Check market is open, verify account has sufficient balance, ensure epic is valid

**Issue**: Authentication fails
- **Solution**: Verify 2FA is enabled, check API key is active, ensure credentials are correct

---

## Security Best Practices

1. **Never hardcode credentials** - use environment variables or secure vaults
2. **Use encrypted password method** for production environments
3. **Implement IP whitelisting** if available
4. **Monitor API key usage** regularly
5. **Rotate API keys** periodically
6. **Use demo environment** for testing
7. **Implement request logging** for audit trails
8. **Set appropriate stop losses** on all positions

---

## Resources

- **Official Documentation**: https://open-api.capital.com/
- **Postman Collection**: https://github.com/capital-com-sv/capital-api-postman
- **Java Examples**: https://github.com/capital-com-sv/api-java-samples
- **Support Email**: support@capital.com
- **Phone**: +357 25123646

---

## Quick Reference

### Essential Headers
```
X-CAP-API-KEY: your_api_key (for session creation)
CST: access_token (for authenticated requests)
X-SECURITY-TOKEN: account_token (for authenticated requests)
Content-Type: application/json
```

### Base Endpoints
```
POST   /api/v1/session              - Create session
GET    /api/v1/session              - Get session info
DELETE /api/v1/session              - Close session
GET    /api/v1/ping                 - Keep alive
GET    /api/v1/accounts             - List accounts
GET    /api/v1/markets              - Search markets
GET    /api/v1/positions            - Get positions
POST   /api/v1/positions            - Open position
DELETE /api/v1/positions/{dealId}   - Close position
GET    /api/v1/workingorders        - Get orders
POST   /api/v1/workingorders        - Create order
```

---

## Important Notes

1. **Security**: Never share API keys or credentials
2. **2FA Required**: Must enable 2FA before generating API key
3. **Session Timeout**: Sessions expire after 10 minutes of inactivity
4. **Demo Account**: Use demo account for testing before live trading
5. **Rate Limits**: Always respect rate limits to avoid blocks
6. **Required Headers**: All authenticated requests need CST and X-SECURITY-TOKEN
7. **Token Lifespan**: Both tokens valid for 10 minutes from last use
8. **Base URL**: Use correct base URL for production vs demo

---

*Documentation generated for Claude Code integration with Capital.com API*
