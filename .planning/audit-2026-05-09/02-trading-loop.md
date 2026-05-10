# Trading Loop / Reconciler Audit — 2026-05-09

**Scope reviewed:** `paper_loop.py`, `close_detector.py`, `state_recovery.py`, `broker/client.py`, `broker/websocket_client.py`, `api/routers/trading.py`, `tests/trading/`.

---

## CRITICAL

### C1 — `_broker_closed_deals` reset inside `_detect_broker_closed` voids cross-tick double-close guard

`paper_loop.py:1121`

**What**: Top of every `_detect_broker_closed` call: `self._broker_closed_deals = set()` unconditionally. `_finalize_close` has multiple awaits after `_broker_closed_deals.add(deal_id)`. If 15s reconciler tick fires while previous `_finalize_close` is suspended at await, `_broker_closed_deals` resets, making `deal_id` invisible to next tick's `_check_stop_losses`.

**Why it matters**: Only in-process guard against redundant broker `close_position` calls. DB idempotency stops Trade row dup but NOT the broker call. Redundant close on already-closed position can open new position if broker interprets as open.

**Fix**: Per-tick set passed as parameter through `_run_reconciler_tick`, OR persistent `_inflight_close_deals` cleared only on `_finalize_close` completion.

---

### C2 — `_load_positions_from_broker` returns `list[Position]` typed as `list[dict]`; `_reconcile_positions` subscripts `p["deal_id"]` — crashes every DEMO/LIVE restart

`state_recovery.py:218,298`

**What**: `broker.list_positions()` returns Pydantic `Position` objects, NOT dicts. `_reconcile_positions:298` does `{p["deal_id"] for p in broker_positions}` → `TypeError`. Caught silently at line 187, broker path abandoned, DB fallback used.

**Why it matters**: Documented in `project_state_recovery_position_bug.md` — NOT FIXED. Violates Invariant #5 (broker authoritative). Compounds with M1 below: DB fallback uses wrong key names → SL/TP enforcement absent.

**Fix**: Convert in `_load_positions_from_broker`:
```python
return [{"deal_id": p.deal_id, "size": float(p.size), "level": float(p.level), 
         "epic": p.epic, "direction": p.direction.value,
         "stop_level": p.stop_level, "profit_level": p.profit_level,
         "deal_reference": getattr(p, "deal_reference", None)} for p in positions]
```

---

## HIGH

### H1 — `rehydrate_pending_closes` never called at startup

`state_recovery.py:694`, `api/main.py`

**What**: Method exists, unit-tested, but never wired in `main.py`. Tier 2 retry queue `first_seen=now` reset on every restart. Slow Capital.com settlement (NATGAS, DE40) → indefinite Tier 2 deferrals across restarts, never reach UNRECONCILED.

**Fix**: Add `await recovery_service.rehydrate_pending_closes()` after `reinject_orphans()` in main.py.

---

### H2 — When `CLOSE_DETECTION_V2_ENABLED=true`, `CloseDetector.detect()` called twice per tick — fetches activity+transactions twice

`paper_loop.py:1174,1416`

**What**: `_detect_broker_closed` line 1182 calls `detector.detect(...)` with cached lists. Then line 1416 → `_run_shadow_close_detection` line 1482 → `detector.detect(...)` AGAIN without `activities=`/`transactions=` kwargs → fresh broker fetch. Per tick: +2 activity calls + 2 transaction calls.

**Why it matters**: 10 req/sec rate limit. Reconciler tick with 3 positions: ~9 calls baseline, +4 from double-detect = 13 → 429 throttling.

**Fix**: Pass already-fetched lists to `_run_shadow_close_detection`.

---

### H3 — Transaction cache TTL 60s vs reconciler interval 15s — misses settled closes

`paper_loop.py:1006`

**What**: `_fetch_recent_transactions` caches 60s. Reconciler runs 15s. Ticks 2/3/4 reuse stale cache. Broker close settling between ticks → v1 Strategy 1+2 miss → defer to Tier 2 unnecessarily.

**Why it matters**: Tier 2 holds DB reconciliation, blocks re-entry on epic. Worse than legacy 60s tick.

**Fix**: `cached_ts < self._reconciler_interval` instead of hardcoded 60.

---

### H4 — Time-stop `continue` fires unconditionally — SL/TP enforcement skipped on close failure

`paper_loop.py:3640`

**What**: `continue` at same indent as `if result.success:`. Always fires, even when `result.success=False`. On weekend index (DE40, NAS100) close fails (market closed) → `continue` → SL/TP checks skipped. Gap-open Monday SL miss.

**Fix**: Move `continue` inside `if result.success:` block.

---

## MEDIUM

### M1 — DB-recovered positions use `stop_loss`/`take_profit` keys; `_check_stop_losses` reads `stop_level`/`profit_level`

`state_recovery.py:259`, `paper_loop.py:3587`

**What**: Key name mismatch. DB-fallback positions get NO SL/TP enforcement until next successful `broker.list_positions()`. Combined with C2: every DEMO/LIVE restart leaves positions un-protected.

**Fix**: `_load_positions_from_db` use `"stop_level"`/`"profit_level"` keys.

---

### M2 — Emergency stop alert not CRITICAL, gated on `alerts_enabled=False`

`api/routers/trading.py:674`

**What**: Fires WARNING `alert_circuit_breaker` only when `alerts_enabled=True`. Invariant #4 says CRITICAL. If alerts disabled, emergency stop = zero notification.

**Fix**: Add unconditional CRITICAL alert bypassing `alerts_enabled`.

---

### M3 — `_reconcile_positions` silently marks DB-only positions CLOSED with reason "EXTERNAL", no P&L

`state_recovery.py:314`

**What**: Positions in DB OPEN but not on broker → `mark_as_closed(close_reason="EXTERNAL")`. No CLOSE Trade row, no P&L, no UNRECONCILED alert. Bypasses three-tier path.

**Fix**: Inject into `_pending_close_detections` instead.

---

### M4 — `get_positions_async` mutates `trailing_stop_manager._positions` non-atomically

`paper_loop.py:459`

**What**: pop+assign+setitem on dict during dealId rotation. No await currently between, but architecturally fragile.

**Fix**: Expose `trailing_stop_manager.remap_deal_id(old, new)` atomic method.

---

## Coverage Gaps

1. `_reconcile_positions` with real `list[Position]` broker objects (C2)
2. `rehydrate_pending_closes` startup wiring (H1)
3. `_check_stop_losses` with DB-format positions (M1)
4. Time-stop `continue` placement on `result.success=False` (H4)
5. `_broker_closed_deals` cross-tick voiding (C1)
6. Shadow detection double-fetch (H2)

---

## Summary

| Pri | ID | Issue |
|-----|-----|-------|
| CRITICAL | C1 | `_broker_closed_deals` per-call reset |
| CRITICAL | C2 | Position-vs-dict crash on every DEMO/LIVE restart |
| HIGH | H1 | `rehydrate_pending_closes` never called |
| HIGH | H2 | v2 CloseDetector double-fetch per tick |
| HIGH | H3 | Transaction cache TTL 4× reconciler interval |
| HIGH | H4 | Time-stop `continue` skips SL/TP on close failure |
| MEDIUM | M1 | DB position key mismatch breaks SL enforcement |
| MEDIUM | M2 | Emergency stop alert not CRITICAL |
| MEDIUM | M3 | EXTERNAL close bypasses 3-tier P&L path |
| MEDIUM | M4 | Trailing stop dict mutation non-atomic |

**Most dangerous combo: C2 + M1.** Every DEMO/LIVE restart with open positions = broker path crashes silently, DB fallback uses wrong keys, SL/TP enforcement absent. **Live risk for LIVE deploy.**
