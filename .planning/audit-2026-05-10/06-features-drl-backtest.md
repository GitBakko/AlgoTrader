# Features / DRL / Backtest Audit — 2026-05-10

**Files reviewed:** `backend/src/features/`, `drl/`, `rl/`, `backtest/`, `scripts/batch_oos_scorecard.py`, tests.

---

## CRITICAL

### C1 — DRL action-space mismatch: SB3 5-action outputs fed RAW into 3-action ensemble voter
`backend/src/drl/base_drl_agent.py:106-110` + `drl/ensemble.py:136-140`

**What**: `MantisDRLAgent.predict()` returns raw integer from `self._model.predict()`. SB3 model trained on `MantisRLEnvironment` (`action_space = Discrete(5)`, `RLAction`: 0=LONG_ENTRY, 1=LONG_EXIT, 2=SHORT_ENTRY, 3=SHORT_EXIT, 4=NEUTRAL). `MantisDRLEnsemble._tally_votes()` interprets winner as 3-class `DRLEnsembleSignal.action` (0=HOLD, 1=BUY, 2=SELL). NEUTRAL(4) plurality → undefined `action=4`. The non-ensemble `MantisRLAgent._map_action()` already does correct 5→3 remapping; `base_drl_agent` lacks it.

**Why it matters**: Phase 5 PoC FAIL (Sharpe -54% BTC, -85% SOL per CLAUDE.md memory) likely caused by this. Every DRL ensemble inference is semantically broken when NEUTRAL or SHORT_EXIT majorities occur.

**Fix**: Apply 5→3 remap in `MantisDRLAgent.predict()`:
```python
_RL_TO_DRL = {0: 1, 2: 2}  # LONG_ENTRY→BUY, SHORT_ENTRY→SELL; rest→HOLD
drl_action = _RL_TO_DRL.get(int(action_scalar), 0)
```

---

### C2 — `XGBOverlayEnv` baseline expects `SignalClass` encoding (0=SELL,1=HOLD,2=BUY); DRL backtester feeds DRL encoding (0=HOLD,1=BUY,2=SELL) — INVERTED
`backend/src/rl/xgb_overlay_env.py:110-115` + `backend/src/drl/backtest.py:68`

**What**: `XGBOverlayEnv._compute_baseline_pnl`: `if sig == 2: desired = 1` (BUY→long), `elif sig == 0: desired = -1` (SELL→short). DRL backtester passes `DRLEnsembleSignal.action` where 0=HOLD, 1=BUY, 2=SELL. Result: DRL HOLD(0) interpreted as SELL→short; DRL BUY(1) → flat; DRL SELL(2) → long (coincidentally inverted to LONG).

**Why it matters**: Phase 5-bis marginal reward computed against inverted baseline. DRL agent penalized for taking positions XGBoost would also take, rewarded for opposing — exact opposite of intent. Plausible root cause of Phase 5 failure; combines with C1.

**Fix**: Add encoding parameter to `XGBOverlayEnv.__init__` (`"signalclass"` vs `"drl"`) and remap internally. OR convert DRL→SignalClass before passing: `{HOLD(0)→HOLD(1), BUY(1)→BUY(2), SELL(2)→SELL(0)}`.

---

## HIGH

### H1 — `add_historical_volatility` hardcodes `sqrt(252)` annualization for all assets including 24/7 crypto
`backend/src/features/technical.py:335` + `backend/src/drl/performance_analyzer.py:19`

**What**: Crypto trades 365d/year. `sqrt(252)` understates crypto annualized vol by ~17% (factor 0.831). Same hardcode in `MantisPerformanceAnalyzer.ANNUALIZATION_FACTOR=252` affects DRL Sharpe/Sortino on crypto.

**Why it matters**: `hvol_20` is XGBoost feature — biased cross-asset comparisons. DRL `_auto_select_for_regimes` biased against crypto-trained agents.

**Fix**: Accept `annualization_factor` parameter. Use 365 (or 365.25) for `CRYPTO_EPICS = {"BTCUSD","ETHUSD","SOLUSD","BNBUSD","DOGUSD","ICPUSD"}`.

---

### H2 — Scorecard EXCLUDE threshold (3+ failures) too lenient — catastrophic single-criterion failures get REVIEW
`backend/src/backtest/scorecard.py:71-80`

**What**: `n_failed < 3 → REVIEW`, only `>= 3 → EXCLUDE`. AUDUSD (Sharpe -19.75, WR 0.0%) fails only 2 criteria → REVIEW per code, despite catastrophic individual values. CLAUDE.md says these single criteria should EXCLUDE.

**Fix**: Add catastrophic check forcing EXCLUDE: `sharpe < -1.0 OR win_rate < 0.15 OR max_drawdown > 0.50` → bypass count gate.

---

### H3 — Walk-forward defaults (252/63/21/21) don't match CLAUDE.md production spec (2646/662/220/220)
`backend/src/models/walk_forward.py:57-64` + `backend/scripts/batch_oos_scorecard.py`

**What**: Default windows ~10-week training; CLAUDE.md spec ~110-week. `batch_oos_scorecard.py` never overrides. 42 folds requires ~12,775 bars with prod windows; default would need ~1,134.

**Why it matters**: Every OOS scorecard run uses tiny training windows → underfit XGBoost → pessimistic Sharpe estimates. Test `test_default_params_match_docs` asserts the wrong defaults.

**Fix**: Update defaults to prod spec OR add `production_factory()` and use it in `batch_oos_scorecard.py`. Update test to match.

---

### H4 — RL drawdown computed from floor-zero, not running peak — termination fires too late
`backend/src/rl/environment.py:224-228`

**What**: `peak = max(self._state.cumulative_pnl, 0.0)` — always floors to 0. True peak-to-trough (e.g., +10% → -5% = 15% DD) reported as 5%.

**Why it matters**: `max_drawdown_pct=0.01` termination guard fires when below zero, not below running high. Reward penalty understates DD by 2-10× → weak training signal against drawdowns.

**Fix**: Track `peak_pnl: float = 0.0` in `EnvState`, update each step: `hwm = max(state.peak_pnl, state.cumulative_pnl); state.peak_pnl = hwm; drawdown = hwm - state.cumulative_pnl`.

---

### H5 — Missing spread entries for KEEP-basket assets — falls back to 0.5 default (wrong both directions)
`backend/src/backtest/costs.py:ASSET_SPREADS`

**What**: Dict has 10 entries. Missing XAGUSD, US30, AAPL, AMZN. Default 0.5 price-units = ~zero cost for indices, ~0.3% per side for stocks (too high).

**Fix**: Add realistic spreads: `XAGUSD: 0.03, US30: 2.0, AAPL: 0.05, AMZN: 0.10`. Source from broker demo snapshots.

---

## MEDIUM

### M1 — Regime hysteresis applied batch-wise — look-ahead at fold boundaries
`backend/src/features/regime.py:73-76`

**What**: For bar `i = train_end - 1`, stabilized label depends on bars `train_end..train_end+hysteresis-1` (in purge or val). Mild look-ahead.

**Fix**: Apply regime detection per-fold or document batch-only contract.

---

### M2 — `normalize_rolling` warmup rows produce all-zero z-scores
`backend/src/rl/feature_pipeline.py:71-88`

**What**: Row 0 std=0 → guarded to 1.0 → all features zero. First `window` (200 default) rows degenerate.

**Fix**: `min_valid_window=30` skip threshold OR pre-populate with global stats.

---

### M3 — `_evaluate_agent` uses per-step rewards as Sharpe input, not trading returns
`backend/src/drl/trainer.py:114-127`

**What**: `analyzer.generate_report(returns)` called with reward stream, not actual return stream. Sharpe meaningless.

**Why it matters**: `_auto_select_for_regimes` picks "best" agent by reward-Sharpe, not trading-Sharpe. Wrong selection.

**Fix**: Track equity curve in env state; pass cumulative returns to analyzer at episode end.

---

## Coverage Gaps

1. ZERO tests for `MantisDRLBacktester.run` — action mapping bug uncatchable in CI
2. No fold-boundary regime transition test
3. No `XGBOverlayEnv` signal encoding test
4. No regime hysteresis fold-truncation test
5. No `scorecard.py` decision-boundary test
6. `adaptive_trainer._train_one_cycle` is stub — never produces model; untested

---

## Summary

| Pri | ID | Location | Issue |
|-----|-----|----------|-------|
| **CRITICAL** | C1 | base_drl_agent.py:106 | 5-action SB3 → 3-action ensemble; NEUTRAL→action=4 undefined |
| **CRITICAL** | C2 | xgb_overlay_env.py:110 | Inverted SignalClass vs DRL encoding — Phase 5 PoC failure cause |
| HIGH | H1 | technical.py:335 | sqrt(252) for crypto understates vol 17% |
| HIGH | H2 | scorecard.py:75 | 3-failure EXCLUDE threshold misses single-criterion catastrophes |
| HIGH | H3 | walk_forward.py:57 | Default windows don't match CLAUDE.md prod spec |
| HIGH | H4 | environment.py:224 | DD floor-zero, not running peak — late termination |
| HIGH | H5 | costs.py | Missing spreads for stocks/indices/silver |
| MEDIUM | M1-M3 | various | hysteresis look-ahead, normalize warmup, eval Sharpe wrong |
