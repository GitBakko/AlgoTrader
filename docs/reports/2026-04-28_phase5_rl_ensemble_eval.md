# Phase 5 — RL Adaptive Layer (proof-of-concept) · 2026-04-28

**Goal**: per `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 5 — train a
PPO agent on the Phase-3 KEEP basket and use it as a timing/sizing layer on
top of the XGBoost director. Pass criteria: ensemble Sharpe > XGBoost-only
+15 %, max drawdown does not increase.

This is a proof-of-concept first pass before committing to the full
500 K-step + per-fold-retrain regime described in the roadmap.

## Setup

| Knob | Value |
|---|---|
| Top-2 basket | BTCUSD, SOLUSD (top performers Phase 3) |
| Timeframe | 4h |
| PPO total timesteps | 50 000 (vs 500 000 spec) |
| Train split | first 70 % of pre-OOS bars (single-shot, no per-fold retrain) |
| Walk-forward windows | `train=1512, val=378, test=126, step=126, purge=30, embargo=12` |
| Feature pruning | drop bottom 50 % (matches Phase 1-D / 3) |
| Ensemble logic | concordance filter (XGB=BUY ∧ PPO=LONG_ENTRY → keep, else HOLD) |
| Reward | composite (40 % scalping + 40 % sharpe + 20 % risk_adjusted) |
| Runner | `backend/scripts/phase5_rl_ensemble_eval.py` |
| Output | `backend/data/config/phase5_rl_ensemble_eval.json` |

## Result

| Epic   | Sh-XGB | Sh-Ens | Uplift  | DD-XGB | DD-Ens | DDinc  | Trd-XGB | Trd-Ens | Kept/In |
|--------|-------:|-------:|--------:|-------:|-------:|-------:|--------:|--------:|--------:|
| BTCUSD |   5.36 |   2.47 | -54.0 % |  0.9 % |  1.2 % | +34.7 %|     273 |     108 | 847 / 1897 |
| SOLUSD |   6.96 |   1.02 | -85.4 % |  1.4 % |  1.8 % | +30.8 %|     329 |      64 | 294 / 2215 |

PPO action distribution OOS was heavily skewed toward NEUTRAL on BTC and
toward SHORT_EXIT on SOL — both of which fail the strict "concordance"
test (`PPO=LONG_ENTRY` for XGB BUY, `PPO=SHORT_ENTRY` for XGB SELL).

Resulting ensemble blocks **55 %** of BTC's XGB signals and **87 %** of
SOL's. The remaining trades are too few and too noisy to maintain the
XGBoost-only Sharpe.

## Gate verdict — **FAIL**

| Criterion | Result | Pass? |
|---|---:|---|
| Sharpe uplift ≥ 15 % per epic | -54 % / -85 % | **FAIL** |
| DD does not increase per epic | +34 % / +31 % | **FAIL** |

## Why it failed (and what we learned)

1. **PPO under-trained**. 50 K steps is 10× below the spec's 500 K. The
   policy didn't converge on direction-following behaviour and defaults
   to NEUTRAL/SHORT_EXIT which the strict concordance gate rejects.

2. **Strict concordance is too aggressive**. Requiring PPO to
   independently predict the same entry direction as XGBoost discards the
   ensemble's main value (PPO acting as a *timing/sizing modulator*, not
   as a duplicate director).

3. **XGBoost is already very good**. With Phase 3 Sharpe at 4-7 across the
   top-5, the headroom for an RL overlay is minimal. Same pattern as
   Phase 1 (+20 % gate FAIL) and Phase 2 (DD-reduction FAIL): the gate
   criteria were specced for a weaker baseline that Phase 0/1/3 already
   pushed past.

4. **No reward shaping for ensemble role**. The PPO reward is the
   environment's standalone P&L. The agent is optimising "trade
   independently and beat the market" — not "veto bad XGB signals" or
   "scale size up/down on good ones". For Phase 5 to work, the reward
   must be defined relative to the XGBoost baseline.

## Decision

Do **not** wire PPO into the live paper loop. The PoC clearly shows that
a strict concordance ensemble harms performance.

A Phase 5-bis revisit becomes worthwhile when:
- the live equity curve has 2-4 weeks of post-Sizing-Revert data (so RL
  trains on a sizing-realistic distribution),
- per-fold retrain and 500 K steps are feasible compute-wise,
- the reward is reformulated as "marginal P&L over XGBoost-only".

## Outputs

| File | Purpose |
|---|---|
| `backend/scripts/phase5_rl_ensemble_eval.py` | PoC runner |
| `backend/data/config/phase5_rl_ensemble_eval.json` | Per-epic eval JSON |
| `backend/data/models/{BTCUSD,SOLUSD}/rl/ppo_phase5.zip` | Trained PoC PPOs |

## Reproducibility

```powershell
cd backend
.venv\Scripts\python.exe scripts\phase5_rl_ensemble_eval.py `
    --steps 50000 --epics BTCUSD SOLUSD
```

## Roadmap status after Phase 5 PoC

| Phase | Status |
|---|---|
| 0 — Validation Gate     | PASS (10 KEEP / 3 REVIEW / 5 EXCLUDE) |
| 1 — Focus & Optimize    | FAIL gate, but PASS practical (mean Sharpe 4.72) |
| 2 — Regime Gate         | FAIL gate, gate not enabled (DD already < 2 %) |
| 3 — Real Costs          | **PASS** (mean Sharpe 4.35 with realistic spreads) |
| 4 — Bybit Migration     | **BLOCKED** until broker account opens (next month) |
| 5 — RL Adaptive Layer   | **PoC FAIL** — revisit after sizing-revert soak |
| 6 — Advanced Alpha      | **DEFERRED** — needs 3 mo positive track record first |

The next productive lever pre-Phase-4 is the 2-week Sizing-Revert
intermediate soak. After that, either ramp to full-prod sizing
(0.05 / × 0.50 / 0.50) or revisit Phase 5-bis with a position-aware
ensemble reward and 500 K steps.
