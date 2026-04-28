# Phase 3 — Real Costs in Backtest · 2026-04-28

**Goal**: per `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 3 — verify
the top-5 KEEP basket survives realistic transaction costs (spread, slippage,
overnight swap). Pass criteria: ≥ 3 assets profitable after all costs, net
Sharpe > 0.5 on top assets, profit factor > 1.2 after costs.

## Cost-table calibration

The `CostSimulator` was already wired into `BacktestEngine` since pre-Phase 0
runs, but `ASSET_SPREADS` only had explicit entries for `XAUUSD`, `BTCUSD`,
`US500`. Every other epic — including ETHUSD, SOLUSD, BNBUSD — fell back to a
flat `0.5` USD default that **dramatically underestimated** the real spread on
mid-cap crypto.

Sampled live broker snapshots on 2026-04-28 15:35 UTC:

| Epic   | Old (`ASSET_SPREADS`) | Snap abs | Snap %  | New (snap × 1.2) |
|--------|----------------------:|---------:|--------:|-----------------:|
| XAUUSD | 0.40                  | 0.50     | 0.011 % | **0.60**         |
| BTCUSD | 50.0                  | 50.0     | 0.066 % | **60.0**         |
| ETHUSD | 0.5 (default)         | 1.75     | 0.077 % | **2.10**         |
| SOLUSD | 0.5 (default)         | 0.42     | 0.500 % | **0.50**         |
| BNBUSD | 0.5 (default)         | 3.11     | 0.500 % | **3.75**         |

Buffer factor 1.2× to cover off-hours widening. ETHUSD was 4.2× under-priced,
BNBUSD was 7.5× under-priced.

`OVERNIGHT_RATES` extended from 3 epics to 11 (top-13 KEEP basket) with
Capital.com demo public swap-table approximations. Long/short rates differ;
weekend Fri/Sat charged 3× (already handled in engine).

Source: `backend/src/backtest/costs.py` updated 2026-04-28.

## Setup

| Knob | Value |
|---|---|
| Top-5 basket | SOLUSD, BTCUSD, ETHUSD, XAUUSD, BNBUSD |
| Timeframe | 4h |
| Walk-forward windows | `train=1512, val=378, test=126, step=126, purge=30, embargo=12` |
| Optuna trials per asset | 100 |
| Feature pruning | drop bottom 50 % by Fold-0 importance (matches Phase 1-D) |
| Threshold sweep | enabled |
| Monte Carlo | disabled |
| Costs | spread + 10 % slippage + 50 % SL slippage + overnight swap (3× weekend) |
| Runner | `backend/scripts/phase1_optuna_top5.py --tune-trials 100 --prune-pct 0.5` |
| Output | `backend/data/config/optimal_thresholds_phase3.json` |

## Scorecard — Phase 1-D (old spreads) vs Phase 3 (realistic spreads)

| Epic   | P1-D Sharpe | P3 Sharpe | ΔSharpe | WR % | PF   | MaxDD | Trades | Return | Threshold |
|--------|------------:|----------:|--------:|-----:|-----:|------:|-------:|-------:|----------:|
| BTCUSD | 6.63        | **6.58**  | -0.05   | 70.3 | 3.88 | 0.5 % |    259 | +19.8 % | 0.30      |
| ETHUSD | 5.08        | **4.97**  | -0.11   | 72.8 | 3.59 | 1.1 % |    173 | +24.0 % | 0.48      |
| SOLUSD | 4.96        | **4.96**  |  0.00   | 69.2 | 2.67 | 2.2 % |    308 | +34.2 % | 0.30      |
| XAUUSD | 3.31        | **3.29**  | -0.02   | 63.7 | 2.59 | 0.8 % |     80 |  +3.7 % | 0.55      |
| BNBUSD | 3.62        | **1.95**  | -1.67   | 57.8 | 1.55 | 1.3 % |    185 |  +7.2 % | 0.45      |

Mean Sharpe **4.35** (Phase 1-D was 4.72; -7.8 % cost-driven).

All 5 epics still classified `KEEP` — no failed criteria.

## Cost-impact analysis

- **BTC/ETH/SOL/XAU**: cost update barely moved the needle. Spread was either
  already correct (BTC), priced into a smaller position size via ATR-based
  Kelly (XAU's tiny ATR keeps positions small enough that absolute spread
  cost stays minimal), or the edge per trade was big enough to absorb the
  4× spread bump (ETH, SOL).
- **BNB**: hit hardest. Spread went 0.5 → 3.75 (7.5× under-priced) on
  Capital.com demo. Combined with the lowest profit factor in the basket
  (1.55), the new spread now eats almost half the per-trade edge.
  Sharpe dropped from 3.62 → 1.95 (-46 %).

This is the kind of finding Phase 3 was designed to catch: a "good"
backtest where the real-world friction was cooked-in low, masking a thin
edge. BNB still passes the gate (Sharpe 1.95, PF 1.55, DD 1.3 %) but is now
the weakest of the basket.

## Gate verdict — **PASS**

| Criterion | Result | Pass? |
|---|---:|:---:|
| ≥ 3 assets profitable after costs | 5 / 5 | ✅ PASS |
| Net Sharpe > 0.5 on top assets    | min 1.95 | ✅ PASS |
| Profit factor > 1.2 after costs   | min 1.55 | ✅ PASS |

The basket has a real edge that survives realistic transaction costs.

## Caveats

1. **Single-snapshot calibration**. New spreads were calibrated from one
   live broker snapshot at 15:35 UTC. Capital.com widens spreads off-hours
   (Asia session, weekend reopens). The 1.2× buffer is conservative but not
   measured. A future Phase 3-bis should sample spreads across a full week
   and use a distribution-aware model.
2. **Slippage model is simplistic**. `DEFAULT_SLIPPAGE_FACTOR=0.1` (10 % of
   spread). Reality is non-linear in size and volatility. For Phase 4 (Bybit)
   we should use realised-vs-mark slippage per execution.
3. **Funding rate is NOT modeled** (Capital.com CFD doesn't have funding —
   it's swap-based). For Phase 4 (Bybit perpetual futures) we'll need to
   add 8h funding-rate cost.
4. **Old swap rates retained** for XAUUSD/BTCUSD/US500 from pre-Phase-0
   defaults. New rates added for ETHUSD/SOLUSD/BNBUSD/WTIUSD/DE40/PLATINUM/
   TSLA/NVDA are public-table approximations — may differ from broker actual
   by 10-20 %.

## Decision

1. **Promote top-5 basket to extended paper run** with new costs in place.
   The Sharpe is real, the DD is < 3 % across the board, win-rate is
   55-73 %.
2. **Watch BNBUSD** — it now sits at the gate floor. If a regression
   appears in the next sweep (Sharpe drops below 1.5 OR PF below 1.3), it
   should be moved to REVIEW.
3. **Phase 4 unblocked**: BTC is the top performer (Sharpe 6.58) and is the
   prime candidate for migration to Bybit perpetual futures (lower fees,
   real funding-rate alpha, real transaction history). Per the roadmap,
   Phase 4 prerequisite is *"Phase 3 shows BTC is in the top profitable
   assets"* — clearly satisfied.

## Outputs

| File | Purpose |
|---|---|
| `backend/data/config/optimal_thresholds_phase3.json` | Phase 3 per-asset best thresholds |
| `backend/src/backtest/costs.py` | Updated `ASSET_SPREADS` + `OVERNIGHT_RATES` (top-13) |

## Reproducibility

```powershell
cd backend
.venv\Scripts\python.exe scripts\phase1_optuna_top5.py `
    --tune-trials 100 --prune-pct 0.5 `
    --output data\config\optimal_thresholds_phase3.json
```

(Same runner as Phase 1-D — the only delta is the updated cost tables in
`backend/src/backtest/costs.py`.)
