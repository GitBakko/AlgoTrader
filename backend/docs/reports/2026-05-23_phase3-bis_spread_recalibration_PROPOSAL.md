# Phase 3-bis — Spread Recalibration Proposal

**Generated**: 2026-05-23T09:07:05.599294+00:00 UTC
**Audit window**: 2026-05-20 07:42:06.579759 → 2026-05-23 09:06:40.517560
**Total observations**: 18,459
**Filter**: tradeable_only=True, min_samples=40

## Per-epic recalibration proposal

| Epic | Class | n | p50 (price) | p95 (price) | max (price) | p95 bps | Current ASSET_SPREADS | **Proposed (p95×1.1)** | Δ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BNBUSD | crypto | 855 | 3.2600 | 3.3000 | 3.3200 | 50.10 | 3.7500 | **3.6300** | -3.2% |
| SOLUSD | crypto | 855 | 0.4319 | 0.4373 | 0.4390 | 50.01 | 0.5000 | **0.4810** | -3.8% |
| PLATINUM | precious | 717 | 6.0000 | 7.0000 | 20.0000 | 36.14 | 1.0000 | **7.7000** | +670.0% ⚠️ |
| AMD | stocks | 538 | 0.3500 | 0.9800 | 2.1000 | 21.99 | 0.5000 | **1.0780** | +115.6% ⚠️ |
| AMZN | stocks | 538 | 0.1600 | 0.5000 | 0.8900 | 18.90 | 0.5000 | **0.5500** | +10.0% |
| META | stocks | 538 | 0.3600 | 1.0400 | 2.1500 | 17.22 | 0.5000 | **1.1440** | +128.8% ⚠️ |
| AAPL | stocks | 538 | 0.1600 | 0.4700 | 0.8500 | 15.69 | 0.5000 | **0.5170** | +3.4% |
| MSFT | stocks | 538 | 0.2400 | 0.6000 | 1.2500 | 14.34 | 0.5000 | **0.6600** | +32.0% |
| GOOGL | stocks | 538 | 0.2000 | 0.5300 | 0.8800 | 13.65 | 0.5000 | **0.5830** | +16.6% |
| NVDA | stocks | 538 | 0.1400 | 0.2800 | 0.4100 | 12.68 | 0.1000 | **0.3080** | +208.0% ⚠️ |
| TSLA | stocks | 538 | 0.1900 | 0.4500 | 1.1000 | 10.72 | 0.1000 | **0.4950** | +395.0% ⚠️ |
| ETHUSD | crypto | 855 | 1.7500 | 1.7500 | 1.7500 | 8.48 | 2.1000 | **1.9250** | -8.3% |
| BTCUSD | crypto | 855 | 50.0000 | 50.0000 | 50.0000 | 6.63 | 60.0000 | **55.0000** | -8.3% |
| COPPER | other | 717 | 0.0027 | 0.0027 | 0.0027 | 4.34 | 0.5000 | **0.0030** | -99.4% ⚠️ |
| WTIUSD | other | 717 | 0.0400 | 0.0400 | 0.0800 | 4.19 | 0.0400 | **0.0440** | +10.0% |
| USDCHF | forex | 741 | 0.0001 | 0.0003 | 0.0027 | 3.81 | 0.5000 | **0.0003** | -99.9% ⚠️ |
| DE40 | index | 741 | 1.5000 | 8.0000 | 8.0000 | 3.23 | 1.0000 | **8.8000** | +780.0% ⚠️ |
| XAUUSD | precious | 717 | 0.5000 | 0.7500 | 0.7500 | 1.66 | 0.6000 | **0.8250** | +37.5% |
| USDCAD | forex | 741 | 0.0002 | 0.0002 | 0.0020 | 1.46 | 0.5000 | **0.0002** | -100.0% ⚠️ |
| USDJPY | forex | 741 | 0.0120 | 0.0140 | 0.0900 | 0.88 | 0.5000 | **0.0154** | -96.9% ⚠️ |
| US500 | index | 741 | 0.6000 | 0.6000 | 1.5000 | 0.81 | 0.5000 | **0.6600** | +32.0% |

Marker ⚠️ = |Δ| > 50% vs current — verify before applying.

## Session breakdown (TRADEABLE only, p95 spread in bps)

| Epic | US | EU | Asia |
|---|---:|---:|---:|
| AAPL | 5.38 | 19.30 | 13.62 |
| AMD | 13.33 | 26.97 | 18.90 |
| AMZN | 7.61 | 23.06 | 17.35 |
| BNBUSD | 50.10 | 50.10 | 50.10 |
| BTCUSD | 6.54 | 6.70 | 6.63 |
| COPPER | 4.33 | 4.35 | 4.29 |
| DE40 | 0.61 | 0.62 | 3.24 |
| ETHUSD | 8.34 | 8.63 | 8.48 |
| GOOGL | 6.70 | 12.62 | 21.94 |
| META | 7.88 | 17.79 | 24.66 |
| MSFT | 7.73 | 18.17 | 14.26 |
| NVDA | 7.67 | 14.53 | 12.68 |
| PLATINUM | 31.20 | 36.05 | 45.77 |
| SOLUSD | 50.01 | 50.01 | 50.01 |
| TSLA | 6.17 | 12.82 | 9.17 |
| US500 | 0.80 | 0.81 | 2.01 |
| USDCAD | 1.46 | 1.45 | 14.52 |
| USDCHF | 1.90 | 1.78 | 19.58 |
| USDJPY | 0.76 | 0.75 | 5.03 |
| WTIUSD | 4.18 | 4.15 | 8.22 |
| XAUUSD | 1.67 | 1.67 | 1.66 |

US session = 13:00-20:00 UTC, EU = 06:00-13:00 UTC, Asia = 00:00-06:00 UTC.

## Proposed `ASSET_SPREADS` dict (drop-in replacement)

```python
# Recalibrated 2026-05-23 from 72h passive `spread_audit.py` run.
# p95 × 1.1 buffer (more aggressive than prior snap × 1.2 flat).
ASSET_SPREADS = {
    "BNBUSD": 3.6300,  # n=855, p95=3.3000
    "SOLUSD": 0.4810,  # n=855, p95=0.4373
    "PLATINUM": 7.7000,  # n=717, p95=7.0000
    "AMD": 1.0780,  # n=538, p95=0.9800
    "AMZN": 0.5500,  # n=538, p95=0.5000
    "META": 1.1440,  # n=538, p95=1.0400
    "AAPL": 0.5170,  # n=538, p95=0.4700
    "MSFT": 0.6600,  # n=538, p95=0.6000
    "GOOGL": 0.5830,  # n=538, p95=0.5300
    "NVDA": 0.3080,  # n=538, p95=0.2800
    "TSLA": 0.4950,  # n=538, p95=0.4500
    "ETHUSD": 1.9250,  # n=855, p95=1.7500
    "BTCUSD": 55.0000,  # n=855, p95=50.0000
    "COPPER": 0.0030,  # n=717, p95=0.0027
    "WTIUSD": 0.0440,  # n=717, p95=0.0400
    "USDCHF": 0.0003,  # n=741, p95=0.0003
    "DE40": 8.8000,  # n=741, p95=8.0000
    "XAUUSD": 0.8250,  # n=717, p95=0.7500
    "USDCAD": 0.0002,  # n=741, p95=0.0002
    "USDJPY": 0.0154,  # n=741, p95=0.0140
    "US500": 0.6600,  # n=741, p95=0.6000
}
```

## Required follow-up (manual, requires LLM judgment)

1. Review proposed values, especially rows marked ⚠️.
2. Apply patch: replace `ASSET_SPREADS` in `backend/src/backtest/costs.py`.
3. Re-run Phase 3 backtest for each TRADABLE_ASSETS epic at 4h:
   ```bash
   cd backend
   for epic in $(echo "XAUUSD BTCUSD US500 WTIUSD NVDA TSLA DE40 SOLUSD ETHUSD BNBUSD COPPER PLATINUM USDJPY AAPL MSFT GOOGL AMZN META AMD USDCHF USDCAD"); do
       .venv/Scripts/python.exe scripts/walk_forward_backtest.py \
           --epic $epic --timeframe 4h --capital 11000 --risk 0.02 \
           --tune --tune-trials 40 --monte-carlo
   done
   ```
4. Verify Phase 0 gates (Sharpe ≥ 0.3, WR ≥ 40%, Max DD ≤ 30%) — exclude epics that fail by editing `_EXCLUDED_ASSETS` in `backend/src/utils/constants.py`.
5. Re-verify Phase 4 BTC: same command, --epic BTCUSD --sweep-threshold.
6. If KEEP basket survives + BTC still passes → authorize Binance Wave 2 (live testnet) per `docs/evolutive/BINANCE_MIGRATION_WAVE_PLAN.md`.
7. Atomic commits:
   - `feat(backtest): recalibrate ASSET_SPREADS from 72h live audit (Phase 3-bis)`
   - `feat(phase0): exclude <epics> after Phase 3-bis cost re-run` (only if exclusions)
   - `docs(phase3-bis): spread recalibration + Phase 3 re-run final report`

## Artefacts

- This proposal: `docs/reports/2026-05-23_phase3-bis_spread_recalibration_PROPOSAL.md`
- Side-by-side patch target: `src/backtest/costs.py.proposed`
- Raw audit data: `data/diagnostics/spread_audit/*.parquet`
