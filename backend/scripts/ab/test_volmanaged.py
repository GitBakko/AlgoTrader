"""Candidate #2: VOLATILITY-MANAGED S&P 500 (Moreira-Muir, leak-free A/B test).

Hypothesis (Moreira & Muir, JF 2017): scale equity exposure inversely to last month's
realized variance: w = c^2 / RV_{prev month}. Vol mean-reverts faster than expected returns,
so de-risking high-vol months raises the Sharpe without sacrificing much return.

Leak-free: RV_m from daily returns WITHIN month m; the normalizer c^2 is a CAUSAL expanding
mean of RV (no full-sample look-ahead); w_{m+1} = c^2 / RV_m is applied to month m+1's return.
Benchmark = buy&hold (w=1). Net of monthly rebalance cost. OOS = last 35%. Reports Sharpe vs
B&H + appraisal alpha/IR (regress managed on B&H) + Deflated Sharpe + bootstrap CI.
GO if managed OOS Sharpe > B&H AND appraisal alpha > 0 AND DSR > 0.95.

Run: .venv/Scripts/python.exe scripts/ab/test_volmanaged.py
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

PPY = 12
COST = 2e-4
OOS_FRAC = 0.35
MIN_HIST = 24    # months before c^2 is trusted


def main():
    spx = yf.download("^GSPC", start="1990-01-01", progress=False, auto_adjust=False)["Close"]
    spx = (spx[spx.columns[0]] if isinstance(spx, pd.DataFrame) else spx).dropna()
    spx.index = pd.to_datetime(spx.index)
    dret = spx.pct_change().dropna()

    # monthly realized variance from daily returns, and monthly simple return
    rv = dret.groupby(dret.index.to_period("M")).apply(lambda x: (x**2).sum())
    mret = (1 + dret).groupby(dret.index.to_period("M")).prod() - 1
    M = pd.DataFrame({"rv": rv, "mret": mret}).dropna()
    M.index = M.index.to_timestamp("M")

    # causal normalizer: expanding mean of RV up to and including month m
    c2 = M["rv"].expanding(MIN_HIST).mean()

    results = {}
    trial_sh = []
    for cap in (1.5, 2.0):
        w = (c2 / M["rv"]).clip(0, cap)          # weight decided at end of month m
        w_next = w.shift(1)                       # applied to month m+1 (leak-free)
        turn = w_next.diff().abs().fillna(0)
        managed = (w_next * M["mret"] - turn * COST).dropna()
        results[f"vol-managed cap{cap}"] = managed
        trial_sh.append(metrics(managed, PPY)["sharpe"])
    bench = M["mret"].reindex(results["vol-managed cap1.5"].index)
    results["buy&hold"] = bench

    oos = bench.index[int(len(bench) * (1 - OOS_FRAC))]
    print(f"S&P monthly: {len(bench)} months  {bench.index.min().date()} -> "
          f"{bench.index.max().date()}  OOS from {oos.date()}\n")

    for name, r in results.items():
        mf = metrics(r, PPY); mo = metrics(r[r.index >= oos], PPY)
        ci = block_boot_ci(r[r.index >= oos], PPY, block=6)
        print(line(name, mf, f"  CAGR={cagr(r,PPY)*100:.1f}%"))
        print(line("  OOS", mo, f"  bootCI[{ci[0]:+.2f},{ci[2]:+.2f}]"))

    # appraisal: regress managed (cap1.5) on buy&hold -> alpha (monthly), IR
    m = results["vol-managed cap1.5"]
    df = pd.concat([m.rename("mgd"), bench.rename("bh")], axis=1).dropna()
    for tag, sl in [("FULL", df), ("OOS", df[df.index >= oos])]:
        x = sl["bh"].to_numpy(); y = sl["mgd"].to_numpy()
        beta = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
        alpha = y.mean() - beta * x.mean()
        resid = y - (alpha + beta * x)
        ir = alpha / resid.std(ddof=1) * np.sqrt(PPY) if resid.std() > 0 else 0.0
        print(f"  appraisal {tag}: alpha={alpha*PPY*100:+.2f}%/yr  beta={beta:.2f}  IR={ir:.2f}")

    dsr, sr0 = deflated_sr(m, trial_sh, PPY)
    print(f"\nDeflated SR* (N={len(trial_sh)}) = {sr0:.2f} -> Deflated PSR (cap1.5) = {dsr:.3f}")
    print("GO if managed OOS Sharpe > buy&hold AND appraisal alpha>0 (OOS) AND DSR>0.95.")


if __name__ == "__main__":
    main()
