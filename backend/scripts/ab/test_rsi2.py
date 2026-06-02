"""H1 screen — Connors RSI-2 dip-buy on cash indices (long-only, uptrend filter).

Leak-safe: position[i] is decided from data up to and including close[i]; the
DailyBacktester applies weights.shift(1)*returns so it earns return i->i+1.
Expectation (prior memory): mean-reversion family decayed post-2010 -> likely
DEAD/decayed OOS. Confirm cheaply here before any forward test. Run from backend/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from harness import (  # noqa: E402
    DailyBacktester, load_daily_prices, normalize_book, oos_split_date,
)

INDEX_EPICS = ["US500", "US100", "DE40"]


def rsi(close: pd.Series, n: int = 2) -> pd.Series:
    """Wilder RSI. Causal (ewm uses only past), so no look-ahead."""
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / n, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / n, adjust=False).mean()
    # When rd==0 and ru>0: RSI=100; ru==0 and rd>0: RSI=0; both 0: RSI=50.
    result = pd.Series(50.0, index=close.index, dtype=float)
    both_zero = (ru == 0.0) & (rd == 0.0)
    normal = ~both_zero & (rd > 0.0)
    overbought = ~both_zero & (rd == 0.0) & (ru > 0.0)
    oversold = ~both_zero & (ru == 0.0) & (rd > 0.0)
    rs = ru[normal] / rd[normal]
    result[normal] = 100.0 - 100.0 / (1.0 + rs)
    result[overbought] = 100.0
    result[oversold] = 0.0
    return result


def rsi2_position(close: pd.Series, entry: float = 5.0, exit_: float = 70.0,
                  ma_len: int = 0) -> pd.Series:
    """Long-only state machine: enter when RSI(2)<entry (and close>MA if ma_len>0);
    exit when RSI(2)>exit_. Decided at close[i] (causal).

    ma_len=0 (default) disables the uptrend filter; pass ma_len=200 in production
    screens to restrict entries to established uptrends.
    """
    r = rsi(close, 2)
    ma = close.rolling(ma_len).mean() if ma_len > 0 else None
    pos = np.zeros(len(close), dtype=float)
    holding = False
    for i in range(len(close)):
        if not holding:
            uptrend = True
            if ma is not None:
                ma_i = ma.iloc[i]
                uptrend = not np.isnan(ma_i) and close.iloc[i] > ma_i
            if r.iloc[i] < entry and uptrend:
                holding = True
        elif r.iloc[i] > exit_:
            holding = False
        pos[i] = 1.0 if holding else 0.0
    return pd.Series(pos, index=close.index)


def main() -> None:
    px = load_daily_prices(INDEX_EPICS)
    pos = pd.DataFrame({
        e: rsi2_position(px[e].dropna(), ma_len=200).reindex(px.index).fillna(0.0)
        for e in px.columns
    })
    w = normalize_book(pos)
    res = DailyBacktester(px).run(w, oos_split_date(px))
    print(res["full"].line("FULL"))
    print(res["oos"].line("OOS"))
    decay = res["full"].sharpe - res["oos"].sharpe
    dead = res["oos"].t_stat < 2.0 or res["oos"].sharpe <= 0
    print(f"decay(full-oos Sharpe) = {decay:.2f}")
    print("VERDICT:", "DEAD/decayed — drop." if dead else "SURVIVES -> forward lab.")


if __name__ == "__main__":
    main()
