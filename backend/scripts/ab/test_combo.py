"""Capstone: COMBINE the 2 surviving overlays into a 50/50 book.
  A = VIX-gated US500 (long S&P when VIX/VIX3M<1 else cash)
  B = seasonal gold  (long XAUUSD Jul->Feb else flat, net of CFD financing)
Both leak-free, net of cost. Question: are A and B uncorrelated enough that a 50/50 combo
beats each single AND beats a naive 50/50 buy&hold (US500+gold) on risk-adjusted terms?

Run: .venv/Scripts/python.exe scripts/ab/test_combo.py
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
COST = 2e-4
GOLD_FIN = 0.03 / PPY
OOS_FRAC = 0.35


def dl(t, start):
    d = yf.download(t, start=start, progress=False, auto_adjust=False)["Close"]
    s = d[d.columns[0]] if isinstance(d, pd.DataFrame) else d
    s.index = pd.to_datetime(s.index)
    return s.dropna()


def main():
    vix = dl("^VIX", "2006-01-01"); vix3m = dl("^VIX3M", "2006-01-01")
    spx = dl("^GSPC", "2006-01-01"); gold = dl("GC=F", "2006-01-01")
    P = pd.DataFrame({"spx": spx, "gold": gold, "vix": vix, "vix3m": vix3m}).dropna()
    spx_r = P["spx"].pct_change(); gold_r = P["gold"].pct_change()

    # A: VIX gate on S&P
    posA = (P["vix"] / P["vix3m"] < 1.0).astype(float)
    rA = posA.shift(1) * spx_r - posA.diff().abs() * COST
    # B: seasonal gold (Jul-Feb)
    m = P.index.month
    posB = pd.Series(((m >= 7) | (m <= 2)).astype(float), index=P.index)
    rB = posB.shift(1) * gold_r - posB.diff().abs() * COST - posB.shift(1) * GOLD_FIN
    # combo 50/50
    combo = 0.5 * rA + 0.5 * rB
    # naive 50/50 buy&hold (US500 + gold)
    bh = 0.5 * spx_r + 0.5 * gold_r

    df = pd.DataFrame({"A_vix_spx": rA, "B_seas_gold": rB, "combo": combo, "bh5050": bh}).dropna()
    oos = df.index[int(len(df) * (1 - OOS_FRAC))]
    print(f"common {df.index.min().date()}->{df.index.max().date()}  OOS from {oos.date()}")
    corr_full = df["A_vix_spx"].corr(df["B_seas_gold"])
    corr_oos = df.loc[df.index >= oos, "A_vix_spx"].corr(df.loc[df.index >= oos, "B_seas_gold"])
    print(f"corr(A,B) full={corr_full:+.2f}  OOS={corr_oos:+.2f}  (low = diversification)\n")

    trial = []
    for name in ["A_vix_spx", "B_seas_gold", "combo", "bh5050"]:
        r = df[name]
        mf = metrics(r, PPY); mo = metrics(r[r.index >= oos], PPY)
        ci = block_boot_ci(r[r.index >= oos], PPY)
        if name in ("A_vix_spx", "B_seas_gold"):
            trial.append(mf["sharpe"])
        print(line(name, mf, f"  CAGR={cagr(r,PPY)*100:.1f}%"))
        print(line("  OOS", mo, f"  bootCI[{ci[0]:+.2f},{ci[2]:+.2f}]"))

    dsr, sr0 = deflated_sr(df["combo"], trial + [metrics(df["combo"], PPY)["sharpe"]], PPY)
    co = metrics(df["combo"][df.index >= oos], PPY)
    bo = metrics(df["bh5050"][df.index >= oos], PPY)
    print(f"\nDeflated SR* (N=3) = {sr0:.2f} -> Deflated PSR (combo) = {dsr:.3f}")
    print(f"OOS combo Sharpe {co['sharpe']:.2f} (DD {co['dd']*100:.0f}%) vs naive 50/50 buy&hold "
          f"{bo['sharpe']:.2f} (DD {bo['dd']*100:.0f}%)")
    print("\nWIN if combo OOS Sharpe > both singles AND > naive 50/50 B&H, with lower DD.")


if __name__ == "__main__":
    main()
