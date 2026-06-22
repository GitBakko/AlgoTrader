"""CAPACITY / FILL analysis for the live composite3 book (real-money sizing).

The book is ~388 equal-weight names, monthly rebalanced. At a given AUM each name takes
AUM/N dollars; whether you can fill that in a normal monthly trade depends on each name's
dollar ADV. Constraint: a position should be a small slice of ADV (here <=10% participation
=> fillable inside ~1 day without moving the price). The binding names are the least-liquid
($2B-mcap but thin) winners.

ADV proxy = median over the last 6 month-end snapshots of (closeadj * volume) per name
(month-end-day $ turnover; the cache has one trading day per month, so this is an order-of-
magnitude ADV, not a precise 21-day ADV).

Reports, per AUM: # names whose position > 10% ADV (slow to fill), the worst offenders, and
the MAX AUM at which the whole book fills in <=1 day at 10% participation.

Run: .venv/Scripts/python.exe scripts/ab/capacity_fill.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
sys.stdout.reconfigure(encoding="utf-8")

from xsec_factors import CACHE, load, price_panel  # noqa: E402

PARTICIPATION = 0.10   # max fraction of one day's $ volume you'll take
AUM_GRID = [1e5, 5e5, 1e6, 5e6, 2.5e7, 1e8, 5e8]


def main():
    # latest live book
    books = sorted(CACHE.glob("portfolio_*.csv"))
    if not books:
        print("no portfolio CSV — run generate_portfolio.py first."); return
    book = pd.read_csv(books[-1])
    asof = books[-1].stem.replace("portfolio_", "")
    n = len(book)

    tk, sep, sf1 = load()
    P = price_panel(sep)
    sep["date"] = pd.to_datetime(sep["date"])
    # $ turnover per (date,ticker) on month-end snapshots
    sep["dollar"] = sep["closeadj"] * sep["volume"]
    dvol = sep.pivot_table(index="date", columns="ticker", values="dollar", aggfunc="last")
    adv = dvol.tail(6).median().reindex(book["ticker"])   # robust recent $ ADV proxy
    adv = adv.dropna()
    bk = book.set_index("ticker").loc[adv.index]
    print(f"book {asof}: {n} names, ADV proxy for {len(adv)} of them")
    print(f"  $ADV  median={adv.median()/1e6:.1f}M  p10={adv.quantile(.1)/1e6:.1f}M  "
          f"min={adv.min()/1e6:.2f}M ({adv.idxmin()})")

    print(f"\n{'AUM':>8}{'pos/name':>10}{'>10%ADV':>9}{'>50%ADV':>9}"
          f"{'worst name (days@10%)':>26}")
    for aum in AUM_GRID:
        pos = aum / n
        frac = pos / adv                       # position as fraction of one-day $ vol
        days = frac / PARTICIPATION            # days to fill at 10% participation
        slow = int((frac > 0.10).sum())
        vslow = int((frac > 0.50).sum())
        w = days.idxmax()
        aum_s = f"${aum/1e6:.2f}M" if aum >= 1e6 else f"${aum/1e3:.0f}k"
        print(f"{aum_s:>8}{'$'+format(pos,',.0f'):>10}{slow:>9}{vslow:>9}"
              f"{w+' ('+format(days.max(),'.1f')+'d)':>26}")

    # max AUM s.t. EVERY name fills <=1 day at participation: pos <= part*min(adv)
    max_aum = PARTICIPATION * adv.min() * n
    # softer: allow the bottom 5% of names up to 1 day (use 5th-pct ADV)
    soft_aum = PARTICIPATION * adv.quantile(0.05) * n
    print(f"\nMAX AUM, whole book fills <=1 day @10% part = ${max_aum/1e6:.1f}M "
          f"(binding name = {adv.idxmin()}, ${adv.min()/1e6:.2f}M ADV)")
    print(f"MAX AUM tolerating the thinnest 5% spilling to ~1 day = ${soft_aum/1e6:.0f}M")
    print("\nAt personal scale ($50k-$1M) fill is a non-issue; the ceiling is the thin biotech/")
    print("small-$2B winners. Mitigate at scale: liquidity floor on $ADV, or trade thin names")
    print("over 2-3 days. ADV here is a 1-day/month proxy — verify with real 21d ADV pre-capital.")


if __name__ == "__main__":
    main()
