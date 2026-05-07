# MANTIS — Production LIVE Deploy Plan
## Date: 2026-05-06
## Status: planning — NOT YET DEPLOYED

User decision (2026-05-06): keep current sizing config for LIVE
(`max_position_pct=0.20` / kelly fallback `×0.75` / `reduction_factor=0.70`).
The original "stage 2 cut to 0.05/×0.50/0.50" path is **abandoned**.

---

## Pre-flight checklist (HARD-BLOCKERS)

All must be ✅ before any LIVE switch.

### 0. Sanity at the trading-loop level
- [x] R:R fix `745f2ee` held: 9/10 epic ≥ 0.58 avg post-fix (verified 2026-05-06)
- [x] TSLA outlier root-caused 2026-05-06: NOT an `_enforce_min_tp` bypass — signals were
  emitted by ScalpScore (no MR-style floor) and the strategy used a stale snapshot price
  3 USD away from the actual fill, so the resulting pair had R:R 0.02–0.21 even though the
  pair-as-is rule was respected. Backstop shipped: `RiskManager.check_trade` step 4-ter
  rejects any signal whose final `|TP-entry| / |entry-SL|` falls below
  `MIN_SIGNAL_RR_THRESHOLD` (default 0.40). Replay of the 3 historical TSLA outliers all
  reject; control trades at R:R 0.42 / 0.72 still approve. No mix of risk-mgr SL with
  strategy TP — rule 6 preserved.
- [x] BTCUSD partial-close loop fix (live-price source) — `paper_loop._check_stop_losses` + `_update_trailing_stops` use ONLY `broker.get_market_details(epic).snapshot.{bid,offer}`
- [x] Trailing ladder compression fix (`max_ladder_cycles=2` cap) — measurement showed 44.4% sequences ended SL pre-fix
- [x] Equity sync after state recovery — broker truth wins
- [x] Ping silent fix — keep-alive immediate on task start
- [x] Tz-aware DB writes audited (signal_repository, strategy_repository, trade_repository)
- [ ] TSLA `_enforce_min_tp` bypass root-cause closed
- [x] 16 remaining pytest failures triaged 2026-05-06 — all green. Final
  baseline: **2690 passed / 0 failed / 8 skipped / 1 xfailed**, coverage
  **70.59 %** (CI floor 70 %). Fixes: stale assertions on the 2026-04-29
  trailing/reconciler refactor, AsyncMock side_effect coroutine bug,
  CloseDetector lazy-init attrs missing in `__new__`-bypassed fixtures,
  Capital.com `overnightFee` schema-name drift, DB swap-snapshot
  test-hermeticity (force broker-stub fallback), `going` bucketed on
  opened_at only post-`25444fd`, and a global `tests/conftest.py`
  autouse that forces `MR_PRIMARY_ENABLED=false` /
  `ML_PRIMARY_ENABLED=false` so paper-loop / pipeline-e2e tests
  exercise the legacy `_process_default` path instead of the routed
  primary chains (which return HOLD on mocked market data).

### 1. Risk floor / sizing config locked
Settings effective for LIVE:
```env
MAX_POSITION_PCT=0.20
KELLY_FALLBACK_FRACTION=0.75
EQUITY_FILTER_REDUCTION_FACTOR=0.70
MIN_NOTIONAL_USD=200
MIN_RISK_AMOUNT_USD=5
FOREX_USD_BASE_SIZE_MULTIPLIER=30
MAX_SPREAD_PCT=0.15
MAX_TOTAL_EXPOSURE=0.80
```
Confirmed by user 2026-05-06: this is the LIVE config.

### 2. Capital + broker
- [ ] LIVE Capital.com account funded (deposit ≥ $11,000 to match initial_equity prior)
- [ ] LIVE API keys swapped in `.env` (key + email + password) — kept off git
- [ ] `EXECUTION_MODE=LIVE` (not DEMO)
- [ ] `USE_DEMO=false`
- [ ] Capital.com REST URL switched to `https://api-capital.backend-capital.com/`
- [ ] WS URL kept `wss://api-streaming-capital.backend-capital.com/connect`
- [ ] Rate-limit headroom verified: 10 req/sec, 40 WS subs, 1000 orders/hour

### 3. Asset basket finalized
- KEEP (Phase 0 PASS): BTCUSD, ETHUSD, BNBUSD, XAUUSD, US500, NVDA, TSLA*, USDJPY, COPPER, PLATINUM
  - *TSLA pending `_enforce_min_tp` bypass close
- EXCLUDE: ICPUSD, NATGAS, EURUSD, DOGUSD, GBPUSD (auto-cut Phase 0)
- REVIEW: WTIUSD, SOLUSD, DE40 — keep ON for first 2 weeks LIVE then re-evaluate

### 4. Monitoring stack ready
- [ ] Prometheus scraping `mantis_*` counters (close-detection paths, signal counts, CB trips)
- [ ] Telegram alerts wired + tested (`ALERT_TELEGRAM_ENABLED=true`)
- [ ] In-app alerts surface in dashboard (CbBanner deployed)
- [ ] Daily P&L summary at 23:55 UTC (auto if loop running through midnight)
- [ ] PostgreSQL backup nightly (`backup_manager.py`)

### 5. Kill switches accessible
- [ ] `POST /api/trading/emergency-stop` works from external tool (curl) — does not require browser
- [ ] `POST /api/trading/reset-circuit-breakers` documented for support runbook
- [ ] `POST /api/trading/stop` (graceful) tested
- [ ] Capital.com web platform admin access verified (manual close fallback)

### 6. Test coverage minimum
- [ ] `tests/risk/` ≥ 90% lines, all pass
- [ ] `tests/broker/` ≥ 80% lines, all pass
- [ ] `tests/trading/test_close_no_synthetic_pnl.py` PASS (verified 2026-05-06)
- [ ] `tests/trading/test_stop_loss_check.py` PASS (verified 2026-05-06)
- [ ] Strategy suite 311/319 PASS (verified 2026-05-06; 8 skips known)
- [ ] Integration `test_pipeline_e2e.py::test_prediction_to_signal` triaged

### 7. Rollback procedure documented
- [ ] `.env.demo` snapshot kept alongside `.env.live`
- [ ] `docker-compose.demo.yml` ↔ `docker-compose.live.yml` swap path
- [ ] DB schema unchanged DEMO↔LIVE → no migration on switch
- [ ] Roll back: stop loop, swap `.env`, restart backend, manually close any LIVE positions on Capital.com web

---

## Rollout sequence (when checklist green)

### Day 0 — Soft launch
1. Switch `.env` to LIVE creds, mode LIVE, `USE_DEMO=false`
2. Restart backend; verify `/health` reports `trading.broker=live` + `mode=live`
3. **DO NOT start the loop yet.** Verify:
   - `broker.list_positions()` returns clean (LIVE account empty)
   - `broker.get_accounts()[0].deposit` matches funded amount
   - `risk_manager.drawdown_monitor.state.current_equity` synced to broker truth
4. Manual smoke trade: open + close 1 micro-size position via REST (e.g. EURUSD 0.001) to confirm round-trip.
5. Reset Kelly history + CB state via `POST /api/trading/reset-risk-state` so day 0 starts on a clean slate.

### Day 0 EOD — Loop on (limited basket)
1. Start loop: `POST /api/trading/start`
2. Monitor for 2 hours:
   - `check_count` increments every 60s
   - `error_count` stays 0
   - Telegram alerts on first signal
   - First closed trade: P&L matches broker `Transaction.size` (no synthetic-P&L drift)
3. If clean → leave running overnight
4. If ANY anomaly (R:R < 0.5, partial-close cycle on stale price, equity drift > $5 from broker truth, ping_silent gap > 7min) → **emergency-stop, swap back to DEMO, root-cause**

### Day 1-3 — Gradual confidence
- Watch 3 full 24h cycles with live broker close-detection working
- Daily P&L variance vs intermediate-sizing-DEMO baseline should match within 30%
- No manual interventions: 0 unreconciled rows, 0 false TP1_HIT loops

### Day 4-14 — Soak
- Full basket active
- Track:
  - Max drawdown (alert if > 5%)
  - Win rate (compare vs DEMO baseline)
  - Slippage per fill (target < 5pt avg on majors)
  - Trailing-ladder cycles per trade (cap 2 — verify no leaks)
- Decision at day 14: keep LIVE or fall back to DEMO for remediation

### Day 14+ — Steady state
- Weekly review: equity curve, Sharpe rolling 7-day, drawdown
- Monthly: full Phase 0-3 re-validation on LIVE-collected data
- No new feature flag flips during soak; only bug fixes

---

## Operational runbook (post-deploy)

### When CB trips
1. Banner appears in dashboard + Telegram alert
2. Identify root cause: which CB type? (daily_loss, consecutive_losses, max_positions, slippage_anomaly, heartbeat_timeout, volatility_spike)
3. If root cause is recoverable (e.g. consecutive losses on transient regime change) → manual reset via banner button
4. If root cause is structural (e.g. broker disconnect, model drift) → emergency-stop, root-cause, code fix, re-deploy

### When equity drifts from broker
1. Probe: `curl localhost:8000/api/system/risk-status | jq .data.current_equity`
2. Compare to Capital.com web platform live equity
3. If drift > $1: backend restart will re-sync (post-2026-05-05 fix)
4. If drift persists post-restart: state_recovery `_restore_risk_state` may have over-written; check log for "Equity drift after state recovery"

### When close-detection lags
1. Probe: `mantis_close_detection_path_total{path}` Prometheus
2. If `unreconciled` > 0: position closed at broker but no matching TRADE row
3. CLI recovery: `python scripts/reconcile_position.py --deal-id <id>` (manual broker-side P&L lookup)
4. v2 close detector should auto-handle this — alert if reconciler queue grows > 5

### When trailing migrates >2 cycles unexpectedly
- Should not happen post `max_ladder_cycles=2` fix
- If observed: log `[XAUUSD] Trailing migration cap reached (3/2)` should appear
- If cap reached but more migrations follow → register_migration logic regression, halt + investigate

---

## Known limitations / accepted risks

1. **No PPO/RL ensemble** — Phase 5-bis untested; LIVE goes XGBoost-only
2. **No regime gate** — `REGIME_GATE_ENABLED=False` (Phase 2 FAIL); accept that we'll trade through unreadable regimes, equity filter is the protection
3. **TSLA min_tp bypass open** — accept TSLA P&L noise OR exclude from basket on day 0
4. **Capital.com demo-quirk fallback paths** — close-detection v2 with /history/activity SoT mitigates, but residual edge cases tracked in `project_close_detection_v2_progress.md`
5. **No multi-broker** — single-broker dependency on Capital.com REST/WS uptime; Binance migration is wave 2

---

## When to abort the LIVE switch

Hard blockers — stop and revert to DEMO if any of these surface in the
first 7 days:

- Net P&L < −5% of initial equity in any 24h window
- ≥ 2 unreconciled close events in any 24h window
- Trailing ladder fires > 2 cycles on any single position (cap regression)
- Capital.com session_silent > 15min on any sustained period
- BTCUSD/XAUUSD partial-close loop pattern returns (any sign of stale-price trigger)
- Manual broker dashboard shows positions diverging from MANTIS dashboard
