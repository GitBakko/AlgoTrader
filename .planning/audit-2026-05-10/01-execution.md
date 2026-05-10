# Execution Engine Audit — 2026-05-10

**Files reviewed:** `backend/src/execution/execution_engine.py`, `order_manager.py`, `position_tracker.py`, `schemas.py`; `backend/tests/execution/`.

---

## CRITICAL

### C1 — `execution_engine._persist_close_to_db` missing SELECT-then-INSERT idempotency on CLOSE Trade row
`backend/src/execution/execution_engine.py:354-367` (session-factory path) + `:396-409` (injected-repos fallback)

**What**: Direct `session.add(trade_db)` without first checking for existing `(position_id, trade_type='CLOSE')` row. CLAUDE.md Invariant #10 (post `ce2c3e1`) requires SELECT-then-INSERT — first writer wins. The `paper_loop._persist_position_close` path at `paper_loop.py:744-757` has the correct guard; `execution_engine` does not.

**Why it matters**: When emergency-stop + reconciler tick fire on the same position, two CLOSE Trade rows are created — the second carries entry_price as fallback (broker context lost), corrupting Kelly sizer and dashboard P&L aggregates.

**Fix**: Mirror the guard:
```python
existing = await session.execute(
    select(Trade).where(Trade.position_id == position_db.id, Trade.trade_type == "CLOSE").limit(1)
)
if existing.scalar_one_or_none() is None:
    session.add(trade_db)
await session.commit()
```

---

### C2 — `(exit-entry)*size` arithmetic P&L written to DB violates Invariant #2
`backend/src/execution/execution_engine.py:315-318, 323-327, 387-392`

**What**: `_persist_close_to_db` computes `position_db.profit_loss = price_diff * position_db.size` at three sites. Method comment lines 214-219 explicitly says "no arithmetic fallback — authoritative P&L from broker TRADE row" but the body does it anyway.

**Why it matters**: For USDJPY/forex pip-aware sizing, the naïve `price_diff * size` formula is wrong. The fabricated P&L overwrites broker-authoritative reconciled values, propagates to Trade row, dashboard, Kelly sizer.

**Fix**: Set `position_db.profit_loss = None` at this path; let CloseDetector reconcile from broker TRADE row.

---

## HIGH

### H1 — `order_manager._set_stops_after_fill` epic-only deal_id lookup modifies WRONG position when two deals share epic
`backend/src/execution/order_manager.py:519-524`

**What**: Iterates `broker.list_positions()` picking first `p.epic == epic`. No deal_id verification.

**Why it matters**: DEMO partial-close flow closes one deal and reopens new one on same epic. If `_set_stops_after_fill` runs in this window, it can match the **new** position and overwrite its SL/TP. CLAUDE.md `dea2a29` explicitly flagged epic-only matching as bug class.

**Fix**: Match by creation `deal_id` first; epic-only fallback only when single match.

---

### H2 — Eager pre-close `get_position()` doubles `list_positions()` broker calls per close, risks 429
`backend/src/execution/execution_engine.py:191`

**What**: `close_position()` snapshots `get_position(deal_id)` BEFORE `close_order`. In DEMO/LIVE, this triggers `sync_positions()` → `broker.list_positions()`. Then `close_order` calls broker again. 2 calls per close × 3 concurrent closes = 6 + reconciler overhead → close to 10 req/s rate limit.

**Fix**: Move `get_position` to lazy fallback only when `closed_position is None`.

---

## MEDIUM

### M1 — Requested SL/TP (not broker-confirmed) stored in local tracker after live fill
`backend/src/execution/execution_engine.py:116-119`

**What**: `open_paper_position(order, fill_price, deal_id)` uses `order.stop_loss = risk_result.stop_loss` (requested) instead of `result.actual_stop_loss` (broker-confirmed). If broker widened SL via min-distance, local tracker holds tighter value.

**Fix**: After successful fill, call `update_stops(deal_id, stop_level=result.actual_stop_loss, profit_level=result.actual_take_profit)` if differ.

---

### M2 — Spurious `session.commit()` in error path
`backend/src/execution/execution_engine.py:347-352`

**What**: `else: await session.commit(); return None`. No mutations precede this branch, but creates inconsistency with normal flow.

**Fix**: Remove commit, return None.

---

### M3 — SL/TP regex extraction without directional sanity check
`backend/src/execution/order_manager.py:296-303`

**What**: `_re.search(r":\s*([\d.]+)", str(e))` matches first colon-followed-by-number. False-positive can produce SL on wrong side of entry.

**Fix**: Direction guard after extraction (BUY-SL < entry, SELL-SL > entry).

---

## Coverage Gaps

1. `_persist_close_to_db` session-factory path zero unit-test coverage
2. Double `close_position()` on same deal_id untested
3. `_set_stops_after_fill` with multiple epic positions untested
4. Broker-confirmed SL/TP propagation untested
5. `CapitalComError` SL/TP correction path untested
6. `test_close_position` only checks count, not P&L correctness

---

## Summary

| Pri | ID | Location | Issue |
|-----|-----|----------|-------|
| CRITICAL | C1 | execution_engine.py:354 | Missing CLOSE Trade idempotency |
| CRITICAL | C2 | execution_engine.py:315 | (exit-entry)*size P&L violates Invariant #2 |
| HIGH | H1 | order_manager.py:519 | Epic-only lookup overwrites wrong position |
| HIGH | H2 | execution_engine.py:191 | Eager pre-close list_positions doubles calls |
| MEDIUM | M1 | execution_engine.py:116 | Requested SL/TP stored not broker-confirmed |
| MEDIUM | M2 | execution_engine.py:347 | Spurious commit in error branch |
| MEDIUM | M3 | order_manager.py:296 | SL extraction no direction guard |
