"""Tier-1 A/B test #3: BTC/ETH pairs stat-arb (market-neutral), daily.

Forward-only rolling hedge ratio (beta of logETH on logBTC), spread z-score, enter
when |z|>2, exit when |z|<0.5. Dollar-hedged two-leg book normalized to leverage 1.
Evaluated net of cost (both legs pay spread + swap) OOS via the shared backtester.

Cointegration tested OUT-OF-SAMPLE implicitly (beta + z use only trailing data).
GO if OOS net Sharpe > 0.6 with enough trades. Daily horizon first (intraday is an
alternative if daily reversion is too slow).
Run: .venv/Scripts/python.exe scripts/ab/test_pairs.py
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

from scripts.ab.harness import DailyBacktester, load_daily_prices, normalize_book, oos_split_date  # noqa: E402

LEG_A, LEG_B = "ETHUSD", "BTCUSD"   # spread = logA - beta*logB
HEDGE_WIN = 90
Z_WIN = 30
Z_ENTRY = 2.0
Z_EXIT = 0.5


def pairs_weights(prices: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    a, b = np.log(prices[LEG_A]), np.log(prices[LEG_B])
    cov = a.rolling(HEDGE_WIN).cov(b)
    var = b.rolling(HEDGE_WIN).var()
    beta = (cov / var).clip(0.1, 5.0)          # forward-only hedge ratio
    spread = a - beta * b
    z = (spread - spread.rolling(Z_WIN).mean()) / spread.rolling(Z_WIN).std()

    w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    state = 0  # +1 long-spread (long A / short B), -1 short-spread, 0 flat
    n_trades = 0
    for t in prices.index:
        zt, bt = z.get(t, np.nan), beta.get(t, np.nan)
        if np.isnan(zt) or np.isnan(bt):
            continue
        if state == 0:
            if zt > Z_ENTRY:
                state = -1; n_trades += 1
            elif zt < -Z_ENTRY:
                state = +1; n_trades += 1
        elif abs(zt) < Z_EXIT:
            state = 0
        if state == +1:      # long spread: long A, short beta*B
            w.at[t, LEG_A] = 1.0
            w.at[t, LEG_B] = -bt
        elif state == -1:    # short spread: short A, long beta*B
            w.at[t, LEG_A] = -1.0
            w.at[t, LEG_B] = bt
    return normalize_book(w), n_trades


def main():
    prices = load_daily_prices([LEG_A, LEG_B])
    print(f"daily prices: {prices.shape[0]} days  {prices.index.min().date()} -> {prices.index.max().date()}")
    oos = oos_split_date(prices, 0.4)
    print(f"OOS from {oos.date()}\n")
    w, n_trades = pairs_weights(prices)
    bt = DailyBacktester(prices)
    res = bt.run(w, oos)
    print(f"BTC/ETH pairs (hedge_win={HEDGE_WIN}, z_win={Z_WIN}, entry={Z_ENTRY}, exit={Z_EXIT})")
    print(f"  total round-trips (full sample): {n_trades}")
    print(res["full"].line("FULL"))
    print(res["oos"].line("OOS"))
    go = "GO" if (res["oos"].sharpe > 0.6) else "no"
    print(f"\n  OOS Sharpe {res['oos'].sharpe:.2f} -> {go} (threshold 0.6)")


if __name__ == "__main__":
    main()
