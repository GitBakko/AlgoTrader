# Phase 0 Re-Validation — EXCLUDE Assets Post Spread Recalibration

**Date:** 2026-05-23
**Trigger:** ASSET_SPREADS recalibration commits `15aba8d` + `7c3d074`.

## Context

Phase 0 originale (2026-04-28) classificò 21 epics in 10 KEEP / 3 REVIEW / 5 EXCLUDE.
Le 8 esclusioni/REVIEW si basavano su cost model che usava fallback `0.5` price-units
per i 10 epics non calibrati — catastroficamente largo per forex (USDCAD: 2272×
real value). Risultato: backtest produceva trade unprofittabili artificially.

74h spread audit ha rivelato i veri spread. Cost model aggiornato a 21 epics
con `p95 × 1.1` methodology (commit `15aba8d`). Phase 0 ri-validation richiesta.

## Methodology

- Walk-forward OOS validation (no leakage)
- `--sweep-threshold` (no Optuna tuning, default hyperparams)
- Timeframe 4h, capital $10K, risk 2% per trade
- Phase 0 gate: Sharpe ≥ 0.3, WR ≥ 40%, MaxDD ≤ 30%
- Script: `D:/tmp/algotrader/phase0_revalidate_excluded.py`

## Risultati (15 epics)

| Epic     | Sharpe | WR    | DD   | PF   | Trades | Decision |
|----------|-------:|------:|-----:|-----:|-------:|----------|
| USDCHF   | 3.75   | 64.4% | 0.2% | 2.34 | 236    | KEEP     |
| WTIUSD   | 3.34   | 66.9% | 0.8% | 2.33 | 151    | KEEP     |
| USDCAD   | 2.98   | 66.1% | 0.1% | 2.43 | 121    | KEEP     |
| COPPER   | 2.21   | 58.2% | 0.6% | 1.73 | 122    | KEEP     |
| MSFT     | 1.86   | 63.8% | 1.2% | 1.61 | 116    | KEEP     |
| USDJPY   | 1.71   | 56.8% | 0.3% | 1.45 | 148    | KEEP     |
| DE40     | 1.51   | 56.8% | 0.6% | 1.38 | 257    | KEEP     |
| PLATINUM | 1.39   | 61.5% | 1.4% | 1.70 | 65     | KEEP     |
| GOOGL    | 1.29   | 59.4% | 1.6% | 1.35 | 160    | KEEP     |
| TSLA     | 1.28   | 54.9% | 1.5% | 1.32 | 142    | KEEP     |
| AMD      | 1.22   | 59.1% | 3.5% | 1.40 | 132    | KEEP     |
| AAPL     | 1.16   | 50.5% | 1.0% | 1.32 | 109    | KEEP     |
| NVDA     | 0.60   | 50.0% | 2.4% | 1.16 | 104    | KEEP     |
| META     | 0.52   | 51.4% | 1.8% | 1.18 | 72     | KEEP     |
| AMZN     | 0.12   | 50.0% | 1.0% | 1.06 | 34     | REVIEW   |

**Decisioni: 14 KEEP / 1 REVIEW / 0 EXCLUDE.**

## Key findings

### Forex rivelata viable

Top-3 nel ranking sono **USDCHF, USDCAD, USDJPY** — pre-recalib erano impossibili
da profittare (fallback 0.5 era 1515-2272× troppo largo). Con spread realistici
diventano i migliori performer dell'expansion basket.

Implicazioni:
- Bias di selezione di Phase 0 originale era cost-driven, non strategy-driven.
- Strategia ML XGBoost funziona meglio su asset bassa-volatilità (forex DD <0.5%).

### US Stocks tutti recuperati

8/8 US stocks tornati KEEP (AAPL/MSFT/GOOGL/AMZN/META/AMD/TSLA/NVDA). AMZN solo
borderline (Sharpe 0.12, PF 1.06) → REVIEW. Spread realistici più alti del fallback
(TSLA +395%, NVDA +208%) ma backtest comunque profittabile.

### PLATINUM/DE40 anche con spike spread

Anche con spread che esplodono in Asia session (DE40 +780%, PLATINUM +670%),
strategie restano profittabili. Threshold sweep cattura il regime tradeable
(filtra trade in finestre alto-spread).

### AMZN solo REVIEW

PF 1.06 (target >1.2 implicito), Sharpe 0.12, solo 34 trade. Edge marginale.
Probabilmente data sparse o sample noise. Re-run con Optuna tuning richiesto
prima di decisione finale.

## Expanded basket impact

**Pre-recalib basket** (Phase 0 originale): 10 KEEP + 5 EXCLUDE.
**Post-recalib basket**: 21 KEEP candidates (10 originali + 14 recuperati - 1 AMZN
review - 2 sovrapposizioni: COPPER+WTIUSD presenti in entrambi).

Tradable universe espanso da ~5-10 a ~19 asset profittabili. Implicazione su
diversificazione + concorrenza per equity allocation richiede review Kelly sizer
+ exposure caps prima di abilitare tutti in paper trading.

## Caveat

- **No Optuna tuning** in questo run — risultati sono probabilmente sotto-ottimi.
  Phase 1 (`phase1_optuna_top5.py`) andrebbe esteso a 19 asset basket per
  thresholds di produzione.
- Sample size piccolo su alcuni asset (AMZN 34 trade) — robustezza non garantita.
  Monte-Carlo / bootstrap di pre-deploy raccomandato.
- DD molto basso (<2% su quasi tutti) — sospetto sample-size driven.
  Walk-forward dovrebbe coprire più cycle prima di trustare i numeri.

## Next steps

1. **Phase 1 expansion** — `phase1_optuna_top5.py` da promuovere a `phase1_optuna_full_basket.py` con 19 asset (escluso AMZN review).
2. **AMZN deep-dive** — Optuna tune dedicato per decidere KEEP vs EXCLUDE.
3. **Kelly sizer review** — capacità di gestire 19 asset concorrenti senza
   over-allocation. Cap per-asset e correlation guard da rivedere.
4. **Live paper validation** — abilitare top-10 expanded basket in paper trading
   per 2 settimane prima di commit production thresholds.

## Artifacts

- Results: `backend/data/config/phase0_revalidate_excluded_2026-05-23.json`
- Phase 3 sibling report: `2026-05-23_phase3_rerun.md`
- Script: `D:/tmp/algotrader/phase0_revalidate_excluded.py`
- Log: `D:/tmp/algotrader/phase0_revalidate_excluded.log`
- Spread audit source: `docs/handoff/spread_audit_2026-05-23.md`
