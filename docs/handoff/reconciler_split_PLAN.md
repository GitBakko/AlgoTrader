# MANTIS AI -- Reconciler Sub-Loop Split: Architecture Blueprint

**Date:** 2026-04-29  
**Target commit branch:** main (direct push authorized, pre-prod)  
**Status:** Blueprint only. Zero production lines written. Read-and-approve before coding.  
**Codebase baseline:** commit d178db2 (2026-04-29). All line refs below verified against current checkout.

---

## Premise and Invariants

This plan splits broker-position reconciliation out of the main 60s strategy tick into a faster 15s dedicated sub-loop. Every Trading Invariant from CLAUDE.md (especially #2 "no code path invents P&L", #3 "three-tier close detection unchanged", #5 "DEMO/LIVE broker authoritative") is a hard constraint that every step below satisfies. The phrase "guanti bianchi" means no surprises -- every hazard is named and mitigated before coding begins.

---

## 1. Shared-State Inventory

The following attributes on `PaperTradingLoop` are mutated by code that is being moved. Each row states who will own it after the split, who reads it from the "other side", and the precise concurrency hazard.

### 1.1 `_previous_positions: dict[str, dict]`

**Owner after split:** Reconciler loop (exclusive writer).  
**Cross-reader:** None. The strategy loop does not read this at all -- it only used it as an argument to `_detect_broker_closed` which moves to the reconciler.  
**Hazard:** None after split.  
**Action:** No lock needed. Reconciler reads and writes in a single coroutine.

Source: `paper_loop.py:213` (declaration), `paper_loop.py:1343` (write at end of `_detect_broker_closed`), `paper_loop.py:1054-1057` (write on early return).

### 1.2 `_pending_close_detections: dict[str, PendingClose]`

**Owner after split:** Reconciler loop (exclusive writer at runtime).  
**Cross-reader:** `state_recovery.reinject_orphans` (`state_recovery.py:638`) writes to it at startup. `state_recovery.rehydrate_pending_closes` (`state_recovery.py:722`) writes to it at startup. Both run ONCE, before `loop.start()` is called, so there is zero concurrent access.  
**Hazard:** If `reinject_orphans` were ever called AFTER `start()` (e.g., via a future admin API), there is a mutation-during-iteration risk. Current code does not do this. The plan preserves this invariant by documentation and an optional startup-guard assertion (see Risk #5).  
**Action:** No lock needed given the startup sequencing invariant.

Source: `paper_loop.py:216`, `state_recovery.py:638,722`.

### 1.3 `_broker_closed_deals: set` (dynamic attribute, no `__init__` declaration)

**Owner after split:** Reconciler loop (exclusive writer). Created as empty `set()` at the top of each `_detect_broker_closed` call (`paper_loop.py:1041`) and filled during that call.  
**Cross-reader:** Currently read by `_check_stop_losses` at `paper_loop.py:3120` via `getattr(self, "_broker_closed_deals", set())`. After the split, `_check_stop_losses` ALSO moves to the reconciler, so this cross-read DISAPPEARS entirely. The strategy loop no longer reads `_broker_closed_deals`.  
**Hazard:** None after split. Both the writer (`_detect_broker_closed`) and the reader (`_check_stop_losses`) live in the same reconciler tick, executing sequentially (no concurrent interleave possible within a single `async` call stack).  
**Action:** No change to existing code. Attribute remains a dynamic set.

### 1.4 `_close_detector: CloseDetector | None`

**Owner after split:** Reconciler (lazily initialized by `_get_close_detector`, called from `_detect_broker_closed`).  
**Cross-reader:** None.  
**Hazard:** None.  
**Action:** No change. Attribute stays on `PaperTradingLoop` instance; `_get_close_detector` moves to reconciler context but remains a method on `self`.

### 1.5 `_txn_cache` and `_txn_cache_ts` (dynamic attributes on `self`)

**Owner after split:** Reconciler (`_fetch_recent_transactions` uses these for 60s caching).  
**Cross-reader:** None -- `_fetch_recent_transactions` is only called from `_detect_broker_closed`.  
**Hazard:** None.  
**Action:** No change.

### 1.6 `trailing_stop_manager: TrailingStopManager`

**Owner after split:** Reconciler writes (via `_update_trailing_stops`, `_finalize_close`, `_on_position_closed` which calls `unregister_position`). Strategy loop reads (via `get_positions_async` which calls `trailing_stop_manager.get_state`).  
**Hazard:** `get_positions_async` (`paper_loop.py:370`) is called by the strategy loop. Inside it, at line 391, it iterates `trailing_stop_manager.tracked_positions`. Concurrently the reconciler's `_update_trailing_stops` may mutate `trailing_stop_manager._positions`. Under asyncio's cooperative model, a mutation only happens when a coroutine suspends at an `await`. `get_positions_async` awaits `execution_engine.get_open_positions()` (line 375), which may schedule other tasks. If the reconciler runs during that await and mutates `_positions`, the subsequent read at line 391 sees the updated dict. This is SAFE because dict iteration in Python is safe against concurrent modification as long as you don't mutate DURING the iteration itself. The reconciler would only modify `_positions` keys, not during the strategy's iteration of the same dict. Worst case: the strategy reads a key that was just removed (returns None, handled by the `if state is None` branch at line 386). Not a data-corruption hazard.  
**Action:** No lock needed. Document the cooperative-model guarantee.

### 1.7 `_trade_history: deque`, `_epic_sl_hits: dict`, `_per_asset_losses: dict`, `_asset_tracker: AssetPerformanceTracker`

**Owner after split:** Written by `_on_position_closed` (called from the reconciler's `_finalize_close`). Read by the strategy loop in `_process_epic` (SL penalty at line 2048 area, Kelly history passed to risk_manager).  
**Hazard:** `_on_position_closed` is a SYNCHRONOUS method (no `await` anywhere). Under asyncio, synchronous code runs atomically -- no other coroutine can interleave within a synchronous call stack. Therefore the reconciler calling `_on_position_closed` cannot race with the strategy loop reading the same dicts, because both are in synchronous sections.  
**Action:** No lock needed. Add a comment in `_on_position_closed` citing the cooperative-model guarantee.

### 1.8 `_level_deviations: dict[str, dict]`

**Owner after split:** Written at position OPEN time by the strategy loop (`paper_loop.py:2xxx` area, after execution). Cleaned up by `_on_position_closed` (called from reconciler). Read by `get_positions_async` (strategy loop).  
**Hazard:** Same cooperative-model safety as 1.7. `_on_position_closed` is sync; `get_positions_async` reads a snapshot via `self._level_deviations.get(deal_id)` (not iteration). Dict `.get()` is atomic.  
**Action:** No change.

---

## 2. Surgical Move List

"Moves verbatim" means the method body is unchanged. "Needs adaptation" means the calling site (not the body) changes.

| Method | Current location | Move? | How | Signature change? |
|---|---|---|---|---|
| `_detect_broker_closed` | `paper_loop.py:1025` | Stays on `PaperTradingLoop` | Called from `_run_reconciler_tick` instead of `_run_iteration` | None |
| `_fetch_recent_transactions` | `paper_loop.py:914` | Stays | Called only from `_detect_broker_closed` | None |
| `_match_transaction` | `paper_loop.py:952` | Stays | Called only from `_detect_broker_closed` | None |
| `_normalize_instrument_name` | `paper_loop.py:943` | Stays (dead code, harmless) | N/A | None |
| `_finalize_close` | `paper_loop.py:1452` | Stays | Called from `_detect_broker_closed` (reconciler path) | None |
| `_emit_unreconciled_close` | `paper_loop.py:1544` | Stays | Called from `_detect_broker_closed` | None |
| `_get_close_detector` | `paper_loop.py:1347` | Stays | Called from `_detect_broker_closed` | None |
| `_run_shadow_close_detection` | `paper_loop.py:1376` | Stays | Called from `_detect_broker_closed` | None |
| `_update_trailing_stops` | `paper_loop.py:2946` | Stays | Called from `_run_reconciler_tick` instead of `_run_iteration` | None |
| `_check_stop_losses` | `paper_loop.py:3043` | Stays | Called from `_run_reconciler_tick` instead of `_run_iteration` | None |
| `_persist_position_close` | `paper_loop.py:554` | Stays | Called from `_finalize_close` and `_emit_unreconciled_close` | None |
| `_on_position_closed` | `paper_loop.py:3289` | Stays | Called from `_finalize_close` (reconciler); same `self` | None |
| `_run_iteration` | `paper_loop.py:1843` | Stays, ADAPTED | Remove 3 calls; add flag guard | See below |
| `start()` | `paper_loop.py:1671` | Stays, ADAPTED | Spawn reconciler task if flag | See below |
| `stop()` | `paper_loop.py:1690` | Stays, ADAPTED | Cancel reconciler task | See below |

**No method needs a new module.** Everything stays on `PaperTradingLoop`. The reconciler is two new methods added to the existing class:

- `_run_reconciler_loop()`: the outer coroutine (sleep/tick/error-backoff pattern, mirrors `_run_loop`)
- `_run_reconciler_tick()`: single tick (fetch positions, detect, trailing-stop, check-SL)
- `_on_reconciler_done(task)`: done callback (mirrors `_on_task_done`)

**Adaptation of `_run_iteration` (`paper_loop.py:1843`):**

Lines 1872-1878 currently read:
```
await self._detect_broker_closed(current_positions)
await self._update_trailing_stops(current_positions)
await self._check_stop_losses(current_positions)
await self._refresh_spread_blocks()
await self._refresh_correlation_regime()
self._init_regime_gate()
```

After the split these three lines become conditional:
```
if not self._reconciler_enabled:
    await self._detect_broker_closed(current_positions)
    await self._update_trailing_stops(current_positions)
    await self._check_stop_losses(current_positions)
await self._refresh_spread_blocks()
await self._refresh_correlation_regime()
self._init_regime_gate()
```

When `RECONCILER_DEDICATED_ENABLED=false` (default), behavior is byte-identical to today.

---

## 3. New Components

**File:** `backend/src/trading/paper_loop.py` (no new file)

**New methods on `PaperTradingLoop`:**

```
_run_reconciler_loop(self) -> None  [coroutine]
_run_reconciler_tick(self) -> None  [coroutine]
_on_reconciler_done(self, task: asyncio.Task) -> None  [sync]
```

**New `__init__` attributes (added in Step 1 commit):**

```
self._reconciler_enabled: bool = get_settings().reconciler_dedicated_enabled
self._reconciler_interval: int = get_settings().reconciler_interval_seconds
self._reconciler_task: asyncio.Task | None = None
self._reconciler_lock: asyncio.Lock = asyncio.Lock()
```

**Why not a separate class or module?** All ten methods that move into the reconciler call `self.*` on `PaperTradingLoop` attributes (`self._db_session_factory`, `self.trailing_stop_manager`, `self.risk_manager`, `self.broker`, etc.). Extracting them into a `BrokerReconciler` class would require passing ~15 references from `PaperTradingLoop` into the new class, or holding a back-reference (`self.paper_loop = loop`), which is the same cyclic coupling as `state_recovery.py`. The refactoring rule is "move it, don't rewrite it." Staying on `self` satisfies this.

---

## 4. Lifecycle

### Spawn

`start()` after the split:
```python
def start(self) -> None:
    self.risk_manager.circuit_breakers.heartbeat()
    self._running = True
    self._started_at = datetime.now(UTC)
    self._task = asyncio.create_task(
        self._run_loop(), name="paper_trading_loop"
    )
    self._task.add_done_callback(self._on_task_done)
    if self._reconciler_enabled:
        self._reconciler_task = asyncio.create_task(
            self._run_reconciler_loop(), name="paper_reconciler_loop"
        )
        self._reconciler_task.add_done_callback(self._on_reconciler_done)
```

### Cancel

`stop()` after the split:
```python
def stop(self) -> None:
    self._running = False
    if self._task and not self._task.done():
        self._task.cancel()
    if self._reconciler_task and not self._reconciler_task.done():
        self._reconciler_task.cancel()
        self._reconciler_task = None
```

### `_run_reconciler_loop` structure

```python
async def _run_reconciler_loop(self) -> None:
    import random
    consecutive_errors = 0
    # Jitter on startup to desync from strategy loop's first tick
    await asyncio.sleep(random.uniform(2, 5))
    try:
        await self._run_reconciler_tick()
        consecutive_errors = 0
    except Exception as e:
        consecutive_errors += 1
        logger.error(f"Reconciler first tick failed: {e}")

    while self._running:
        try:
            await asyncio.sleep(self._reconciler_interval)
            if not self._running:
                break
            async with self._reconciler_lock:
                await self._run_reconciler_tick()
            consecutive_errors = 0
        except asyncio.CancelledError:
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Reconciler tick error ({consecutive_errors}): {e}")
            if consecutive_errors >= 10:
                raise
            backoff = min(30 * (2 ** (consecutive_errors - 1)), 300)
            await asyncio.sleep(backoff)
```

### `_run_reconciler_tick` structure

```python
async def _run_reconciler_tick(self) -> None:
    try:
        current_positions = await asyncio.wait_for(
            self.get_positions_async(), timeout=10.0
        )
    except (TimeoutError, Exception) as e:
        logger.warning(f"Reconciler position fetch failed ({e})")
        current_positions = self.get_paper_positions()
    await self._detect_broker_closed(current_positions)
    await self._update_trailing_stops(current_positions)
    await self._check_stop_losses(current_positions)
```

### Crash containment

`_on_reconciler_done` mirrors `_on_task_done`. A crash in `_reconciler_task` does NOT propagate to `_task`. `asyncio.create_task` wraps exceptions in the task object; the strategy loop coroutine is unaffected. Auto-restart fires after 30s via `loop.call_later(30.0, self._auto_restart_reconciler)`.

`_auto_restart_reconciler`:
```python
def _auto_restart_reconciler(self) -> None:
    if not self._running or self._reconciler_task and not self._reconciler_task.done():
        return
    self._reconciler_task = asyncio.create_task(
        self._run_reconciler_loop(), name="paper_reconciler_loop"
    )
    self._reconciler_task.add_done_callback(self._on_reconciler_done)
    logger.warning("Reconciler loop auto-restarted")
```

### Re-entrancy guard

`asyncio.Lock()` around `_run_reconciler_tick()`. If a tick takes longer than 15s (e.g., slow broker), the lock is held and the next iteration's `await asyncio.sleep(15)` expires, but the `async with self._reconciler_lock` blocks until the previous tick finishes. No two ticks overlap.

### Emergency-stop interaction

`POST /api/trading/emergency-stop` (`trading.py:615`) calls `paper_loop.stop()` which cancels both tasks. No change needed -- the new `stop()` cancels `_reconciler_task` too.

---

## 5. State Recovery Interaction

`state_recovery.reinject_orphans` (`state_recovery.py:557`) writes directly to `paper_loop._pending_close_detections` (line 638: `pending_map = self.paper_loop._pending_close_detections`). After the split, `_pending_close_detections` is still on `paper_loop` and still a plain dict. The reference is stable.

**Timing invariant (critical):** `main.py` calls `recovery_service.reinject_orphans()` at line 393. The loop object is created at line 345. `loop.start()` is NOT called during lifespan startup -- it is called by the `/api/trading/start` endpoint or, if AUTO_START env is set, by a startup hook that fires AFTER the lifespan. Either way, `reinject_orphans` runs before the reconciler loop exists as a task. No concurrent modification.

`state_recovery.rehydrate_pending_closes` (`state_recovery.py:680`) is defined but NEVER called from `main.py`. If wired in the future, it must be called before `loop.start()`. Add a docstring warning: "Must not be called after start()."

**No changes to `state_recovery.py` are required.** The external API (`paper_loop._pending_close_detections`, `paper_loop.paper_loop` back-ref) is preserved byte-for-byte.

---

## 6. Config and Env

**File: `backend/src/utils/config.py`**

Add inside the `Settings` class (after `close_detection_v2_enabled` at line 227):

```python
# Dedicated reconciler sub-loop.
# When True, broker-position reconciliation (detect_broker_closed,
# trailing_stops, check_stop_losses) runs in a separate asyncio.Task
# at RECONCILER_INTERVAL_SECONDS cadence, decoupled from the 60s
# strategy signal loop. When False (default), legacy behavior: all
# four calls happen inside _run_iteration at SCALP_CHECK_INTERVAL.
reconciler_dedicated_enabled: bool = Field(
    default=False, alias="RECONCILER_DEDICATED_ENABLED"
)
reconciler_interval_seconds: int = Field(
    default=15, alias="RECONCILER_INTERVAL_SECONDS"
)
```

**File: `backend/src/trading/paper_loop.py` `__init__` (~line 266, after existing init block)**

```python
_rec_settings = get_settings()
self._reconciler_enabled: bool = _rec_settings.reconciler_dedicated_enabled
self._reconciler_interval: int = _rec_settings.reconciler_interval_seconds
self._reconciler_task: asyncio.Task | None = None
self._reconciler_lock: asyncio.Lock = asyncio.Lock()
```

**Why 15s default?** Capital.com TRADE rows settle within ~5-10s of close. A 15s tick catches 100% of closes within one reconciler cycle. At 4 ticks per 60s from the reconciler plus 1 from the strategy loop, the total `list_positions` budget is 5 calls/60s = 0.083 req/s vs. the 10 req/s limit. Safe margin of 120x.

---

## 7. Test Plan

### Tests that WILL break (and why they are already green in legacy mode)

None will break in legacy mode (`RECONCILER_DEDICATED_ENABLED=false`), because the flag defaults to False and `_run_iteration` retains its four calls unchanged. All existing tests use legacy mode implicitly.

If any test is written to call `_run_iteration` and then assert on `_detect_broker_closed` behavior with `RECONCILER_DEDICATED_ENABLED=true`, it will fail. Current tests do not set this flag. Document this invariant in conftest.

### Existing tests to verify still pass (no change)

- `test_close_detection.py` -- tests `_match_transaction` directly, no behavior change
- `test_paper_loop_close_v2_shadow.py` -- calls `_detect_broker_closed` directly, no behavior change
- `test_stop_loss_check.py` -- calls `_check_stop_losses` directly, no behavior change
- `test_state_recovery_orphans.py` -- writes to `_pending_close_detections`, no behavior change
- `test_close_no_synthetic_pnl.py` -- tests the no-synthetic-P&L invariant in `_check_stop_losses`, no behavior change
- `test_integration/test_close_reconciliation_e2e.py` -- end-to-end with flag=False

### New tests to write (Step 4 commit)

1. `test_reconciler_not_started_when_flag_false` -- `loop.start()` with flag=False; assert `loop._reconciler_task is None`.

2. `test_reconciler_started_when_flag_true` -- mock `_run_reconciler_loop` as a noop coroutine; `loop.start()` with flag=True; assert `loop._reconciler_task is not None` and is an `asyncio.Task`.

3. `test_reconciler_stop_cancels_both_tasks` -- start with flag=True; `stop()`; assert both `_task` and `_reconciler_task` are cancelled or done.

4. `test_reconciler_reentrancy_guard` -- mock `_run_reconciler_tick` to sleep 30s; run two reconciler ticks overlapping; assert second tick starts AFTER first completes (verify lock semantics via timing assertion).

5. `test_reconciler_crash_does_not_kill_strategy_loop` -- mock `_run_reconciler_tick` to `raise RuntimeError("boom")`; run both tasks; assert strategy task is still alive after reconciler crashes.

6. `test_strategy_loop_skips_reconciler_calls_when_enabled` -- mock `_detect_broker_closed`, `_update_trailing_stops`, `_check_stop_losses`; run `_run_iteration` with flag=True; assert none of the three were called.

7. `test_strategy_loop_calls_reconciler_methods_when_disabled` -- same mocks; flag=False; assert all three were called (regression guard for legacy mode).

8. `test_state_recovery_handoff_before_start` -- write orphans to `_pending_close_detections` before `start()`; assert reconciler first tick picks them up via `_detect_broker_closed`.

---

## 8. Risk Register (ordered by severity)

### Risk 1 -- Concurrent broker position fetches hit Capital.com rate limit

**Severity:** HIGH  
**Failure mode:** Strategy loop and reconciler loop both call `broker.list_positions()` within the same 1s window. Capital.com demo rate limit is 10 req/s. Normally: 1 from strategy/60s + 4 from reconciler/60s = 5 total. Burst: both fire simultaneously at startup (before jitter kicks in).  
**Blast radius:** HTTP 429 on one call. Loop logs warning, falls back to empty positions. Strategy loop may see `current_positions=[]` (from `get_paper_positions()` fallback), skip reconciliation for one tick, or attempt to open positions on epics that are already at max.  
**Mitigation 1:** Startup jitter in `_run_reconciler_loop`: `await asyncio.sleep(random.uniform(2, 5))` before first tick. Desynchronizes the two loops on startup.  
**Mitigation 2:** `_fetch_recent_transactions` already caches for 60s (`paper_loop.py:927`). One transaction API call serves the entire reconciler tick.  
**Mitigation 3:** Existing broker client timeout/retry. A 429 from `list_positions` already returns empty; the reconciler falls back gracefully to `get_paper_positions()`.  
**Detection:** Monitor `mantis_broker_errors_total{type="rate_limit"}` Prometheus counter. Alert if >2 per minute.

### Risk 2 -- Double-close for positions that the strategy loop triggered via `_check_stop_losses`

**Severity:** HIGH  
**Failure mode:** At reconciler tick T, `_check_stop_losses` fires `execution_engine.close_position(deal_id)`. At tick T+1, `_detect_broker_closed` sees the position gone and tries `_finalize_close` again for the same deal.  
**Blast radius:** `_persist_position_close` called twice for the same `deal_id`. Without the PR #7 triple-fallback upsert this would create a duplicate CLOSED row.  
**Mitigation:** `_broker_closed_deals` set (reset at top of each `_detect_broker_closed` call, filled when `_finalize_close` or `_emit_unreconciled_close` runs). In the reconciler tick, `_detect_broker_closed` runs BEFORE `_check_stop_losses` (same order as legacy `_run_iteration`). The position closed by `_check_stop_losses` at tick T will be gone from `current_positions` at tick T+1, so `_detect_broker_closed` at T+1 sees it as newly disappeared and routes it through the normal Tier 1/2/3 path, NOT double-closing. The PR #7 triple-fallback upsert (`_persist_position_close:607`) also guards against duplicate rows if timing is unusual.  
**Detection:** DB query after each deployment: `SELECT deal_id, COUNT(*) c FROM positions WHERE status='CLOSED' GROUP BY deal_id HAVING c > 1`.

### Risk 3 -- Reconciler crash leaves pending closes un-processed during 30s restart window

**Severity:** MEDIUM  
**Failure mode:** Reconciler task raises an unhandled exception. Auto-restart fires after 30s. A position closes at broker during the 30s gap. On the next reconciler tick, the position is missing from broker but not in `_previous_positions` (which was correctly set in the last successful tick, so the position IS in `_previous_positions`). It enters `newly_disappeared` and is queued in `_pending_close_detections` correctly.  
**Blast radius:** Close detection is delayed by up to 45s (30s restart + 15s first tick). Still within the 10-minute Tier 2 timeout. No P&L is invented. The Tier 3 UNRECONCILED path remains intact.  
**Mitigation:** Auto-restart via `_on_reconciler_done` (same pattern as strategy loop). Log `CRITICAL` + Telegram alert on reconciler crash.  
**Detection:** `mantis_reconciler_crashes_total` counter (add in the same way `mantis_close_detection_total` is wired).

### Risk 4 -- `_reconciler_lock` deadlocks if `_run_reconciler_tick` raises inside `async with`

**Severity:** LOW  
**Failure mode:** `_run_reconciler_tick` raises inside `async with self._reconciler_lock`. asyncio `Lock` is an async context manager -- `__aexit__` is called even on exception (same guarantee as sync `with`). No deadlock.  
**Blast radius:** None. Lock is released on exception.  
**Mitigation:** No action. This is asyncio Lock standard behavior.  
**Detection:** N/A.

### Risk 5 -- Future code calls `reinject_orphans` after `loop.start()`

**Severity:** LOW (currently)  
**Failure mode:** A new admin API endpoint calls `recovery_service.reinject_orphans()` while the reconciler loop is running. `reinject_orphans` iterates `pending_map` read-then-write while the reconciler's `_detect_broker_closed` calls `del self._pending_close_detections[deal_id]`. Dict size changes during non-concurrent but interleaved async operations.  
**Blast radius:** `RuntimeError: dictionary changed size during iteration` if `_detect_broker_closed` iterates the dict without snapshots. Current code at line 1064 uses `list(self._pending_close_detections.items())` for `retry_pending` which snapshots correctly. The `del` at lines 1170/1200/1234/1241 operates on the live dict, not the snapshot. If `reinject_orphans` adds a key between the `list()` snapshot and a `del`, the del succeeds (it removes the key that existed in the snapshot). No error.  
**Mitigation:** Document: "reinject_orphans MUST NOT be called after loop.start()." Add optional assertion in `reinject_orphans`: `if self.paper_loop._running: logger.error("reinject_orphans called after start -- skip"); return 0`.  
**Detection:** The logger.error line above.

---

## 9. Rollback

The entire behavioral branch is guarded by a single read of `self._reconciler_enabled` inside `start()`. The env var `RECONCILER_DEDICATED_ENABLED` controls it.

To revert to legacy behavior without redeployment:
1. Set `RECONCILER_DEDICATED_ENABLED=false` (or remove it -- default is False)
2. Restart the backend
3. Verify log line: `Paper trading loop started (check every Xs, epics=[...])` WITHOUT a corresponding `Paper reconciler loop started`

To revert WITH redeployment (if needed):
- Every step in the change order is independently revertable via `git revert <commit>`. The flag-guard means even Steps 3 and beyond can be reverted without touching Step 1 (config) behavior.

---

## 10. Change Order (Atomic Commits)

Each step compiles, all existing tests pass, and can be reverted independently.

### Step 1 -- Config fields + `__init__` attributes (no behavior change)

Files changed:
- `backend/src/utils/config.py`: add two fields after line 227 (`close_detection_v2_enabled`)
- `backend/src/trading/paper_loop.py`: add four attributes to `__init__` (after line 265)

Test: run `pytest tests/` -- expect same pass/fail count as baseline.  
Commit message: `refactor(trading): add reconciler config fields and loop attributes`

### Step 2 -- Reconciler loop methods (scaffold, never called yet)

Files changed:
- `backend/src/trading/paper_loop.py`: add `_run_reconciler_loop`, `_run_reconciler_tick`, `_on_reconciler_done`, `_auto_restart_reconciler` methods

Test: run `pytest tests/` -- zero behavior change, all methods are unreachable (flag=False, reconciler never spawned).  
Add new test: `test_reconciler_not_started_when_flag_false`.  
Commit message: `refactor(trading): add reconciler loop scaffold (disabled by default)`

### Step 3 -- Gate reconciler methods out of strategy tick

Files changed:
- `backend/src/trading/paper_loop.py` `_run_iteration` lines 1872-1874: wrap three calls in `if not self._reconciler_enabled:`
- `backend/src/trading/paper_loop.py` `start()` lines 1683-1688: add reconciler task spawn
- `backend/src/trading/paper_loop.py` `stop()` lines 1697-1699: add reconciler task cancel

Test: run `pytest tests/` -- legacy behavior preserved (flag=False).  
Add new tests: `test_strategy_loop_skips_reconciler_calls_when_enabled`, `test_strategy_loop_calls_reconciler_methods_when_disabled`, `test_reconciler_started_when_flag_true`, `test_reconciler_stop_cancels_both_tasks`.  
Commit message: `refactor(trading): gate reconciler methods out of strategy tick (flag-guarded)`

### Step 4 -- Concurrency and crash-containment tests

Files changed:
- `backend/tests/trading/test_reconciler_lifecycle.py` (new file)

Add tests: `test_reconciler_reentrancy_guard`, `test_reconciler_crash_does_not_kill_strategy_loop`, `test_state_recovery_handoff_before_start`.  
Commit message: `test(trading): reconciler lifecycle, reentrancy, crash containment`

### Step 5 -- Enable in production (env change only)

Files changed:
- `.env` (not committed per CLAUDE.md): `RECONCILER_DEDICATED_ENABLED=true`

Deployment procedure:
1. Restart backend with `RECONCILER_DEDICATED_ENABLED=true`
2. Verify log: `paper_reconciler_loop started (interval=15s)`
3. Observe for 30 minutes: reconciler ticks every 15s in logs, strategy ticks every 60s
4. Confirm close-detection still fires within 30s on next broker-closed position
5. Monitor Prometheus for 429 rates, close detection counters

Rollback: set `RECONCILER_DEDICATED_ENABLED=false`, restart.

---

## Data Flow After Split

```
[Broker Capital.com]
       |
       | broker.list_positions() -- one call per coroutine
       |
  +----|------------------+         +----|------------------+
  |  Strategy Loop (60s) |         |  Reconciler Loop (15s) |
  |  _run_loop           |         |  _run_reconciler_loop  |
  |    _run_iteration    |         |    _run_reconciler_tick |
  |      heartbeat CB    |         |      get_positions_async|
  |      daily reset     |         |      _detect_broker_closed
  |      get_positions   |         |        _match_transaction
  |      (for gate only) |         |        _fetch_recent_txns
  |      _refresh_spread |         |        _finalize_close
  |      _refresh_regime |         |          _on_position_closed
  |      _init_regime    |         |          _persist_pos_close
  |      _process_epic   |         |          alert + WS broadcast
  |        predict       |         |        v2 shadow path
  |        signal        |         |      _update_trailing_stops
  |        risk_check    |         |      _check_stop_losses
  |        execute       |         |        (time stop / SL / TP)
  |      persist_risk    |         |        execution_engine.close
  +-----------------------+         +------------------------+
       |                                      |
       | writes: _signal_history, new position| writes: _previous_positions,
       |  _level_deviations (at open)         |  _pending_close_detections,
       |                                      |  _broker_closed_deals (ephemeral),
       |                                      |  calls _on_position_closed (sync)
       |                                      |    -> _trade_history, _epic_sl_hits,
       |                                      |    -> _per_asset_losses, _asset_tracker
       +---------- SHARED VIA self.*----------+
```

---

## Critical Implementation Notes

1. The jitter (`random.uniform(2, 5)` on reconciler startup) is not optional. Without it, both loops call `list_positions` within the same second on every backend restart.

2. Do NOT add `await` inside `_on_position_closed`. If an async operation is needed (e.g., alerting), use `asyncio.ensure_future()` as the existing code already does for `_alert_epic_cooldown` at line 3325. This preserves the synchronous atomicity guarantee.

3. The `_broker_closed_deals` set is reset to `set()` at the START of every `_detect_broker_closed` call (`paper_loop.py:1041`). This is intentional -- it prevents cross-tick bleed. After the split, it is reset at the start of every RECONCILER tick. `_check_stop_losses` (now in the same reconciler tick) reads it AFTER `_detect_broker_closed` finishes. This sequencing is preserved by `_run_reconciler_tick` calling them in the same order as `_run_iteration` does today.

4. `rehydrate_pending_closes` is dead code at the call-site level (defined, never called from main.py). Do NOT wire it during this refactor -- it requires separate analysis of whether it duplicates `reinject_orphans`.

5. The `asyncio.Lock()` for the reconciler must be created INSIDE `__init__`, not at class level. Each `PaperTradingLoop` instance needs its own lock. Existing code has no class-level shared state.

6. When running tests with `RECONCILER_DEDICATED_ENABLED=true`, tests that mock `_run_iteration` and assert it calls `_detect_broker_closed` will fail (correctly -- the methods are no longer called from the strategy tick). This is expected. New tests cover the reconciler path.

---

## Files to Create or Modify

- **`backend/src/utils/config.py`** -- add `reconciler_dedicated_enabled` and `reconciler_interval_seconds` (2 lines)
- **`backend/src/trading/paper_loop.py`** -- add 4 `__init__` attrs; add 4 new methods; adapt `_run_iteration`, `start()`, `stop()` (approximately 80 new lines, 6 modified lines)
- **`backend/tests/trading/test_reconciler_lifecycle.py`** -- new test file (~120 lines)

No other files require modification. `state_recovery.py`, `main.py`, `close_detector.py`, all routers -- unchanged.

---

*End of blueprint. Verification before coding: (1) confirm `reinject_orphans` is always called before `loop.start()` in the deployment flow, (2) confirm no test sets `RECONCILER_DEDICATED_ENABLED=true` implicitly, (3) read Steps 1-3 diffs aloud against this document before committing Step 1.*
