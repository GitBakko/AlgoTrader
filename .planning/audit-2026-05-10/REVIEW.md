# MANTIS Codebase Audit Phase 2 — Consolidated Review — 2026-05-10

7 parallel reviewers (6 backend surfaces + 1 frontend). Findings ranked by production impact.

---

## CRITICAL (block LIVE deploy)

| # | File:Line | Issue | Surface |
|---|-----------|-------|---------|
| **C1-EXEC** | `execution_engine.py:354` + `:396` | Missing SELECT-then-INSERT idempotency on CLOSE Trade row in BOTH paths (session-factory + injected-repos). Violates Invariant #10. Concurrent close → duplicate Trade rows + corrupted Kelly P&L. | execution |
| **C2-EXEC** | `execution_engine.py:315, 323, 387` | `(exit-entry)*size` arithmetic P&L written to DB at 3 sites. Method docstring says no fallback; body does it anyway. Violates Trading Invariant #2 — wrong P&L for forex pip-aware pairs. | execution |
| **C1-MODELS** | `trainer.py:233, 311, 323` | `last_split = None` unguarded dereference crashes training silently on edge data sizes. PredictionService keeps stale model. | models |
| **C2-MODELS** | `trainer.py:321-330` | Calibrator fitted on last-fold val with best-fold model → leakage in rolling walk-forward when best ≠ last fold. Every traded `signal.confidence` biased over-confident. | models |
| **C1-DB** | `execution_engine.py:394` + `repository.py:79` | `BaseRepository.update(position_db)` wrong-signature crash. Every PAPER-mode API close throws TypeError, position stays OPEN in DB → ghost positions on restart. | database |
| **C2-DB** | `backup_manager.py:178` | Tz-naive vs tz-aware comparison TypeError. `cleanup_old_backups()` permanently broken; backups accumulate forever. | database |
| **C3-DB** | `models.py:23` + `alembic/env.py` | Empty `MetaData()` standalone object used as `target_metadata`. `alembic revision --autogenerate` produces destructive DROP-ALL migration. | database |
| **C1-API** | All routers | UNAUTHENTICATED trading/operations endpoints. Anyone with network access can stop trading, fire emergency-stop (closes ALL real positions), reset CBs, retrain, modify risk limits. **Auth bypass on entire control surface.** | api |
| **C2-API** | `auth.py:152` | `POST /api/auth/register` accepts `role_name` from body — anyone can self-create ADMIN account. Privilege escalation. | api |
| **C3-API** | `auth.py:487` | Avatar serve endpoint unauth + no path-traversal containment. | api |
| **C1-DRL** | `base_drl_agent.py:106` | SB3 5-action outputs (`RLAction`) fed RAW into 3-action ensemble voter. NEUTRAL(4) plurality → undefined `action=4`. Plausible root cause Phase 5 PoC failure (-54% BTC, -85% SOL). | drl |
| **C2-DRL** | `xgb_overlay_env.py:110` + `drl/backtest.py:68` | Inverted SignalClass vs DRL encoding. `XGBOverlayEnv` expects `0=SELL` but DRL backtester feeds `0=HOLD`. Phase 5-bis marginal reward semantically backwards. | drl |
| **C1-FE** | `paper-trading.component.ts:482` | Heatmap drawer routes to wrong position via epic-only match (Bug class `dea2a29`). | frontend |
| **C2-FE** | `paper-trading.component.ts:578` | Cockpit P&L hero fabricates `(current - level) * size` when UPL is null. Invariant #2 violation. Same defect in `pnlPct`. | frontend |
| **C3-FE** | `auth.interceptor.ts:14` | Module-level `isRefreshing` + `refreshTokenSubject` survive logout/login. New-session 401s queue indefinitely; old-session subscriptions fire on new-session token. | frontend |

---

## HIGH (production-impacting)

### Execution / Trading-loop
- **H1-EXEC** `order_manager.py:519` — Epic-only deal_id lookup overwrites WRONG position when two deals on same epic
- **H2-EXEC** `execution_engine.py:191` — Eager pre-close `list_positions()` doubles broker calls per close → 429 risk

### Models / Training
- **H1-MODELS** `training_orchestrator.py:273` — `asyncio.get_event_loop()` deprecated/breaks Python 3.12+
- **H2-MODELS** `training_orchestrator.py:178, 241, 265` — `progress: float` violated by string assignment, breaks WS consumers
- **H3-MODELS** `prediction_service.py:435` — Hot-reload non-atomic; window with new model + stale calibrator
- **H4-MODELS** `features/builder.py:63` — Naive `datetime.now()` silently drops sentiment data via swallowed TypeError
- **H5-MODELS** `target_builder.py:60` — `atr_14=0` produces `inf` future-return → spurious BUY/SELL training labels

### Database
- **H1-DB** `repository.py:117` — `count()` full table scan
- **H2-DB** `position_repository.py:147` — `close_reason != "UNRECONCILED"` silently drops NULL rows from perf stats

### Broker
- **H1-BROKER** `client.py:205` — HTTP 429 NOT retried; treated as non-retryable → drops orders under load
- **H2-BROKER** `session.py:199` — `_ping_loop` tight-spin on network exception (no sleep) → loop saturation on outage
- **H3-BROKER** `client.py:411` — `modify_position` Pydantic v2 `exclude_none` config invalid; latent null-leg call strips broker SL silently

### API
- **H1-API** `agents.py:26, vision.py:30` — Local `_error()` returns HTTP 200 ignoring `status` arg
- **H2-API** `models.py:520` — `success_response(..., status_code=503)` raises TypeError → 500 instead of 503
- **H3-API** `main.py:607` — Signal handler + lifespan double-close broker WS / DB
- **H4-API** `positions.py:111` — `/api/positions/closed` double-fetches up to 10K rows per page → DoS vector
- **H5-API** `websocket.py:52` — `broadcast()` not asyncio-safe; concurrent mutations during iteration drop clients

### DRL / Backtest
- **H1-DRL** `technical.py:335` + `performance_analyzer.py:19` — `sqrt(252)` annualization for crypto understates vol 17%
- **H2-DRL** `scorecard.py:75` — 3-failure EXCLUDE threshold misses single-criterion catastrophes (AUDUSD WR 0.0% → REVIEW not EXCLUDE)
- **H3-DRL** `walk_forward.py:57` + `batch_oos_scorecard.py` — Default windows (252/63/21/21) don't match CLAUDE.md prod spec (2646/662/220/220)
- **H4-DRL** `environment.py:224` — RL drawdown floor-zero, not running peak; termination fires too late
- **H5-DRL** `costs.py:ASSET_SPREADS` — Missing entries for KEEP-basket assets (XAGUSD, US30, AAPL, AMZN); 0.5 default wrong both directions

### Frontend
- **H1-FE** `websocket.service.ts:236` — `disconnect()` triggers reconnect storm on all 4 channels
- **H2-FE** `notification-center.service.ts:6` — Root-scoped service `ngOnDestroy` unreachable; reconnect loop forever
- **H3-FE** 4 services — Raw `HttpClient` bypasses `ApiService` env contract
- **H4-FE** `trade-journal.component.ts:358` — `openPositionsByEpic` last-write-wins on same epic

---

## MEDIUM (correctness concerns)

### Execution
- M1-EXEC `execution_engine.py:116` — Requested SL/TP (not broker-confirmed) stored in tracker after live fill
- M2-EXEC `execution_engine.py:347` — Spurious `session.commit()` in error branch
- M3-EXEC `order_manager.py:296` — SL/TP regex extraction without directional sanity check

### Models
- M1-MODELS `trainer.py:329` — `n_classes = len(np.unique(y))` wrong if class absent
- M2-MODELS `walk_forward.py:3` — Docstring claims expanding/rolling, code rolling-only
- M3-MODELS `train_models.py:39` — Parallel BARS_PER_DAY table diverges from `asset_metadata.py`
- M4-MODELS `calibration.py:108` — Dead expression `y_proba.shape[0]`

### Database
- M1-DB `trailing_stop_repository.py:131` — Bulk_delete N sequential SELECT+DELETE
- M2-DB `position_repository.py:73` — Missing index on `(epic, status, entry_price)` for dealId-rotation fallback
- M3-DB `trade_journal_note_repository.py:38` — `delete_note` missing `flush()`
- M4-DB `models.py:585` — `SwapDailySnapshot.id` Integer (32-bit) inconsistent

### Broker
- M1-BROKER `websocket_client.py:96` — Sync handler types declared, called with `await`
- M2-BROKER `websocket.py:326` + `pnl_snapshot_scheduler.py:125` — Quote-listener race during dual init
- M3-BROKER `models.py:122` — `SessionTokens.created_at` naive default factory

### API
- M1-API `auth.py:307` — Refresh token race under READ COMMITTED isolation
- M2-API `trading.py:159` — JSONB `features` content propagated unsanitized
- M3-API `schemas.py:14` — `success_response` HTTP 200 indistinguishable from degraded service
- M4-API `analytics.py:45` — `Path("data/historical")` relative to CWD
- M5-API `auth.py:519` — Avatar `media_type="image/jpeg"` hardcoded

### DRL
- M1-DRL `regime.py:73` — Hysteresis batch-wise; look-ahead at fold boundaries
- M2-DRL `feature_pipeline.py:71` — `normalize_rolling` warmup rows produce all-zero z-scores
- M3-DRL `trainer.py:114` — `_evaluate_agent` uses per-step rewards as Sharpe input, not trading returns

### Frontend
- M1-FE `positions.component.ts:529` — Same Invariant #2 fallback in `/positions` list
- M2-FE `backtest.component.ts:307` — Hardcoded hex colors instead of tokens
- M3-FE `signals.component.ts:173` — `(x: any)` casts lose type safety

---

## LOW

8 items across 7 reports. See individual files.

---

## Coverage Gaps (cross-cutting)

1. **`backend/tests/strategies/`** still absent (Phase 1 finding)
2. Concurrent CLOSE writes idempotency untested
3. `execution_engine._persist_close_to_db` not exercised
4. `MantisDRLBacktester.run` ZERO tests — action mapping bug uncatchable
5. `XGBOverlayEnv` signal encoding untested
6. `scorecard.py` decision-boundary untested
7. `auth.py` no test file — login fail, register dup, refresh, logout, avatar all uncovered
8. No e2e for double-position-same-epic drawer routing
9. No test for refresh-token race across logout/login
10. WS reconnect storm after logout untested
11. `backup_manager.cleanup_old_backups()` tz bug untested
12. `last_split=None` crash path untested
13. Calibrator-leakage detection untested
14. `atr_14=0` input untested

---

## Recommended Fix Order

### **Tier 1 — block LIVE deploy (auth + data integrity)**
1. **C1-API** Add auth guards to all state-changing endpoints — full bypass currently
2. **C2-API** Restrict `POST /register` `role_name` parameter — privilege escalation
3. **C1-DB** Fix `BaseRepository.update(position_db)` wrong-signature — PAPER close crash
4. **C1-EXEC + C2-EXEC** CLOSE Trade idempotency + remove arithmetic P&L fallback
5. **C2-DB** Backup cleanup tz-comparison TypeError
6. **C3-DB** `MetaData = SQLModel.metadata` — fix autogenerate

### **Tier 2 — DRL pipeline correctness (re-evaluate Phase 5 verdict)**
7. **C1-DRL + C2-DRL** Action-space remap + signal encoding alignment — likely cause of Phase 5 PoC failure
8. **C1-MODELS** `last_split=None` guard
9. **C2-MODELS** Calibrator best-fold val instead of last-fold

### **Tier 3 — frontend integrity**
10. **C1-FE + C2-FE** Match by deal_id + remove fabricated P&L fallback
11. **C3-FE + H1-FE + H2-FE** Auth interceptor reset + WS disconnect guard + notification cleanup
12. **C3-API** Avatar path containment + auth

### **Tier 4 — broker + monitoring resilience**
13. **H1-BROKER + H2-BROKER + H3-BROKER** 429 retry, ping-loop sleep, modify_position exclude_none
14. **H1-EXEC + H2-EXEC** epic-only lookup + double list_positions
15. **H3-API + H5-API** double-close shutdown + WS broadcast snapshot

### **Tier 5 — sweep**
16. All HIGH models/training (H1-H5)
17. All HIGH DRL/backtest (H1-H5)
18. HIGH database (H1-H2)
19. All HIGH frontend (H3-H4)

### **Tier 6 — MEDIUM/LOW + coverage gaps**
20. All MEDIUM items per surface
21. All LOW items
22. Add missing tests (auth, DRL backtest, scorecard, fold boundaries, atr=0, calibrator leakage)

---

## Summary by Surface

| Surface | CRITICAL | HIGH | MEDIUM | LOW |
|---------|----------|------|--------|-----|
| Execution | 2 | 2 | 3 | 0 |
| Models/Prediction | 2 | 5 | 4 | 0 |
| Database | 3 | 2 | 4 | 0 |
| Broker | 0 | 3 | 3 | 2 |
| API/Auth/WS | 3 | 5 | 5 | 3 |
| Features/DRL/Backtest | 2 | 5 | 3 | 0 |
| Frontend Angular | 3 | 4 | 3 | 1 |
| **Total Phase 2** | **15** | **26** | **25** | **6** |
| **+ Phase 1 already shipped** | 3 | 13 | 14 | 7 |
| **Total audit** | **18** | **39** | **39** | **13** |

---

## Files

- [01-execution.md](01-execution.md)
- [02-models-prediction.md](02-models-prediction.md)
- [03-database.md](03-database.md)
- [04-broker.md](04-broker.md)
- [05-api-routers.md](05-api-routers.md)
- [06-features-drl-backtest.md](06-features-drl-backtest.md)
- [07-frontend.md](07-frontend.md)
