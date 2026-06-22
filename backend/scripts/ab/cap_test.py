"""B (the useful version): does a per-industry CAP control the momentum tilt without
breaking the edge? Neutralization-granularity was a no-op (neutralize_compare.py); the real
lever for the semis+pharma tilt is a hard cap on names per Fama-French industry.

Deployed config (sicsector-neutral composite3, top quintile, equal-weight, monthly). Greedy
capped selection: walk the universe by score desc, add a name unless its FF industry already
holds cap x (quintile size). Measure OOS long (absolute) + excess (alpha) Sharpe and the
realized max single-industry share, at caps none / 25% / 20% / 15%.

Run: .venv/Scripts/python.exe scripts/ab/cap_test.py
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
    MIN_PRICE, compute_factors, dsr, load, metrics, pit_fundamentals,
    price_panel, sector_neutralize,
)

MCAP_FLOOR = 2e9
TOP_FRAC = 0.20
TRADING_MONTHS = 12


def capped_book(row_scores: pd.Series, industry: pd.Series, target_n: int, cap_frac):
    """row_scores: scored universe (index=ticker). Return chosen tickers (<=target_n),
    greedily by score, each FF industry limited to cap_frac*target_n names."""
    ranked = row_scores.sort_values(ascending=False)
    if cap_frac is None:
        return list(ranked.index[:target_n])
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
    return chosen


def run(P, score, mask, industry, fwd, split, cap_frac):
    fg = industry.reindex(P.columns).fillna("UNKNOWN")
    long_r, exc_r, maxshare = {}, {}, []
    for d in P.index:
        row = score.loc[d].where(mask.loc[d]).dropna()
        if len(row) < 50:
            long_r[d] = exc_r[d] = 0.0
            continue
        target_n = int(round(len(row) * TOP_FRAC))
        holds = capped_book(row, fg, target_n, cap_frac)
        rb = fwd.loc[d, holds].fillna(0).mean()
        rew = fwd.loc[d, row.index].fillna(0).mean()
        long_r[d], exc_r[d] = rb, rb - rew
        if d >= split and holds:
            maxshare.append(fg.reindex(holds).value_counts(normalize=True).iloc[0])
    return (pd.Series(long_r).sort_index(), pd.Series(exc_r).sort_index(),
            np.mean(maxshare) if maxshare else np.nan)


def main():
    tk, sep, sf1 = load()
    P = price_panel(sep)
    fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= MIN_PRICE) & (mcap >= MCAP_FLOOR)
    raw = compute_factors(P, fund, mom_lb=12)["composite3"]
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    industry = tk.drop_duplicates("ticker").set_index("ticker")["famaindustry"]
    score = sector_neutralize(raw, sector)
    fwd = P.shift(-1) / P - 1.0
    split = P.index[int(len(P) * 0.65)]
    n_trials = 8

    print(f"sicsector-neutral composite3, top quintile, OOS from {split.date()}")
    print(f"{'cap/FFindustry':<16}{'LONG OOSsh':>11}{'EXC OOSsh':>10}{'EXC OOSt':>9}"
          f"{'EXC dd':>8}{'DSR(L)':>8}{'maxFFshare':>12}")
    for cap in (None, 0.25, 0.20, 0.15):
        lr, er, ms = run(P, score, mask, industry, fwd, split, cap)
        lo = metrics(lr[lr.index >= split]); eo = metrics(er[er.index >= split])
        p = dsr(lr, n_trials)
        tag = "none" if cap is None else f"{int(cap*100)}%"
        print(f"{tag:<16}{lo['sharpe']:>11.2f}{eo['sharpe']:>10.2f}{eo['t']:>9.2f}"
              f"{eo['dd']*100:>7.0f}%{p:>8.2f}{ms*100:>10.0f}% ")
    print("\nKEEP the tightest cap that holds OOS Sharpe ~baseline AND lowers maxFFshare.")
    print("If every cap leaves Sharpe ~unchanged -> tilt is benign; cap optional risk hygiene.")


if __name__ == "__main__":
    main()
