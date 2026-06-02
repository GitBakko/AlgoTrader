# H1/H5 Backtest Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cheaply kill-or-promote H1 (Index RSI-2 dip-buy) and H5 (overnight drift) with leak-free daily backtests, BEFORE spending forward-demo months on them.

**Architecture:** Two standalone scripts in `backend/scripts/ab/` reusing the existing `harness.py` (`DailyBacktester`, `load_daily_prices`, `normalize_book`, `oos_split_date`) and `factory_stats.py` (`metrics`, `block_boot_ci`). Core math lives as importable pure functions, unit-tested for leak-safety (no look-ahead). No broker, no forward.

**Tech Stack:** Python 3.12, pandas, numpy, existing `scripts/ab` harness. Run from `backend/` with `.venv/Scripts/python.exe`.

> Branch: `feature/forward-demo-lab` (shared with the forward-lab plan; these screens are the parallel track). Independent of the forward lab — can be executed concurrently.

---

### Task 1: H5 overnight-drift economic screen

**Files:**
- Create: `backend/scripts/ab/test_overnight.py`
- Test: `backend/tests/ab/test_screens.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/ab/test_screens.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import numpy as np
import pandas as pd


def test_overnight_net_leak_safe_and_financing():
    from test_overnight import overnight_net
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    close = pd.Series([100.0, 110.0, 121.0], index=idx)
    open_ = pd.Series([100.0, 105.0, 110.0], index=idx)
    out = overnight_net(open_, close, 0.001)
    assert pd.isna(out.iloc[0])                       # no prev close -> NaN, never look ahead
    assert abs(out.iloc[1] - (105/100 - 1 - 0.001)) < 1e-9   # 0.049
    assert abs(out.iloc[2] - (110/110 - 1 - 0.001)) < 1e-9   # -0.001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ab/test_screens.py::test_overnight_net_leak_safe_and_financing -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'test_overnight'`.

- [ ] **Step 3: Write the pure function + screen**

```python
# backend/scripts/ab/test_overnight.py
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
    pooled = pd.DataFrame(series).mean(axis=1).dropna()  # equal-weight overnight book
    m = metrics(pooled, 252)
    lo, _mid, hi = block_boot_ci(pooled, 252)
    print(line("H5 overnight (net fin)", m, f"  CI90=[{lo:.2f},{hi:.2f}]"))
    dead = m["t"] < 2.0 or m["sharpe"] <= 0 or (lo <= 0 <= hi)
    print("VERDICT:", "DEAD — drop, do NOT forward-test."
          if dead else "SURVIVES -> graduate to forward lab.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ab/test_screens.py::test_overnight_net_leak_safe_and_financing -v`
Expected: PASS.

- [ ] **Step 5: Run the screen (manual observation)**

Run: `.venv/Scripts/python.exe scripts/ab/test_overnight.py`
Expected: one metrics line + VERDICT. (Expectation from prior memory: net ≤ 0 → DEAD; confirm.)

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/ab/test_overnight.py backend/tests/ab/test_screens.py
git commit -m "test(ab): H5 overnight-drift screen (leak-safe, net of CFD financing)"
```

---

### Task 2: H1 Index RSI-2 dip-buy screen

**Files:**
- Create: `backend/scripts/ab/test_rsi2.py`
- Test: `backend/tests/ab/test_screens.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/ab/test_screens.py

def _uptrend_with_dip() -> pd.Series:
    idx = pd.date_range("2022-01-01", periods=320, freq="D")
    base = 100.0 * (1.0005 ** np.arange(320))   # gentle uptrend, ends well above MA200
    base[250:255] *= 0.93                         # sharp dip -> RSI(2) collapses
    return pd.Series(base, index=idx)


def test_rsi_extremes():
    from test_rsi2 import rsi
    up = pd.Series(np.arange(1, 60, dtype=float))
    dn = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert rsi(up, 2).iloc[-1] > 95
    assert rsi(dn, 2).iloc[-1] < 5


def test_rsi2_position_no_lookahead():
    from test_rsi2 import rsi2_position
    close = _uptrend_with_dip()
    full = rsi2_position(close)
    k = 260
    trunc = rsi2_position(close.iloc[:k])
    # causal by construction: truncating the input cannot change past positions
    assert np.array_equal(full.iloc[:k].to_numpy(), trunc.to_numpy())
    assert full.iloc[:200].sum() == 0.0   # no position before MA200 is defined
    assert full.iloc[250:].sum() > 0.0    # enters after the oversold dip in uptrend
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/ab/test_screens.py -k rsi -v`
Expected: FAIL — `No module named 'test_rsi2'`.

- [ ] **Step 3: Write the pure functions + screen**

```python
# backend/scripts/ab/test_rsi2.py
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
    rs = ru / rd.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def rsi2_position(close: pd.Series, entry: float = 5.0, exit_: float = 70.0,
                  ma_len: int = 200) -> pd.Series:
    """Long-only state machine: enter when RSI(2)<entry AND close>MA200; exit when
    RSI(2)>exit_. Decided at close[i] (causal)."""
    r = rsi(close, 2)
    ma = close.rolling(ma_len).mean()
    pos = np.zeros(len(close), dtype=float)
    holding = False
    for i in range(len(close)):
        ma_i = ma.iloc[i]
        if not holding:
            if r.iloc[i] < entry and not np.isnan(ma_i) and close.iloc[i] > ma_i:
                holding = True
        elif r.iloc[i] > exit_:
            holding = False
        pos[i] = 1.0 if holding else 0.0
    return pd.Series(pos, index=close.index)


def main() -> None:
    px = load_daily_prices(INDEX_EPICS)  # close only, wide [date x epic]
    pos = pd.DataFrame({
        e: rsi2_position(px[e].dropna()).reindex(px.index).fillna(0.0)
        for e in px.columns
    })
    w = normalize_book(pos)  # equal-weight among active signals each day
    res = DailyBacktester(px).run(w, oos_split_date(px))
    print(res["full"].line("FULL"))
    print(res["oos"].line("OOS"))
    decay = res["full"].sharpe - res["oos"].sharpe
    dead = res["oos"].t_stat < 2.0 or res["oos"].sharpe <= 0
    print(f"decay(full-oos Sharpe) = {decay:.2f}")
    print("VERDICT:", "DEAD/decayed — drop." if dead else "SURVIVES -> forward lab.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/ab/test_screens.py -k rsi -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the screen (manual observation)**

Run: `.venv/Scripts/python.exe scripts/ab/test_rsi2.py`
Expected: FULL + OOS metric lines, decay number, VERDICT.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/ab/test_rsi2.py backend/tests/ab/test_screens.py
git commit -m "test(ab): H1 RSI-2 dip-buy screen (leak-safe, OOS decay check)"
```

---

## Self-Review

- **Spec coverage (spec §9):** H5 = Task 1 (overnight_net from daily OHLC − OVERNIGHT_RATES via `swap_abs`); H1 = Task 2 (RSI-2 + MA200 → `DailyBacktester` OOS). Both covered. Kill criteria (`t<2` / `sharpe≤0` / CI⊇0) present.
- **Placeholder scan:** none — all code complete, no TODO/TBD.
- **Type consistency:** `overnight_net`, `rsi`, `rsi2_position` signatures match between test and script; harness symbols (`swap_abs`, `metrics`, `block_boot_ci`, `line`, `load_daily_prices`, `normalize_book`, `oos_split_date`, `DailyBacktester`, `Metrics.line`) match the read source.

**Survivors graduate into the forward lab (other plan) alongside H2/H3/H4.**
