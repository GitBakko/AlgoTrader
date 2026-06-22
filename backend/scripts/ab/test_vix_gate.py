"""Candidate #1: VIX TERM-STRUCTURE GATE on the S&P 500 (leak-free A/B test).

Hypothesis (Fassas-Hourvouliades SSRN 3189502): when VIX futures are in contango
(VIX/VIX3M < 1 = calm) hold the S&P; in backwardation (>=1 = stress) step to cash. The
ratio is a realized-vs-implied / risk-appetite regime signal, not a calendar artifact.

Leak-free: R_t = VIX_t / VIX3M_t from closes of day t -> position held t->t+1 (pos.shift(1)).
Benchmark = buy&hold S&P. Net of CFD cost. OOS = last 35%. Deflated Sharpe over the variants
tested + block-bootstrap CI. GO if a gate BEATS buy&hold OOS (Sharpe up / DD down) with CI
lower > 0 and DSR > 0.95.

Run: .venv/Scripts/python.exe scripts/ab/test_vix_gate.py
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

from factory_stats import block_boot_ci, cagr, deflated_sr, line, metrics, psr  # noqa: E402

PPY = 252
COST = 2e-4   # US500 CFD ~ half-spread per unit turnover (tight index)
OOS_FRAC = 0.35


def fetch():
    df = {}
    for t, name in [("^VIX", "vix"), ("^VIX3M", "vix3m"), ("^GSPC", "spx")]:
        d = yf.download(t, start="2006-01-01", progress=False, auto_adjust=False)["Close"]
        df[name] = d[d.columns[0]] if isinstance(d, pd.DataFrame) else d
    P = pd.DataFrame(df).dropna()
    P.index = pd.to_datetime(P.index)
    return P


def main():
    P = fetch()
    ret = P["spx"].pct_change()
    R = (P["vix"] / P["vix3m"])
    oos = P.index[int(len(P) * (1 - OOS_FRAC))]
    print(f"S&P + VIX/VIX3M: {len(P)} days  {P.index.min().date()} -> {P.index.max().date()}  "
          f"OOS from {oos.date()}")
    print(f"backwardation (R>=1) freq: {(R >= 1).mean()*100:.1f}% of days\n")

    def run(pos: pd.Series) -> pd.Series:
        turn = pos.diff().abs()
        return pos.shift(1) * ret - turn * COST

    variants = {
        "buy&hold": pd.Series(1.0, index=P.index),
        "gate R<1.0": (R < 1.0).astype(float),
        "gate R<0.95": (R < 0.95).astype(float),
        "gate R<1.0 ma3": (R.rolling(3).mean() < 1.0).astype(float),
        "gate L/S R<1.0": (R < 1.0).astype(float) * 2 - 1,   # +1 long / -1 short
    }
    series, trial_sh = {}, []
    print(f"{'variant':<24}{'FULL':<2}{'':>0}")
    for name, pos in variants.items():
        r = run(pos)
        series[name] = r
        mf = metrics(r, PPY)
        mo = metrics(r[r.index >= oos], PPY)
        ci = block_boot_ci(r[r.index >= oos], PPY)
        if name != "buy&hold":
            trial_sh.append(mf["sharpe"])
        print(line(name, mf))
        print(line("  OOS", mo, f"  bootCI[{ci[0]:+.2f},{ci[2]:+.2f}]  CAGR={cagr(r[r.index>=oos],PPY)*100:.1f}%"))

    # deflated PSR for the primary gate vs the variant set
    prim = series["gate R<1.0"]
    dsr, sr0 = deflated_sr(prim, trial_sh, PPY)
    bh_oos = metrics(series["buy&hold"][series["buy&hold"].index >= oos], PPY)
    g_oos = metrics(prim[prim.index >= oos], PPY)
    print(f"\nDeflated SR* (N={len(trial_sh)}) = {sr0:.2f}  -> Deflated PSR (gate R<1.0) = {dsr:.3f}")
    print(f"OOS gate R<1.0 Sharpe {g_oos['sharpe']:.2f} (DD {g_oos['dd']*100:.0f}%) "
          f"vs buy&hold {bh_oos['sharpe']:.2f} (DD {bh_oos['dd']*100:.0f}%)")
    print("\nGO if gate OOS Sharpe > buy&hold AND bootCI lower > 0 AND DSR > 0.95 AND DD better.")


if __name__ == "__main__":
    main()
