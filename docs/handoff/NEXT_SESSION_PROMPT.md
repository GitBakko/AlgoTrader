# MANTIS — Next Session Handoff (frozen 2026-04-28)

Read first: `CLAUDE.md` (project rules) + `MEMORY.md` (auto-memory index).

## What landed today

| Track | Commit | Status |
|---|---|---|
| Phase 0 validation re-run | `a5a8b4f` | PASS |
| Phase 1 Optuna+prune top-5 | `2931789` | gate FAIL +12.1% (practical PASS, mean Sharpe 4.72) |
| WTIUSD TP reconcile | manual DB | reconciled +$53.09 |
| Phase 2 regime gate eval | `40dfbe9` | gate FAIL — `REGIME_GATE_ENABLED=False` |
| Phase 3 realistic costs | `fdb70f0` | **PASS** mean Sharpe 4.35 |
| Sizing revert intermediate | `bfec4aa` | applied (0.20 / ×0.75 / 0.70) — 2-week soak then full-prod |
| Position-card EXP indicator | `65ce137` | live (notional + % equity) |
| Phase 5 RL PoC | `c428dd7` | FAIL — defer Phase 5-bis |
| Settings (#12) Style Bible | `c8d1724` | DONE |
| Trade Journal (#04) Style Bible | `2f0d273` | DONE |
| Strategia (#07) Style Bible | `81de886` | DONE |
| Phase 5-bis foundation (XGB-marginal reward + overlay env) | `f0da610` | shipped, untested live |
| Bybit adapter spec + mock + 17 tests | `64dbc59` | shipped, stub awaits real account |
| **CRITICAL R:R inversion fix** | `745f2ee` | shipped, backend restarted 17:24 UTC |
| MR stale tests aligned | `92eff51` | 7/7 MR pass |

## Hot decision needed at session start

**Verify R:R fix held in production.** Fix shipped 2026-04-28 17:24. Run this query at session start (>24h after fix):

```sql
SELECT epic,
       AVG(ABS(take_profit - entry_price) / ABS(stop_loss - entry_price)) AS avg_rr,
       COUNT(*) AS n
FROM positions
WHERE opened_at > '2026-04-28 17:24'
  AND stop_loss IS NOT NULL AND take_profit IS NOT NULL
GROUP BY epic
ORDER BY avg_rr;
```

Expected: avg_rr ≥ 0.75 across the basket. If anything still shows < 0.5, the fix is incomplete or another path bypasses `RiskManager.check_trade`. Investigate `_signal_handler` / `_process_epic` in `paper_loop.py` for any direct broker `create_position` that skips the SL/TP reconciliation block.

## Open follow-ups (in priority order)

### 1. Style Bible refactor — remaining 7 pages

Promote PARZIALE → CONFORME via HDR-02/03 + Bible buttons + form tokens.
Order: Posizioni #03 → Modelli AI #08 → Risk Manager #09 → Broker #10 →
Notifications #11 → Segnali AI #05 → Backtest #06.

Patterns to copy from today's commits (`c8d1724`, `2f0d273`, `81de886`):
- Eyebrow + title + meta header strip
- `.{view}-btn--ghost/secondary/primary/success` button variants
- Uppercase mono labels with letter-spacing 0.14em
- Card top-border accent variants (warning/info/danger)
- Card radius pinned to `var(--mantis-radius-sm)` (6px)

### 2. Sizing revert stage 2 (full-prod)

After 2-week soak with intermediate sizing, evaluate:
- Daily P&L variance vs intermediate baseline
- Per-trade risk in $ terms vs configured 2%

If healthy → cut to (`max_position_pct=0.05`, kelly fallback `×0.50`,
`reduction_factor=0.50`). Required before LIVE deploy.
File: `C:\Users\bakko\.claude\projects\d--Develop-AI--ClaudeCode-AlgoTrader\memory\project_sizing_relaxed_for_demo.md`.

### 3. Phase 4 Bybit migration (when account opens)

Stub at `backend/src/broker/bybit_client.py` raises `BybitNotImplementedError` on every method. Replace bodies with real V5 REST + WS calls. Protocol contract enforced by `tests/broker/test_broker_protocol.py` (17 tests). Add `BybitClient` to `runtime_protocol_check` after implementation.

Sprint 2 of Phase 4: funding rate engine using `get_funding_rate_history` + 14 funding-rate features for XGBoost.

### 4. Phase 5-bis RL revisit (after sizing-revert soak)

Foundation ready: `src/rl/xgb_overlay_env.py:XGBOverlayEnv` + `xgb_marginal_reward`. Next steps:
- Wire a runner script that uses `XGBOverlayEnv` instead of bare `MantisRLEnvironment`.
- Train PPO 500 K steps + per-fold retrain (vs PoC 50 K single-shot).
- Compare to XGBoost-only baseline post sizing-revert soak data.

### 5. Baseline test failures (~28 chronic)

Mostly:
- `tests/strategy/test_strategy_manager*.py` — need `get_settings` mocks setting `mr_primary_enabled=False` / `ml_primary_enabled=False` since production `.env` ships both true.
- `tests/trading/test_paper_loop*.py` + `test_persist_unreconciled.py` — incomplete `AsyncMock` setups (`MagicMock can't be used in 'await' expression`).
- 1 `tests/strategy/test_orb_fvg.py` — m1_bars routing.

Per-test surgery, ~2-3h focused. Not a one-shot pass. Track in CI floor decisions.

## Operational checklist for first 30 minutes of next session

1. Read `MEMORY.md` (auto-loaded) + `CLAUDE.md`.
2. Run R:R verification SQL (see "Hot decision" above).
3. `git log --oneline -20` to see recent commits.
4. Backend status: `curl http://localhost:8000/health`.
5. Frontend status: ng serve usually on `:4321` (started by user).
6. `gh pr list -R GitBakko/AlgoTrader` if working PRs.

## Files / commits to remember

- `backend/src/risk/risk_manager.py` §4-bis — **paired SL/TP rule**.
- `backend/src/backtest/costs.py` — calibrated `ASSET_SPREADS` + `OVERNIGHT_RATES` for 11 epics (was 3).
- `backend/data/models/{epic}/regime/` — HMM detectors trained but `REGIME_GATE_ENABLED=False`.
- `backend/data/models/{BTCUSD,SOLUSD}/rl/ppo_phase5.zip` — PoC PPOs, kept for inspection.
- `backend/data/config/optimal_thresholds_phase3.json` — best per-asset thresholds with realistic costs.
- `backend/src/broker/protocol.py` + `bybit_client.py` + `mock_client.py` — Phase 4 seam.
- `backend/src/rl/xgb_overlay_env.py` — Phase 5-bis env wrapper.

## Pending verification

- User has not yet confirmed the position-card EXP indicator is visible after hard refresh (commit `65ce137` verified in dist + chunk-UFIKR5M2.js + ng serve up). If still invisible: open DevTools → Network → Disable cache → `Ctrl+Shift+R`.
