# CRITICAL: P&L Pipeline Fix — Real Broker Data Reconciliation

> **Priority: P0 — BLOCKING. No other work until this is done.**
> The entire P&L pipeline is producing fictional numbers. Every financial figure in the platform (equity, P&L, drawdown, win rate) may be wrong.

## The Problem

When Capital.com broker closes a position (SL/TP hit), our system:
1. Detects the position disappeared from `list_positions()`
2. Queries the **current live price** to guess if SL or TP was hit
3. Uses the **SL or TP level** as the exit price to calculate P&L

This is fundamentally broken because:
- The live price AFTER close can be far from the actual exit price
- SL gets classified as TP and vice versa (confirmed in BNBUSD data)
- P&L is calculated from theoretical SL/TP levels, not the real exit price
- All downstream data (equity, drawdown, win rate, Kelly) is corrupted

### Evidence
- BNBUSD BUY entry=615.97, exit recorded as 644.63, P&L=+54.17, reason="SL" — **SL cannot produce profit**
- BNBUSD BUY entry=618.36, exit=616.27, P&L=-7.83, reason="TP" — **TP cannot produce loss**
- NVDA SELL shows -634$ loss in MANTIS, broker shows -6.69$ — **100x error**
- XAUUSD SELL shows -145$ in MANTIS, broker shows +11.18$ — **sign is inverted**
- Broker equity: $9,200 vs MANTIS equity: $9,980 — **$780 discrepancy**

---

## Fix 1: Use Broker Transaction History API

**File**: `backend/src/trading/paper_loop.py` — `_detect_broker_closed_positions()`

Capital.com has `GET /api/v1/history/transactions` that returns the **real** exit details:
```json
{
  "transactions": [{
    "type": "TRADE",
    "reference": "deal_id",
    "date": "2026-03-28T14:18:00",
    "instrumentName": "BNBUSD",
    "size": "+5.2",
    "openLevel": "615.97",
    "closeLevel": "620.15",
    "pl": "+21.73",
    "currency": "USD"
  }]
}
```

### Implementation

**File**: `backend/src/broker/client.py`

The `get_transaction_history()` method already exists (line 480). It returns `Transaction` objects. Check what fields are available on `Transaction` model in `backend/src/broker/models.py`.

**File**: `backend/src/trading/paper_loop.py`

Replace the live-price guessing logic in `_detect_broker_closed_positions()` with:

```python
# Instead of guessing from live price, query transaction history
try:
    from_date = datetime.now(timezone.utc) - timedelta(hours=1)
    to_date = datetime.now(timezone.utc)
    transactions = await self.broker.get_transaction_history(from_date, to_date)

    # Find the transaction for this deal_id
    for txn in transactions:
        if txn.reference == deal_id or epic in txn.instrument_name:
            exit_price = txn.close_level  # REAL exit price from broker
            pnl = txn.pl                  # REAL P&L from broker
            # Determine reason from P&L sign vs direction
            if direction == "BUY":
                close_reason = "TP" if pnl > 0 else "SL"
            else:
                close_reason = "TP" if pnl > 0 else "SL"
            break
except Exception:
    # Fallback to current logic if transaction API fails
    pass
```

**Key**: The Transaction model may need updating. Check `backend/src/broker/models.py` for the `Transaction` class fields. Capital.com returns `openLevel`, `closeLevel`, `pl` in the transaction data — these might not be mapped yet.

### Steps
1. Read `backend/src/broker/models.py` — check Transaction class fields
2. Read `backend/src/broker/client.py` — check `get_transaction_history()` method
3. Test the transaction API: `curl http://localhost:8000/...` or use the broker client directly
4. Update `_detect_broker_closed_positions()` to query transactions first
5. Keep the live-price logic as FALLBACK only
6. Add the sanity check (SL+profit=impossible, TP+loss=impossible)

---

## Fix 2: Reconcile Corrupted DB Data

**File**: Create `backend/scripts/reconcile_trades.py`

Script that:
1. Queries Capital.com transaction history for the last 7 days
2. Queries our `positions` table for closed positions in the same period
3. Compares P&L and close_reason
4. Updates our DB records with the broker's real values

```python
# Pseudocode
broker_txns = await client.get_transaction_history(7_days_ago, now)
db_positions = await repo.get_closed_in_period(7_days_ago, now)

for db_pos in db_positions:
    broker_txn = find_matching_txn(broker_txns, db_pos.deal_id, db_pos.epic)
    if broker_txn:
        if abs(db_pos.profit_loss - broker_txn.pl) > 0.01:
            print(f"MISMATCH {db_pos.epic}: DB={db_pos.profit_loss} Broker={broker_txn.pl}")
            db_pos.profit_loss = broker_txn.pl
            db_pos.exit_price = broker_txn.close_level
            db_pos.close_reason = determine_reason(broker_txn)
            await repo.update(db_pos)
```

### Steps
1. Create the reconciliation script
2. Run it against the last 7 days of data
3. Log all corrections made
4. Update the drawdown monitor state with corrected equity

---

## Fix 3: Audit Entire P&L Pipeline

Every place where P&L is calculated or displayed must be verified:

### Backend P&L Sources (check each one)

| Location | File | What it does | Status |
|----------|------|-------------|--------|
| Broker close detection | `paper_loop.py:572-690` | Guesses exit price from live price | **BROKEN** — Fix 1 |
| Paper mode close | `execution_engine.py:260-320` | Calculates P&L from fill price | Verify |
| Dashboard overview | `api/routers/dashboard.py:70-90` | Sums `profit_loss` from DB | Depends on DB data |
| Drawdown monitor | `risk/drawdown_monitor.py` | Tracks equity from `update_equity()` | Verify source |
| Kelly sizer | `risk/kelly_sizer.py` | Uses trade_history P&L | Verify source |
| Trading performance | `api/routers/trading.py` | Aggregates from DB | Depends on DB data |
| Trade logger | `monitoring/trade_logger.py` | Logs P&L events | Verify |

### Frontend P&L Sources (check each one)

| Location | File | What it does | Status |
|----------|------|-------------|--------|
| Header live P&L | `default-header.component.ts` | `(current - entry) * size` from WS prices | Verify WS prices match broker |
| Header daily P&L | Same | `today_realized_pnl` from overview API | Depends on DB |
| Dashboard KPIs | `dashboard.component.ts` | From overview API | Depends on DB |
| Paper trading positions | `paper-trading.component.ts` | Live calc from WS prices | Verify |
| Positions page | `positions.component.ts` | From closed positions API | Depends on DB |
| Trade journal | `trade-journal.component.ts` | From closed positions + WS | Depends on DB + verify |

### Key Questions to Answer
1. Where does `drawdown_monitor.state.current_equity` come from? Is it the broker's real equity or calculated from our (wrong) P&L?
2. When `_fetch_equity()` is called in paper_loop, does it query the broker account API or use internal state?
3. Are WebSocket prices (bid/ask) matching the broker's actual prices?
4. Is the `risk_result.position_size` in the correct units for Capital.com?

### Steps
1. Trace `_fetch_equity()` in paper_loop — where does it get the number?
2. Trace `drawdown_monitor.update_equity()` — who calls it and with what?
3. Verify WS prices match broker bid/ask for a few assets
4. Check if `list_positions()` returns the same data as the broker web UI

---

## Fix 4: Frontend P&L for Open Positions

The frontend calculates live P&L as:
```typescript
const current = pos.direction === 'BUY' ? tick.bid : tick.offer;
const diff = pos.direction === 'BUY' ? current - pos.level : pos.level - current;
return diff * pos.size;
```

Problems:
- During weekends/market closed, WS prices may be stale or zero
- The `size` from broker may be in different units than expected
- The `level` (entry price) is correct (from broker) but prices might not match

### Fix
- When market is closed, show "Market closed" instead of a calculated P&L
- Or: query broker account API for the real unrealized P&L (it has this data)
- Add a "last price update" timestamp to detect stale prices

---

## Fix 5: Equity Tracking

The `drawdown_monitor.state.current_equity` might be tracking our fictional P&L instead of the broker's real equity.

### Steps
1. Find where `update_equity()` is called
2. Verify it uses the broker's real account balance, not a calculated value
3. If it's using `_fetch_equity()`, verify that method queries the broker API

---

## Execution Order

1. **Fix 1** first — stop the bleeding (new closes use real data)
2. **Fix 3** in parallel — understand the full pipeline
3. **Fix 2** after Fix 1 — clean up historical data
4. **Fix 4** after Fix 3 — frontend accuracy
5. **Fix 5** after Fix 3 — equity tracking

## Files to Touch

| File | Fix | Priority |
|------|-----|----------|
| `backend/src/trading/paper_loop.py` | Fix 1 (transaction API) | P0 |
| `backend/src/broker/models.py` | Fix 1 (Transaction model) | P0 |
| `backend/src/broker/client.py` | Fix 1 (verify get_transaction_history) | P0 |
| `backend/scripts/reconcile_trades.py` | Fix 2 (new script) | P0 |
| `backend/src/api/routers/dashboard.py` | Fix 3 (verify) | P1 |
| `backend/src/risk/drawdown_monitor.py` | Fix 5 (verify) | P1 |
| `frontend/src/app/layout/default-header/` | Fix 4 (stale price guard) | P1 |
| `frontend/src/app/views/paper-trading/` | Fix 4 (stale price guard) | P1 |
