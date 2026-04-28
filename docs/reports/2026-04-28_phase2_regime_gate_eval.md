# Phase 2 — Regime Gate Evaluation · 2026-04-28

**Goal**: per `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 2 — wire an
HMM regime detector + PSI drift monitor in front of the signal pipeline.
Pass criteria: DD reduction > 20 %, blocked trades net P&L < 0, < 30 % of
profitable trades incorrectly blocked.

## Setup

| Knob | Value |
|---|---|
| Top-5 basket | SOLUSD, BTCUSD, ETHUSD, XAUUSD, BNBUSD |
| Timeframe | 4h |
| Walk-forward windows | `train=1512, val=378, test=126, step=126, purge=30, embargo=12` |
| Feature pruning | drop bottom 50 % by Fold-0 XGBoost importance (matches Phase 1-D) |
| Gate type | HMM 4-state regime detector |
| Gate confidence threshold | 0.65 (Phase 2 spec default) |
| Gate window | last 200 OHLC bars per signal |
| Drift monitor | trained but **not wired in this eval** (post-hoc) |
| Runner | `backend/scripts/phase2_regime_gate_eval.py` |
| HMM training | `backend/scripts/train_regime_detector.py --timeframe 4h` per epic |

Each top-5 epic has a fitted detector at `data/models/{epic}/regime/`:
`hmm_detector.pkl`, `drift_monitor.pkl`, `drift_features.json`.

> **Leakage caveat**: the HMM was trained on the full 4500-bar history,
> including the OOS test windows. This makes the gate look *better* than a
> properly walk-forward-aware version would. Even with that bias, the gate
> still failed — see verdict.

## Scorecard

Ungated (un) vs gated (gt) walk-forward OOS:

| Epic   | Sh-un | Sh-gt | DD-un | DD-gt | DDred  | Trd-un | Trd-gt | BlkPnL | FPblk |
|--------|------:|------:|------:|------:|-------:|-------:|-------:|-------:|------:|
| SOLUSD |  6.97 |  7.10 |  1.4 % |  1.1 % | +23.3 % |   329 |   319 | **+$270.78** | 5.6 % |
| BTCUSD |  5.41 |  5.13 |  0.9 % |  0.9 % |   0.0 % |   273 |   272 | **+$125.23** | 8.5 % |
| ETHUSD |  4.02 |  4.00 |  1.8 % |  1.8 % |  +0.4 % |   239 |   238 | **+$155.57** | 5.0 % |
| XAUUSD |  2.13 |  2.17 |  0.8 % |  0.8 % |   0.0 % |   135 |   133 |  +$10.91 | 2.6 % |
| BNBUSD |  2.10 |  2.00 |  2.0 % |  2.3 % | -15.7 % |   234 |   228 | **+$111.30** | 6.6 % |

`BlkPnL` = net P&L of trades whose open-time was gate-blocked (ie what the
gate *threw away*). All five are **positive** — the gate killed net winners.

`FPblk` = profitable trades blocked / profitable trades total.

Block rate across the basket: **3-5 %** of active signals → very small.
Aggregate blocked trades net: **+$673.79** profit thrown away.

## Gate criteria

| Criterion | Result | Verdict |
|---|---:|---|
| Mean DD reduction > 20 %  | **+1.6 %**     | **FAIL** |
| Blocked trades net P&L < 0 | **+$673.79** | **FAIL** |
| Profitable-trade FP block < 30 % | 6.1 % | PASS |

**Phase 2 gate verdict: FAIL**.

## Why it failed (and what it means)

The roadmap framed Phase 2 as *"this alone can transform -16 % into -5 %"*,
quoted at the bottom of §Phase 2 with **+15-25 % net P&L** and **-30-40 %
drawdown** estimated impact. Those numbers were specced when:

- Top-5 mean Sharpe was negative-to-low,
- Drawdowns were 5-20 %,
- Win-rate was at-or-below random,
- Models hadn't yet been pruned/tuned via Phase 1.

After Phase 0 (validation) + Phase 1-D (tune + prune 50 %):

- Top-5 mean Sharpe is **4.72** (Phase 1-D) → **4.13** in this eval (post-prune,
  no-tune; SOL/BTC actually higher here because tuning saturation was avoided),
- DD is **0.8-2.0 %** across all 5 — already an order of magnitude better than
  the 16 % baseline the gate was meant to cut,
- Win-rate is **60-75 %** on KEEP basket.

There is **no DD to remove**. The HMM "low confidence" regime, in this
high-Sharpe regime, correlates more with *winnable choppy entries* than
losing trends. The gate fires 3-5 % of the time and on average blocks small
winners.

This is the same structural lesson as Phase 1's +20 % gate FAIL: the gate's
pass criteria assume a high baseline DD that no longer exists.

## Decision — do NOT enable `REGIME_GATE_ENABLED`

`backend/src/utils/config.py::regime_gate_enabled` stays `False` (default).
Detectors saved to `data/models/{epic}/regime/` for future use.

The `RegimeGate` infrastructure (`hmm_detector.py`, `drift_monitor.py`,
`gate.py`, paper_loop wiring at line 2352) is fully built and tested
(16/16 unit tests pass). It will become valuable when:

- a regression in the model pushes baseline DD back above 5-10 %,
- new assets are introduced whose pre-prune walk-forward DD > 10 %,
- a risk-event needs a kill switch (HIGH_VOLATILITY regime → block).

A future re-eval should:

1. Train HMM **per walk-forward fold** (no leakage) instead of full-history,
2. Wire drift monitor too (currently unused in eval),
3. Sweep confidence thresholds (0.50, 0.55, 0.60, 0.65) and pick the one that
   maximises post-gate Sharpe rather than blocking arbitrary 5 %.

## Next step — recommendation

Skip Phase 2 enablement (gate not productive at current performance level).
Move to **Phase 3 — Real Costs in Backtest** per the roadmap:

> Spread-aware backtester, slippage model, funding cost, fee structure.
> Re-run all backtests with real costs.

This is the next *real* lever. Phase 1's Sharpe of 4.72 and Phase 2's eval
both used backtests with `default fee model` — i.e. the costs assumed, not
measured. Phase 3 verifies whether the edge survives Bybit-level taker fees,
Capital.com spread distributions, and overnight swap.

## Outputs

| File | Purpose |
|---|---|
| `backend/data/config/phase2_regime_gate_eval.json` | Full per-epic gate eval |
| `backend/data/models/{epic}/regime/hmm_detector.pkl` | Trained HMM per top-5 |
| `backend/data/models/{epic}/regime/drift_monitor.pkl` | Trained drift monitor (unused in eval) |
| `backend/data/models/{epic}/regime/drift_features.json` | Top-30 feature names for drift |

## Reproducibility

```powershell
cd backend
# Train detectors per epic (full-history HMM fit)
foreach ($e in 'SOLUSD','BTCUSD','ETHUSD','XAUUSD','BNBUSD') {
    .venv\Scripts\python.exe scripts\train_regime_detector.py --epic $e --timeframe 4h
}
# Evaluate gate on/off
.venv\Scripts\python.exe scripts\phase2_regime_gate_eval.py `
    --confidence 0.65 --gate-window 200 --prune-pct 0.5
```
