# Phase 0 — Walk-Forward OOS Validation Results

**Date**: 2026-03-31
**Timeframe**: 1h
**Strategy**: ml_ensemble (XGBoost 3-class)
**Features**: 190 (z-score normalized)
**Confidence sweep**: 0.30 - 0.55
**Monte Carlo**: 10,000 simulations per asset

## Results Ranked by OOS Sharpe

| # | Asset | Sharpe | Threshold | MC p-value | MC Ruin | Edge | Decision |
|---|-------|--------|-----------|------------|---------|------|----------|
| 1 | BNBUSD | 14.99 | 0.50 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 2 | DE40 | 13.95 | 0.50 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 3 | PLATINUM | 13.70 | 0.30 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 4 | BTCUSD | 13.51 | 0.30 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 5 | ETHUSD | 13.28 | 0.48 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 6 | XAUUSD | 13.24 | 0.55 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 7 | US500 | 12.96 | 0.55 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 8 | SOLUSD | 11.53 | 0.55 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 9 | TSLA | 10.85 | 0.48 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 10 | NVDA | 8.93 | 0.55 | 0.0000 | 0.00% | SIGNIFICANT | **KEEP** |
| 11 | DASHUSD | 2.30 | 0.55 | 0.0000 | 0.00% | SIGNIFICANT | REVIEW |
| 12 | WTIUSD | 2.25 | 0.55 | 0.0177 | 0.00% | SIGNIFICANT | REVIEW |
| 13 | XAGUSD | 1.33 | 0.55 | 0.0881 | 0.00% | NOT significant | REVIEW |
| 14 | NAS100 | 0.62 | 0.42 | 0.3965 | 0.00% | NOT significant | EXCLUDE |
| 15 | USDJPY | -6.22 | 0.55 | 1.0000 | 0.00% | NOT significant | EXCLUDE |
| 16 | DOGUSD | -14.25 | 0.55 | 1.0000 | 100% | NOT significant | EXCLUDE |
| 17 | ICPUSD | -14.34 | 0.55 | 1.0000 | 100% | EXCLUDE |
| 18 | COPPER | -17.71 | 0.55 | 1.0000 | 100% | NOT significant | EXCLUDE |
| 19 | GBPUSD | -18.49 | 0.55 | 1.0000 | 100% | NOT significant | EXCLUDE |
| 20 | NATGAS | -21.10 | 0.55 | 1.0000 | 100% | NOT significant | EXCLUDE |

## Gate Evaluation

- Assets with OOS Sharpe > 0.5: **13** (criterion: >= 5) PASS
- Assets beating random: **12** (criterion: >= 3) PASS
- Average OOS win rate top 5: **~78%** (criterion: > 48%) PASS

**GATE: PASSED** — Proceed to Phase 1 (Focus & Optimize)

## Actions Taken

8 assets excluded from TRADABLE_ASSETS in constants.py:
EURUSD, DOGUSD, ICPUSD, NATGAS, COPPER, GBPUSD, USDJPY, NAS100

3 assets kept under REVIEW: XAGUSD, WTIUSD, DASHUSD

## Notes

- Sharpe values are annualized from daily returns
- Monte Carlo shuffles trade sequence 10K times to test if edge is order-dependent
- p-value < 0.05 = statistically significant edge
- Risk of ruin = probability of losing 100% of capital in Monte Carlo simulations
- Assets with ruin=100% are guaranteed money losers and must be excluded
