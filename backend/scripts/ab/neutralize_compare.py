"""B: does FINER sector-neutralization keep the edge AND cut the concentration?

Spec §6 caveat: sicsector is 1-digit (9 groups) -> "Manufacturing" lumps semis+pharma+
biotech, so the top quintile piles into one mega-group. Test finer groupings on the
DEPLOYED config (composite3, top quintile, long + excess styles) and confirm the validated
OOS alpha SURVIVES (most fake refinements break it) while the book concentration drops.

Groupings: sicsector(9) baseline vs sector(11) vs famaindustry(48, Fama-French standard)
vs industry(152). Concentration measured on the SAME fine ruler (famaindustry) for all, so
it's an apples-to-apples 'how lumped is the book really'.

Run: .venv/Scripts/python.exe scripts/ab/neutralize_compare.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
sys.stdout.reconfigure(encoding="utf-8")

from xsec_factors import (  # noqa: E402
    MIN_PRICE, backtest_factor, compute_factors, dsr, load, metrics,
    pit_fundamentals, price_panel, sector_neutralize,
)

MCAP_FLOOR = 2e9
TOP_FRAC = 0.20
TRADING_MONTHS = 12


def boot_ci(r, block=6, n=2000):
    d = r.dropna().values
    L = len(d)
    if L < 24:
        return (np.nan, np.nan)
    rng = np.random.RandomState(12345)
    nb = int(np.ceil(L / block))
    sh = []
    for _ in range(n):
        starts = rng.randint(0, L, nb)
        idx = np.concatenate([np.arange(s, s + block) % L for s in starts])[:L]
        s = d[idx]
        sh.append(s.mean() / s.std(ddof=1) * np.sqrt(TRADING_MONTHS) if s.std() > 0 else 0)
    return tuple(np.percentile(sh, [5, 95]))


def book_concentration(P, score, mask, fine_group, oos_split):
    """Avg (over OOS months) share of the top-quintile book in its single largest
    famaindustry, + the single biggest group name's avg share."""
    fg = fine_group.reindex(P.columns).fillna("UNKNOWN")
    shares, top_grp = [], {}
    for d in P.index:
        if d < oos_split:
            continue
        row = score.loc[d].where(mask.loc[d]).dropna()
        if len(row) < 50:
            continue
        cut = row.quantile(1 - TOP_FRAC)
        holds = row[row >= cut].index
        g = fg.reindex(holds).value_counts(normalize=True)
        if len(g):
            shares.append(g.iloc[0])
            top_grp[g.index[0]] = top_grp.get(g.index[0], 0) + 1
    biggest = max(top_grp, key=top_grp.get) if top_grp else "-"
    return (np.mean(shares) if shares else np.nan), biggest


def main():
    tk, sep, sf1 = load()
    P = price_panel(sep)
    fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= MIN_PRICE) & (mcap >= MCAP_FLOOR)
    raw = compute_factors(P, fund, mom_lb=12)["composite3"]
    split = P.index[int(len(P) * 0.65)]

    td = tk.drop_duplicates("ticker").set_index("ticker")
    groupings = {
        "sicsector(9)": td["sicsector"],
        "sector(11)": td["sector"],
        "famaindustry(48)": td["famaindustry"],
        "industry(152)": td["industry"],
    }
    fine = td["famaindustry"]   # the common concentration ruler
    n_trials = len(groupings) * 2

    print(f"composite3, top quintile, OOS from {split.date()}  N_trials={n_trials}")
    print(f"{'neutralize':<18}{'style':<8}{'FULLsh':>7}{'OOSsh':>7}{'OOSt':>6}"
          f"{'OOSdd':>7}{'boot90 CI':>15}{'DSR':>6}{'concentr':>9}")
    for gname, gser in groupings.items():
        sn = sector_neutralize(raw, gser)
        conc, biggest = book_concentration(P, sn, mask, fine, split)
        for style in ("long", "excess"):
            r, to = backtest_factor(P, sn, mask, top_frac=TOP_FRAC, style=style)
            full = metrics(r)
            oos = metrics(r[r.index >= split])
            lo, hi = boot_ci(r[r.index >= split])
            p = dsr(r, n_trials)
            ci = f"[{lo:+.2f},{hi:+.2f}]"
            print(f"{gname:<18}{style:<8}{full['sharpe']:>7.2f}{oos['sharpe']:>7.2f}"
                  f"{oos['t']:>6.2f}{oos['dd']*100:>6.0f}%{ci:>15}{p:>6.2f}"
                  f"{conc*100:>7.0f}% ")
        print(f"{'':18}-> book's biggest famaindustry on avg = {biggest}, "
              f"{conc*100:.0f}% of names")
    print("\nKEEP finer grouping ONLY if OOS Sharpe holds (~>=0.85) AND concentration drops.")
    print("If a finer grouping breaks the edge -> the lump WAS the alpha -> stay sicsector.")


if __name__ == "__main__":
    main()
