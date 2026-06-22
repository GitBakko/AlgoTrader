"""Does a CONCENTRATED book (few names) preserve the composite3 edge? Decides whether a
small-AUM (~EUR10k) live pilot can run a real version, or must stay paper until AUM grows.

At small AUM the IBKR per-order minimum ($0.35 Tiered) dominates: cost drag ~ 0.5*N trades/mo
* $0.35 * 12 / AUM. Full book (N~388) = ~8% drag on EUR10k (unviable); N~30 = ~0.6%. So we
need the smallest N that still holds the OOS edge.

Selects top-N by sector-neutral composite3 (with the 20% FF-industry cap), equal-weight,
monthly; reports OOS long + excess Sharpe / DD and the modeled IBKR drag at EUR10k.

Run: .venv/Scripts/python.exe scripts/ab/namecount_test.py
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
    MIN_PRICE, compute_factors, load, metrics, pit_fundamentals, price_panel,
    sector_neutralize,
)
from generate_portfolio import MCAP_FLOOR  # noqa: E402

TRADING_MONTHS = 12
FF_CAP = 0.20
ORDER_MIN_USD = 0.35     # IBKR Tiered per-order minimum
AUM_PILOT = 11000        # ~EUR10k in USD


def topn_capped(row, industry, n, cap_frac=FF_CAP):
    ranked = row.sort_values(ascending=False)
    cap = max(1, int(np.floor(cap_frac * n)))
    chosen, counts = [], {}
    for tk in ranked.index:
        ind = industry.get(tk, "UNKNOWN")
        if counts.get(ind, 0) >= cap:
            continue
        chosen.append(tk); counts[ind] = counts.get(ind, 0) + 1
        if len(chosen) >= n:
            break
    return chosen


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

    print(f"sector-neutral composite3, top-N capped, OOS from {split.date()}, "
          f"pilot AUM ${AUM_PILOT}")
    print(f"{'N':>5}{'LONG OOSsh':>11}{'LONG dd':>9}{'EXC OOSsh':>10}{'EXC OOSt':>9}"
          f"{'turn':>6}{'$drag@10k':>10}{'net edge':>9}")
    for n in (20, 30, 50, 100, 190, 388):
        lr, er, turns = {}, {}, []
        prev = set()
        for d in P.index:
            row = score.loc[d].where(mask.loc[d]).dropna()
            if len(row) < max(50, n):
                continue
            holds = topn_capped(row, industry, n)
            rb = fwd.loc[d, holds].fillna(0).mean()
            rew = fwd.loc[d, row.index].fillna(0).mean()
            lr[d] = rb; er[d] = rb - rew
            cur = set(holds)
            if prev:
                turns.append(len(cur ^ prev) / (2 * len(cur)))
            prev = cur
        lr = pd.Series(lr).sort_index(); er = pd.Series(er).sort_index()
        lo = metrics(lr[lr.index >= split]); eo = metrics(er[er.index >= split])
        to = float(np.mean(turns)) if turns else 0.0
        trades_mo = to * n * 2
        drag = trades_mo * ORDER_MIN_USD * 12 / AUM_PILOT
        net = eo["sharpe"]  # Sharpe is cost-aware via the 10bp already? no -> note below
        print(f"{n:>5}{lo['sharpe']:>11.2f}{lo['dd']*100:>8.0f}%{eo['sharpe']:>10.2f}"
              f"{eo['t']:>9.2f}{to:>6.2f}{drag*100:>9.1f}%{(0.06-drag)*100:>8.1f}%")
    print("\n'net edge' = ~6% gross alpha minus the IBKR per-order drag at EUR10k (rough).")
    print("Pick smallest N that (a) holds EXC OOS Sharpe ~>=0.8 and (b) keeps drag affordable.")
    print("If even N=30 holds the edge -> a concentrated EUR10k pilot is viable; else paper-only.")


if __name__ == "__main__":
    main()
