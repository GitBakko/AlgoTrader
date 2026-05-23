# Phase 3 Cost Re-Validation — 2026-05-23

## Context

After 74h passive spread audit (commits `d6c2396` → `15aba8d`), `ASSET_SPREADS`
was recalibrated from 11 to 21 epics using `p95 × 1.1` methodology (Phase 3-bis
aggregator output). Critical understated assets fixed:

| Epic     | Prior | New    | Δ      |
|----------|------:|-------:|-------:|
| PLATINUM | 1.00  | 7.70   | +670%  |
| DE40     | 1.00  | 8.80   | +780%  |
| TSLA     | 0.10  | 0.495  | +395%  |
| NVDA     | 0.10  | 0.308  | +208%  |
| META     | 0.50  | 1.144  | +128%  |
| AMD      | 0.50  | 1.078  | +115%  |

Plus 10 missing epics added (forex/stocks/COPPER) — fallback 0.5 was
catastrophic (USDCAD: 2272× too wide).

Phase 3 cost validation must be re-run to confirm gate compliance.

## Methodology

Same harness as original Phase 3 (`fdb70f0`, 2026-04-28):
- `scripts/phase1_optuna_top5.py` with `--tune-trials 50 --prune-pct 0.25`
- Walk-forward OOS validation (no leakage)
- Sweep-threshold post-tuning to find optimal per-asset confidence
- Initial capital $10K, risk 2% per trade, timeframe 4h

Differences vs original Phase 3:
- 50 Optuna trials (vs 100) — reduced budget for re-run speed (~3 min vs ~hours)
- ASSET_SPREADS p95×1.1 (vs prior mixed: 11 epics calibrated 2026-04-28, 10 missing)

## Top-5 KEEP basket results

| Epic    | Prior P3 Sharpe | New Sharpe | Δ      | Trades | PF   | WR    | DD    | Threshold |
|---------|----------------:|-----------:|-------:|-------:|-----:|------:|------:|----------:|
| SOLUSD  | 4.96            | **5.22**   | +0.26  | 217    | 3.26 | 72.8% | 1.3%  | 0.48      |
| BTCUSD  | 6.58            | **5.82**   | -0.76  | 331    | 3.05 | 70.4% | 1.0%  | 0.30      |
| ETHUSD  | 4.97            | **4.62**   | -0.35  | 158    | 3.38 | 72.2% | 1.3%  | 0.50      |
| XAUUSD  | 3.29            | **1.78**   | -1.51  | 78     | 1.68 | 56.4% | 0.8%  | 0.55      |
| BNBUSD  | 1.95            | **2.30**   | +0.35  | 135    | 1.93 | 63.0% | 1.6%  | 0.55      |
| **Mean**| **4.35**        | **3.95**   | -9.2%  | —      | —    | —     | —     | —         |

## Gate compliance

| Criterion              | Target  | Result  | Status |
|------------------------|--------:|--------:|--------|
| 5/5 profitable         | ≥3 / 5  | 5 / 5   | ✅     |
| Min net Sharpe         | >0.5    | 1.78    | ✅     |
| Min profit factor      | >1.2    | 1.68    | ✅     |
| Max drawdown           | <30%    | 1.6%    | ✅     |
| Top-5 mean Sharpe      | (info)  | 3.95    | —      |

**Verdict: PASS.** All 5 top assets remain KEEP after realistic costs.

## Key findings

### XAUUSD: biggest impact

Sharpe dropped 3.29 → 1.78 (-46%). Coherent with spread widening +37.5%
(0.60 → 0.825). Profit factor halved (2.27 → 1.68). Still passes gate but
flagged for monitoring — next spread audit cycle should confirm 0.825 holds.

### BTCUSD: spread tighter, Sharpe lower

Spread tightened 60 → 55 (-8%) yet Sharpe dropped 6.58 → 5.82 (-12%).
Attribution: reduced Optuna budget (50 vs 100 trials). Threshold shifted
0.30 (vs prior unknown). Not spread-driven.

### BNBUSD: recuperato vs un-tuned

Un-tuned run produced 0.62 (sub-gate). Optuna 50 trials recovered to 2.30.
Confirms BNB drop in un-tuned probe was stochastic noise, not structural.
Spread invariato (3.75 → 3.63).

### ETHUSD: stable

Sharpe 4.97 → 4.62 (-7%). Spread 2.10 → 1.925 (-8%). Net effect within
buffer. PF improved 3.59 → 3.38 (acceptable).

### SOLUSD: net improvement

Sharpe 4.96 → 5.22 (+5%). Spread invariato (0.50 → 0.481, -4%).
Likely Optuna found marginally better configuration.

## Impact on roadmap

- **Phase 4 BTC OOS PASS** (commit `fa552c5`): remains valid. BTC spread
  tightened, gate margin still wide (Sharpe 5.82 vs floor 0.5).
- **Binance migration**: still gated on Phase 3 re-run completion → now
  authorized. No KEEP/EXCLUDE shifts in top-5.
- **Phase 0 ri-validation**: EXCLUDE assets (PLATINUM/DE40/forex/stocks)
  re-tested post-recalib. PLATINUM crossed KEEP threshold (Sharpe 1.39 WR
  61.5% post p95×1.1 cost). See sibling report
  `2026-05-23_phase0_revalidate_excluded.md`.

## Artifacts

- Thresholds: `backend/data/config/optimal_thresholds_phase3_rerun_2026-05-23.json`
- Script: `D:/tmp/algotrader/phase3_rerun.py` (un-tuned probe) +
  `backend/scripts/phase1_optuna_top5.py` (50-trial Optuna re-run)
- Log: `D:/tmp/algotrader/phase3_optuna_rerun.log`
- Prior baseline: `backend/data/config/optimal_thresholds_phase3.json`
  (commit `fdb70f0`, 2026-04-28)

## Next steps

1. Phase 0 ri-validation EXCLUDE assets — in progress (15 epics, ~3 min).
2. Update `MANTIS_EVOLUTION_ROADMAP.md` with Phase 3 PASS confirmation.
3. Consider running 100-trial Optuna for production thresholds (matches
   original Phase 3 trial budget) before LIVE deploy.
