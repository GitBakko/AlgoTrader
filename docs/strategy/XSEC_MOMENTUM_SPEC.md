# Cross-Sectional Composite Momentum — Operational Spec (v1, 2026-06-01)

**Status:** validated in backtest (the first edge to survive the full A/B ruthless gauntlet).
Forward PAPER-TRADE STARTED 2026-06-01 (obs #1 = 2026-05-29 book, `paper_trade.py`). NOT yet
live with capital. Next gate = ≥6–12 forward monthly obs + deployment-venue decision (IBKR).

> Data source: Sharadar (Nasdaq Data Link), Personal-Use licence. Raw data is **never**
> committed or displayed in any UI; only derived signals/metrics (this doc) are shared.

## 1. Thesis

On liquid US equities, ranking stocks by a **sector-neutral composite** of value + quality +
12-month price momentum and holding the top quintile, equal-weight, rebalanced monthly, has
delivered a persistent **~6%/yr alpha over the equal-weight market (Sharpe ~1.0, maxDD ~-6%)**
across 2016–2026, stable across both OOS sub-periods and robust to parameters, cost, and a
block-bootstrap CI that excludes zero. The edge survives sector-neutralization (it is genuine
stock selection, not a sector bet) — the test that kills most factor mirages.

## 2. Exact rules

| Component | Rule |
|---|---|
| Universe | US equities (Sharadar SEP/SF1), marketcap ≥ **$2B**, price ≥ **$3**, has a current price. Survivorship-free (delisted names live in the data). ~1,300–1,900 names/month. |
| Value | z(earnings yield = netinc/marketcap, PE>0) + z(book/price = 1/PB, PB>0), nan-tolerant mean |
| Quality | nan-tolerant mean of z(ROE), z(grossmargin), z(−debt/equity) |
| Momentum | 12-1: return from t−12m to t−1m (skip last month). **Driver of the edge.** Robust 6–12m. |
| Composite | nan-tolerant mean of z(value), z(quality), z(momentum) |
| **Sector-neutral** | demean composite **within `sicsector`** before ranking (removes sector tilts) |
| Selection | **top quintile** (20%) by sector-neutral composite (~250–390 names) |
| Weighting | equal-weight |
| Rebalance | **monthly** (month-end). Turnover ~0.55/mo. |
| Fundamentals timing | strict point-in-time: only SF1 rows with `datekey` ≤ rebalance date (merge_asof) |

## 3. Validated performance (leak-free, net of 10bp/side, OOS = 2016-10 → 2026-05)

| Variant | OOS CAGR | OOS Sharpe | OOS maxDD | Note |
|---|---|---|---|---|
| **Long-only (pure)** | **17.5%** | 0.92 | −23.8% | carries full market beta |
| Benchmark (EW universe) | 10.7% | 0.64 | −28.7% | the market we beat |
| **Excess / alpha** | **6.2%** | **1.00** | **−6.2%** | the genuine skill |
| Vol-target 10% | 8.8% | 0.74 | −23.7% | delevered long book |

Robustness (champion): momentum 6/9/12m all positive (lb9 best, Sharpe 1.04); cut top5%→tercile all
0.8–1.0; survives cost to 30bp/side; sub-periods 2016-21 (0.87) ≈ 2021-26 (0.84); bootstrap OOS
Sharpe 90% CI **[0.41, 1.37]** (excludes 0); persistent yearly 2022→2026 (0.9→2.7).

## 4. Deployment options

1. **Long-only via equity broker (IBKR).** ~250–390 US stocks, equal-weight, fractional shares,
   monthly rebalance via API. Gets 17.5% CAGR but eats market crashes (−24% OOS / −53% incl. 2008).
2. **Market-neutral.** Same long book + short the S&P index (ONE instrument — SPX future, or even
   Capital.com US500 CFD) sized to the book's beta. Harvests the ~6% alpha at Sharpe 1.0, maxDD −6%.
   Cleanest risk profile; needs only one extra hedge leg.

Capital.com (current MANTIS stack) CANNOT trade hundreds of single US stocks affordably → the long
leg needs **IBKR** or similar. This is a **separate system from MANTIS** (intraday CFD), not a
modification of it.

## 5. Paper-trade protocol (in progress, NO capital at risk)

Tooling: `scripts/ab/paper_trade.py` (reuses the exact validated selection + the backtest
return convention: book = fwd[longs].fillna(0).mean(); excess = book − EW-universe).

**Monthly runbook (do at each month-end):**
1. `paper_trade.py` (alias `simulate`) — optional integrity check on cache.
2. `generate_portfolio.py --refresh` → pulls fresh Sharadar, writes the target book CSV.
3. `paper_trade.py open` → freezes this month's book into the live ledger (one forward obs).
4. `paper_trade.py mark` → realizes every prior open book whose next month is now in cache,
   appending book / EW-universe / excess returns to `paper_track_record.csv`.
5. `paper_trade.py status` → running ledger + forward track record (Sharpe/CAGR once ≥3 obs).

**Gate:** accumulate ≥6–12 LIVE forward monthly obs; confirm the excess (alpha) Sharpe holds
near the validated ~1.0 before committing capital. Backtest OOS is honest; forward is the judge.

**Integrity check (2026-06-01):** the operational path reproduces the backtest — replaying
open→mark over the last 24 cached months gave EXCESS ann-Sharpe **1.47**, CAGR 11.1%, maxDD
−3.2% (LONG book CAGR 27.5%); the 1.47 vs full-OOS 1.0 is the documented 2022→2026
acceleration, not drift. Operational == research confirmed before going forward.

## 6. Known caveats / refinement backlog

- ~~**Coarse sector**: refine on finer `sicindustry`.~~ **RESOLVED 2026-06-01 (B):** finer
  neutralization (sector11 / famaindustry48 / industry152) is a **no-op** — OOS Sharpe
  unchanged (long ~0.9, excess ~1.0 across all) and book concentration on a proper 48-industry
  ruler is ~16% regardless. The scary "51% Manufacturing" was a 1-digit-label artifact; the
  live book's biggest *real* (Fama-French) industry is only ~15% (Electronic Equipment),
  pharma ~14%, then drops. A **20% per-FF-industry cap** is now applied in `select_book`
  (edge-neutral: OOS Sharpe invariant none→15%, `cap_test.py`) as guardrail — non-binding
  today, protects against a future pathological momentum pile-up. Book selection is a single
  canonical `select_book` shared by the generator, the ledger, and the integrity sim.
- **Delisting-return survivorship** — **QUANTIFIED 2026-06-01 (`delisting_audit.py`):** book
  names delist next-month only **0.66%** of the time. Bounding the unobserved delisting price:
  LONG OOS Sharpe 0.96 (current 0%) → 0.86 (−30%) → 0.60 (−100%-on-all); EXCESS 1.13 → **0.78
  (−30%)** → 0.00 (−100%). The realistic case (−30%) keeps a solid edge; −100%-on-all is
  non-physical for a MOMENTUM winners book (delisting winners skew to M&A premium; bankruptcies
  are recent *losers* = bottom quintile, not held). Honest delisting-adjusted excess Sharpe ≈
  **0.8–1.1**. Forward paper-trade observes real outcomes → zero assumption risk live. Optional:
  fetch Sharadar `ACTIONS` for exact delisting returns. NOT a blocker.
- **Capacity / fill** — **QUANTIFIED 2026-06-01 (`capacity_fill.py`):** book median $ADV ~$93M
  (p10 $19M); at personal/small scale ($100k–$1M, ~$260–$2.6k per name) fill is a non-issue.
  Soft capacity ceiling ~**$429M** AUM (10% participation). Lone outlier AACO (~$0 month-end-day
  volume) is a 1-day/month proxy artifact, not a real wall. Optional pre-capital: add a $ADV
  liquidity floor (drop sub-$5M ADV, consistent with the $2B/$3 floors) — test edge-invariance
  first; verify with true 21-day ADV.
- **Position count** (~388) needs fractional shares + automated execution; operationally non-trivial.
- **Untapped data ($79 bundle, NOT yet mined):** additional factors (gross-profitability/assets,
  accruals, asset growth, net buyback/issuance, Piotroski F-score, 52-week-high, PEAD/earnings
  surprise, short-term reversal), and the **SF2 insider** + **SF3 institutional (13F)** datasets —
  documented alpha sources, entirely untested. The data likely holds more than this one strategy.

## 7. Artifacts (scripts/ab/, not committed; data gitignored)

`fetch_sharadar.py` (cache) · `xsec_factors.py` (research: sweep/sector/robust/spec) ·
`generate_portfolio.py` (monthly target portfolio + canonical `select_book` w/ FF cap) ·
`paper_trade.py` (forward ledger open/mark/status + integrity sim) · `neutralize_compare.py`
+ `cap_test.py` (B: neutralization-granularity & per-industry-cap robustness) ·
`audit_integrity.py` (5-check leak/PIT/survivorship audit) · `delisting_audit.py` +
`capacity_fill.py` (delisting-bias bound + capacity/fill) · `confirm_sharadar_interface.py`.

## 8. Remaining steps to real capital (off-platform decisions)

1. **Forward paper-trade** (running) — ≥6–12 monthly obs via `paper_trade.py`.
2. **Broker**: open IBKR (Italian resident → IBIE). Capital.com CFD cannot trade hundreds of
   single US stocks affordably. Long leg needs IBKR fractional shares + API.
3. **Execution**: monthly, diff held book vs new target → API orders (rebalance ~0.55 turnover).
4. **Variant choice at funding time**: long-only (17.5% CAGR, full beta) OR market-neutral
   (long book + ONE SPX short ≈ the EW-universe hedge → ~6% alpha, Sharpe 1.0, −6% DD). The
   hedge leg alone can run on Capital.com US500; the long leg is IBKR.
5. **Optional hardening** (spec §6): delisting-return survivorship in the forward label
   (small for a winners book); capacity/fill analysis at real sizing. Not paper-trade blockers.

## 9. Alpha-integrity audit (2026-06-01, `audit_integrity.py`) — 5/5 PASS

Adversarial pre-capital gate (this project has a catastrophic look-ahead leak in its history;
the whole prior ML hunt was poisoned). All five clean:
- **A. Survivorship** — 21,300 panel tickers, 71% delisted-in-panel, 99% of delisted names'
  price series end → genuinely survivorship-free (delisted names live with real history).
- **B. PIT filing lag** — `datekey − calendardate` median **44d** (p10 31 / p90 88), <0.1%
  negative → `datekey` is the public filing date, not period-end. No restatement leak.
- **C. Asof sanity** — 0 filings dated after their month-end; 0/2000 sampled rows used a
  non-latest valid filing.
- **D. Truncation invariance (gold standard)** — recomputing the composite3 score at a recent
  month-end from the full panel vs a panel truncated at that date gives max abs diff
  **0.00e+00** over 16,765 names → the score is a pure function of data ≤ D. **No look-ahead.**
- **E. Label/cost** — label = `closeadj[D+1]/closeadj[D]` (month-end close, dividend-adjusted
  total return); book turnover 0.25/mo one-way → 0.31% annual drag @10bp/side (edge survives
  to 30bp). Realistic and tradable.

composite3 survives the adversarial audit that killed every other lead. Cleared for forward
paper-trade; integrity is not the gate — only forward persistence + venue remain.
