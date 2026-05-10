# Broker Integration Audit — 2026-05-10

**Files reviewed:** `backend/src/broker/` (all), `backend/src/utils/broker_error_parser.py`, tests.

---

## CRITICAL

None at ≥80% threshold producing wrong orders or lost positions in current call-graph. Three HIGH below approach critical under degraded conditions.

---

## HIGH

### H1 — HTTP 429 from broker NOT retried — treated as non-retryable 4xx
`backend/src/broker/client.py:205-215`

**What**: `_request` retry loop only retries on `status_code >= 500`. Any `>= 400` (including 429) immediately propagates as `RateLimitError`. Token-bucket limiter throttles outgoing rate but Capital.com can still 429 on burst windows.

**Why it matters**: 429 on SL/TP set or position-open immediately fails. Order_manager catches `CapitalComError`, returns `success=False`. No trade opens. No SL set on already-open position.

**Fix**: Add 429 branch INSIDE retry loop with backoff +1s buffer:
```python
if response.status_code == 429 and attempt < retry_attempts - 1:
    await asyncio.sleep(retry_base_delay * (2 ** attempt) + 1.0)
    continue
```

---

### H2 — `_ping_loop` tight-spin on network exception (no sleep in error branch)
`backend/src/broker/session.py:199-207`

**What**: Loop pattern catches generic `Exception`, logs, re-enters with NO sleep. Network outage → coroutine spins as fast as scheduled, saturating event loop.

**Why it matters**: Sustained outage → hundreds of failing pings/sec, starves trading loop, trips BackendHealthSentinel 7-min threshold.

**Fix**: Add `await asyncio.sleep(min(ping_interval, 30))` in exception branch.

---

### H3 — `modify_position` sends `null` SL/TP — `exclude_none` config key not valid in Pydantic v2
`backend/src/broker/client.py:411` + `backend/src/broker/models.py:210-213`

**What**: `model_config = {"exclude_none": True}` — NOT a valid Pydantic v2 ConfigDict key. `model_dump(by_alias=True)` at line 411 emits None values. Future call updating only SL or only TP sends `{"stopLevel": null, ...}`. Broker interprets `null` as "remove the SL".

**Why it matters**: Latent bug — current call sites pass both legs. One future single-leg modify call silently strips broker SL.

**Fix**: `model_dump(by_alias=True, exclude_none=True)` at call site. Remove dead `"exclude_none"` from model_config.

---

## MEDIUM

### M1 — WS handler types declared `Callable[[X], None]` but called with `await`
`backend/src/broker/websocket_client.py:96`

**What**: Type annotation lies. Future sync handler registration → `TypeError: object NoneType can't be used in await`.

**Fix**: `Callable[[X], Awaitable[None]]` OR `inspect.iscoroutinefunction` guard.

---

### M2 — Dual fan-out setup race loses listener on concurrent init
`backend/src/api/websocket.py:326-337` + `backend/src/data/pnl_snapshot_scheduler.py:125-139`

**What**: Both check `getattr(broker_ws, "_quote_listeners", [])`. Concurrent init → both see [], both create separate `_fan_out` closures. Second `on_quote(_fan_out)` replaces first → first listener orphaned.

**Why it matters**: PnL snapshot scheduler quote cache goes stale after WS reconnect, forcing REST fallback per snapshot tick.

**Fix**: Centralize fan-out on `CapitalComWebSocketClient` — add `_quote_listeners` attribute in `__init__`, iterate natively in `_handle_message`.

---

### M3 — `SessionTokens.created_at` default factory naive
`backend/src/broker/models.py:122-123`

**What**: `default_factory=datetime.now` (naive). Production explicitly passes tz-aware so default never triggers, but test fixtures constructing without `created_at` get TypeError on expiry comparison.

**Fix**: `default_factory=lambda: datetime.now(UTC)`.

---

## LOW

### L1 — WS subscription guard counts already-subscribed epics as new
`backend/src/broker/websocket_client.py:254`

**Fix**: Dedupe `new_epics = [e for e in epics if e not in self._subscribed_quotes]` before guard.

### L2 — `DealConfirmation`, `WorkingOrder`, `Account` missing `populate_by_name=True`
`backend/src/broker/models.py:602-613`

**Fix**: Add `model_config = {"populate_by_name": True}`.

---

## Coverage Gaps

- 429 retry path untested
- `_ping_loop` exception branch untested
- WS `_resubscribe` after disconnect untested
- `modify_position` with single-leg None untested
- `get_transaction_history` tz-naive datetime edge untested
- `FxConverter` cache invalidation untested
- `DealConfirmation` two-step delay untested
- Concurrent auth refresh under `_lock` untested

---

## Summary

| Pri | ID | Location | Issue |
|-----|-----|----------|-------|
| HIGH | H1 | client.py:205 | 429 not retried — drops orders under load |
| HIGH | H2 | session.py:199 | Ping loop tight-spin saturates loop on outage |
| HIGH | H3 | client.py:411 | modify_position null leg strips broker SL silently |
| MEDIUM | M1 | websocket_client.py:96 | Sync handler type contract violated |
| MEDIUM | M2 | websocket.py:326 | Quote-listener race during init |
| MEDIUM | M3 | models.py:122 | Naive datetime default in SessionTokens |
| LOW | L1-L2 | misc | WS dedupe, populate_by_name |
