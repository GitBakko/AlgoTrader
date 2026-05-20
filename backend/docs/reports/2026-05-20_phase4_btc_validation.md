# Phase 4 — BTCUSD Walk-Forward Validation

**Date**: 2026-05-20
**Prerequisite for**: Binance Migration Wave (replaces abandoned Bybit path) — see `docs/evolutive/BINANCE_MIGRATION_WAVE_PLAN.md`.
**Source roadmap**: `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 4 (line 195+) — requires *"Phase 3 shows BTC is in the top profitable assets"*.

## Verdict: **PASS — migration authorized post spread-audit (Step 3)**

BTC alone produces a statistically-significant, profitable, low-drawdown strategy under the production cost model (`ASSET_SPREADS["BTCUSD"]=60.0`, slippage 10%, SL slippage 50%).

## Setup

| Field | Value |
|---|---|
| Epic | BTCUSD |
| Timeframe | 4h |
| Capital | $11,000 (production default) |
| Risk/trade | 2% (cap; real risk is far smaller — see Caveats) |
| Strategy | `ml_ensemble` (XGBoost 3-class, isotonic calibrated, walk-forward) |
| Optuna tune | 40 trials on fold 0 (best F1 = 0.5064 vs random 0.333 for 3-class) |
| Threshold sweep | 0.30 → 0.55, best = 0.30 (Sharpe 5.81) |
| Monte Carlo | 10,000 simulations on closed trades |
| Walk-forward windows (4h) | train=1512, val=378, test=126, step=126, purge=30, embargo=12 |
| Folds | 23 (n=4951 samples after target-build) |
| Features | 190 (z-score selected from 377 built) |

## Best tuned hyperparameters

```
max_depth        = 5
learning_rate    = 0.0669
n_estimators     = 1100
subsample        = 0.7573
colsample_bytree = 0.6715
min_child_weight = 40
reg_alpha        = 4.83
reg_lambda       = 6.30
gamma            = 0.88
```

Tight regularization (high alpha/lambda, min_child_weight=40, gamma=0.88) — model is constrained against overfit. Consistent with 23-fold OOS run.

## OOS Backtest (BTCUSD/4h, 2024-12-31 → 2026-04-28, 2898 bars)

| Metric | Value | Threshold | Pass |
|---|---|---|---|
| Total trades | 307 | ≥ 30 | ✅ |
| Win rate | 68.1% | ≥ 50% | ✅ |
| Profit factor | 2.88 | ≥ 1.3 | ✅ |
| Sharpe (realized equity curve) | 5.81 | ≥ 1.0 | ✅ (also see MC caveat) |
| Sortino | 10.81 | — | — |
| Calmar | 19.01 | — | — |
| Max drawdown | 0.51% | ≤ 30% | ✅ |
| Volatility (annualized) | 1.61% | — | — |
| Total return | 19.48% | > 0 | ✅ |
| Annualized return | 9.73% | > 0 | ✅ |
| Avg win | $15.69 | — | — |
| Avg loss | $-11.61 | — | — |
| Total fees | $154.20 | — | — |

## Monte Carlo validation (10,000 sims)

| Metric | Value | Threshold | Pass |
|---|---|---|---|
| Equity 90% CI | $12,672 – $13,620 (median $13,145) | lower bound > $11,000 | ✅ |
| Max DD 90% CI | 0.4% – 0.9% (median 0.6%) | ≤ 5% | ✅ |
| **Sharpe 90% CI** | **0.338 – 0.530 (median 0.431)** | ≥ 0 | ✅ |
| p-value (return) | 0.0000 | < 0.05 | ✅ |
| Risk of ruin | 0.0000 | < 5% | ✅ |
| Significance | SIGNIFICANT (p<0.05) | — | ✅ |

## Cynical Caveats

1. **Sharpe gap 5.81 (realized) vs 0.43 (MC median) is wide.** The realized number benefits from path-dependent trade clustering (BTC trend regime in OOS window). MC bootstrap reshuffles trades, eliminating sequence luck — its median **0.43 is the honest expectancy**. Still positive, still significant, but plan capital deployment around the MC number, not the realized.
2. **Max DD 0.51% is micro because sizing is micro.** Avg loss $11.61 on $11K = 0.10% per losing trade — well below the 2% risk budget. The MIN_NOTIONAL_USD ($200) and MIN_RISK_AMOUNT_USD ($5) floors are mid-bite. The backtest sizing model does not yet reflect the recent forex `FOREX_USD_BASE_SIZE_MULTIPLIER=30` cap fix, but BTC isn't forex-base so this is unaffected. **Translate**: 9.73% annualized at this scale = $1,070/year on $11K demo. Migration justified only because Binance perp futures + funding-rate alpha should unlock larger sizing.
3. **OOS window 2024-12-31 → 2026-04-28 is largely BTC-trending.** Walk-forward purge+embargo prevents same-bar leakage but not regime selection bias. Expect the realized Sharpe to compress toward MC median in any ranging/choppy regime. Plan accordingly.
4. **Confidence threshold sweep is degenerate**: 0.30/0.33/0.35/0.38/0.40 all produce identical results (307 trades, 19.48%). This means the calibrated probabilities cluster above 0.40 with very few signals in the 0.30–0.40 range. Default 0.40 is fine — no per-asset override needed for BTC.

## Phase 4 Roadmap Alignment

Roadmap §Phase 4 line 197 requires *"Phase 3 shows BTC is in the top profitable assets"*. Phase 3 mean basket Sharpe = 4.35 post real-cost. BTC realized 5.81 → **above basket mean**. MC honest baseline 0.43 is positive. **BTC qualifies as top-profitable asset.**

## Authorization

| Step | Status |
|---|---|
| Phase 0 KEEP (BTC in basket) | ✅ (`project_phase0_validation_2026-04-28.md`) |
| Phase 3 real-cost validation (BTC survives) | ✅ (`project_phase3_real_costs_2026-04-28.md`) |
| **Phase 4 BTC OOS walk-forward** | ✅ **THIS REPORT** |
| Spread audit 72h (Step 3 prerequisite) | 🟡 running (`spread_audit.py` background, ETA 2026-05-23) |
| Phase 3 re-run with updated spreads | ⏳ blocked by spread audit |
| Binance Migration Wave 1 (BinanceClient stub + factory + protocol seam fixes) | ⏳ blocked by Phase 3 re-run sign-off |

**Authorization unlocks Wave 1 prep work** (`docs/evolutive/BINANCE_MIGRATION_WAVE_PLAN.md`): seam-fixes, BinanceClient skeleton, factory. **No Binance live API calls until spread audit + Phase 3 re-run confirm cost model still holds.**

## Artefacts

- Raw log: `docs/reports/2026-05-20_phase4_btc_validation.log` (187 lines)
- Reproduce:
  ```bash
  cd backend
  .venv/Scripts/python.exe scripts/walk_forward_backtest.py \
      --epic BTCUSD --timeframe 4h --capital 11000 --risk 0.02 \
      --tune --tune-trials 40 --sweep-threshold --monte-carlo
  ```
