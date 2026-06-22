"""Last-gasp crypto free-data shot: Deribit DVOL vol-risk-premium -> BTC/ETH directional
timing. DEPLOYABLE on the existing Capital.com CFD stack (single-asset long/flat/short,
not the 100-stock problem).

VRP = DVOL (Deribit implied-vol index, annualized %) - realized vol (annualized %). A small
PRE-REGISTERED rule set (3 directional rules x BTC/ETH = honest trial count for DSR):
  R1 vrp>0 -> long, else flat        (positive vol premium = calm regime = stay long)
  R2 dvol z>+1 -> long, else flat     (buy capitulation/fear)
  R3 dvol < MA20 -> long, else flat   (falling vol = risk-on regime)
Benchmark = buy&hold. Leak-free (signal from data thru t; position earns t->t+1 via shift).

  GO if a rule beats buy&hold AND OOS Sharpe>0 + boot CI lower>0 + DSR>0.95.
Run: .venv/Scripts/python.exe scripts/ab/pit_vrp.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from scripts.ab.pit_funding import block_boot_ci, deflated_sr, psr  # noqa: E402

CACHE = ROOT / "data" / "crypto_perp"
TRADING_DAYS = 365
RV_WIN = 30
COST = 3e-4  # BTC/ETH CFD half-spread+taker per unit turnover


def load_asset(cur: str):
    dvol = pd.read_parquet(CACHE / f"dvol_{cur}.parquet")["dvol"]
    k = pd.read_parquet(CACHE / "klines_daily.parquet")
    sym = f"{cur}USDT"
    px = (k[k.symbol == sym].set_index("date")["close"].sort_index())
    px.index = pd.to_datetime(px.index).normalize()
    idx = dvol.index.union(px.index)
    dvol = dvol.reindex(idx).ffill(limit=3)
    px = px.reindex(idx).ffill(limit=3)
    df = pd.DataFrame({"dvol": dvol, "px": px}).dropna()
    return df


def rules(df: pd.DataFrame) -> dict[str, pd.Series]:
    logret = np.log(df.px).diff()
    rv = logret.rolling(RV_WIN).std() * np.sqrt(TRADING_DAYS) * 100
    vrp = df.dvol - rv
    z = (df.dvol - df.dvol.rolling(60).mean()) / df.dvol.rolling(60).std()
    ma20 = df.dvol.rolling(20).mean()
    return {
        "R1 vrp>0": (vrp > 0).astype(float),
        "R2 dvol_z>1": (z > 1).astype(float),
        "R3 dvol<MA20": (df.dvol < ma20).astype(float),
        "buy&hold": pd.Series(1.0, index=df.index),
    }


def metrics(daily, oos_start):
    def m(d):
        d = d.dropna()
        n = len(d)
        if n < 5:
            return (n, 0.0, 0.0, 0.0, 0.0)
        mean, sd = d.mean(), d.std(ddof=1)
        sh = mean / sd * np.sqrt(TRADING_DAYS) if sd > 0 else 0.0
        t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
        eq = (1 + d).cumprod()
        dd = (eq / eq.cummax() - 1).min()
        return (n, sh, t, dd, mean * TRADING_DAYS)
    return m(daily), m(daily[daily.index >= oos_start])


def main():
    trial_sh, primary = [], None
    print(f"{'asset/rule':<22}{'FULL Sh':>9}{'ann%':>7}{'boot95 CI':>17}"
          f"{'OOS Sh':>8}{'OOS t':>7}{'OOSann':>8}{'maxDD':>8}{'expo':>6}")
    for cur in ("BTC", "ETH"):
        df = load_asset(cur)
        ret = df.px.pct_change().clip(-0.4, 0.4)
        oos = df.index[int(len(df) * 0.65)]
        print(f"--- {cur}  {df.index.min().date()}->{df.index.max().date()}  "
              f"OOS {oos.date()} ---")
        for name, pos in rules(df).items():
            daily = pos.shift(1) * ret
            turn = pos.diff().abs()
            daily = daily - turn * COST
            ci = block_boot_ci(daily)
            (fn, fsh, ft, fdd, fan), (on, osh, ot, odd, oan) = metrics(daily, oos)
            if name != "buy&hold":
                trial_sh.append(fsh)
            if cur == "BTC" and name == "R2 dvol_z>1":
                primary = daily  # best candidate -> honest DSR on the winner, not a control
            ci_s = f"[{ci[0]:+.2f},{ci[2]:+.2f}]" if ci is not None else "n/a"
            print(f"{cur+' '+name:<22}{fsh:>9.2f}{fan*100:>6.0f}%{ci_s:>17}"
                  f"{osh:>8.2f}{ot:>7.2f}{oan*100:>7.0f}%{fdd*100:>7.0f}%{pos.mean():>6.2f}")
    dsr, sr0 = deflated_sr(primary, trial_sh, n_trials=max(8, len(trial_sh)))
    print(f"\nDeflated SR* (N={max(8,len(trial_sh))}) = {sr0:.2f} -> Deflated PSR = {dsr:.3f}")
    print("GO if a rule BEATS buy&hold + OOS Sh>0 + boot CI lower>0 + DSR>0.95.")


if __name__ == "__main__":
    main()
