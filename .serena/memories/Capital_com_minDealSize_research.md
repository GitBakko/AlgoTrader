# Capital.com MinDealSize Research — Complete Flow

## Overview
The Capital.com broker client **already has infrastructure to fetch market information including minDealSize**, but there is **NO minimum size validation** currently implemented before orders are sent. Orders can be rejected by the broker if size is too small.

---

## 1. BROKER CLIENT — Market Information Fetching

### File: `backend/src/broker/client.py`

#### Key Method: `get_market_details(epic: str) -> dict`
```python
async def get_market_details(self, epic: str) -> dict:
    """
    Get detailed market info including status, trading hours, and instrument specs.

    Uses GET /api/v1/markets/{epic} — returns snapshot with marketStatus
    (TRADEABLE, CLOSED, etc.), instrument details, and dealing rules.

    Args:
        epic: Internal epic code (e.g., "XAUUSD", "TSLA")

    Returns:
        Raw dict from Capital.com (includes 'snapshot', 'instrument', 'dealingRules')
    """
    broker_epic = self._to_broker_epic(epic)
    return await self._request("GET", f"/api/v1/markets/{broker_epic}")
```

**Response Structure:**
```json
{
  "snapshot": {
    "marketStatus": "TRADEABLE|CLOSED|SUSPENDED",
    "scalingFactor": "spread_info",
    "updateTime": "timestamp"
  },
  "instrument": {
    "name": "Asset name",
    "type": "SPOT|CFD|etc"
  },
  "dealingRules": {
    "minDealSize": {
      "value": 0.01,        // Minimum position size
      "unit": "UNITS"       // Or "PERCENTAGE"
    },
    "marketOrderPreference": {
      "openingTime": "HH:MM",
      "closingTime": "HH:MM"
    }
  }
}
```

---

## 2. POSITION SIZING FLOW

### Files Involved:
1. `backend/src/risk/kelly_sizer.py` — Adaptive Kelly-based sizing
2. `backend/src/risk/position_sizer.py` — Fixed-fractional sizing (fallback)
3. `backend/src/risk/risk_manager.py` — Orchestrates all risk checks

### Kelly Sizer (Default for 30+ trades)
```python
class AdaptiveKellySizer:
    def calculate_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        confidence: float,
        trade_history: list[dict],
        max_position_pct: float = 0.05,
    ) -> tuple[float, str]:
        """
        Returns: (position_size, sizing_method)
        - kelly / fixed_fractional / kelly_zero / invalid
        """
```

### Fixed-Fractional Sizing (Fallback for <30 trades)
```python
class PositionSizer:
    @staticmethod
    def calculate_size(
        equity: float,
        risk_per_trade: float,        # e.g., 0.02 = 2%
        entry_price: float,
        stop_loss: float,
        confidence: float,
        max_position_pct: float = 0.05,
    ) -> float:
        """
        Formula:
        1. risk_amount = equity * risk_per_trade
        2. base_size = risk_amount / stop_distance
        3. confidence_mult = max(0.5, min(1.5, (confidence - 0.5) * 3.33))
        4. final_size = base_size * confidence_mult
        5. cap at max_position_pct * equity / entry_price
        """
```

### Risk Manager Pipeline (in `risk_manager.py`)
```python
def check_trade(self, signal: TradingSignal, equity: float, atr: float, ...):
    # 1. Circuit breaker checks
    # 2. Drawdown checks
    # 3. Calculate stop-loss (2x ATR)
    # 4. Calculate take-profit (2x ATR, 2:1 R:R)
    # 5. Correlation checks
    # 6. Calculate position size (Kelly or fixed-fractional)
    # 7. Apply equity curve filter
    # 8. Multi-target TP1/TP2 calculation
    return RiskCheckResult(position_size=X, stop_loss=Y, take_profit=Z)
```

---

## 3. EXECUTION FLOW

### File: `backend/src/execution/execution_engine.py`

```python
async def execute_signal(self, signal: TradingSignal, risk_result: RiskCheckResult):
    """
    1. Build ExecutionOrder from signal + risk_result
       - position_size from risk_result (ALREADY CALCULATED)
       - entry_price from signal.entry_price
       - stop_loss from risk_result.stop_loss
       - take_profit from risk_result.take_profit
    
    2. Call OrderManager.submit_order(order)
    
    3. Persist position to DB if in DEMO/LIVE mode
    """
```

### File: `backend/src/execution/order_manager.py`

```python
async def _live_fill(self, order: ExecutionOrder) -> ExecutionResult:
    """
    1. Build CreatePositionRequest with:
       - epic, direction, size (from order.size)
       - stop_level, profit_level
    
    2. Call broker.create_position(request)
    
    3. If broker returns REJECTED:
       - Parse error via parse_broker_error()
       - Return ExecutionResult with error
    
    4. If opened without stops (SL/TP rejected):
       - Call _set_stops_after_fill() to set them via modify_stops()
    """
```

---

## 4. CURRENT ERROR HANDLING

### File: `backend/src/utils/broker_error_parser.py`

```python
def parse_broker_error(error_message: str, epic: str | None = None):
    # Already handles:
    # - "minimum size" → error_type="min_size"
    # - "minvalue" → error_type="min_size"
    # - "error.invalid.size" → error_type="min_size"
    
    # Returns: ParsedBrokerError(
    #   error_type="min_size",
    #   summary="Size troppo piccola per {label} (min: 0.01)",
    #   details="La dimensione calcolata è inferiore al minimo consentito dal broker.",
    #   market_hours=None,
    #   raw=original_error
    # )
```

### File: `backend/src/broker/exceptions.py`

```python
# Already maps:
# - "minimum" + "size" → OrderRejectedError
# - "error.invalid.size" → OrderRejectedError
```

---

## 5. VALIDATION GAPS

### Current Issues:

1. **NO PRE-CHECK OF minDealSize**
   - Risk manager calculates position_size WITHOUT checking broker's minDealSize
   - If calculated size < minDealSize → broker rejects with error
   - Order is rejected at API layer, not prevented upfront

2. **LATE DETECTION**
   - Error only discovered after broker.create_position() call
   - Position never opens
   - Error is logged and returned to frontend, but is reactive

3. **NO CACHING**
   - Market details (including minDealSize) fetched on-demand in markets router
   - Not cached for reuse during trading loop
   - Would require additional API call if we added pre-validation

---

## 6. WHERE TO ADD minDealSize VALIDATION

### Option A: Risk Manager (Recommended)
**File:** `backend/src/risk/risk_manager.py`

Add a new validation step AFTER position size calculation, BEFORE returning RiskCheckResult:

```python
def check_trade(...) -> RiskCheckResult:
    # ... existing checks ...
    
    # 7. Calculate position size (Kelly or fixed-fractional)
    position_size = ...  # existing code
    
    # NEW: Validate against broker's minDealSize
    if market_min_size and position_size < market_min_size:
        return RiskCheckResult(
            approved=False,
            rejection_reason=f"Calculated size {position_size:.4f} < broker minimum {market_min_size:.4f}"
        )
    
    # 8. Apply equity curve filter
    # ... rest of existing code ...
```

### Option B: Order Manager (Secondary)
**File:** `backend/src/execution/order_manager.py`

Catch rejection and retry with minimum size:

```python
async def _live_fill(self, order: ExecutionOrder):
    # Try with calculated size first
    confirmation = await broker.create_position(request)
    
    # If minDealSize error, retry with minimum
    if "minimum" in confirmation.reason.lower() and "size" in confirmation.reason.lower():
        min_match = re.search(r"(\d+\.?\d*)", confirmation.reason)
        if min_match:
            min_size = float(min_match.group(1))
            # Retry with min_size
            request.size = min_size
            confirmation = await broker.create_position(request)
```

---

## 7. WHERE minDealSize IS FETCHED

### Already Used In:
1. **Script:** `backend/scripts/verify_epic_candidates.py`
   - Extracts `minDealSize` from `dealingRules.minDealSize.value`
   - Displays in verification report

2. **Router:** `backend/src/api/routers/markets.py`
   - `get_market_status()` calls `broker.get_market_details(epic)`
   - Returns in response (not currently used by frontend)

### Example from verify_epic_candidates.py:
```python
details = await tester.get_market_details(epic_code)
dealing_rules = details.get("dealingRules", {})
min_size = dealing_rules.get("minDealSize", {}).get("value")
```

---

## 8. COMPLETE ORDER FLOW (Current)

```
TradingSignal (with entry_price, direction, confidence)
    ↓
RiskManager.check_trade()
    ├─ Circuit breaker checks
    ├─ Drawdown checks
    ├─ SL/TP calculation
    ├─ Correlation checks
    ├─ Position size calculation (Kelly or fixed-fractional)
    │  └─ NO minDealSize check
    ├─ Equity curve filter
    └─ Returns RiskCheckResult(position_size=X, ...)
    ↓
PaperTradingLoop.execute()
    └─ ExecutionEngine.execute_signal(signal, risk_result)
        └─ OrderManager.submit_order(order)
            ├─ Paper mode: fake fill
            └─ DEMO/LIVE mode: broker.create_position(request)
                ├─ If rejected: parse_broker_error() → return error
                ├─ If "minimum size": log + return ExecutionResult(success=False)
                └─ If OK: return ExecutionResult(success=True, deal_id=X)
```

---

## 9. MARKET DETAILS API ENDPOINT

**Endpoint:** `GET /api/markets/status/{epic}`

Currently returns:
```json
{
  "success": true,
  "data": {
    "epic": "XAUUSD",
    "is_open": true,
    "status": "TRADEABLE",
    "next_open": null,
    "session": {
      "open": "23:00",
      "close": "22:00",
      "timezone": "UTC"
    }
  }
}
```

**Could extend to include:**
```json
{
  "dealing_rules": {
    "min_deal_size": 0.01,
    "max_deal_size": 100000.0
  }
}
```

---

## 10. SUMMARY OF FINDINGS

| Aspect | Status | Details |
|--------|--------|---------|
| Fetch minDealSize | ✅ YES | `broker.get_market_details()` → `dealingRules.minDealSize` |
| Cache minDealSize | ❌ NO | Fetched on-demand, not cached for trading |
| Validate minDealSize | ❌ NO | No pre-check before order submission |
| Handle minDealSize error | ✅ PARTIAL | Broker rejects, error parsed, returned to frontend |
| Position sizing method | ✅ YES | Kelly (30+ trades) or fixed-fractional (<30 trades) |
| Size capping | ✅ YES | Max 5% of equity per position |
| Order validation | ✅ PARTIAL | SL/TP validation, but not size validation |

---

## 11. RECOMMENDED IMPLEMENTATION

### Phase 1: Add to Risk Manager (Safe, Non-Breaking)
1. Fetch market details with `broker.get_market_details(epic)`
2. Extract minDealSize from response
3. Check if `position_size < minDealSize`
4. If too small: return RiskCheckResult(approved=False) with clear message
5. Log at INFO level for transparency

### Phase 2: Optional Caching
1. Cache market details for 1 hour per asset
2. Reduce API calls during busy trading periods

### Phase 3: Optional Auto-Sizing
1. If position_size < minDealSize, round up to minDealSize
2. Requires explicit config flag (default: reject with message)

---

## Key Code References

- **Broker Client:** `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend\src\broker\client.py` (line 78-89)
- **Risk Manager:** `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend\src\risk\risk_manager.py` (line 1-240)
- **Position Sizer:** `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend\src\risk\position_sizer.py`
- **Kelly Sizer:** `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend\src\risk\kelly_sizer.py`
- **Order Manager:** `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend\src\execution\order_manager.py`
- **Error Parser:** `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend\src\utils\broker_error_parser.py` (handles min_size errors)
- **Verification Script:** `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend\scripts\verify_epic_candidates.py` (already extracts minDealSize)
