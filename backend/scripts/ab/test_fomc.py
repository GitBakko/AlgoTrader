"""2nd-tier candidate: PRE-FOMC ANNOUNCEMENT DRIFT (leak-free, DAILY proxy).

Hypothesis (Lucca-Moench JF2015): S&P drifts up in the ~24h before scheduled FOMC
announcements. CAVEAT: the true effect is INTRADAY (2pm day-before → 2pm announcement);
daily closes can only approximate it. The original drift DIED 2015-2019 (Kurov) with a claimed
partial recovery 2020+. We test the recovery era (2021-2026, the dates we have) with two daily
proxies: the pre-FOMC DAY (close[d-2]→close[d-1]) and the announcement DAY (close[d-1]→close[d]).

Is the window return abnormally positive vs baseline? And does a long-only-in-window rule add
annualized return? Small sample (43 events) → wide CI; honest screen, not a deployable verdict.

Run: .venv/Scripts/python.exe scripts/ab/test_fomc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
sys.stdout.reconfigure(encoding="utf-8")

PPY = 252
COST = 2e-4

FOMC = [  # announcement dates 2021-2026 (federalreserve.gov)
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22",
    "2021-11-03", "2021-12-15", "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14", "2023-02-01", "2023-03-22",
    "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18",
    "2024-11-07", "2024-12-18", "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10", "2026-01-28", "2026-03-18",
    "2026-04-29",
]


def main():
    spx = yf.download("^GSPC", start="2020-10-01", progress=False, auto_adjust=False)["Close"]
    spx = (spx[spx.columns[0]] if isinstance(spx, pd.DataFrame) else spx).dropna()
    spx.index = pd.to_datetime(spx.index)
    ret = spx.pct_change()
    dates = sorted(pd.Timestamp(d) for d in FOMC)
    pos_in = pd.Series(spx.index.isin(dates), index=spx.index)  # announcement day
    # map each announcement day to the day BEFORE it (pre-FOMC day)
    loc = {spx.index[i]: i for i in range(len(spx.index))}
    preday_idx = [spx.index[loc[d] - 1] for d in dates if d in loc and loc[d] >= 1]
    annday_idx = [d for d in dates if d in loc]

    base = ret.dropna()
    r_pre = ret.reindex(preday_idx).dropna()
    r_ann = ret.reindex(annday_idx).dropna()

    print(f"S&P {spx.index.min().date()}->{spx.index.max().date()}  FOMC events used: {len(annday_idx)}\n")
    print(f"{'window':<16}{'n':>4}{'mean%':>9}{'t vs 0':>8}{'t vs base':>11}{'hit%':>7}")
    bmean = base.mean()
    for name, r in [("baseline (all)", base), ("pre-FOMC day", r_pre), ("announce day", r_ann)]:
        t0 = stats.ttest_1samp(r, 0).statistic if len(r) > 2 else 0
        tb = stats.ttest_ind(r, base, equal_var=False).statistic if name != "baseline (all)" else 0
        print(f"{name:<16}{len(r):>4}{r.mean()*100:>8.3f}%{t0:>8.2f}{tb:>11.2f}{(r>0).mean()*100:>6.0f}%")

    # tradeable: long S&P ONLY on pre-FOMC day (else cash), net of cost (2 trades/event)
    sig = pd.Series(0.0, index=spx.index)
    sig.loc[preday_idx] = 1.0
    strat = sig.shift(1) * ret  # decide at close d-2, hold d-1 ... but pre-day return is close[d-2]->close[d-1]
    # correct: to capture pre-FOMC day return we must be positioned at close of d-2.
    strat = sig * ret - sig.diff().abs().fillna(0) * COST   # sig already marks the pre-day; its return is that day's
    s = strat[strat != 0].dropna()
    n = len(s)
    ann_ret = s.mean() * len(annday_idx) * (252 / 252)  # ~ per-event mean * events/yr... report simply:
    yrs = (spx.index.max() - spx.index.min()).days / 365.25
    total = (1 + strat).prod() - 1
    cagr = (1 + total) ** (1 / yrs) - 1
    sh = strat.mean() / strat.std(ddof=1) * np.sqrt(PPY) if strat.std() > 0 else 0
    print(f"\nlong-only pre-FOMC-day rule: in-market {n} days over {yrs:.1f}yr, "
          f"total {total*100:+.1f}%, CAGR {cagr*100:+.1f}%, Sharpe {sh:.2f}")
    print(f"  vs buy&hold S&P same period: total {((1+ret).prod()-1)*100:+.1f}%, "
          f"CAGR {((1+ (ret.dropna()).sum())**(1/yrs)-1)*100:.1f}% (approx)")
    print("\nHONEST: daily proxy (not the true intraday 2pm window) + 43 events + recovery-era only.")
    print("Drift is REAL if pre-FOMC day mean >> baseline with t>2. Deployable only intraday.")


if __name__ == "__main__":
    main()
