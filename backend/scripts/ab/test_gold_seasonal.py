"""2nd-tier candidate: GOLD AUTUMN SEASONALITY (leak-free A/B test).

Hypothesis: gold has a demand-driven seasonal (Indian wedding/Diwali Aug-Nov, Chinese NY
Nov-Jan, Western year-end) → long the Jul→Feb window, flat the weak Mar-Jun. Calendar rule =
zero look-ahead. BUT an 8-month CFD long pays overnight financing, which the literature warns
erodes the ~7% seasonal gain — so we charge it explicitly.

Benchmark = buy&hold gold. Net of cost + CFD financing on held days. OOS=last 35%. DSR over the
window variants + bootstrap. GO if a seasonal window BEATS buy&hold risk-adjusted OOS with
bootCI lower>0 and DSR>0.95.

Run: .venv/Scripts/python.exe scripts/ab/test_gold_seasonal.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
sys.stdout.reconfigure(encoding="utf-8")

from factory_stats import block_boot_ci, cagr, deflated_sr, line, metrics  # noqa: E402

PPY = 252
COST = 3e-4
FINANCING_ANN = 0.03      # CFD long overnight financing ~3%/yr
OOS_FRAC = 0.35


def in_window(idx: pd.DatetimeIndex, start_m: int, end_m: int) -> pd.Series:
    """1.0 on days within [start_m, end_m] (wraps year-end if start>end)."""
    m = idx.month
    inside = (m >= start_m) | (m <= end_m) if start_m > end_m else (m >= start_m) & (m <= end_m)
    return pd.Series(inside.astype(float), index=idx)


def main():
    px = yf.download("GC=F", start="2000-01-01", progress=False, auto_adjust=False)["Close"]
    px = (px[px.columns[0]] if isinstance(px, pd.DataFrame) else px).dropna()
    px.index = pd.to_datetime(px.index)
    ret = px.pct_change()
    fin_d = FINANCING_ANN / PPY
    oos = px.index[int(len(px) * (1 - OOS_FRAC))]
    print(f"GC=F daily: {len(px)} days  {px.index.min().date()} -> {px.index.max().date()}  "
          f"OOS from {oos.date()}\n")

    def run(pos):
        turn = pos.diff().abs()
        return pos.shift(1) * ret - turn * COST - pos.shift(1) * fin_d

    variants = {
        "buy&hold": pd.Series(1.0, index=px.index),
        "seasonal Jul-Feb": in_window(px.index, 7, 2),
        "seasonal Aug-Feb": in_window(px.index, 8, 2),
        "seasonal Sep-Jan": in_window(px.index, 9, 1),
    }
    series, trial_sh = {}, []
    for name, pos in variants.items():
        r = run(pos)
        series[name] = r
        mf = metrics(r, PPY); mo = metrics(r[r.index >= oos], PPY)
        ci = block_boot_ci(r[r.index >= oos], PPY)
        if name != "buy&hold":
            trial_sh.append(mf["sharpe"])
        print(line(name, mf, f"  CAGR={cagr(r,PPY)*100:.1f}%"))
        print(line("  OOS", mo, f"  bootCI[{ci[0]:+.2f},{ci[2]:+.2f}]"))

    prim = series["seasonal Jul-Feb"]
    dsr, sr0 = deflated_sr(prim, trial_sh, PPY)
    bh = metrics(series["buy&hold"][series["buy&hold"].index >= oos], PPY)
    se = metrics(prim[prim.index >= oos], PPY)
    print(f"\nDeflated SR* (N={len(trial_sh)}) = {sr0:.2f} -> Deflated PSR (Jul-Feb) = {dsr:.3f}")
    print(f"OOS seasonal {se['sharpe']:.2f} (CAGR {cagr(prim[prim.index>=oos],PPY)*100:.1f}%, "
          f"DD {se['dd']*100:.0f}%) vs buy&hold {bh['sharpe']:.2f} "
          f"(CAGR {cagr(series['buy&hold'][series['buy&hold'].index>=oos],PPY)*100:.1f}%, DD {bh['dd']*100:.0f}%)")
    print("\nGO if seasonal OOS Sharpe > buy&hold AND bootCI lower>0 AND DSR>0.95.")
    print("(seasonal's value = capture most upside while FLAT in weak Mar-Jun -> lower DD)")


if __name__ == "__main__":
    main()
