# MANTIS — Next Session Prompt (frozen 2026-05-23)

Read first: `CLAUDE.md` (project rules) + `MEMORY.md` (auto-memory index).

## Stato a fine sessione 2026-05-23

### 5 commit landed on `main`
```
94ffabe  docs(phase3,phase0): re-validation reports + result snapshots
7c3d074  feat(phase3): re-run Optuna 50 trials × top-5 with new ASSET_SPREADS
373713c  docs(spread-audit): 2026-05-23 recalibration handoff + Phase 3-bis proposal
15aba8d  fix(costs): recalibrate ASSET_SPREADS from 74h audit (p95×1.1, 21 epics)
87ddf2f  fix(monitoring): add risk_event_log.source column + alembic migration
```

### Servizi residui
- **Backend uvicorn :8000** — running (task `bmpce8pt0`). Verifica: `Get-NetTCPConnection -LocalPort 8000`
- **Frontend ng serve :4321** — running (task `blrc3ck6f`). Verifica: `Get-NetTCPConnection -LocalPort 4321`
- **Paper trading loop** — STOPPED via `/api/trading/stop`
- **Spread audit collector** — STOPPED
- **Monitors stream** — TUTTI stoppati

Per stoppare residui: `POST http://localhost:8000/api/trading/stop` non serve (loop già off). Kill processi se vuoi pulizia totale.

### Working dir
- Pulito da 13 scratch files (tmp_*.json + here-string remnants)
- Resta solo WIP non-related: `paper_loop.py`, `paper-trading.component.*`, `paper-trading.ts` model (modifiche pre-sessione, non toccate)
- `.claude/scheduled_tasks.lock` deleted, `.planning/HANDOFF.json` modified (background hooks)

## Tradable basket expansion 5 → 19

Phase 0 originale (2026-04-28) era 10 KEEP / 3 REVIEW / 5 EXCLUDE su 21 asset. Spread audit ha rivelato che **8 esclusioni erano cost-driven** (fallback 0.5 catastrofico per forex, ~2272× troppo largo per USDCAD).

Post-recalibration ri-validation: **14 KEEP / 1 REVIEW (AMZN) / 0 EXCLUDE** sui 15 esclusi.

| Asset class | Pre | Post | Note |
|---|---|---|---|
| Crypto (BTC/ETH/SOL/BNB) | KEEP | KEEP | Phase 3 PASS, mean Sharpe 3.95 |
| Gold (XAU) | KEEP | KEEP* | Sharpe -1.51 (spread +37.5%), watch |
| Indices (US500/DE40) | 1 KEEP / 1 EXCL | 2 KEEP | DE40 Sharpe 1.51 post-recalib |
| Commodities (WTI/PLAT/COPPER) | 1 KEEP / 2 EXCL | 3 KEEP | PLATINUM 1.39, COPPER 2.21 |
| US Stocks (8) | 0 KEEP / 8 mixed | 7 KEEP / 1 REVIEW | AMZN REVIEW Sharpe 0.12 |
| Forex (USDJPY/CHF/CAD) | 0 KEEP / 3 EXCL | 3 KEEP | USDCHF top 3.75 |

## Priorità prossima sessione

### Priorità ALTA — 2-week paper soak validation
Enable expanded 18-asset basket (drop AMD + META REVIEW + AMZN excluded) in DEMO paper trading. Monitor for 14 days:
- Concurrent position count distribution (target: utilizing ~5-8 of 10 slots)
- Per-asset Kelly fraction drift (log `kelly_stats` every 30 min)
- Correlation guard size-multiplier rejections (count per epic)
- Realised vs expected DD (should stay < Phase 0 baseline)

Promotion to LIVE only if all above pass + no new failures appear.

Tradable basket (18 assets):
```python
PAPER_SOAK_BASKET = [
    # Core (5)
    "SOLUSD", "BTCUSD", "ETHUSD", "XAUUSD", "BNBUSD",
    # Forex (3)
    "USDCHF", "USDCAD", "USDJPY",
    # Commodities (3)
    "WTIUSD", "PLATINUM", "COPPER",
    # Indices (2)
    "US500", "DE40",
    # US Stocks (5) — AMD + META + AMZN excluded
    "MSFT", "GOOGL", "AAPL", "TSLA", "NVDA",
]
```

### Priorità MEDIA — Per-asset Kelly stats
After 2-week soak, implement `epic → deque(maxlen=100)` per-asset Kelly stats. Fallback to global when `len < min_trades=30`. ~30 lines, no architectural change. See `docs/handoff/kelly_correlation_review_2026-05-23.md` §6 (Phase 2).

### Priorità BASSA — Cleanup
- Wire OR delete the deprecated paper_loop pre-session WIP bundled into commit `48c6128` (market_status override / `_status_from_opening_hours`).
- Fix `backend/scripts/spread_audit.py` `--duration-hours` default 72h enforcement.
- `OVERNIGHT_RATES` for 10 missing epics in `backend/src/backtest/costs.py:46`.

## Hard rules da preservare

- **NO MOCK DATA NELLE MASCHERE** — invariant
- **Backend off limits unless task explicitly says backend** — autorizzato per spread audit + cost recalib in sessione `2026-05-23`
- **SL/TP paired-pair rule** (post `745f2ee`) — when strategy populates BOTH suggested_stop+suggested_tp, use pair as-is
- **MIN_RISK_AMOUNT_USD=$5** floor in step 7-bis (post `e6efede`)
- **Asyncpg tz-aware datetime**: `.replace(tzinfo=None)` per qualsiasi write Postgres
- **Reconciler split** flag-rollback via `RECONCILER_DEDICATED_ENABLED=false` se necessario
- **Capital.com Position model NO `current_price` field** — only `level` (entry) + `upl`. Live price → WS quote cache / REST `get_market_details.snapshot.{bid,offer}` / UPL reconstruction

## Reference artifacts (sessione 2026-05-23)

| Risorsa | Path |
|---|---|
| Spread audit parquet (74h, 18,732 obs) | `backend/data/diagnostics/spread_audit/2026-05.parquet` |
| Phase 3-bis proposal | `backend/docs/reports/2026-05-23_phase3-bis_spread_recalibration_PROPOSAL.md` |
| Phase 3 re-run report | `backend/docs/reports/2026-05-23_phase3_rerun.md` |
| Phase 0 ri-val report | `backend/docs/reports/2026-05-23_phase0_revalidate_excluded.md` |
| Phase 3 thresholds (Optuna 50) | `backend/data/config/optimal_thresholds_phase3_rerun_2026-05-23.json` |
| Phase 3 thresholds (no-tune) | `backend/data/config/phase3_rerun_untuned_2026-05-23.json` |
| Phase 0 ri-val snapshot | `backend/data/config/phase0_revalidate_excluded_2026-05-23.json` |
| Spread audit handoff | `docs/handoff/spread_audit_2026-05-23.md` |
| Spread audit log | `D:/tmp/algotrader/spread_audit.log` |
| Phase 3 Optuna log | `D:/tmp/algotrader/phase3_optuna_rerun.log` |
| Phase 0 ri-val log | `D:/tmp/algotrader/phase0_revalidate_excluded.log` |
| Backend log | `D:/tmp/algotrader/backend.log` |
| Frontend log | `D:/tmp/algotrader/frontend.log` |
| Re-run script | `D:/tmp/algotrader/phase3_rerun.py` |
| Phase 0 ri-val script | `D:/tmp/algotrader/phase0_revalidate_excluded.py` |

## Stato roadmap evolution

- ✅ Phase 0 Validation Gate (2026-04-28) — original 10/3/5
- ✅ Phase 1 Optuna top-5 (2026-04-28) — FAIL gate +20% target
- ✅ Phase 2 Regime gate (2026-04-28) — FAIL, gate stays disabled
- ✅ Phase 3 real costs (2026-04-28) — PASS
- ✅ Phase 4 BTC walk-forward OOS (2026-05-20) — PASS Sharpe 5.81 / MC 0.43
- ✅ Phase 3-bis spread audit (2026-05-20→05-23) — 74h passive collector + recalib
- ✅ **Phase 3 cost re-run** (2026-05-23) — PASS post-recalib
- ✅ **Phase 0 ri-validation EXCLUDE** (2026-05-23) — 14 KEEP / 1 REVIEW / 0 EXCLUDE
- ✅ **Phase 1 expansion 20-asset basket Optuna 100 trials** (2026-05-23) — PASS (18/20 KEEP, median Sharpe 2.10, top-5 mean 4.28 vs Phase 3 re-run 3.95 +8.5%; AMD + META REVIEW)
- ✅ **Risk-stack config landed** (2026-05-23) — schemas 10 slots / 0.10 pos cap, exposure guard active at default 1.0, dynamic correlation matrix decoupled + full basket + NaN/Inf validation, dead `max_correlated_exposure` cleanup
- ⏳ **2-week paper soak** — NEXT (DEMO validation before LIVE promotion)
- ⏸ Per-asset Kelly stats (Phase 2 of Kelly/correlation review) — deferred until soak data is in
- ⏸ Phase 5 RL PoC FAIL (2026-04-28, deferred Phase 5-bis)
- ⏸ Binance migration prep — still gated on paper soak completion

## Quick start prossima sessione

```bash
# 1. Verify services
Get-NetTCPConnection -LocalPort 8000,4321 -ErrorAction SilentlyContinue

# 2. If needed restart backend
cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 3. Phase 1 expansion (NEW SCRIPT TO BUILD)
cd backend && .venv/Scripts/python.exe scripts/phase1_optuna_full_basket.py --tune-trials 100 --prune-pct 0.25

# 4. AMZN deep-dive
cd backend && .venv/Scripts/python.exe scripts/walk_forward_backtest.py --epic AMZN --tune --tune-trials 100 --prune-pct 0.25 --sweep-threshold --monte-carlo
```
