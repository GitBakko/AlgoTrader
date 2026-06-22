"""Tier-1 A/B test #2: time-series momentum (TSMOM), daily, vol-scaled.

Signal per asset (point-in-time): blend of sign(cum return) over [21,63,252] trading
days -> raw in [-1,1]. Vol-scale by target_vol / realized_vol (20d). Normalize the
book to leverage 1. Evaluated net of cost, OOS, via the shared DailyBacktester.

GO if OOS net Sharpe > 0.4 on the full basket or a coherent sub-basket.
Run from backend/: .venv/Scripts/python.exe scripts/ab/test_tsmom.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
for _n in ("sqlalchemy.engine", "src"):
    logging.getLogger(_n).setLevel(logging.WARNING)

from scripts.ab.harness import (  # noqa: E402
    DailyBacktester,
    load_daily_prices,
    normalize_book,
    oos_split_date,
)
from src.utils.constants import TRADABLE_ASSETS  # noqa: E402

LOOKBACKS = [21, 63, 252]
VOL_WINDOW = 20
TARGET_VOL = 0.15
MAX_ASSET_LEV = 3.0
SUBBASKETS = {
    "ALL": TRADABLE_ASSETS,
    "comdty+idx+fx": ["WTIUSD", "XAUUSD", "COPPER", "PLATINUM", "US500", "DE40",
                       "USDJPY", "USDCAD", "USDCHF"],
    "crypto": ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD"],
    "stocks": ["TSLA", "NVDA", "AAPL", "MSFT", "GOOGL"],
}


def tsmom_weights(prices: pd.DataFrame) -> pd.DataFrame:
    ret = prices.pct_change()
    # momentum blend: average sign of cumulative return over each lookback (point-in-time)
    sig = None
    for lb in LOOKBACKS:
        mom = prices / prices.shift(lb) - 1.0
        s = np.sign(mom)
        sig = s if sig is None else sig + s
    sig = sig / len(LOOKBACKS)  # in [-1,1]
    realized_vol = ret.rolling(VOL_WINDOW).std() * np.sqrt(252)
    scale = (TARGET_VOL / realized_vol).clip(upper=MAX_ASSET_LEV)
    w = (sig * scale).clip(-MAX_ASSET_LEV, MAX_ASSET_LEV)
    return w


def main():
    prices = load_daily_prices(TRADABLE_ASSETS)
    print(f"daily prices: {prices.shape[0]} days  {prices.index.min().date()} -> {prices.index.max().date()}")
    oos = oos_split_date(prices, 0.4)
    print(f"OOS from {oos.date()} (last 40%)\n")

    w_all = tsmom_weights(prices)
    print(f"{'TSMOM sub-basket':<16} {'OOS Sharpe':>10} {'OOS ret':>9} {'hit':>6} {'maxDD':>8} {'t':>6}  GO?")
    for name, epics in SUBBASKETS.items():
        cols = [e for e in epics if e in prices.columns]
        w = normalize_book(w_all[cols].reindex(columns=prices.columns).fillna(0.0))
        bt = DailyBacktester(prices)
        res = bt.run(w, oos)
        m = res["oos"]
        go = "GO" if m.sharpe > 0.4 else "no"
        print(f"{name:<16} {m.sharpe:>10.2f} {m.ann_return*100:>8.1f}% {m.hit_pct:>5.1f}% "
              f"{m.max_dd*100:>7.1f}% {m.t_stat:>6.2f}  {go}")

    # per-asset standalone TSMOM (single-asset book), OOS Sharpe
    print("\nper-asset standalone TSMOM (OOS Sharpe):")
    bt = DailyBacktester(prices)
    rows = []
    for e in prices.columns:
        w1 = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w1[e] = np.sign(w_all[e]).fillna(0.0)  # +/-1 single asset
        m = bt.run(w1, oos)["oos"]
        rows.append((e, m.sharpe, m.hit_pct))
    for e, sh, hit in sorted(rows, key=lambda x: -x[1]):
        print(f"  {e:<9} Sharpe={sh:>6.2f}  hit={hit:>4.1f}%")


if __name__ == "__main__":
    main()
