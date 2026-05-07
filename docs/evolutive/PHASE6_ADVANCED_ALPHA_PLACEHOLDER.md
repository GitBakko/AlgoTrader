# Phase 6 — Advanced Alpha (placeholder)
## Date: 2026-05-06
## Status: deferred — gated behind 3-month LIVE track record

---

## Trigger conditions (NONE OF WHICH ARE MET YET)

Phase 6 work begins only when all of the following hold:

1. **3 consecutive months of positive LIVE P&L** post-`PRODUCTION_LIVE_DEPLOY_PLAN.md` switch
2. **Sharpe 6m rolling > 0.8** on broker-truth trades
3. **Phase 5-bis result is decided** (ship-or-retire) — see `PHASE5_BIS_RL_REVISIT_PLAN.md`
4. **Binance migration wave-1 stable** — see separate Binance plan (wave to be drafted)

If any of these is not met, do not start Phase 6 work. Other phases
(LIVE soak, Binance migration, Phase 5-bis run, residual debt cleanup)
are higher priority.

---

## Tracks (rough priority order, when triggered)

### Liquidation heatmap (originally Phase 6.1, source: original Sprint 5)
- Pre-condition: Binance perpetual futures account active
- Source: CoinGlass API for BTC liquidation zones (paid tier ~$30/mo)
- Magnetic price levels as XGBoost features
- Initial scope: BTCUSDT only on Binance
- Estimated effort: 1 week dev + 2 weeks shadow eval
- Decision: ship if liquidation feature improves OOS Sharpe by ≥ 10%
  on BTC walk-forward folds, neutral on others

### Multi-agent debate (originally Phase 6.2, source: original Sprint 6)
- Pre-condition: single-model improvements showing diminishing returns
  (e.g. Optuna gains < 2% per quarter)
- Agent ensemble: Technical, Sentiment, Risk, Fundamental
  (already partially built — `src/agents/`)
- Debate protocol with confidence-weighted voting
- Cost: 5-10× compute and complexity per signal
- Estimated effort: 4-6 weeks dev + 1 month live shadow
- Hard gate: ship only if XGBoost+RL ensemble has plateaued AND debate
  reduces drawdown without harming Sharpe

### Order-flow imbalance (Binance-specific track)
- Once Binance integration ships and we have raw L2 order book
- Compute OFI at 1s / 1min / 1h
- Test as XGBoost feature first, then as standalone signal
- Effort: 2-3 weeks dev + 2 weeks eval
- Pre-condition: Binance L2 stream subscribed (cost varies by tier)

### News-event-aware sizing
- Down-size positions automatically around scheduled high-impact events
  (already partially in `EconomicCalendarGate`)
- Phase 6 extension: predictive volatility model, not just calendar
  on/off
- Effort: 1-2 weeks dev + 1 week eval

---

## What NOT to do under "Phase 6"

1. **Don't add complexity for sake of headlines.** Liquidation heatmaps
   sound impressive but only justify if they prove out-of-sample.
2. **Don't pursue Multi-agent debate before Phase 5-bis is decided.**
   RL adds direction-aware reward shaping; debate adds direction-aware
   consensus. Stack them only if both individually help.
3. **Don't skip the 3-month gate.** Track record protects against
   overfitting.
4. **Don't migrate features off pure-Polars/numpy stack.** No `ta-lib`,
   no PyTorch/TF for non-RL paths (CLAUDE.md rule).

---

## Open questions (revisit at trigger)

- Will Binance's L2 stream price tier the right cost-quality trade-off?
- Has Capital.com demo→live edge degraded since Phase 0/3?
- Is the asset basket still 10 KEEP, or does live data prune more?
- Has any alternative broker emerged with cheaper crypto fees than
  Binance + better data than Capital.com? (revisit before committing
  to Binance integration)

---

## Roadmap pointer

This file replaces the speculative Phase 6 section in
`MANTIS_EVOLUTION_ROADMAP.md`. When Phase 6 work actually starts, fork
this into a per-track plan (liquidation, debate, OFI, calendar) under
`docs/evolutive/`.
