# M1 — Money-Path Correctness Fixes (audit round 2)

**Date:** 2026-06-11 · **Source:** repo audit 2026-06-10 (`D:\tmp\MANTIS_AUDIT_2026-06-10.md`, §5 Milestone 1), all findings adversarially verified at the cited lines · **Approved scope:** full M1 + partial M1.8 (user decision 2026-06-11).

## Goal

Close the 10 verified correctness/security gaps on the trading money path before any LIVE deploy. Every fix is surgical; no refactors beyond what each fix needs (exception: `_finalize_entry` extraction, which IS the fix for M1.5's diverged copy).

## Process (per task, non-negotiable)

1. Regression test written FIRST; must fail on current HEAD.
2. Minimal fix.
3. Module test files green.
4. Atomic commit (`fix:`/`test:` prefix, one task per commit).

End of round: full backend suite + ruff + black green, frontend tests green (for M1.10), push `main` + `feature/forward-demo-lab`.

## Operating constraints

- **forward-lab trades 24/7 from this working tree** and imports only `src.broker.*` + `src.utils.config` → **no edits to `src/broker/`** in this round. M1 touches trading/risk/execution/api — safe.
- Main backend is deliberately DOWN (user decision 2026-06-11) → no live process picks up paper_loop edits.
- `_process_epic` is 1,010 lines: edits inside it stay minimal and localized (M1.2, M1.5).

## Tasks

| # | Fix | Where | Acceptance |
|---|---|---|---|
| M1.1 | Kelly deque slice + maxlen contract: `list(trade_history)[-n:]`; new public `PaperTradingLoop.seed_trade_history(history)` wrapping `deque(..., maxlen=200)`; `main.py` recovery uses it instead of poking `_trade_history` | `kelly_sizer.py:64-68`, `paper_loop.py`, `main.py:396-398` | 31st in-session trade sizes normally with a deque history (test reproduces TypeError on HEAD); recovery path keeps the 200-cap |
| M1.2 | Risk caps see in-flight opens: copy position list at tick start; append minimal stub (epic, direction, size, entry) after each successful open; early-exit count uses live count | `paper_loop.py:2402,2431,2475,3049` | Fake 9-open book + 3 simultaneous signals approves exactly 1 (`max_total_open_positions=10`); exposure cap respected in same tick |
| M1.3 | `_live_fill` retry requires broker-confirmed rejection: on `None` confirmation keep `dealReference`, confirm via `list_positions` match (epic+direction+size, <30s) before ANY re-submit; found → treat as filled, push stops; not found → single no-stops retry; `except Exception: pass` → explicit `CapitalComError` handling | `order_manager.py:338-391,447-451` | Mock two-phase timeout-after-fill → exactly one net position, stops pushed; confirmed-rejection path still retries |
| M1.4 | Reconciler outage: DEMO/LIVE position-fetch failure → skip tick (WARNING + counter), never substitute `[]`; trailing state unregisters only on confirmed close | `paper_loop.py:2144-2152,3643-3648` | Outage test: trailing state intact, zero UNRECONCILED rows from a single timeout |
| M1.5 | Min-size lift bounded + unified success path: post-lift re-run exposure check (`final = min(lifted, cap)`, 7-bis pattern); fix stale ">=80%" comment; extract `_finalize_entry()` used by main and retry-success paths | `paper_loop.py:3113-3123,3447-3536,3159-3445` | Lifted size never exceeds exposure cap (test); retry fill gets stops-align + `_level_deviations` + R:R check + EXECUTED audit rows (test asserts parity with main path) |
| M1.6 | `partial_close` honesty: pre-check `remaining_size >= minDealSize` (refuse scale-out otherwise); reopen failure → `success=False` + `degenerate_full_close=True` detail; caller alerts and records true outcome | `execution_engine.py:520-609`, `paper_loop.py:3781-3848` | Near-min scale-out refused (test); reopen-failure test shows alert + audit row reflecting full close |
| M1.7 | SL/TP side validation in `check_trade` step 4-bis (BUY: SL<entry<TP; SELL: TP<entry<SL) + R:R floor on signed distances | `risk_manager.py:307-332` | Inverted-levels signal REJECTED with audit reason (test); the April R:R-inversion class is caught at the gate |
| M1.8 | (partial) Boot hard-fail on default SECRET_KEY when `use_demo=false`; raise on EXECUTION_MODE/USE_DEMO mismatch (no silent PAPER no-op). WS auth deferred to pre-LIVE blocker memo | `config.py:643-655`, `main.py:160-175` | Boot test: non-demo + default key → RuntimeError; LIVE+USE_DEMO=true → RuntimeError; demo boots unchanged |
| M1.9 | CLOSE Trade row P&L backfill: idempotency guards (engine + loop) UPDATE `profit_loss`/`price` on the existing CLOSE row instead of skip-only | `execution_engine.py:360-384`, `paper_loop.py:827-857` | Locally-closed position ends with non-NULL `Trade.profit_loss` after reconciliation (test) |
| M1.10 | Frontend: `errorInterceptor` retries only GET/HEAD (status 0/502/503); `ApiService` throws on `success:false` envelope | `error.interceptor.ts:7,42-46`, `api.service.ts:39-63` | Vitest: POST never retried on status 0; `success:false` surfaces as error not `undefined` data |

## Execution order

M1.1 → M1.2 → M1.3 → M1.4 (the four High) → M1.7 → M1.9 → M1.5 → M1.6 → M1.8 → M1.10.

## Risks

- M1.2/M1.5 edit inside `_process_epic`: highest-traffic method in the repo; keep diffs minimal, no drive-by cleanup.
- M1.3 is live-order code: behavior covered only by mocks until next DEMO session; flag for observation on next backend start.
- M1.5 `_finalize_entry` extraction is the only structural change: parity test (retry vs main path side-effects) is the gate.
- M1.9 touches close-detection idempotency that previously produced duplicate-row incidents (`ce2c3e1`): UPDATE must stay within the existing SELECT-then-act transaction shape.

## Out of scope (explicitly)

WS handshake auth + frontend token (pre-LIVE memo) · AUTH_REQUIRED default flip (user decision: stays false in demo) · M2.1 ClosePersister unification · M2.2 event-loop offloading (SLA <30s confirmed as target, later phase) · any `src/broker/` change.
