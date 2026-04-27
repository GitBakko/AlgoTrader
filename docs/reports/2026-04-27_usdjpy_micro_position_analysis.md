# USDJPY micro-position diagnosis (2026-04-27)

## Symptom
The user observed a USDJPY paper-trading position open with a "ridiculously
small" size and a take-profit only `+0.05%` away from entry. With entry
near `152.10` that corresponds to **~7-8 pips of TP and a P&L impact in
the order of $1**, well below the noise floor of spread + swap.

## Why this happens

Sizing is computed by [`PositionSizer.calculate_size`](../../backend/src/risk/position_sizer.py)
as
```
final_size = (equity * risk_per_trade) / abs(entry - stop_loss)
```
and then capped by `max_position_pct * equity / entry`. There is **no
floor** on the resulting notional — when `stop_distance` is small the
formula returns a perfectly valid (but economically meaningless) size.

The TP comes from the strategy. For `scalp_score_strategy`:
```
sl_distance = atr * stop_multiplier        # default 2x
tp_distance = sl_distance * risk_reward_ratio   # default 2x..2.5x
```
USDJPY in low-volatility 4h regimes shows ATR/price ≈ `0.02%`. With
`stop_multiplier=2`, SL ≈ `0.04%`. With `risk_reward_ratio=2`, TP ≈
`0.08%`. The closer the regime gets to a flat tape, the tighter both
levels become — and below ~`0.05%` the spread + overnight swap eat all
the upside.

## Reproduction inputs (current `.env`)
- `EXECUTION_MODE=DEMO`
- No `MIN_RISK_AMOUNT_USD` / `MIN_NOTIONAL_USD` / `MIN_TP_PCT`
- `MAX_TOTAL_EXPOSURE=0.80`, `MAX_SPREAD_PCT=0.15`
- Strategies use ATR-based stops with no absolute floor

## Proposed remediation (separate PR)

1. **Hard floor on TP distance** (strategy layer)
   - Add `MIN_TP_PCT` setting (default `0.15%` — ~3× typical forex spread).
   - In `scalp_score_strategy.calculate_levels` and
     `mean_reversion_strategy.calculate_tp` raise the TP to
     `max(raw_tp, entry * (1 ± MIN_TP_PCT))` (signed by direction).
   - Equivalent floor on SL only if it would invert R:R.

2. **Hard floor on risk amount** (sizer layer)
   - Add `MIN_RISK_AMOUNT_USD` setting (default `$5`).
   - In `RiskManager` after sizing, if `risk_amount = size * stop_distance < MIN_RISK_AMOUNT_USD`
     reject with `error.min_notional` and surface in the rejected-signals
     feed. Do NOT auto-scale up: a too-tight stop is the symptom of a
     low-conviction regime, not something to amplify.

3. **Per-asset minimum TP override**
   - Forex pairs need a wider absolute floor than equities/crypto (spread
     overhead is proportionally larger). Add `MIN_TP_PCT_FOREX` /
     `MIN_TP_PCT_DEFAULT` so the floor scales with asset class.

## Why not fix it in this PR
Sizing/SL/TP changes touch the live trading path and need:
- Backtest revalidation across the ranked asset universe.
- Updated unit tests in `tests/risk/`, `tests/strategy/` (today they
  rely on the unconstrained formulas).
- A coordinated `.env` rollout — these floors must be set before deploy.

This document captures the root cause so the follow-up can land
independently.
