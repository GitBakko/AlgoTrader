# Spread Audit — Calibration 2026-05-23

## Summary

Passive spread collector ran 74h (2026-05-20 07:42 → 2026-05-23 12:11 UTC) across 21 epics on Capital.com demo.
Collected 18,732 obs total, 14,349 TRADEABLE (76.6%). Output: `backend/data/diagnostics/spread_audit/2026-05.parquet`.

## Key Findings

### Understated (backtests TOO OPTIMISTIC on these epics)

| Epic | Measured p95 | Previous config | New config | Delta vs previous |
|---|---|---|---|---|
| PLATINUM | 7.00 | 1.00 | 7.70 | **+670%** |
| DE40 | 8.00 | 1.00 | 8.80 | **+780%** (Asia session spike) |
| TSLA | 0.45 | 0.10 | 0.495 | **+395%** |
| NVDA | 0.28 | 0.10 | 0.308 | +208% |

### Missing config (were using fallback 0.5 — wildly wrong for forex)

| Epic | Measured p95 | Fallback 0.5 was | New config |
|---|---|---|---|
| USDCHF | 0.0003 | **1515× too wide** | 0.00033 |
| USDCAD | 0.0002 | **2272× too wide** | 0.00022 |
| USDJPY | 0.014 | **32× too wide** | 0.0154 |
| COPPER | 0.0027 | 185× too wide | 0.0030 |
| AAPL | 0.47 | +6% | 0.517 |
| AMZN | 0.50 | exact | 0.55 |
| GOOGL | 0.53 | +6% | 0.583 |
| MSFT | 0.60 | +20% | 0.66 |
| AMD | 0.98 | +96% | 1.078 |
| META | 1.04 | +108% | 1.144 |

### Confirmed (existing 2026-04-28 calibration validated, kept ±20%)

XAUUSD (0.60→0.825), BTCUSD (60→55), ETHUSD (2.10→1.925), SOLUSD (0.50→0.481), BNBUSD (3.75→3.63), US500 (0.50→0.66), WTIUSD (0.04→0.044) — minor adjustments within buffer.

## Implications

1. **Phase 3 cost validation needs re-run** — previous run had PLATINUM/DE40/TSLA backtests with cost 60-85% lower than reality. Per-epic Sharpe ranking likely shifts.
2. **Forex strategies** — backtests impossible to profit with 0.5 price-unit fallback on USDCAD (~2272× too wide). Re-run will reveal real edge.
3. **Phase 4 BTCUSD OOS PASS remains valid** — BTC config now slightly tighter (55 vs 60).

## Buffer Methodology

All values = `measured_p95 × 1.1` (Phase 3-bis aggregator methodology, see
`backend/docs/reports/2026-05-23_phase3-bis_spread_recalibration_PROPOSAL.md`).
Justification: p95 captures off-hours widening AND spike windows; ×1.1 covers
broker latency on Asia-session FX/index opens.

## Next Steps

1. ☐ Re-run Phase 3 cost validation with new ASSET_SPREADS
2. ☐ Add OVERNIGHT_RATES for missing 10 epics (current rates only cover original 11)
3. ☐ Set up periodic re-audit (monthly?) to catch broker-side spread changes
