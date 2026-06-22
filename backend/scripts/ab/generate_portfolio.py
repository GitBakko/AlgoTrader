"""Paper-trade core: generate the TARGET PORTFOLIO you would hold this month from
the validated sector-neutral composite strategy. This is the artifact you actually
execute / paper-trade each month.

Strategy (validated 2026-06-01, see project_xsec_factor_result memory):
  universe : liquid US equities, marketcap >= $2B, price >= $3
  score    : sector-neutral composite = nanmean of z(value), z(quality), z(12-1 momentum)
             demeaned within sicsector
  hold     : top quintile (20%) by score, equal-weight, ~250 names
  rebalance: monthly (month-end)
  expected : OOS ~6% alpha over EW market (Sharpe 1.0, maxDD -6%), or ~17% long CAGR
             with full market beta (maxDD -24%). Deploy long-only via IBKR, or
             market-neutral by hedging with one SPX index short.

Usage from backend/:
  .venv/Scripts/python.exe scripts/ab/generate_portfolio.py            # latest cached date
  .venv/Scripts/python.exe scripts/ab/generate_portfolio.py --refresh  # pull fresh first
  .venv/Scripts/python.exe scripts/ab/generate_portfolio.py 2026-04-30 # as-of a date

Writes data/sharadar/portfolio_<asof>.csv (gitignored). NEVER commits data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from xsec_factors import (  # noqa: E402
    CACHE, MIN_PRICE, load, price_panel, pit_fundamentals,
    compute_factors, sector_neutralize,
)

MCAP_FLOOR = 2e9
TOP_FRAC = 0.20
FF_CAP = 0.20   # max fraction of book names in any one Fama-French industry (risk hygiene,
                # edge-neutral: OOS Sharpe unchanged none->15%, cap_test.py 2026-06-01)


def select_book(row: pd.Series, industry: pd.Series,
                top_frac: float = TOP_FRAC, cap_frac: float | None = FF_CAP) -> pd.Series:
    """Canonical book selection — THE single source of truth used by the live generator,
    the paper-trade ledger, and the integrity sim (so they can never drift). Greedy by
    score desc, target = round(top_frac * universe), each FF industry limited to
    cap_frac*target names (cap_frac=None disables). Returns score-sorted holdings."""
    ranked = row.sort_values(ascending=False)
    target_n = int(round(len(row) * top_frac))
    if cap_frac is None:
        return ranked.iloc[:target_n]
    cap = max(1, int(np.floor(cap_frac * target_n)))
    chosen, counts = [], {}
    for tk in ranked.index:
        ind = industry.get(tk, "UNKNOWN")
        if counts.get(ind, 0) >= cap:
            continue
        chosen.append(tk)
        counts[ind] = counts.get(ind, 0) + 1
        if len(chosen) >= target_n:
            break
    return ranked.loc[chosen]


def generate(asof: str | None = None, mcap_floor: float = MCAP_FLOOR):
    tk, sep, sf1 = load()
    P = price_panel(sep)
    fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    td = tk.drop_duplicates("ticker").set_index("ticker")
    sector = td["sicsector"]
    name = td["name"]
    industry = td["famaindustry"]

    facs = compute_factors(P, fund, mom_lb=12)
    score = sector_neutralize(facs["composite3"], sector)

    # pick the rebalance date
    if asof:
        d = P.index[P.index <= pd.Timestamp(asof)][-1]
    else:
        d = P.index[-1]

    mask = (P.loc[d] >= MIN_PRICE) & (mcap.loc[d] >= mcap_floor)
    row = score.loc[d].where(mask).dropna()
    if len(row) < 50:
        raise RuntimeError(f"only {len(row)} scored names on {d.date()} — stale data?")
    holds = select_book(row, industry)   # canonical capped selection (shared w/ paper_trade)

    out = pd.DataFrame({
        "ticker": holds.index,
        "name": name.reindex(holds.index).values,
        "sector": sector.reindex(holds.index).values,
        "industry": industry.reindex(holds.index).values,
        "score": holds.values,
        "weight": 1.0 / len(holds),
    })
    fpath = CACHE / f"portfolio_{pd.Timestamp(d).date()}.csv"
    out.to_csv(fpath, index=False)

    print(f"=== TARGET PORTFOLIO as-of {pd.Timestamp(d).date()} ===")
    print(f"{len(out)} positions, equal-weight {100/len(out):.2f}% each, "
          f"universe {int(mask.sum())} names")
    print(f"sector spread: {out['sector'].value_counts().to_dict()}")
    print(f"\ntop 20 by score:")
    print(out.head(20).to_string(index=False))
    print(f"\n-> full list: {fpath}")
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--refresh" in sys.argv:
        print("refreshing Sharadar cache ...")
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "ab" / "fetch_sharadar.py")],
                       check=False)
    generate(args[0] if args else None)
