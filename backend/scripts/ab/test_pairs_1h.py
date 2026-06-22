"""Tier-1 confirmation: BTC/ETH ratio-spread stat-arb at 1h (many trades).

Daily pairs looked great (OOS Sharpe 1.88) but on only ~13 round-trips = not robust.
At 1h the BTC/ETH ratio mean-reverts on an hours half-life, giving hundreds of trades
=> a statistically meaningful confirm/kill. Dollar-neutral ratio spread (log ETH - log
BTC), z-entry/exit, net of full round-trip spread per leg + overnight swap. Forward-only
rolling z (no look-ahead). Reports full + OOS (time-split) per-trade stats.
Run: .venv/Scripts/python.exe scripts/ab/test_pairs_1h.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
for _n in ("sqlalchemy.engine", "src"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from src.backtest.costs import ASSET_SPREADS, OVERNIGHT_RATES  # noqa: E402
from src.data.storage import ParquetStorageManager  # noqa: E402

A, B = "ETHUSD", "BTCUSD"
Z_WIN = 120          # 1h bars (~5 days) trailing z-score window
Z_ENTRY, Z_EXIT = 2.0, 0.5
SLIP = 0.10
MAX_HOLD_BARS = 24 * 14   # safety vertical barrier (14 days)


def main():
    st = ParquetStorageManager()
    da = st.read_candles(A, "1h").sort("timestamp").to_pandas().set_index("timestamp")["close"]
    db = st.read_candles(B, "1h").sort("timestamp").to_pandas().set_index("timestamp")["close"]
    df = (da.rename("A").to_frame().join(db.rename("B"), how="inner")).dropna()
    print(f"1h bars (common): {len(df)}  {df.index.min()} -> {df.index.max()}")

    la, lb = np.log(df["A"].to_numpy()), np.log(df["B"].to_numpy())
    spread = la - lb
    s = __import__("pandas").Series(spread, index=df.index)
    z = ((s - s.rolling(Z_WIN).mean()) / s.rolling(Z_WIN).std()).to_numpy()
    pa, pb = df["A"].to_numpy(), df["B"].to_numpy()
    ts = df.index.to_numpy()

    cost_frac = 0.5 * (1 + SLIP) * 0  # placeholder, computed per-trade below
    swap_pair = (abs(OVERNIGHT_RATES.get(A, {"long": -1.5e-5})["long"])
                 + abs(OVERNIGHT_RATES.get(B, {"long": -1.5e-5})["long"])) / 2.0

    trades = []  # (entry_ts, ret_net)
    state, ei = 0, -1
    for i in range(len(df)):
        zi = z[i]
        if np.isnan(zi):
            continue
        if state == 0:
            if zi > Z_ENTRY:
                state, ei = -1, i
            elif zi < -Z_ENTRY:
                state, ei = +1, i
        else:
            held = i - ei
            if abs(zi) < Z_EXIT or held >= MAX_HOLD_BARS:
                retA = pa[i] / pa[ei] - 1.0
                retB = pb[i] / pb[ei] - 1.0
                gross = (retA - retB) if state == +1 else (retB - retA)
                # full round-trip spread per leg, /2 for leverage-1 normalization
                c = ((ASSET_SPREADS[A] / pa[ei]) + (ASSET_SPREADS[B] / pb[ei])) / 2.0 * (1 + SLIP)
                nights = (held) // 24
                fin = nights * swap_pair
                net = gross / 2.0 - c - fin
                trades.append((ts[ei], net))
                state, ei = 0, -1

    if not trades:
        print("no trades"); return
    import pandas as pd
    tr = pd.DataFrame(trades, columns=["entry", "net"])
    tr["entry"] = pd.to_datetime(tr["entry"])
    oos_cut = tr["entry"].quantile(0.6)

    def stats(x, label):
        n = len(x)
        if n < 3:
            print(f"  {label:<5} n={n} (too few)"); return
        mean, sd = x.mean(), x.std(ddof=1)
        # annualize: trades are episodic; scale per-trade Sharpe by sqrt(trades/yr)
        span_yrs = max((tr['entry'].max() - tr['entry'].min()).days / 365.0, 0.5)
        tpy = n / span_yrs
        sharpe = (mean / sd * np.sqrt(tpy)) if sd > 0 else 0.0
        t = (mean / (sd / np.sqrt(n))) if sd > 0 else 0.0
        print(f"  {label:<5} n={n:<4} mean={mean*1e4:>7.1f}bps  win={ (x>0).mean()*100:>4.1f}%  "
              f"total={x.sum()*100:>6.1f}%  ann.Sharpe={sharpe:>5.2f}  t={t:>5.2f}")

    print(f"\nBTC/ETH 1h ratio spread (z_win={Z_WIN}, entry={Z_ENTRY}, exit={Z_EXIT}), net of cost")
    stats(tr["net"], "FULL")
    stats(tr[tr["entry"] < oos_cut]["net"], "IS")
    stats(tr[tr["entry"] >= oos_cut]["net"], "OOS")
    print(f"\n  OOS cut at {oos_cut}")


if __name__ == "__main__":
    main()
