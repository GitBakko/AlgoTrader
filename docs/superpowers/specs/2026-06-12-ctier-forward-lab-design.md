# C-tier Forward-Lab Fixes — Design

**Date:** 2026-06-12
**Status:** approved (user, 2026-06-12)
**Scope:** `backend/scripts/ab/forward/` + `backend/src/utils/config.py` + one one-shot script. **Zero edits to `src/broker/`** (shared with the running lab process).
**Branch:** `feature/forward-demo-lab`

## Context

Forward Demo Lab (H2 gap-fade + H3 ORB) co-running on Capital.com 'Account test' since 2026-06-04. Four C-tier issues were queued in memory; a verified code-mapping pass (4 Haiku scouts + 4 Sonnet verifiers, 2026-06-12) corrected the picture:

1. **Restart open_px wart**: core fix ALREADY SHIPPED (`59ca9c9`, 2026-06-08 — `_session_open_price()` reconstructs the true 09:30 open from a historical M5 bar, snapshotTimeUTC-filtered). Only residuals remain.
2. **exit_price**: `_realized()` returns `fallback_px` (live mid at reconcile time, up to 15 min after the actual close) in ALL tiers. The true close price is already parsed by Pydantic (`ActivityEventDetails.level`, `models.py:535`) but never read. Live DB: 28/28 closed rows are BROKER_ACTIVITY. Bonus finding: `_realized` Tier-1 matches TRADE rows on `row['deal_id']` (create-confirmation id) only — our own EOD-flatten closes use the broker's *current* (possibly rotated) dealId, so Tier-1 can silently fail and degrade to Tier-2.
3. **429 pacing**: real bursts confirmed in logs (153 on 06-05, 112 on 06-08, 3 on 06-11). Root cause: cold-cache first pass fires ~25 GETs against the client token bucket (rate 10/s, burst 20); the existing `scan_pacing_s` sleep sits AFTER `_mid()` but BEFORE the M5 fetches, so it paces only one of up to three calls per epic. Every watchdog restart re-triggers the burst.
4. **FX EUR**: experiment account is EUR-denominated. `pl_value_in("USD")` at `scheduler.py:430/465` never warns because Capital.com demo currency `"USDd"` normalises to `"USD"` and matches the hardcoded arg — the mismatch is fully masked. Sharpe is unaffected (scale-invariant); absolute return values carry a latent ~8% EUR/USD factor (accepted, documented). **Confirmed dead guard**: `executor._halted` is read (line 40) but never set; `daily_loss_limit_usd` is never consumed after construction — the daily loss limit has never been enforced.

## Fix 1 — Hygiene + M5 gate (`scheduler.py`)

- **Delete** dead `on_session_open()` (lines 280-298). Zero callers (verified: `cmd_run` schedules only `entry_pass` + `mark_pass`; no other entry point). It still carries the pre-fix `today_open=mid` pattern — a trap if ever re-wired.
- **`mark_pass` ctx fix** (line 354): `today_open=row["today_open"] if row.get("today_open") is not None else row["entry"]`. Currently unused by any `exit_rule` (zero runtime impact) but a real bug for any future strategy that reads `ctx.today_open`.
- **Entry gate**: in `entry_pass`, after the `_session_open_price` attempt, if `strat.uses_today_open` and `epic not in self._state.open_px` → log INFO + `continue` (skip epic this pass, retry next 5-min pass). Eliminates the residual false-gap window (gap-fade entering on `today_open=mid` at 09:30-09:35 before the M5 bar publishes). ORB never reaches the gate (`uses_today_open=False`).
- **Known limitation, accepted, NOT fixed**: after a mid-session watchdog restart, `screened=False` causes RVOL re-screening at restart time; the eligible set may differ from the 09:30 screen (intraday RVOL decay). Idempotency guard prevents double entries.
- **Not backfilled**: pre-fix ledger rows (06-03→06-08) have `today_open≈entry/mid`; the true M5 open is unrecoverable from the ledger. Historical 50%-fill targets were mildly biased; noted, left as-is.

## Fix 2 — True exit_price + Tier-1 rotation + backfill

- **Tier-2 level** (`_realized`, lines ~453-467): on a matched close event, `close_px = float(a.details.level) if a.details.level is not None else fallback_px`; DEBUG log when `level` is None (empirical probe on field availability). Return `close_px` instead of `fallback_px`. P&L untouched (already broker-truth from the TRADE row).
- **Tier-1 rotation closure**: new ledger column `close_deal_id` (reuse the idempotent `ADD COLUMN` migration pattern, `ledger.py:34-41`). When `mark_pass` sends our own close (`close_position(matched.deal_id)`), persist `matched.deal_id` via new `ledger.set_close_deal_id(deal_id, close_deal_id)`. `_realized` Tier-1 then matches TRADE rows on `row['deal_id']` **or** `row['close_deal_id']`. Closes the our-close-with-rotated-dealId hole (today it degrades to Tier-2 and risks the <24h activity-window clamp).
- **Backfill one-shot** `backend/scripts/ab/backfill_exit_price.py`: for the 28 historical closed rows, query `get_activity_history` over `[closed_at−23h, closed_at]` (respects the <24h range cap; arbitrary past windows allowed), match `is_close_event() && epic && |openPrice−entry| ≤ tol` (same tol as `_realized`: `max(1e-6, |entry|·1e-4)`), extract `details.level`, `UPDATE trades SET exit_price=?`. Unresolved rows stay untouched; script prints hit-rate report. **Run manually once, after ledger backup** (`copy ledger.db ledger.pre-backfill.db`). Uses the experiment API key/session like `forward_lab.py`.

## Fix 3 — Pre-call pacing (`scheduler.py` + `config.py`)

- Helper `async def _paced(self)`: `if self.scan_pacing_s: await asyncio.sleep(self.scan_pacing_s)`.
- Call **before** every broker GET in the `entry_pass` per-epic loop: `_prev_close`, `_mid`, `_session_open_price`, `_opening_range` call sites. Remove the existing post-`_mid` sleep (lines 238-239).
- `forward_lab_scan_pacing_s` default `0.12 → 0.20` (`config.py:94`). Cold-cache first pass: ~25 GETs × 0.20s ≈ 5s wall — negligible in a 5-min tick; bucket (burst 20, refill 10/s) absorbed.
- `mark_pass` not paced (≤ `max_concurrent`=5 rows, sequential awaits, fine).

## Fix 4 — EUR semantics + stateless daily-loss guard

- `ExperimentExecutor.account_ccy: str = "EUR"` (constructor-injected like the other fields). `scheduler._realized` calls `t.pl_value_in(self.executor.account_ccy)` at both sites (430/465). If broker txn currency normalises to `"USD"` the WARNING now fires on every close — **expected and desired** (it surfaces the genuine mismatch; value used as-is, no FX conversion). If it normalises to `"EUR"`, silence is correct.
- **Daily-loss guard, stateless** (no `_halted` flag — day-roll is automatic via `session_date`):
  - New `ledger.session_net(session_date) -> float`: `SELECT COALESCE(SUM(net_pnl),0) FROM trades WHERE session_date=? AND closed_at IS NOT NULL`.
  - In `try_enter`, before strategy evaluation: `if self.ledger.session_net(session_date) <= -self.daily_loss_limit_eur:` → `logger.critical` + return None (block new entries; open positions keep their broker SL and EOD flatten).
  - Executor field renamed `daily_loss_limit_usd → daily_loss_limit_eur`. Remove the dead `_halted` field.
- **Config key kept as `forward_lab_daily_loss_limit_usd`** (comment: "EUR-denominated despite the suffix") — avoids breaking a possible `.env` override that the session cannot read (deny-list). User may rename later via `!` commands.
- Close log gets currency label: `net={net:+.2f} EUR`.
- **Scorer: no change.** Sharpe is invariant to the constant EUR/USD factor; only absolute CAGR-like values are ~8% off — documented here, accepted for the soak horizon.

## Testing

- TDD per task; tests in `backend/tests/forward/` (existing suite: `test_scheduler.py`, `test_realized_dealid.py`, `test_ledger.py`, `test_executor.py`, ...).
- Fix 1: gate skips epic when M5 open missing + retries next pass; entry proceeds when bar present; `on_session_open` gone (no references); line-354 ctx uses ledger value.
- Fix 2: Tier-2 returns `details.level` when present, `fallback_px` when None; Tier-1 matches on `close_deal_id`; ledger migration adds column idempotently; `set_close_deal_id` round-trip. Backfill script: dry-run mode test against a temp sqlite DB with fabricated activity payloads.
- Fix 3: with a recording fake client + fake sleep, assert one pace-sleep precedes each broker GET on a cold-cache pass; assert post-`_mid` sleep removed.
- Fix 4: `session_net` aggregates only closed rows of the day; `try_enter` blocks at/below `-limit` and logs CRITICAL; allows when above; `pl_value_in` receives `"EUR"`.
- Full backend suite must stay green (baseline 2268 pass / 0 fail). No file edits while the suite runs.

## Deployment / Runbook

1. Merge to `feature/forward-demo-lab`, ff to `main` (`git push . feature/forward-demo-lab:main && git push origin main feature/forward-demo-lab`).
2. Edits do NOT affect the running lab process (module already loaded). Restart deliberately OUTSIDE the 09:30-12:00 ET entry window (ideally post EOD-flatten): kill python `forward_lab.py` process → `start_forward_lab.ps1` relaunches (or wait for watchdog).
3. Before backfill: `copy backend\data\forward_lab\ledger.db backend\data\forward_lab\ledger.pre-backfill.db`, then run `backfill_exit_price.py` once; review hit-rate output.
4. Post-restart check: first entry_pass logs show paced scan, no 429 burst; first reconciled close logs `net=… EUR` and (if txn ccy is USD-normalised) the expected `pl_value_in` WARNING.

## Out of scope

- `src/broker/**` — untouchable (shared with the live lab session).
- Scorer changes, FX conversion of P&L values, ledger column renames (Option B rejected).
- Re-screening drift post-restart (known limitation, accepted).
- Main-scalper backlog (M1 follow-ups, M2.x) — separate rounds.
