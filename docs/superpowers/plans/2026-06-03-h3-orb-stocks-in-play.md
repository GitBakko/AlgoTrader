# H3 ORB (stocks-in-play) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Opening-Range-Breakout (ORB) "stocks-in-play" forward hypothesis (H3) to the Forward Demo Lab, co-running with the live H2 gap-fade on the experiment account.

**Architecture:** New `ORBStrategy` under the existing `ForwardStrategy` ABC. A real-exchange-volume relative-volume screen (`RvolScreener`, via yfinance) picks the day's in-play names; the opening range + breakout detection + order execution use Capital.com. The scheduler is generalized from one strategy to a **list**, a unified `entry_pass` (5-min poll over a session window) drives entries for all strategies, `mark_pass` dispatches the right `exit_rule` per owning strategy, and realized P&L is matched by **dealId** (closes a latent epic-match misattribution bug that co-running would otherwise hit).

**Tech Stack:** Python 3.12, pytest + pytest-asyncio, pandas, yfinance, APScheduler, Capital.com REST client. Run via `backend/.venv/Scripts/python.exe`. All new code under `backend/scripts/ab/forward/`; tests under `backend/tests/forward/`.

**Spec:** `docs/superpowers/specs/2026-06-03-h3-orb-stocks-in-play-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/scripts/ab/forward/strategy.py` | `MarketContext` (+ OR/rvol fields), `ForwardStrategy` ABC (+ `needs_opening_range`), `ORBStrategy` | Modify |
| `backend/scripts/ab/forward/screener.py` | `RvolScreener` — yfinance RVOL + eligible top-K | Create |
| `backend/scripts/ab/forward/executor.py` | Size on `current_price` (correct for ORB; identical for H2 at open) | Modify |
| `backend/scripts/ab/forward/scheduler.py` | `SessionState`, `strategies` list, `entry_pass`, `_opening_range`, multi-strategy `mark_pass`, `_realized` by dealId | Modify |
| `backend/scripts/ab/forward_lab.py` | Wire `[GapFadeStrategy, ORBStrategy]`, ORB universe/params, `entry_pass` job, status/score for both | Modify |
| `backend/src/utils/config.py` | `forward_lab_orb_*` settings | Modify |
| `backend/tests/forward/test_orb_strategy.py` | ORB strategy unit tests | Create |
| `backend/tests/forward/test_screener.py` | RvolScreener unit tests | Create |
| `backend/tests/forward/test_session_state.py` | SessionState + `_opening_range` tests | Create |
| `backend/tests/forward/test_realized_dealid.py` | dealId-match `_realized` tests | Create |
| `backend/tests/forward/test_scheduler.py` | Update existing 3 tests to the `strategies` list API + add multi-strategy `mark_pass` test | Modify |

**Conventions (all test files start with this — copy verbatim):**
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
```
Run all forward tests: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/ -v`

---

## Task 1: MarketContext — opening-range + rvol fields

**Files:**
- Modify: `backend/scripts/ab/forward/strategy.py:10-22`
- Test: `backend/tests/forward/test_orb_strategy.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/forward/test_orb_strategy.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

from datetime import datetime, timezone


def test_market_context_has_orb_fields_defaulting_none():
    from forward.strategy import MarketContext
    now = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    sc = datetime(2026, 6, 3, 20, 45, tzinfo=timezone.utc)
    ctx = MarketContext("AAPL", 100.0, 101.0, 101.5, now, sc)
    assert ctx.or_high is None and ctx.or_low is None and ctx.rvol is None
    ctx2 = MarketContext("AAPL", 100.0, 101.0, 101.5, now, sc,
                         atr=1.0, or_high=102.0, or_low=100.5, rvol=2.3)
    assert ctx2.or_high == 102.0 and ctx2.or_low == 100.5 and ctx2.rvol == 2.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_orb_strategy.py::test_market_context_has_orb_fields_defaulting_none -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'or_high'`

- [ ] **Step 3: Add the fields**

In `strategy.py`, extend the `MarketContext` frozen dataclass (after the `atr` field):
```python
@dataclass(frozen=True)
class MarketContext:
    epic: str
    prev_close: float
    today_open: float
    current_price: float
    now: datetime
    session_close: datetime
    atr: float | None = None
    or_high: float | None = None
    or_low: float | None = None
    rvol: float | None = None

    @property
    def gap(self) -> float:
        return (self.today_open / self.prev_close - 1.0) if self.prev_close > 0 else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_orb_strategy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add backend/scripts/ab/forward/strategy.py backend/tests/forward/test_orb_strategy.py
git commit -m "feat(forward-lab): MarketContext opening-range + rvol fields"
```

---

## Task 2: ForwardStrategy ABC — needs_opening_range flag

**Files:**
- Modify: `backend/scripts/ab/forward/strategy.py:46-69`
- Test: `backend/tests/forward/test_orb_strategy.py`

- [ ] **Step 1: Write the failing test**

Append to `test_orb_strategy.py`:
```python
def test_gap_fade_does_not_need_opening_range():
    from forward.strategy import GapFadeStrategy
    assert GapFadeStrategy(epics=["AAPL"]).needs_opening_range is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_orb_strategy.py::test_gap_fade_does_not_need_opening_range -v`
Expected: FAIL — `AttributeError: 'GapFadeStrategy' object has no attribute 'needs_opening_range'`

- [ ] **Step 3: Add the class attribute to the ABC**

In `strategy.py`, add to `ForwardStrategy`:
```python
class ForwardStrategy(ABC):
    name: str = "abstract"
    needs_opening_range: bool = False

    @abstractmethod
    def universe(self) -> list[str]:
        """Epics this strategy trades."""
    ...
```
(`GapFadeStrategy` inherits `needs_opening_range = False` — no change needed there.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_orb_strategy.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**
```bash
git add backend/scripts/ab/forward/strategy.py backend/tests/forward/test_orb_strategy.py
git commit -m "feat(forward-lab): ForwardStrategy.needs_opening_range flag"
```

---

## Task 3: ORBStrategy — should_enter (breakout) + exit_rule (EOD)

**Files:**
- Modify: `backend/scripts/ab/forward/strategy.py` (append `ORBStrategy`)
- Test: `backend/tests/forward/test_orb_strategy.py`

ORB semantics: requires a frozen opening range (`or_high`/`or_low`); gates on `rvol >= rvol_min`
when rvol is provided; `current_price` strictly beyond OR (± buffer) → fade-free momentum entry
(break up → BUY, break down → SELL). SL = opposite OR side, widened to an ATR (or %-fallback)
floor so a tiny range can't produce a sub-noise stop. Exit = EOD only (SL is broker-side).

- [ ] **Step 1: Write the failing tests**

Append to `test_orb_strategy.py`:
```python
def _octx(or_hi, or_lo, cur, **kw):
    from forward.strategy import MarketContext
    now = kw.get("now", datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc))
    sc = kw.get("session_close", datetime(2026, 6, 3, 20, 45, tzinfo=timezone.utc))
    return MarketContext("AAPL", 100.0, 101.0, cur, now, sc,
                         atr=kw.get("atr"), or_high=or_hi, or_low=or_lo,
                         rvol=kw.get("rvol", 2.0))


def test_orb_break_up_goes_long_stop_below():
    from forward.strategy import ORBStrategy
    from src.broker.models import Direction
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    sig = s.should_enter(_octx(102.0, 100.0, 102.5))   # price above OR high
    assert sig is not None and sig.direction == Direction.BUY
    assert sig.stop_level < 102.5                       # stop below entry

def test_orb_break_down_goes_short_stop_above():
    from forward.strategy import ORBStrategy
    from src.broker.models import Direction
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    sig = s.should_enter(_octx(102.0, 100.0, 99.5))     # price below OR low
    assert sig is not None and sig.direction == Direction.SELL
    assert sig.stop_level > 99.5                         # stop above entry

def test_orb_inside_range_no_trade():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    assert s.should_enter(_octx(102.0, 100.0, 101.0)) is None

def test_orb_no_opening_range_no_trade():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"])
    assert s.should_enter(_octx(None, None, 105.0)) is None

def test_orb_below_rvol_threshold_no_trade():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    assert s.should_enter(_octx(102.0, 100.0, 102.5, rvol=1.0)) is None

def test_orb_buffer_blocks_marginal_break():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5, breakout_buffer=0.01)  # need +1% beyond
    assert s.should_enter(_octx(102.0, 100.0, 102.5)) is None            # +0.49% < 1%
    assert s.should_enter(_octx(102.0, 100.0, 103.1)) is not None        # +1.08% > 1%

def test_orb_atr_floor_widens_tight_range_stop():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5, stop_atr_mult=1.0)
    # tight range (or_low 102.4 vs price 102.5) but atr=2.0 -> stop floored to 100.5
    sig = s.should_enter(_octx(102.45, 102.4, 102.5, atr=2.0))
    assert sig.stop_level == 100.5                       # min(or_low, price - atr) = 102.5-2.0

def test_orb_exit_eod_only():
    from forward.strategy import ORBStrategy, OpenPosition
    from src.broker.models import Direction
    s = ORBStrategy(epics=["AAPL"])
    pos = OpenPosition("AAPL", Direction.BUY, 102.5, 1.0, 100.0, 0.0, 102.5,
                       datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc), "D1")
    early = _octx(102.0, 100.0, 110.0, now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc))
    late = _octx(102.0, 100.0, 110.0, now=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc))
    assert s.exit_rule(pos, early) is False              # mid-session: hold (SL is broker-side)
    assert s.exit_rule(pos, late) is True                # past session_close: flatten
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_orb_strategy.py -v`
Expected: FAIL — `ImportError: cannot import name 'ORBStrategy'`

- [ ] **Step 3: Implement ORBStrategy**

Append to `strategy.py`:
```python
@dataclass
class ORBStrategy(ForwardStrategy):
    epics: list[str]
    rvol_min: float = 1.5
    breakout_buffer: float = 0.0          # fraction beyond OR required (0 = touch)
    stop_atr_mult: float = 1.0
    stop_pct_fallback: float = 0.015      # used when atr is absent
    name: str = field(default="orb")
    needs_opening_range: bool = field(default=True)

    def universe(self) -> list[str]:
        return list(self.epics)

    def _stop_floor(self, ctx: MarketContext) -> float:
        if ctx.atr and ctx.atr > 0:
            return ctx.atr * self.stop_atr_mult
        return ctx.current_price * self.stop_pct_fallback

    def should_enter(self, ctx: MarketContext) -> Signal | None:
        if ctx.or_high is None or ctx.or_low is None:
            return None
        if ctx.rvol is not None and ctx.rvol < self.rvol_min:
            return None
        floor = self._stop_floor(ctx)
        up = ctx.or_high * (1.0 + self.breakout_buffer)
        dn = ctx.or_low * (1.0 - self.breakout_buffer)
        if ctx.current_price > up:                                   # break up -> long
            sl = min(ctx.or_low, ctx.current_price - floor)          # stop below, >= floor away
            return Signal(ctx.epic, Direction.BUY, sl,
                          f"ORB long {ctx.current_price:.2f}>{ctx.or_high:.2f} rvol={ctx.rvol}")
        if ctx.current_price < dn:                                   # break down -> short
            sl = max(ctx.or_high, ctx.current_price + floor)         # stop above, >= floor away
            return Signal(ctx.epic, Direction.SELL, sl,
                          f"ORB short {ctx.current_price:.2f}<{ctx.or_low:.2f} rvol={ctx.rvol}")
        return None

    def exit_rule(self, pos: OpenPosition, ctx: MarketContext) -> bool:
        return ctx.now >= ctx.session_close                          # EOD flatten; SL is broker-side
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_orb_strategy.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**
```bash
git add backend/scripts/ab/forward/strategy.py backend/tests/forward/test_orb_strategy.py
git commit -m "feat(forward-lab): ORBStrategy breakout entry + EOD exit"
```

---

## Task 4: RvolScreener — real-volume relative-volume screen (yfinance)

**Files:**
- Create: `backend/scripts/ab/forward/screener.py`
- Test: `backend/tests/forward/test_screener.py`

The screener computes, per symbol: today's early-session volume (regular-session bars in
`[13:30, 13:30+or_window_min)` UTC) ÷ trailing-`baseline_days` mean of the same early-session
volume. Eligible = the `top_k` symbols whose RVOL ≥ `rvol_min`. Network I/O (yfinance) is isolated
behind an injectable `fetch_5m(symbols, days) -> dict[str, pd.DataFrame]` so tests are deterministic.
Each per-symbol DataFrame has a tz-aware (UTC) DatetimeIndex and a `Volume` column.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/forward/test_screener.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pandas as pd
from datetime import datetime, timezone


def _frame(rows):
    """rows: list[(iso_utc, volume)] -> DataFrame[Volume] with UTC DatetimeIndex."""
    idx = pd.to_datetime([r[0] for r in rows], utc=True)
    return pd.DataFrame({"Volume": [r[1] for r in rows]}, index=idx)


def _fake_fetch(data):
    def _f(symbols, days):
        return {s: data[s] for s in symbols if s in data}
    return _f


def test_rvol_high_today_is_eligible():
    from forward.screener import RvolScreener
    # baseline days 06-01,06-02 each 100 early vol; today 06-03 has 300 -> rvol 3.0
    df = _frame([
        ("2026-06-01T13:30:00Z", 100), ("2026-06-02T13:30:00Z", 100),
        ("2026-06-03T13:30:00Z", 300),
    ])
    sc = RvolScreener(fetch_5m=_fake_fetch({"AAPL": df}), rvol_min=1.5, top_k=5,
                      or_window_min=30, baseline_days=20)
    now = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    out = sc.select(["AAPL"], now)
    assert round(out["rvol"]["AAPL"], 2) == 3.0
    assert "AAPL" in out["eligible"]


def test_rvol_below_threshold_not_eligible():
    from forward.screener import RvolScreener
    df = _frame([
        ("2026-06-01T13:30:00Z", 100), ("2026-06-02T13:30:00Z", 100),
        ("2026-06-03T13:30:00Z", 110),   # rvol 1.1 < 1.5
    ])
    sc = RvolScreener(fetch_5m=_fake_fetch({"AAPL": df}), rvol_min=1.5)
    out = sc.select(["AAPL"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert out["eligible"] == set()


def test_top_k_caps_eligible_count():
    from forward.screener import RvolScreener
    data = {}
    for i, sym in enumerate(["A", "B", "C"]):
        today = 200 + i * 100            # A=200,B=300,C=400 -> rvol 2,3,4
        data[sym] = _frame([
            ("2026-06-01T13:30:00Z", 100), ("2026-06-02T13:30:00Z", 100),
            ("2026-06-03T13:30:00Z", today),
        ])
    sc = RvolScreener(fetch_5m=_fake_fetch(data), rvol_min=1.5, top_k=2)
    out = sc.select(["A", "B", "C"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert out["eligible"] == {"C", "B"}        # top-2 by rvol


def test_only_regular_session_window_counts():
    from forward.screener import RvolScreener
    # pre-market 13:00 huge vol must be ignored; only 13:30/13:35 in [13:30,14:00) count
    df = _frame([
        ("2026-06-02T13:00:00Z", 9999),  # pre-market, ignored
        ("2026-06-02T13:30:00Z", 50), ("2026-06-02T13:35:00Z", 50),  # baseline early=100
        ("2026-06-03T13:00:00Z", 9999),  # pre-market, ignored
        ("2026-06-03T13:30:00Z", 150), ("2026-06-03T13:35:00Z", 150),  # today early=300 -> rvol 3
    ])
    sc = RvolScreener(fetch_5m=_fake_fetch({"AAPL": df}), rvol_min=1.5, or_window_min=30)
    out = sc.select(["AAPL"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert round(out["rvol"]["AAPL"], 2) == 3.0


def test_empty_or_missing_feed_skips_symbol():
    from forward.screener import RvolScreener
    sc = RvolScreener(fetch_5m=_fake_fetch({}), rvol_min=1.5)   # no data for AAPL
    out = sc.select(["AAPL"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert out["eligible"] == set() and "AAPL" not in out["rvol"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_screener.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'forward.screener'`

- [ ] **Step 3: Implement the screener**

Create `backend/scripts/ab/forward/screener.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Callable

import pandas as pd
from loguru import logger

# (symbols, days) -> {symbol: DataFrame[Volume] with tz-aware UTC DatetimeIndex}
Fetch5m = Callable[[list[str], int], dict[str, "pd.DataFrame"]]

SESSION_OPEN_UTC = time(13, 30)  # US regular cash open (summer/EDT); winter shifts to 14:30


def _default_fetch_5m(symbols: list[str], days: int) -> dict[str, pd.DataFrame]:
    """Real fetch: yfinance 5-min bars, last `days` days, per symbol, UTC index."""
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    raw = yf.download(symbols, period=f"{days}d", interval="5m",
                      progress=False, auto_adjust=False, group_by="ticker")
    for s in symbols:
        try:
            df = raw[s] if len(symbols) > 1 else raw
            if df is None or df.empty or "Volume" not in df.columns:
                continue
            df = df[["Volume"]].copy()
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            out[s] = df
        except Exception as e:  # noqa: BLE001 — degrade per-symbol, never abort the screen
            logger.warning(f"[screener] {s} fetch/parse failed: {e}")
    return out


@dataclass
class RvolScreener:
    fetch_5m: Fetch5m | None = None
    rvol_min: float = 1.5
    top_k: int = 5
    or_window_min: int = 30
    baseline_days: int = 20

    def _early_volume_by_day(self, df: pd.DataFrame) -> pd.Series:
        """Sum of Volume in [13:30, 13:30+or_window_min) UTC, grouped by calendar date."""
        t = df.index
        minutes = t.hour * 60 + t.minute
        open_min = SESSION_OPEN_UTC.hour * 60 + SESSION_OPEN_UTC.minute
        mask = (minutes >= open_min) & (minutes < open_min + self.or_window_min)
        early = df.loc[mask]
        if early.empty:
            return pd.Series(dtype="float64")
        return early.groupby(early.index.normalize())["Volume"].sum()

    def select(self, symbols: list[str], now: datetime) -> dict:
        data = (self.fetch_5m or _default_fetch_5m)(symbols, self.baseline_days)
        today = pd.Timestamp(now.astimezone(timezone.utc).date(), tz="UTC")
        rvol: dict[str, float] = {}
        for s in symbols:
            df = data.get(s)
            if df is None or df.empty:
                continue
            early = self._early_volume_by_day(df)
            if today not in early.index:
                continue
            baseline = early[early.index < today].tail(self.baseline_days)
            base = float(baseline.mean()) if len(baseline) else 0.0
            if base <= 0:
                continue
            rvol[s] = float(early[today]) / base
        ranked = sorted((s for s, v in rvol.items() if v >= self.rvol_min),
                        key=lambda s: rvol[s], reverse=True)
        return {"rvol": rvol, "eligible": set(ranked[: self.top_k])}
```

Note: remove the dead `end =` placeholder line if your linter flags it — it is not used; the
window test uses `minutes`. (Kept here only to avoid an empty-method confusion; delete it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_screener.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**
```bash
git add backend/scripts/ab/forward/screener.py backend/tests/forward/test_screener.py
git commit -m "feat(forward-lab): RvolScreener real-volume stocks-in-play screen (yfinance)"
```

---

## Task 5: Executor — size on current_price + idempotent entry guard

**Files:**
- Modify: `backend/scripts/ab/forward/ledger.py` (add `exists`)
- Modify: `backend/scripts/ab/forward/executor.py:38-48`
- Test: `backend/tests/forward/test_executor.py`, `backend/tests/forward/test_ledger.py`

Two correctness fixes the unified 5-min `entry_pass` (Task 8) requires:
1. **Size on `ctx.current_price`** — `_size_for(ctx.today_open)` is wrong for ORB (entry ≈
   breakout price, not the open). For H2 at the open pass `current_price == today_open`, unchanged.
2. **Idempotent entry guard** — `try_enter` places the broker order BEFORE `record_open`'s UNIQUE
   constraint fires, so under repeated polling H2's stable gap would re-place an order every 5 min
   then fail to record it. Guard: if a ledger row already exists for `(strategy, epic, session_date)`
   (open OR closed — one trade per strategy/epic/day by design), skip before ordering.

- [ ] **Step 1: Write the failing ledger test**

Append to `backend/tests/forward/test_ledger.py`:
```python
def test_exists_true_after_open_open_or_closed(tmp_path):
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "x.db")
    assert led.exists("orb", "AAPL", "2026-06-03") is False
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-03", deal_id="D1",
                    direction="BUY", entry=100.0, size=1.0, stop_level=98.0,
                    rationale="x", opened_at="2026-06-03T14:00:00+00:00")
    assert led.exists("orb", "AAPL", "2026-06-03") is True
    assert led.exists("orb", "AAPL", "2026-06-04") is False    # different day
    assert led.exists("gap_fade", "AAPL", "2026-06-03") is False  # different strategy
```

- [ ] **Step 2: Run it to verify failure**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_ledger.py::test_exists_true_after_open_open_or_closed -v`
Expected: FAIL — `AttributeError: 'ForwardLedger' object has no attribute 'exists'`

- [ ] **Step 3: Add `exists` to the ledger**

In `ledger.py`, add a method (after `list_open`):
```python
    def exists(self, strategy: str, epic: str, session_date: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM trades WHERE strategy=? AND epic=? AND session_date=? LIMIT 1",
                (strategy, epic, session_date)).fetchone()
            return row is not None
```

- [ ] **Step 4: Run the ledger test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_ledger.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing executor tests**

Append to `backend/tests/forward/test_executor.py`:
```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


def _orb_ctx(today_open, current):
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    from forward.strategy import MarketContext
    now = datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc)
    sc = datetime(2026, 6, 3, 20, 45, tzinfo=timezone.utc)
    return MarketContext("AAPL", 100.0, today_open, current, now, sc,
                         or_high=199.0, or_low=190.0, rvol=2.0)


def _client():
    from src.broker.models import DealConfirmation
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D9", "dealReference": "R9", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "BUY", "size": 1.0, "level": 200.0, "status": "OPEN"})
    return client


@pytest.mark.asyncio
async def test_size_uses_current_price_not_today_open(tmp_path):
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from forward.strategy import ORBStrategy

    client = _client()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "e.db"),
                            notional_usd=200.0, dry_run=False)
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    # today_open 100 (stale), current_price 200 (breakout) -> size 200/200 = 1.0, not 2.0
    await ex.try_enter(s, _orb_ctx(100.0, 200.0), "2026-06-03")
    args, kwargs = client.create_position.call_args
    assert kwargs.get("request", args[0]).size == 1.0


@pytest.mark.asyncio
async def test_try_enter_idempotent_no_double_order(tmp_path):
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from forward.strategy import ORBStrategy

    client = _client()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "i.db"),
                            notional_usd=200.0, dry_run=False)
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    await ex.try_enter(s, _orb_ctx(200.0, 200.0), "2026-06-03")   # 1st: orders + records
    await ex.try_enter(s, _orb_ctx(200.0, 200.0), "2026-06-03")   # 2nd: guard skips
    assert client.create_position.await_count == 1
    assert len(ex.ledger.list_open()) == 1
```

- [ ] **Step 6: Run them to verify failure**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_executor.py -v`
Expected: FAIL — size test: size == 2.0; idempotent test: `await_count == 2` (order placed twice)

- [ ] **Step 7: Apply both executor fixes**

In `executor.py` `try_enter`, after the `max_concurrent` check and before `should_enter`, add the
guard; and change the sizing line. The relevant region becomes:
```python
    async def try_enter(self, strat: ForwardStrategy, ctx: MarketContext,
                        session_date: str) -> Signal | object | None:
        if self._halted:
            return None
        if self.ledger.exists(strat.name, ctx.epic, session_date):
            return None                              # one trade per strategy/epic/day (idempotent)
        if len(self.ledger.list_open()) >= self.max_concurrent:
            logger.warning(f"[forward-lab] max_concurrent={self.max_concurrent} reached — skip")
            return None
        sig = strat.should_enter(ctx)
        if sig is None:
            return None
        size = self._size_for(ctx.current_price)
        ...
```
(Leave the rest of `try_enter` unchanged.)

- [ ] **Step 8: Run executor + existing forward tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_executor.py tests/forward/test_gap_fade.py tests/forward/test_scheduler.py tests/forward/test_ledger.py -v`
Expected: PASS (H2 at open has current==open; first-call enters, repeat skips)

- [ ] **Step 9: Commit**
```bash
git add backend/scripts/ab/forward/executor.py backend/scripts/ab/forward/ledger.py backend/tests/forward/test_executor.py backend/tests/forward/test_ledger.py
git commit -m "fix(forward-lab): size on current_price + idempotent entry guard (safe under 5min entry_pass)"
```

---

## Task 6: `_realized` — match broker TRADE by dealId

**Files:**
- Modify: `backend/scripts/ab/forward/scheduler.py:101-121`
- Test: `backend/tests/forward/test_realized_dealid.py`

Current `_realized` matches the first TRADE txn by epic. Co-running H2+H3 can produce two TRADE
rows on the same epic the same day → misattribution. Match by `Transaction.deal_id == row["deal_id"]`
first; only if no dealId match, fall back to `PENDING_RECONCILE` (no invented P&L). `deal_id` on a
broker-initiated SL/TP close may rotate (CLAUDE.md / `project_capital_com_dealid_mutation`), so the
fallback keeps us honest rather than guessing.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/forward/test_realized_dealid.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


def _txn(deal_id, size, epic="AAPL"):
    from src.broker.models import Transaction
    return Transaction(date=datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc),
                       reference=f"r-{deal_id}", dealId=deal_id, transactionType="TRADE",
                       instrumentName=epic, size=size, currency="USD")


@pytest.mark.asyncio
async def test_realized_picks_txn_by_dealid(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    # two TRADE rows, same epic, different dealId (H2 short vs H3 long on AAPL same day)
    client.get_transaction_history.return_value = [_txn("DH2", "3.00"), _txn("DH3", "-5.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "r.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DH3"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == -5.00 and reason == "BROKER_TRADE"


@pytest.mark.asyncio
async def test_realized_unmatched_dealid_is_pending(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DOTHER", "3.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "r2.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DMINE"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 0.0 and reason == "PENDING_RECONCILE"
```

> NOTE: these tests construct the scheduler with `strategies=[...]` (the new list API from Task 7).
> If you implement Task 6 before Task 7, temporarily use `strategy=...`; Task 7 switches the API and
> updates these two constructions. Recommended: implement Task 7 first, then Task 6. The plan keeps
> them separate for review clarity.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_realized_dealid.py -v`
Expected: FAIL — current `_realized` matches by epic, returns +3.00 for the first txn (wrong dealId)

- [ ] **Step 3: Rewrite `_realized` to match by dealId**

Replace the body of `_realized` in `scheduler.py`:
```python
    async def _realized(self, row: dict, fallback_px: float) -> tuple[float, float, str]:
        """Realized P&L from the broker TRADE transaction matching this row's dealId
        (broker truth). dealId is the deterministic match key for /history/transactions
        TRADE rows; an unmatched id (e.g. broker SL/TP rotation) stays PENDING_RECONCILE
        rather than guessing — no invented P&L."""
        from datetime import timedelta
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=2)
        txns = await self.client.get_transaction_history(from_date, to_date)
        for t in txns:
            if (t.transaction_type or "").upper() != "TRADE":
                continue
            if t.deal_id and t.deal_id == row["deal_id"]:
                pnl = t.pl_value_in("USD")
                if pnl is not None:
                    return float(pnl), fallback_px, "BROKER_TRADE"
        return 0.0, fallback_px, "PENDING_RECONCILE"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_realized_dealid.py -v`
Expected: PASS (2 tests)

> The existing `test_mark_pass_closes_and_reconciles` in `test_scheduler.py` builds a Transaction
> WITHOUT a `dealId` and expects `BROKER_TRADE`. Task 7 updates that test to add `dealId="D1"`
> (matching the ledger row's deal_id). Until then it will fail — expected; fixed in Task 7.

- [ ] **Step 5: Commit**
```bash
git add backend/scripts/ab/forward/scheduler.py backend/tests/forward/test_realized_dealid.py
git commit -m "fix(forward-lab): match realized P&L by dealId (co-run attribution)"
```

---

## Task 7: Scheduler — strategies list + multi-strategy mark_pass

**Files:**
- Modify: `backend/scripts/ab/forward/scheduler.py:19-23,68-99`
- Modify: `backend/tests/forward/test_scheduler.py` (update 3 tests to list API + dealId)
- Test: `backend/tests/forward/test_scheduler.py` (add multi-strategy mark_pass test)

Generalize the scheduler from one `strategy` to `strategies: list`. Build a `{name: strategy}`
registry. `mark_pass` looks up each open row's owning strategy via `row["strategy"]` and applies
THAT strategy's `exit_rule`.

- [ ] **Step 1: Update existing scheduler tests to the new API**

In `test_scheduler.py`:
- In `test_on_session_open_enters_on_gap`: change `strategy=GapFadeStrategy(...)` →
  `strategies=[GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01)]`.
- In `test_mark_pass_closes_and_reconciles`: change `strategy=GapFadeStrategy(epics=["AAPL"])` →
  `strategies=[GapFadeStrategy(epics=["AAPL"])]`, AND add `dealId="D1"` to the Transaction so it
  matches the ledger row's `deal_id="D1"`:
  ```python
  client.get_transaction_history.return_value = [
      Transaction(date=datetime(2026, 6, 2, 16, 0, tzinfo=timezone.utc), reference="r1",
                  dealId="D1", transactionType="TRADE", instrumentName="AAPL",
                  size="2.91", currency="USD")]
  ```
- In `test_prev_close_from_broker_last_completed`: change `strategy=GapFadeStrategy(epics=["AMD"])`
  → `strategies=[GapFadeStrategy(epics=["AMD"])]`.

- [ ] **Step 2: Add the failing multi-strategy mark_pass test**

Append to `test_scheduler.py`:
```python
@pytest.mark.asyncio
async def test_mark_pass_dispatches_exit_rule_by_owning_strategy(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy, ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Transaction

    client = AsyncMock()
    client.get_market_details.return_value = {"snapshot": {"bid": 101.0, "offer": 101.0}}
    client.list_positions.return_value = []          # both broker-closed -> realize both
    client.get_transaction_history.return_value = [
        Transaction(date=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc), reference="rg",
                    dealId="DG", transactionType="TRADE", instrumentName="AAPL",
                    size="1.50", currency="USD"),
        Transaction(date=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc), reference="ro",
                    dealId="DO", transactionType="TRADE", instrumentName="NVDA",
                    size="-2.00", currency="USD")]

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "mm.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-03",
                          deal_id="DG", direction="SELL", entry=103.0, size=1.0,
                          stop_level=105.0, rationale="x", opened_at="2026-06-03T14:00:00+00:00")
    ex.ledger.record_open(strategy="orb", epic="NVDA", session_date="2026-06-03",
                          deal_id="DO", direction="BUY", entry=500.0, size=1.0,
                          stop_level=490.0, rationale="y", opened_at="2026-06-03T14:30:00+00:00")
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"]),
                                            ORBStrategy(epics=["NVDA"])])
    # past session_close -> both exit_rules return True (EOD)
    await sched.mark_pass(now=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc))
    assert ex.ledger.realized("gap_fade")[0]["net_pnl"] == 1.50
    assert ex.ledger.realized("orb")[0]["net_pnl"] == -2.00
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_scheduler.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'strategies'`

- [ ] **Step 4: Refactor the scheduler to a strategies list**

In `scheduler.py`, change the dataclass header:
```python
@dataclass
class ExperimentScheduler:
    client: object
    executor: ExperimentExecutor
    strategies: list[ForwardStrategy]
    eod_flatten_utc: str = "20:45"

    @property
    def _registry(self) -> dict[str, ForwardStrategy]:
        return {s.name: s for s in self.strategies}
```

Update `on_session_open` to iterate strategies (keep it working for H2 until Task 8 replaces it):
```python
    async def on_session_open(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        session_date = now.date().isoformat()
        for strat in self.strategies:
            for epic in strat.universe():
                prev_close = await self._prev_close(epic, now)
                mid = await self._mid(epic)
                if prev_close is None or mid is None:
                    logger.warning(f"[forward-lab] missing price for {epic} — skip")
                    continue
                ctx = MarketContext(epic=epic, prev_close=prev_close, today_open=mid,
                                    current_price=mid, now=now,
                                    session_close=self._session_close(now))
                await self.executor.try_enter(strat, ctx, session_date)
```

Rewrite `mark_pass` to dispatch `exit_rule` by the owning strategy:
```python
    async def mark_pass(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if self.executor.dry_run:
            return
        open_rows = self.executor.ledger.list_open()
        if not open_rows:
            return
        registry = self._registry
        positions = {p.deal_id: p for p in await self.client.list_positions()}
        for row in open_rows:
            strat = registry.get(row["strategy"])
            if strat is None:
                logger.warning(f"[forward-lab] no strategy {row['strategy']!r} for open row — skip")
                continue
            mid = await self._mid(row["epic"])
            if mid is None:
                continue
            pos = OpenPosition(
                epic=row["epic"], direction=Direction(row["direction"]),
                entry=row["entry"], size=row["size"], stop_level=row["stop_level"],
                prev_close=0.0, today_open=row["entry"], opened_at=now,
                deal_id=row["deal_id"])
            ctx = MarketContext(epic=row["epic"], prev_close=0.0, today_open=row["entry"],
                                current_price=mid, now=now,
                                session_close=self._session_close(now))
            still_open = row["deal_id"] in positions
            should_exit = strat.exit_rule(pos, ctx)
            if still_open and should_exit:
                await self.client.close_position(row["deal_id"])
            if not still_open or should_exit:
                net, exitpx, reason = await self._realized(row, mid)
                self.executor.ledger.record_close(
                    deal_id=row["deal_id"], exit_price=exitpx, net_pnl=net,
                    closed_at=now.isoformat(), close_reason=reason)
                logger.info(f"[forward-lab] closed {row['epic']} ({row['strategy']}) "
                            f"net={net:+.2f} ({reason})")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_scheduler.py tests/forward/test_realized_dealid.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**
```bash
git add backend/scripts/ab/forward/scheduler.py backend/tests/forward/test_scheduler.py
git commit -m "refactor(forward-lab): scheduler holds strategies list; mark_pass dispatches exit_rule per owning strategy"
```

---

## Task 8: Scheduler — SessionState, _opening_range, entry_pass (replaces on_session_open)

**Files:**
- Modify: `backend/scripts/ab/forward/scheduler.py` (add `SessionState`, `_opening_range`, `entry_pass`, `_in_window`; inject `screener`)
- Test: `backend/tests/forward/test_session_state.py`

`entry_pass` is the unified 5-min poll. It no-ops outside Mon–Fri 13:30–16:00 UTC. On the first
in-window pass it caches each epic's open price (so H2's gap is stable). For strategies with
`needs_opening_range`, once `now >= open + or_window_min` it computes the opening range from
Capital.com MINUTE_5 bars (once/day/epic) and runs the screener (once/day) to set eligibility; only
eligible epics get an ORB ctx. `try_enter`'s ledger UNIQUE makes repeated polling idempotent.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/forward/test_session_state.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock


def test_session_state_resets_on_new_day():
    from forward.scheduler import SessionState
    st = SessionState()
    st.ensure_day(date(2026, 6, 3))
    st.open_px["AAPL"] = 100.0
    st.ensure_day(date(2026, 6, 3))           # same day -> keep
    assert st.open_px.get("AAPL") == 100.0
    st.ensure_day(date(2026, 6, 4))           # new day -> reset
    assert st.open_px == {} and st.eligible == set()


@pytest.mark.asyncio
async def test_opening_range_from_minute5_bars():
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import OHLCCandle
    import pathlib, tempfile

    def _c(ts, hi, lo):
        return OHLCCandle.model_validate(
            {"snapshotTime": ts, "openPrice": (hi + lo) / 2, "highPrice": hi,
             "lowPrice": lo, "closePrice": (hi + lo) / 2})

    client = AsyncMock()
    client.get_historical_prices.return_value = [
        _c(datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc), 101.0, 99.0),
        _c(datetime(2026, 6, 3, 13, 35, tzinfo=timezone.utc), 102.0, 100.0),
        _c(datetime(2026, 6, 3, 13, 55, tzinfo=timezone.utc), 101.5, 98.5),
    ]
    tmp = pathlib.Path(tempfile.mkdtemp()) / "o.db"
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    now = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    hi, lo = await sched._opening_range("AAPL", now)
    assert hi == 102.0 and lo == 98.5


def test_in_window_guards_weekday_and_hours():
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    import pathlib, tempfile
    from unittest.mock import AsyncMock as AM
    tmp = pathlib.Path(tempfile.mkdtemp()) / "w.db"
    ex = ExperimentExecutor(client=AM(), experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp), dry_run=True)
    sched = ExperimentScheduler(client=AM(), executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    wed = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)        # Wed in-window
    assert sched._in_window(wed) is True
    assert sched._in_window(wed.replace(hour=12)) is False        # before 13:30
    assert sched._in_window(wed.replace(hour=17)) is False        # after 16:00
    sat = datetime(2026, 6, 6, 14, 0, tzinfo=timezone.utc)        # Saturday
    assert sched._in_window(sat) is False


@pytest.mark.asyncio
async def test_entry_pass_orb_enters_only_eligible_on_breakout(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import DealConfirmation

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    # live mid 105 (breakout above OR high 102)
    client.get_market_details.return_value = {"snapshot": {"bid": 104.9, "offer": 105.1}}
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "BUY", "size": 1.9, "level": 105.0, "status": "OPEN"})

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "ep.db"), dry_run=False)

    class _Screener:
        def select(self, symbols, now):
            return {"rvol": {"AAPL": 3.0}, "eligible": {"AAPL"}}

    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"], rvol_min=1.5)],
                                screener=_Screener())
    monkeypatch.setattr(sched, "_opening_range", AsyncMock(return_value=(102.0, 100.0)))
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=101.0))
    now = datetime(2026, 6, 3, 14, 5, tzinfo=timezone.utc)   # after OR window (13:30+30)
    await sched.entry_pass(now=now)
    client.create_position.assert_awaited_once()
    assert ex.ledger.realized("orb") == [] and len(ex.ledger.list_open()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_session_state.py -v`
Expected: FAIL — `ImportError: cannot import name 'SessionState'`

- [ ] **Step 3: Implement SessionState + scheduler additions**

In `scheduler.py`, add imports at top (with the others):
```python
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone, date as _date
```

Add the `SessionState` dataclass (above `ExperimentScheduler`):
```python
@dataclass
class SessionState:
    day: _date | None = None
    prev_close: dict[str, float] = field(default_factory=dict)  # epic -> prior daily close (cached/day)
    open_px: dict[str, float] = field(default_factory=dict)
    or_levels: dict[str, tuple[float, float]] = field(default_factory=dict)  # epic -> (hi, lo)
    rvol: dict[str, float] = field(default_factory=dict)
    eligible: set[str] = field(default_factory=set)
    screened: bool = False

    def ensure_day(self, d: _date) -> None:
        if self.day != d:
            self.day = d
            self.prev_close.clear()
            self.open_px.clear()
            self.or_levels.clear()
            self.rvol.clear()
            self.eligible.clear()
            self.screened = False
```

Extend the `ExperimentScheduler` dataclass fields:
```python
@dataclass
class ExperimentScheduler:
    client: object
    executor: ExperimentExecutor
    strategies: list[ForwardStrategy]
    eod_flatten_utc: str = "20:45"
    screener: object | None = None                 # RvolScreener (optional; needed for ORB)
    session_open_utc: str = "13:30"
    or_window_min: int = 30
    watch_end_utc: str = "16:00"
    _state: SessionState = field(default_factory=SessionState, init=False, repr=False)
```

Add helper + `_opening_range` + `_in_window` + `entry_pass` methods:
```python
    def _hhmm(self, s: str) -> time:
        hh, mm = (int(x) for x in s.split(":"))
        return time(hh, mm, tzinfo=timezone.utc)

    def _in_window(self, now: datetime) -> bool:
        if now.weekday() >= 5:                       # Sat/Sun
            return False
        o, e = self._hhmm(self.session_open_utc), self._hhmm(self.watch_end_utc)
        return o <= now.timetz() <= e

    async def _opening_range(self, epic: str, now: datetime) -> tuple[float, float] | None:
        """OR high/low from Capital.com MINUTE_5 bars in [open, open+or_window_min)."""
        from src.broker.models import Resolution
        try:
            candles = await self.client.get_historical_prices(
                epic, Resolution.MINUTE_5, max_candles=20)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[forward-lab] {epic} MINUTE_5 fetch failed: {e} — skip OR")
            return None
        o = self._hhmm(self.session_open_utc)
        open_min = o.hour * 60 + o.minute
        today = now.date()
        win = [c for c in candles if c.timestamp.date() == today
               and open_min <= (c.timestamp.hour * 60 + c.timestamp.minute) < open_min + self.or_window_min]
        if not win:
            return None
        return max(c.high for c in win), min(c.low for c in win)

    async def entry_pass(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if not self._in_window(now):
            return
        self._state.ensure_day(now.date())
        session_date = now.date().isoformat()
        o = self._hhmm(self.session_open_utc)
        open_min = o.hour * 60 + o.minute
        or_ready = (now.hour * 60 + now.minute) >= (open_min + self.or_window_min)

        for strat in self.strategies:
            for epic in strat.universe():
                if epic not in self._state.prev_close:        # cache prev_close once/day/epic
                    pc = await self._prev_close(epic, now)
                    if pc is None:
                        continue
                    self._state.prev_close[epic] = pc
                prev_close = self._state.prev_close[epic]
                mid = await self._mid(epic)
                if mid is None:
                    continue
                self._state.open_px.setdefault(epic, mid)     # first in-window pass = open
                if strat.needs_opening_range:
                    if not or_ready:
                        continue
                    # screen once per day
                    if not self._state.screened and self.screener is not None:
                        pool = sorted({e for s in self.strategies
                                       if s.needs_opening_range for e in s.universe()})
                        res = self.screener.select(pool, now)
                        self._state.rvol.update(res.get("rvol", {}))
                        self._state.eligible = set(res.get("eligible", set()))
                        self._state.screened = True
                    if epic not in self._state.eligible:
                        continue
                    if epic not in self._state.or_levels:
                        orng = await self._opening_range(epic, now)
                        if orng is None:
                            continue
                        self._state.or_levels[epic] = orng
                    hi, lo = self._state.or_levels[epic]
                    ctx = MarketContext(epic=epic, prev_close=prev_close,
                                        today_open=self._state.open_px[epic], current_price=mid,
                                        now=now, session_close=self._session_close(now),
                                        or_high=hi, or_low=lo,
                                        rvol=self._state.rvol.get(epic))
                else:
                    ctx = MarketContext(epic=epic, prev_close=prev_close,
                                        today_open=self._state.open_px[epic], current_price=mid,
                                        now=now, session_close=self._session_close(now))
                await self.executor.try_enter(strat, ctx, session_date)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_session_state.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full forward suite (no regressions)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/ -v`
Expected: PASS (all forward tests)

- [ ] **Step 6: Commit**
```bash
git add backend/scripts/ab/forward/scheduler.py backend/tests/forward/test_session_state.py
git commit -m "feat(forward-lab): SessionState + unified entry_pass (OR + RVOL screen, window-guarded)"
```

---

## Task 9: Wiring — settings, ORB universe/params, forward_lab.py jobs + CLI

**Files:**
- Modify: `backend/src/utils/config.py:91-95`
- Modify: `backend/scripts/ab/forward_lab.py`
- Test: `backend/tests/forward/test_config.py`

- [ ] **Step 1: Add a failing settings test**

Append to `backend/tests/forward/test_config.py`:
```python
def test_orb_settings_defaults():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from src.utils.config import get_settings
    s = get_settings()
    assert s.forward_lab_orb_or_window_min == 30
    assert s.forward_lab_orb_rvol_min == 1.5
    assert s.forward_lab_orb_top_k == 5
    assert s.forward_lab_orb_watch_end_utc == "16:00"
```

- [ ] **Step 2: Run it to verify failure**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_config.py::test_orb_settings_defaults -v`
Expected: FAIL — `AttributeError: ... has no attribute 'forward_lab_orb_or_window_min'`

- [ ] **Step 3: Add settings**

In `config.py`, after line 95 (`forward_lab_eod_flatten_utc`):
```python
    forward_lab_orb_or_window_min: int = 30          # opening-range minutes (Yahoo delay -> 30)
    forward_lab_orb_watch_end_utc: str = "16:00"     # breakout watch cutoff (UTC)
    forward_lab_orb_rvol_min: float = 1.5            # min relative volume to be "in play"
    forward_lab_orb_top_k: int = 5                   # max in-play names per day
    forward_lab_orb_breakout_buffer: float = 0.0     # fraction beyond OR required
    forward_lab_orb_stop_atr_mult: float = 1.0       # SL ATR floor multiplier
```

- [ ] **Step 4: Run the settings test**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Wire forward_lab.py**

In `forward_lab.py`:

(a) Add the ORB universe constant after `UNIVERSE` (line 36):
```python
ORB_UNIVERSE = [
    "AAPL", "NVDA", "TSLA", "MSFT", "AMD", "AMZN", "META", "GOOGL", "NFLX", "AVGO",
    "JPM", "V", "MA", "UNH", "XOM", "JNJ", "WMT", "PG", "HD", "COST",
    "DIS", "BAC", "KO", "PEP", "CSCO", "ORCL", "CRM", "ADBE", "PFE", "INTC",
]  # liquid US large-cap CFDs; skip-graceful on any epic/data miss
```

(b) Replace `_strategy()` with a strategies-list builder:
```python
def _strategies() -> list:
    from forward.strategy import GapFadeStrategy, ORBStrategy
    s = get_settings()
    return [
        GapFadeStrategy(epics=UNIVERSE, gap_threshold=s.forward_lab_gap_threshold),
        ORBStrategy(epics=ORB_UNIVERSE, rvol_min=s.forward_lab_orb_rvol_min,
                    breakout_buffer=s.forward_lab_orb_breakout_buffer,
                    stop_atr_mult=s.forward_lab_orb_stop_atr_mult),
    ]


def _screener():
    from forward.screener import RvolScreener
    s = get_settings()
    return RvolScreener(rvol_min=s.forward_lab_orb_rvol_min, top_k=s.forward_lab_orb_top_k,
                        or_window_min=s.forward_lab_orb_or_window_min)


def _build_scheduler(client, executor):
    s = get_settings()
    return ExperimentScheduler(
        client=client, executor=executor, strategies=_strategies(),
        eod_flatten_utc=s.forward_lab_eod_flatten_utc, screener=_screener(),
        or_window_min=s.forward_lab_orb_or_window_min,
        watch_end_utc=s.forward_lab_orb_watch_end_utc)
```

(c) Update the import line (top) to include ORBStrategy:
```python
from forward.strategy import GapFadeStrategy, ORBStrategy  # noqa: E402,F401
```

(d) In `cmd_dry_run`, `cmd_mark`, `cmd_live_open`: replace the inline `ExperimentScheduler(...)`
construction with `sched = _build_scheduler(client, ex)`. In `cmd_dry_run` and `cmd_live_open`
replace `await sched.on_session_open()` with `await sched.entry_pass()`.

(e) In `cmd_run`, replace the scheduler construction + jobs:
```python
    s = get_settings()
    client = await _connected_client(experiment=True)
    await client.switch_account(s.capital_experiment_account_id)
    ex = _make_executor(client, dry_run=False)
    sched = _build_scheduler(client, ex)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(sched.entry_pass, IntervalTrigger(minutes=5),
                      id="entry_pass", misfire_grace_time=120)
    scheduler.add_job(sched.mark_pass, IntervalTrigger(minutes=15), id="mark")
    scheduler.start()
    logger.success("[forward-lab] RUN loop started — entry_pass every 5min "
                   "(13:30-16:00 UTC window), mark every 15min, EOD flatten. Ctrl-C to stop.")
```
(Remove the now-unused `CronTrigger` import.)

(f) Update `cmd_status` / `cmd_score` to cover both strategies:
```python
def cmd_status() -> None:
    led = ForwardLedger(LEDGER_PATH)
    print("OPEN:", led.list_open())
    for name in ("gap_fade", "orb"):
        print(f"REALIZED[{name}]:", led.realized(name))


def cmd_score() -> None:
    led = ForwardLedger(LEDGER_PATH)
    for name in ("gap_fade", "orb"):
        print(f"[{name}]", score(led.realized(name)))
```

- [ ] **Step 6: Smoke the CLI imports + status**

Run: `cd backend && .venv/Scripts/python.exe scripts/ab/forward_lab.py status`
Expected: prints `OPEN: [...]`, `REALIZED[gap_fade]: ...`, `REALIZED[orb]: ...` (no traceback)

- [ ] **Step 7: Run any CLI/discover tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_cli_discover.py tests/forward/test_account_switch.py -v`
Expected: PASS (if these reference `_strategy`, update them to `_strategies`/`_build_scheduler`)

- [ ] **Step 8: Commit**
```bash
git add backend/src/utils/config.py backend/scripts/ab/forward_lab.py backend/tests/forward/test_config.py
git commit -m "feat(forward-lab): wire ORB strategy + entry_pass job + dual-strategy status/score"
```

---

## Task 10: Integration — dry-run ORB + yfinance live smoke

**Files:**
- Test: `backend/tests/forward/test_screener_live.py` (new, network-marked)

- [ ] **Step 1: Dry-run an ORB entry_pass (manual integration)**

Temporarily set the experiment client to dry-run by running the existing `dry-run` command, which
logs intended orders without sending. Confirm it runs without error during market hours OR mock-free
just confirm no traceback off-hours (it will log "missing price"/skip):

Run: `cd backend && .venv/Scripts/python.exe scripts/ab/forward_lab.py dry-run`
Expected: no traceback; logs intended gap-fade and/or ORB orders, or skip/missing-price warnings.

- [ ] **Step 2: Write a network-marked yfinance smoke test**

Create `backend/tests/forward/test_screener_live.py`:
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone


@pytest.mark.network
def test_yfinance_default_fetch_returns_real_volume():
    from forward.screener import _default_fetch_5m
    out = _default_fetch_5m(["AAPL", "MSFT"], 5)
    assert "AAPL" in out and not out["AAPL"].empty
    assert "Volume" in out["AAPL"].columns
    # real exchange volume is large (>1000/bar typical), not CFD tick-count
    assert out["AAPL"]["Volume"].max() > 1000
```

- [ ] **Step 3: Run the smoke test (network)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_screener_live.py -v -m network`
Expected: PASS (real Yahoo data; skip if offline)

- [ ] **Step 4: Commit**
```bash
git add backend/tests/forward/test_screener_live.py
git commit -m "test(forward-lab): yfinance real-volume live smoke (network-marked)"
```

---

## Task 11: Regression + deploy (restart live loop)

**Files:** none (ops)

- [ ] **Step 1: Run the full forward suite + the broker model tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/ tests/broker/ -v`
Expected: PASS. (Full single-process repo-wide pytest on Windows floods with pre-existing unrelated
setup/teardown errors — run by subset, per the lab's known note.)

- [ ] **Step 2: ruff + black on changed files**

Run: `cd backend && .venv/Scripts/python.exe -m ruff check scripts/ab/forward scripts/ab/forward_lab.py && .venv/Scripts/python.exe -m black --check scripts/ab/forward scripts/ab/forward_lab.py`
Expected: clean (fix + re-run if not).

- [ ] **Step 3: Stop the old live loop**

Find and stop the detached H2 loop (it runs old code):
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'forward_lab' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

- [ ] **Step 4: Relaunch the loop detached (new code, both strategies)**

```powershell
cd D:\Develop\AI\_ClaudeCode\AlgoTrader\backend
$out = "data\forward_lab\run.log"; $err = "data\forward_lab\run.err.log"
Start-Process -FilePath ".venv\Scripts\python.exe" `
  -ArgumentList "scripts\ab\forward_lab.py","run" `
  -WorkingDirectory (Get-Location) -RedirectStandardOutput $out -RedirectStandardError $err `
  -WindowStyle Hidden
```

- [ ] **Step 5: Confirm both strategies registered**

Run (wait ~10s first): `cd backend && Get-Content data\forward_lab\run.err.log -Tail 15`
Expected: `RUN loop started — entry_pass every 5min (13:30-16:00 UTC window) ...` + account switch
to the experiment account, no traceback.

- [ ] **Step 6: Final commit (branch state)**
```bash
git add -A && git commit -m "chore(forward-lab): H3 ORB live deploy — entry_pass loop restarted with [gap_fade, orb]" --allow-empty
```

---

## Done criteria

- All `tests/forward/` pass (subset run).
- `forward_lab.py status` shows `REALIZED[gap_fade]` and `REALIZED[orb]`.
- Live loop restarted; `run.err.log` shows `entry_pass` registered + experiment-account switch.
- Co-run safe: realized P&L matched by dealId; H2 + ORB attribute to their own ledger rows.
- Merge `feature/forward-demo-lab` → `main` when the user is ready (separate decision).
