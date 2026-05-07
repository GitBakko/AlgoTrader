# Phase 5-bis — RL Revisit Plan
## Date: 2026-05-06
## Status: planning (foundation shipped `f0da610`, runner TBD)

---

## Context

Phase 5 PoC (commit `c428dd7`, eval 2026-04-28) tested a *strict concordance*
ensemble where:
- XGBoost picks direction (BUY/SELL/HOLD)
- PPO acts as a gate
  - both agree → trade
  - only XGBoost confident, PPO HOLD → no trade
  - disagreement → no trade

Result: Sharpe **−54% on BTC / −85% on SOL** vs XGBoost-only baseline. The
gate threw away too many XGBoost winners because PPO had no incentive to
agree most of the time and only veto on real noise. PPO trained against
P&L directly tends to over-conservatism on noisy data, killing the
strategy's edge.

## Why Phase 5-bis exists

Foundation shipped `f0da610` introduces:
- `src/rl/xgb_overlay_env.py:XGBOverlayEnv` — wraps `MantisRLEnvironment`
  to inject XGBoost baseline cumulative-P&L stream into each step's
  state, so reward = *marginal* P&L over XGBoost (not standalone P&L).
- `src/rl/reward_functions.py:MantisRewardCalculator.xgb_marginal_reward`
  — computes `Δ = agent_step_pnl − xgb_step_pnl`. Agent gets credit
  ONLY when its action improves the XGBoost baseline.

Premise: a marginal-reward shape forces PPO to *mostly agree* with
XGBoost (zero-marginal trades cost nothing), and to deviate only when
the deviation is paid back. This sidesteps the PoC failure mode.

## Not-yet-done

1. **Runner script** `scripts/phase5bis_train_xgb_overlay.py`
   - Wires `XGBOverlayEnv` instead of bare `MantisRLEnvironment`
   - Walk-forward folds (4-fold expanding window per asset, matching
     Phase 0 layout)
   - Per-fold PPO retrain (Phase 5 PoC was 50K single-shot — failure
     mode partially attributable to under-training on a single split)

2. **Train PPO 500K steps per fold per asset**
   - Compute budget: ~6h on a single GPU per asset, or ~24h CPU-only
   - Top assets only: BTCUSD, ETHUSD, XAUUSD, US500 (Phase 0 KEEP)
   - Hyperparams from Phase 5 PoC kept as starting point

3. **Eval harness** `scripts/phase5bis_oos_compare.py`
   - Computes Sharpe / Sortino / MaxDD / WinRate / ProfitFactor per
     asset / per fold
   - Compares XGBoost-only vs XGBoost+RL ensemble
   - Bootstrap confidence intervals on Sharpe delta

4. **Decision gate**
   ```
   PASS if:
     - At least 3/4 assets show Sharpe improvement > 15% on at
       least 3/4 folds
     - Average MaxDD does not increase
     - Bootstrap p-value on Sharpe delta < 0.10

   FAIL if:
     - No asset improves Sharpe by > 5% on majority of folds
     - Or MaxDD worsens > 10% on average
     → Retire RL track. The marginal-reward formulation does not
       carry signal at this dataset size.
   ```

## Estimated effort

- Runner + eval scripts: 1-2 days
- Training compute: 24h (CPU) — 48h queued for the 4-asset basket
- Eval + analysis writeup: 1 day
- **Total wall-clock**: ~5 days, mostly idle compute

## Pre-conditions

- Phase 3 soak data (≥14 days under the intermediate sizing) so the
  baseline P&L is broker-truth not optimistic backtest
- `optimal_thresholds_phase3.json` finalized
- TSLA `_enforce_min_tp` bypass investigation closed (R:R outlier)
  → otherwise TSLA P&L is unrepresentative of the model

## Out of scope

- Multi-agent debate (Phase 6) — cited only if Phase 5-bis FAIL pushes
  research toward orthogonal directions
- Liquidation heatmap features — Bybit-specific, deprecated track in
  this evolution path (Binance migration is the new wave)

## Files to create / modify

```
scripts/phase5bis_train_xgb_overlay.py     # NEW
scripts/phase5bis_oos_compare.py           # NEW
docs/reports/2026-05-XX_phase5bis_results.md  # NEW (post-run)
src/rl/xgb_overlay_env.py                  # already shipped (f0da610)
src/rl/reward_functions.py::xgb_marginal_reward  # already shipped
```

## Decision rule for shipping

Even on PASS, **do not enable PPO ensemble in production until**:
1. Out-of-sample Sharpe gain ≥ 15% on 3+ assets
2. Live shadow-mode for 2 weeks (logging would-be PPO actions w/o
   acting) confirms agreement rate > 80% with XGBoost on benign
   regimes
3. RL training pipeline is reproducible end-to-end via CI script
