"""H5 screen — overnight drift (close->open) net of CFD financing.

Kill-cheap economic check: the overnight equity premium is small; CFD overnight
financing is a structural headwind. If net mean <= 0 or not significant, the
hypothesis is dead-on-arrival and must NOT consume forward-demo months.
Leak-safe: overnight_ret[t] = open[t]/close[t-1]-1 uses only data known at t's open.
Run from backend/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from harness import swap_abs  # noqa: E402
from factory_stats import block_boot_ci, line, metrics  # noqa: E402
from src.data.storage import ParquetStorageManager  # noqa: E402

INDEX_EPICS = ["US500", "US100", "DE40"]  # cash indices; script skips any not cached


def overnight_net(open_px: pd.Series, close_px: pd.Series, swap_abs_frac: float) -> pd.Series:
    """Overnight return open[t]/close[t-1]-1 minus one night of financing."""
    prev_close = close_px.shift(1)
    overnight = open_px / prev_close - 1.0
    return overnight - float(swap_abs_frac)


def main() -> None:
    st = ParquetStorageManager()
    series: dict[str, pd.Series] = {}
    for e in INDEX_EPICS:
        df = st.read_candles(e, "1d")
        if df.is_empty():
            continue
        p = df.select(["timestamp", "open", "close"]).to_pandas()
        p["date"] = pd.to_datetime(p["timestamp"]).dt.normalize()
        g = p.dropna(subset=["open", "close"]).groupby("date").last()
        series[e] = overnight_net(g["open"], g["close"], swap_abs(e))
    if not series:
        raise RuntimeError("no daily OHLC for index epics — check cache / INDEX_EPICS")
    pooled = pd.DataFrame(series).mean(axis=1).dropna()
    m = metrics(pooled, 252)
    lo, _mid, hi = block_boot_ci(pooled, 252)
    print(line("H5 overnight (net fin)", m, f"  CI90=[{lo:.2f},{hi:.2f}]"))
    dead = m["t"] < 2.0 or m["sharpe"] <= 0 or (lo <= 0 <= hi)
    print("VERDICT:", "DEAD — drop, do NOT forward-test."
          if dead else "SURVIVES -> graduate to forward lab.")


if __name__ == "__main__":
    main()
