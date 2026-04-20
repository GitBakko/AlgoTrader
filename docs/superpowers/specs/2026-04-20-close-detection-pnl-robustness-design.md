# Close Detection & P&L Robustness — Design Spec

**Date:** 2026-04-20
**Status:** Draft — pending user approval
**Author:** Claude (Opus 4.7) + Stefano Brunelli
**Scope:** `backend/src/trading/paper_loop.py`, `backend/src/broker/client.py`, `backend/src/broker/models.py`, `backend/src/execution/execution_engine.py`, `backend/src/database/models.py`, new CLI script and tests.

---

## 1. Problem Statement

On 2026-04-20 at 00:10 UTC, the trading loop detected three positions closed by the broker (WTIUSD, NATGAS, DE40). The persisted P&L values diverged massively from the actual broker-reported P&L:

| Asset   | MANTIS P&L | Broker P&L  | Ratio |
|---------|-----------:|------------:|------:|
| DE40    |    +$19.95 |   +€44.38   | 0.45  |
| WTIUSD  |    +$74.18 |  +$246.86   | 0.30  |
| NATGAS  |    +$25.20 |   +$26.03   | 0.97  |

### Root cause (two compounding bugs)

**Bug 1 — Primary match fails systematically.** `paper_loop._detect_broker_closed` calls `_fetch_recent_transactions` which returned an empty list for all three positions (log "Fetched N transactions" never emitted, only a successful HTTP 200 on `/api/v1/history/transactions`). The most likely cause is the ISO 8601 timestamp sent to Capital.com without a `Z` suffix (`client.py:514-515`), making the 4-hour window land outside the broker's server timezone and miss just-closed transactions. Secondary fragility: `_match_transaction` matches via `txn.reference == deal_id`, but `reference` in Capital.com's transaction history is the `dealReference`, not the `dealId`, so the deterministic match is broken by design. The tertiary instrument-name fallback uses case-insensitive substring against `instrumentName` (e.g. `"WTIUSD" in "Oil - Crude"`, `"OIL_CRUDE" in "Oil - Crude"`) which fails for almost every asset whose broker display name uses spaces/hyphens where our epic uses underscores.

**Bug 2 — Fallback invents P&L.** When the primary match fails, `_fallback_close_detection` (`paper_loop.py:1009-1108`) picks the closer of SL/TP as the exit price and computes `pnl = (exit - entry) * size`. This formula assumes `contract_multiplier = 1`, which is false for indices (DE40 ≈ €1-25 per point), commodities (WTIUSD ≈ 10-100 per contract), and most non-forex assets. The invented P&L is then written to `positions` table, broadcast via WebSocket, and pushed to Telegram as if it were real.

A prior fix plan (#15438, 2026-04-09) introduced the Transaction History API as the primary path but left the defective fallback in production as "better than nothing". That assumption is now proven dangerous.

### Impact

- `positions` table contains corrupted P&L history (records #2119, #2120, #2121 and potentially others from prior fallback activations).
- Downstream systems consuming `trade_history` — Kelly sizer, equity-curve filter, win-rate analytics, per-asset circuit breakers — operate on wrong data.
- Telegram alerts report invented numbers to the user.
- Equity refresh after close (`paper_loop.py:939`) re-fetches from broker, so the account-level equity is correct, but per-trade attribution is not.

---

## 2. Goals & Non-Goals

### Goals

- **G1.** Guarantee that no invented P&L is ever written to the database, Telegram, or WebSocket.
- **G2.** Make the primary path (Transaction History API) reliable via defense-in-depth fixes at three independent failure points: timezone, deterministic match via `deal_reference`, instrument-name normalization.
- **G3.** When primary fails, retry automatically for up to 10 minutes before giving up.
- **G4.** When retries exhaust, fail safely: persist the close with `pnl=NULL`, `close_reason='UNRECONCILED'`, and require manual reconciliation via a CLI tool.
- **G5.** Keep all downstream stats (Kelly, win rate, equity curve) immune to `UNRECONCILED` records.
- **G6.** Provide observability: Prometheus counter tracking which path (primary / deferred / unreconciled) each close takes, per asset.
- **G7.** Fix the three corrupted records from 2026-04-20 manually via the same CLI tool.

### Non-Goals

- No batch reconciliation script over historical data. The three known records are fixed manually; older fallback-contaminated records stay as-is (the project is demo/paper, full retroactive cleanup is not worth the risk).
- No currency conversion. If `profitAndLoss` arrives in a currency different from the account currency, we log a warning but do not convert (requires reliable FX feed — out of scope).
- No new frontend UI. `close_reason='UNRECONCILED'` is rendered with the existing generic badge logic. A dedicated warning badge can come later if needed.
- No migration to Capital.com's `/history/activity` endpoint. We fix the current endpoint rather than introduce a new one.
- No changes to position opening logic, trailing stop manager, ML strategy, or risk management other than reading the new `close_reason='UNRECONCILED'` filter.

---

## 3. Architecture — Three-Tier Close Path

The close path is reorganized into three tiers with decreasing priority. Each tier has a single, well-defined responsibility.

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1 — PRIMARY (Transaction History API, hardened)        │
│   Deterministic match via deal_reference persisted at open. │
│   Fallback strategies: deal_id, normalized instrument_name. │
│   Uses pnl and exit_price REAL from broker. Final.          │
└─────────────────────────────────────────────────────────────┘
                          │ fails
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Tier 2 — DEFERRED (natural retry loop)                      │
│   Position stays in _previous_positions. NOT written to DB. │
│   NO alerts. Every loop iteration retries Tier 1.           │
│   Timeout: 10 minutes (env-configurable).                   │
└─────────────────────────────────────────────────────────────┘
                          │ timeout
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Tier 3 — UNRECONCILED (fail-safe, no invented data)         │
│   Persist close with pnl=NULL, close_reason='UNRECONCILED'. │
│   Telegram: "closed, P&L not confirmed, reconcile manually".│
│   Downstream stats ignore UNRECONCILED records.             │
└─────────────────────────────────────────────────────────────┘
```

The current `_fallback_close_detection` function is **removed entirely**. No code path computes P&L locally from entry/exit/size.

---

## 4. Components Affected

| File | Change |
|------|--------|
| `backend/src/broker/client.py` | `get_transaction_history`: ISO 8601 `from`/`to` with `Z` suffix. Default window 24h. |
| `backend/src/broker/models.py` | `Transaction.pl_value`: warn when currency prefix ≠ account currency. No conversion. |
| `backend/src/trading/paper_loop.py` | Remove `_fallback_close_detection`. Rewrite `_match_transaction` with three strategies. Add `_pending_close_detections` map. Add `_emit_unreconciled_close`. |
| `backend/src/execution/execution_engine.py` | At open: persist `deal_reference` alongside `deal_id`. |
| `backend/src/execution/state_recovery.py` | At startup: for positions with `status='OPEN'` in DB but absent from broker, re-inject into `paper_loop._pending_close_detections` with `first_seen=now`. |
| `backend/src/database/models.py` | Add `Position.deal_reference: str \| None` column. |
| `backend/alembic/versions/*.py` | Migration for `deal_reference` column. |
| `backend/src/monitoring/metrics.py` | Counter `mantis_close_detection_path_total{path, epic}`. |
| `backend/src/api/routers/positions.py` + repositories | Filter `close_reason != 'UNRECONCILED'` on win-rate / Kelly / equity aggregations. |
| `backend/scripts/reconcile_position.py` *(new)* | CLI for per-deal reconciliation. |
| `backend/tests/trading/test_close_detection.py` *(new)* | Unit coverage of match strategies, deferred retry, timeout. |
| `backend/tests/integration/test_close_reconciliation.py` *(new)* | End-to-end scenarios with mocked broker. |

**Not touched:** position opening flow, trailing stop manager, risk sizers, ML strategy, frontend trading views, TradingView chart, auth, middleware.

**Implementation-time verification:**
- Confirm whether `Position` model already has `deal_reference`. If yes, no migration.
- Confirm whether Kelly sizer reads from DB or from in-memory buffer in `paper_loop`. The UNRECONCILED filter applies at the correct layer.

---

## 5. Data Flow

### 5.1 Open path (small addition)

```
ExecutionEngine.open_position()
  ├─ broker.place_order() → DealConfirmation{deal_id, deal_reference, ...}
  ├─ persist Position(deal_id, deal_reference, epic, entry_price, ...)
  └─ paper_loop tracks (deal_id, deal_reference, ...) in memory
```

### 5.2 Close detection — happy path

```
paper_loop._detect_broker_closed(current_positions)   [every 5-10s loop tick]
  ├─ disappeared = previous_positions − current_positions
  ├─ if disappeared: transactions = _fetch_recent_transactions()  # 24h, ISO-Z
  ├─ for deal_id in disappeared:
  │     result = _match_transaction(transactions, deal_id, deal_reference, epic, entry)
  │       ├─ Strategy 1: txn.reference == deal_reference        [deterministic]
  │       ├─ Strategy 2: txn.reference == deal_id                [legacy compatibility]
  │       └─ Strategy 3: normalize(instrument_name) matches AND
  │                      abs(open_level - entry) / entry < 0.001
  │     if result.matched:
  │       → persist close with REAL pnl/exit_price
  │       → metric: path=primary, retry_count=0
  │       → Telegram alert_trade_closed
  │       → remove from previous_positions and pending_close_detections
```

### 5.3 Close detection — deferred retry

```
  │     else:
  │       → metric: path=deferred
  │       → pending_close_detections[deal_id] = PendingClose(
  │           first_seen=now, retry_count=0, prev_pos=prev_pos, deal_reference=...
  │         )
  │       → NO DB write, NO alert, NO removal from previous_positions

paper_loop._detect_broker_closed()   [next iteration N+1, N+2, ...]
  ├─ for deal_id, pending in pending_close_detections.items():
  │     if now - pending.first_seen > TIMEOUT (10 min default):
  │       → UNRECONCILED path
  │       continue
  │     result = _match_transaction(fresh_transactions, ...)
  │     if result.matched:
  │       → persist close with REAL data
  │       → metric: path=primary, retry_count=N
  │       → log INFO "Reconciled after N retries"
  │       → remove from pending_close_detections
```

### 5.4 Close detection — UNRECONCILED timeout

```
  │     else if timed_out:
  │       → persist Position(
  │           deal_id,
  │           exit_price=prev_pos['level'] (last broker snapshot mid-price),
  │           pnl=NULL,
  │           close_reason='UNRECONCILED',
  │           closed_at=now
  │         )
  │       → metric: path=unreconciled
  │       → Telegram alert:
  │          "⚠️ {epic} closed by broker. P&L not confirmed.
  │           Run: python scripts/reconcile_position.py --deal-id {X}"
  │       → remove from previous_positions and pending_close_detections
  │       → log ERROR with full dump (prev_pos, last transactions fetched)
```

### 5.5 Manual reconciliation CLI

```
python scripts/reconcile_position.py --deal-id 00018509-...
  ├─ Fetch Transaction History (window configurable, default 7d)
  ├─ Apply same matching strategies as runtime
  ├─ If match found:
  │    print diff (current pnl/exit vs broker pnl/exit)
  │    prompt: "Apply UPDATE? [y/N]"
  │    if yes: UPDATE positions SET pnl=..., exit_price=..., close_reason=... WHERE deal_id=...
  ├─ If no match:
  │    print "No match found. Manual value? [enter to skip]"
  │    prompt for pnl + exit_price
  │    UPDATE with confirmation
  ├─ Refuse if Position.status != 'CLOSED' with message to use /positions/close first
```

### 5.6 Observable states

| Metric state | Meaning |
|--------------|---------|
| `path=primary, retry_count=0` | Healthy |
| `path=primary, retry_count=1-3` | Broker API occasionally slow, tolerable |
| `path=deferred` (in-flight > 0 for sustained time) | Broker API degraded, monitor |
| `path=unreconciled` (rate > 0) | Incident — eyes-on required |

---

## 6. Error Handling & Edge Cases

1. **Broker API down / timeout.** `_fetch_recent_transactions` catches exception and returns `[]`. All disappeared positions enter deferred. Loop continues. After 10 min → UNRECONCILED.
2. **Backend restart mid-retry.** `pending_close_detections` is in-memory. At startup, `StateRecovery` finds positions `status='OPEN'` in DB but absent from broker → re-inserts them into `pending_close_detections` with `first_seen=now`. Worst case: extra 10 min of retry window post-restart. Acceptable.
3. **Position modified after open (trailing stop, SL/TP change).** `deal_reference` is immutable → Strategy 1 is immune. Strategy 3 reads `entry_price` from `Position` DB record (not `prev_pos['level']` which may be stale post-modify).
4. **Capital.com returns transaction with `profitAndLoss=None`.** Skipped via `continue`; next match attempt proceeds. If all candidates incomplete → deferred.
5. **Two positions, same epic, same minute.** Strategy 1 (deal_reference) is 1-to-1. Strategy 3 usually distinguishes via entry tolerance (< 0.1%). If entries are identical (possible on ML scalping): log WARNING "Ambiguous match: N candidates", pick the most recent by timestamp.
6. **`deal_reference` missing on legacy positions** (opened before this fix). Strategy 1 skips, Strategies 2+3 remain. No regression vs current behavior.
7. **Currency mismatch** (DE40 P&L in EUR, account in USD). `Transaction.pl_value` strips currency prefix; we log a WARNING if prefix differs from account currency. No conversion performed. Assumption to verify: Capital.com demo always returns account-currency P&L for the account's own trades. Follow-up if assumption fails.
8. **CLI invoked on still-open position.** Guard: refuse if `status != 'CLOSED'` with message directing to `POST /api/positions/close`.
9. **Transaction arrives after UNRECONCILED is written.** DB already has UNRECONCILED record; the loop no longer sees it in `previous_positions`. Only `reconcile_position.py` can recover. Accepted trade-off: >10 min delay is already pathological and deserves manual eyes.
10. **Kelly sizer reads from in-memory buffer.** If `_on_position_closed` is the entry point, it must skip when `pnl is None`. If it reads DB, the filter lives in the SQL query. Verified at implementation time.

---

## 7. Testing Strategy

### 7.1 New unit tests — `backend/tests/trading/test_close_detection.py`

| # | Scenario | Assertion |
|---|----------|-----------|
| 1 | Match via `deal_reference` (Strategy 1) | Real pnl used, `path=primary`, no deferred |
| 2 | Match via `deal_id` (Strategy 2) | Same |
| 3 | Match via normalized `instrument_name` (Strategy 3) — `WTIUSD` vs `Oil - Crude` | Match succeeds |
| 4 | Entry price modified after open (prev_pos level drift) | Strategy 3 uses DB `entry_price`, match succeeds |
| 5 | Transaction API returns `[]` on first iteration | Position in `pending_close_detections`, DB unchanged |
| 6 | Match succeeds on retry attempt 3 | `path=primary`, `retry_count=3` in metric |
| 7 | 10-minute timeout with no match | Position persisted `pnl=NULL`, `close_reason='UNRECONCILED'`, Telegram alert text includes "not confirmed" |
| 8 | Ambiguous match (2 candidates) | WARNING logged, most recent chosen |
| 9 | P&L currency EUR on USD account | WARNING logged, pnl value written as parsed |
| 10 | Transaction with `profitAndLoss=None` | Skipped, next candidate tried |
| 11 | Legacy Position with `deal_reference=None` | Strategy 1 skipped, Strategies 2+3 attempted |

### 7.2 Modified tests

- Remove assertions against `_fallback_close_detection` (the function no longer exists).
- Update Position fixtures to include `deal_reference`.

### 7.3 Fixtures — `backend/tests/fixtures/capital_transactions.py`

Real Capital.com demo payloads for: WTIUSD close, DE40 close, NATGAS close, transaction with null P&L, EUR-currency transaction on USD account.

### 7.4 Integration tests — `backend/tests/integration/test_close_reconciliation.py`

- Mock broker returns `[]` for 3 consecutive iterations, then matching transaction on 4th. Assert final DB record has real pnl, metric `path=primary, retry_count=3`, zero UNRECONCILED.
- Mock broker returns `[]` for >10 min of simulated time. Assert UNRECONCILED record + Telegram alert.

### 7.5 CLI tests — `backend/tests/scripts/test_reconcile_position.py`

- Match found + diff → user confirms → UPDATE executed.
- No match → manual value entered → UPDATE executed.
- Position still OPEN → refusal, no UPDATE.

### 7.6 Out of scope

- Load/performance testing of transaction history endpoint.
- Scaling beyond 2 simultaneous deferred positions (path is symmetric for N).
- Exact Prometheus counter values (assert counter-called rather than counter-equals).

### 7.7 Manual pre-merge verification (staging/demo)

1. Open one test position on each asset class (forex, crypto, index, commodity).
2. Close manually via Capital.com UI.
3. Confirm all four records in DB with `path=primary`, pnl matching broker panel (tolerance < 0.01).
4. Simulate Transaction API error (temporary disconnect) → confirm deferred path, then reconciliation at reconnect.
5. Simulate >10-minute timeout → confirm UNRECONCILED record and Telegram alert.

---

## 8. Rollout Plan

1. Implement on branch `fix/close-detection-robust` (not `master`).
2. Unit + integration test suite passes.
3. Stefano reviews diff.
4. Manual verification steps 1-5 from Section 7.7 on demo.
5. Merge to `master` → deploy backend.
6. 24-hour observation with Prometheus dashboard for `mantis_close_detection_path_total`.
7. Manually reconcile the three corrupted records from 2026-04-20 using `reconcile_position.py` once broker P&L values are known.

---

## 9. Open Questions (to resolve during implementation)

- Does `Position` model already have `deal_reference`? If yes, skip migration.
- Does Kelly sizer read `trade_history` from DB or from an in-memory buffer in `paper_loop`? The UNRECONCILED filter location depends on this.
- Does Capital.com demo ever return P&L in a currency other than the account currency for own trades? Verify by inspecting one real closed transaction.

These are not blockers for the design — they are investigation items for the implementation phase. Each has a clearly defined fallback if the assumption turns out wrong.

---

## 10. References

- Previous fix plan: `docs/superpowers/plans/2026-03-29-critical-pnl-fix.md` (partially implemented, left fallback in place).
- Evidence log: `backend/logs/algotrader_2026-04-20.log` lines 784, 794, 804 (no-match → fallback path for all three closes).
- Memory #15438 (2026-04-09): original diagnosis of the broken primary path.
- Corrupted DB records: `positions` rows id 2119 (WTIUSD), 2120 (NATGAS), 2121 (DE40).
