# MANTIS AI — Evolution Roadmap
## Evidence-Driven Path to Excellence
## Date: 2026-03-31

---

## Current State — Honest Assessment

### What Works
- **Architecture**: Clean Python/FastAPI + Angular + WebSocket. Modular, tested, deployable
- **Data Pipeline**: 21 assets, Parquet storage, 220+ features, multi-timeframe, sentiment, macro
- **Risk Stack**: Circuit breakers, trailing stops, equity curve filter, Kelly sizing, correlation guard (now dynamic)
- **Monitoring**: Telegram alerts, System Logs, audit trail, notification center
- **Infrastructure**: Docker, CI/CD, PostgreSQL + DuckDB + Redis (all optional)
- **Iteration Speed**: Bug-to-fix-to-deploy in hours, not days

### What Doesn't Work
- **Model Performance**: F1 0.22-0.57 on 3-class (random = 0.33). Barely above chance on most assets
- **P&L**: -$1,840 on $11,000 capital (-16.7%) after ~1,000 trades
- **No Statistical Validation**: No rigorous OOS walk-forward. We don't know if any profit is skill or luck
- **Too Many Assets**: 21 assets with weak models = 21 ways to lose money
- **Transaction Costs**: Spread, slippage, funding not in backtest. DOGUSD was burning $12/trade on spread alone
- **No Benchmark**: Never compared vs buy-and-hold or random-entry-with-same-risk-management

### Key Metrics (2026-03-31)
- Broker equity: ~$9,150 (started $11,000)
- Closed trades: ~1,030
- Broker: Capital.com (demo, CFD)
- Active models: 20 (all re-training with cross-asset features)
- Spread filter: active (MAX_SPREAD_PCT=15%)
- Correlation intelligence: active (3 levels deployed)

---

## Evolution Philosophy

> **Evidence before features. Validation before complexity. Profitability before sophistication.**

The #1 mistake in algo trading: building sophisticated systems on unvalidated foundations.
An RL agent on top of a model that doesn't predict is "a system that loses money with more elegance."

### Guiding Principles
1. **Prove it works first** — walk-forward OOS before any new feature
2. **Focus beats breadth** — 3 excellent models > 21 mediocre ones
3. **Costs are real** — every backtest must include spread, slippage, funding
4. **Simplicity is a feature** — complexity hides problems
5. **Gates are mandatory** — each phase has pass/fail criteria before the next

---

## Phase 0: Validation Gate (BLOCKING — Do First)

**Goal**: Answer one question: does the model work out-of-sample?

**Duration**: 2-3 days

### Tasks

1. **Walk-Forward OOS Test** for each of the 20 active assets
   - Expanding window: train on [0..T], test on [T..T+3mo], step 3 months
   - Minimum 4 folds per asset
   - Metrics: Sharpe, Sortino, Max DD, Win Rate, Profit Factor
   - Compare vs buy-and-hold and vs random entry with identical risk management

2. **Asset Ranking** by OOS performance
   - Rank all 20 assets by OOS Sharpe ratio
   - Identify the top 3-5 where the model shows genuine edge
   - Flag assets where model performs WORSE than random

3. **Statistical Significance Test**
   - Bootstrap confidence intervals on OOS returns
   - Is the model's edge statistically significant (p < 0.05)?
   - If not → the model is noise-fitting, not predicting

### Gate Criteria
```
PASS if:
  - At least 5 assets have OOS Sharpe > 0.5
  - At least 3 assets beat random-entry benchmark
  - Average OOS win rate > 48% across top 5 assets
  
FAIL if:
  - No asset has OOS Sharpe > 0.5
  - Model underperforms random on majority of assets
  → STOP. Do not proceed. Fix the model first.
```

### Deliverables
- `docs/validation/PHASE0_RESULTS.md` with real numbers
- Per-asset OOS equity curves
- Ranking table: epic, F1, Sharpe, win_rate, vs_random

---

## Phase 1: Focus & Optimize (1 week)

**Prerequisite**: Phase 0 PASSED

**Goal**: Concentrate on the assets where the model works. Disable the rest.

### Tasks

1. **Disable underperforming assets** — remove from TRADABLE_ASSETS the bottom 50%
2. **Hyperparameter tuning** on top 5 assets only (Optuna, 100+ trials per asset)
3. **Feature importance analysis** — identify which of the 220+ features actually matter
4. **Prune useless features** — reduce feature set to top 50-80 per asset
5. **Re-validate** — run Phase 0 again on the optimized models

### Gate Criteria
```
PASS if:
  - Top 5 assets improved OOS Sharpe by > 20% vs Phase 0
  - No feature has negative importance (removing it improves model)

FAIL if:
  - Optimization doesn't improve OOS metrics
  → Fundamental model approach may be wrong. Consider different targets/timeframes.
```

---

## Phase 2: Regime Gate (2 weeks)

**Prerequisite**: Phase 1 PASSED

**Goal**: Stop trading when the market is unreadable. This alone can transform -16% into -5%.

**Source**: Original Phase 23 Sprint 1 (preserved with minor adjustments)

### Tasks

1. **HMM Regime Detector** (`src/regime/hmm_detector.py`)
   - 4-state Hidden Markov Model: TRENDING_UP, TRENDING_DOWN, MEAN_REVERTING, HIGH_VOLATILITY
   - Confidence threshold: 0.65 (below = NO_TRADE)
   - Train on same data splits as Phase 0

2. **Feature Distribution Drift Monitor** (`src/regime/drift_monitor.py`)
   - Population Stability Index (PSI) on top 30 features
   - PSI > 0.2 = significant drift = block execution
   - Reference distributions saved after each retrain

3. **Regime-Gated Signal Generator** — wrapper around existing pipeline
   - Check HMM regime confidence → block if < 0.65
   - Check PSI drift → block if > 0.2
   - Log every NO_TRADE decision with reason

4. **Regime Dashboard** — `/api/regime/status` endpoint + frontend card

### Estimated Impact
- **+15-25% net P&L** (by avoiding 60-70% of losing trades in unreadable regimes)
- **-30-40% drawdown** reduction

### Gate Criteria
```
PASS if:
  - Backtesting shows regime gate reduces drawdown by > 20%
  - Blocked trades would have been net negative
  - No more than 30% of profitable trades are incorrectly blocked
```

---

## Phase 3: Real Costs in Backtest (1 week)

**Prerequisite**: Phase 2 PASSED

**Goal**: Know the REAL profitability after all costs.

### Tasks

1. **Spread-aware backtester** — use actual bid-ask spread per asset, not midpoint
2. **Slippage model** — stochastic slippage based on volatility and volume
3. **Funding cost** — for crypto perpetual positions, apply 8h funding rate
4. **Fee structure** — Capital.com spread-based or Bybit maker/taker

5. **Re-run all backtests** with real costs
6. **Compare**: profit before costs vs profit after costs
   - If costs eat > 50% of gross profit → the strategy doesn't have enough edge

### Gate Criteria
```
PASS if:
  - At least 3 assets remain profitable after ALL costs
  - Net Sharpe > 0.5 after costs on top assets
  - Profit factor > 1.2 after costs

FAIL if:
  - No asset is profitable after costs
  → Strategy edge is too thin. Need bigger moves (longer timeframe?)
    or lower costs (better broker?)
```

---

## Phase 4: Bybit Migration (2-3 weeks)

**Prerequisite**: Phase 3 shows BTC is in the top profitable assets

**Goal**: Move BTC trading from Capital.com CFD to Bybit perpetual futures for lower costs and alpha-rich data.

**Source**: Original Phase 23 Sprint 2 (Funding Rate) integrated here

### Tasks

1. **Bybit Broker Adapter** — REST + WebSocket, same interface as Capital.com client
   - Authentication (API key + secret)
   - Market data, order placement, position management
   - Transaction history (Bybit has this — unlike Capital.com demo)

2. **Funding Rate Engine** (from original Sprint 2)
   - `BybitFundingRateFetcher` — historical + real-time funding
   - 14 funding rate features for XGBoost
   - Contrarian signal on extreme funding (z-score > 2.5 or < -2.0)

3. **Open Interest Integration**
   - OI as feature for XGBoost
   - OI divergence from price as signal

4. **Dual-Broker Architecture**
   - Abstract broker interface so MANTIS can trade on multiple brokers
   - Capital.com for forex/commodities/indices
   - Bybit for crypto (BTC, ETH)

### Estimated Impact
- **Cost reduction**: 0.5% spread → 0.055% taker fee (10x cheaper on crypto)
- **Funding rate alpha**: +8-15% estimated from contrarian signals
- **Better data**: real transaction history, real open interest

---

## Phase 5: RL Adaptive Layer (3-4 weeks)

**Prerequisite**: Phase 3 gate PASSED with positive OOS P&L after real costs

**Goal**: Add RL for timing and sizing optimization. XGBoost decides direction, RL decides when and how much.

**Source**: Original Phase 23 Sprint 4 (preserved)

### Tasks

1. **Gymnasium Environment** — state = top 50 features + position info + regime + funding
2. **MANTIS Reward Function** — Sharpe-based, not P&L-based. Penalize drawdown, reward consistency
3. **PPO Training** — 500K+ steps on historical data with walk-forward validation
4. **Ensemble**: XGBoost direction + RL timing/sizing
   - Concordance → full size
   - Only XGBoost → half size
   - Discordance → no trade

### Gate Criteria
```
PASS if:
  - XGBoost+RL ensemble beats XGBoost-only on OOS data
  - Sharpe improves by > 15%
  - Max drawdown doesn't increase

FAIL if:
  - RL doesn't improve OOS metrics
  → RL is adding complexity without value. Keep XGBoost-only.
```

---

## Phase 6: Advanced Alpha (ongoing, after 3 months of positive track record)

### Liquidation Heatmap (from original Sprint 5)
- CoinGlass API for BTC liquidation zones
- Magnetic price levels as features
- Only for BTC perpetual (Bybit)

### Multi-Agent Debate (from original Sprint 6)
- Only if Phase 5 shows diminishing returns from single-model improvements
- Agent ensemble: Technical, Sentiment, Risk, Fundamental
- Debate protocol with confidence-weighted voting
- Expensive in compute and complexity — must demonstrate clear value

---

## Timeline Estimate

| Phase | Duration | Prerequisite | Risk |
|-------|----------|-------------|------|
| 0 — Validation | 2-3 days | None | May reveal model doesn't work |
| 1 — Focus | 1 week | Phase 0 PASS | Reducing assets feels like going backward |
| 2 — Regime Gate | 2 weeks | Phase 1 PASS | HMM tuning is finicky |
| 3 — Real Costs | 1 week | Phase 2 PASS | May show strategy is unprofitable |
| 4 — Bybit | 2-3 weeks | Phase 3 shows BTC works | New broker integration is complex |
| 5 — RL | 3-4 weeks | Phase 3 PASS | Reward function tuning is an art |
| 6 — Advanced | Ongoing | 3mo track record | Diminishing returns |

**Total to profitability check**: ~6 weeks (Phase 0-3)
**Total to Bybit+RL**: ~12-14 weeks

---

## What NOT To Do

1. **Don't add more features to a model that doesn't predict** — 220 features is plenty. The bottleneck isn't features
2. **Don't skip validation** — "it works on backtest" means nothing without OOS walk-forward
3. **Don't trade 21 assets with mediocre models** — concentration beats diversification when edge is thin
4. **Don't add RL before proving XGBoost works** — RL amplifies the base model, for better or worse
5. **Don't optimize for Sharpe on in-sample data** — that's overfitting with extra steps
6. **Don't underestimate transaction costs** — they kill more strategies than bad models
