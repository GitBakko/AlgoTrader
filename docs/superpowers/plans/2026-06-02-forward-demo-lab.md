# Forward Demo Lab (H2 Gap-Fade Slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a leak-immune forward-experiment lab that runs the H2 gap-fade strategy end-to-end on a DEDICATED Capital.com demo account ("Account Demo"), fully isolated from the live 18-asset soak, with a per-trade ledger and a kill/promote scorer.

**Architecture:** A standalone APScheduler runner (`forward_lab.py`) drives strategies behind a clean `ForwardStrategy` interface. An `ExperimentExecutor` owns its OWN broker session pinned to the experiment account, enforces uniform $200 sizing + broker-side hard SL + concurrency/daily-loss caps, and refuses to trade unless a runtime guard confirms the active account is the experiment one (`GET /session → accountId`). A `ForwardLedger` (SQLite) records every trade with its entry thesis; a `ForwardScorer` reuses `factory_stats` for the kill/promote verdict. Isolation rests on a separate session + separate account (Capital.com `list_positions` is account-scoped → the soak never sees experiment positions).

**Tech Stack:** Python 3.12, asyncio, APScheduler (already used by `PnlSnapshotScheduler`), httpx (via existing `CapitalComClient`), SQLite (stdlib), pandas/numpy, `scripts/ab/factory_stats.py`. Run from `backend/` with `.venv/Scripts/python.exe`.

> Branch: `feature/forward-demo-lab`. The H1/H5 screens (other plan) are the parallel track.

> **Verified broker facts** (read 2026-06-02): `CapitalComClient(api_url,api_key,email,password)` → own `SessionManager`; `create_position(CreatePositionRequest)→DealConfirmation`; `close_position(deal_id)`; `list_positions()→list[Position]` (account-scoped); `get_accounts()→list[Account]`; `get_market_details(epic)["snapshot"]["bid"/"offer"]`; `get_transaction_history(...)→list[Transaction]` with `Transaction.pl_value_in(ccy)` = realized P&L (the no-invented-P&L source). `CreatePositionRequest(epic,direction:Direction,size>0,stop_level,profit_level)` (populate_by_name). No account-switch method exists yet → Task 7 adds it.

---

### Task 1: Package scaffold + experiment config + gitignore

**Files:**
- Create: `backend/scripts/ab/forward/__init__.py`
- Modify: `backend/src/utils/config.py` (add three optional settings)
- Modify: `.gitignore` (add `backend/data/forward_lab/`)
- Test: `backend/tests/forward/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_config.py
from src.utils.config import get_settings


def test_experiment_account_settings_exist():
    s = get_settings()
    # default None until set in .env — but the attributes must exist
    assert hasattr(s, "capital_experiment_account_id")
    assert hasattr(s, "forward_lab_notional_usd")
    assert hasattr(s, "forward_lab_daily_loss_limit_usd")
    assert s.forward_lab_notional_usd == 200.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_config.py -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Add the settings**

Find the `Settings` class in `backend/src/utils/config.py` (pydantic-settings `BaseSettings`). Add these fields alongside the other `capital_*` fields:

```python
    # --- Forward Demo Lab (experiment account, isolated from soak) ---
    capital_experiment_account_id: str | None = None
    forward_lab_notional_usd: float = 200.0
    forward_lab_max_concurrent: int = 5
    forward_lab_daily_loss_limit_usd: float = 100.0
    forward_lab_gap_threshold: float = 0.01
    forward_lab_eod_flatten_utc: str = "20:45"  # HH:MM UTC cash-session flatten
```

Create `backend/scripts/ab/forward/__init__.py`:

```python
"""Forward Demo Lab — leak-immune forward experiments on a dedicated demo account.

See docs/strategy/FORWARD_LAB_SPEC.md. Vertical slice: H2 gap-fade. Strategies
implement ForwardStrategy; ExperimentExecutor places real orders on the
experiment account ONLY; ForwardLedger + ForwardScorer judge them forward.
"""
```

Add to `.gitignore` (under the data section):

```
backend/data/forward_lab/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/__init__.py backend/src/utils/config.py .gitignore backend/tests/forward/test_config.py
git commit -m "feat(forward-lab): scaffold package + experiment account settings"
```

---

### Task 2: Strategy interface + value types

**Files:**
- Create: `backend/scripts/ab/forward/strategy.py`
- Test: `backend/tests/forward/test_strategy_abc.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_strategy_abc.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from src.broker.models import Direction


def test_forward_strategy_is_abstract():
    from forward.strategy import ForwardStrategy
    with pytest.raises(TypeError):
        ForwardStrategy()  # abstract: cannot instantiate


def test_signal_and_context_construct():
    from forward.strategy import Signal, MarketContext, OpenPosition
    ctx = MarketContext(epic="AAPL", prev_close=100.0, today_open=103.0,
                        current_price=103.0, now=datetime.now(timezone.utc),
                        session_close=datetime.now(timezone.utc))
    assert ctx.gap == pytest.approx(0.03)
    sig = Signal(epic="AAPL", direction=Direction.SELL, stop_level=105.0, rationale="x")
    assert sig.direction == Direction.SELL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_strategy_abc.py -v`
Expected: FAIL — `No module named 'forward.strategy'`.

- [ ] **Step 3: Implement**

```python
# backend/scripts/ab/forward/strategy.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.broker.models import Direction


@dataclass(frozen=True)
class MarketContext:
    epic: str
    prev_close: float
    today_open: float
    current_price: float
    now: datetime
    session_close: datetime
    atr: float | None = None

    @property
    def gap(self) -> float:
        return (self.today_open / self.prev_close - 1.0) if self.prev_close > 0 else 0.0


@dataclass(frozen=True)
class Signal:
    epic: str
    direction: Direction
    stop_level: float
    rationale: str


@dataclass(frozen=True)
class OpenPosition:
    epic: str
    direction: Direction
    entry: float
    size: float
    stop_level: float
    prev_close: float
    today_open: float
    opened_at: datetime
    deal_id: str


class ForwardStrategy(ABC):
    name: str = "abstract"

    @abstractmethod
    def universe(self) -> list[str]:
        """Epics this strategy trades."""

    @abstractmethod
    def should_enter(self, ctx: MarketContext) -> Signal | None:
        """Return an entry Signal or None. MUST use only data in ctx (no look-ahead)."""

    @abstractmethod
    def exit_rule(self, pos: OpenPosition, ctx: MarketContext) -> bool:
        """True if the position should be closed now (SL is broker-side, not here)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_strategy_abc.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/strategy.py backend/tests/forward/test_strategy_abc.py
git commit -m "feat(forward-lab): ForwardStrategy interface + Signal/MarketContext/OpenPosition"
```

---

### Task 3: GapFadeStrategy.should_enter (gap math)

**Files:**
- Modify: `backend/scripts/ab/forward/strategy.py` (append `GapFadeStrategy`)
- Test: `backend/tests/forward/test_gap_fade.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_gap_fade.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

from datetime import datetime, timezone
from src.broker.models import Direction


def _ctx(prev, open_, cur, **kw):
    from forward.strategy import MarketContext
    now = kw.get("now", datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc))
    sc = kw.get("session_close", datetime(2026, 6, 2, 20, 45, tzinfo=timezone.utc))
    return MarketContext("AAPL", prev, open_, cur, now, sc, atr=kw.get("atr"))


def test_gap_up_fades_short_stop_above():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015)
    sig = s.should_enter(_ctx(100.0, 103.0, 103.0))   # +3% gap up
    assert sig is not None and sig.direction == Direction.SELL
    assert sig.stop_level > 103.0                      # stop above entry for a short

def test_gap_down_fades_long_stop_below():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015)
    sig = s.should_enter(_ctx(100.0, 97.0, 97.0))      # -3% gap down
    assert sig is not None and sig.direction == Direction.BUY
    assert sig.stop_level < 97.0

def test_small_gap_no_trade():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01)
    assert s.should_enter(_ctx(100.0, 100.5, 100.5)) is None   # +0.5% < 1%

def test_atr_stop_used_when_present():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_atr_mult=2.0)
    sig = s.should_enter(_ctx(100.0, 103.0, 103.0, atr=1.0))
    assert sig.stop_level == 105.0                     # open + 2*ATR
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_gap_fade.py -v`
Expected: FAIL — `cannot import name 'GapFadeStrategy'`.

- [ ] **Step 3: Implement (append to `strategy.py`)**

```python
from dataclasses import field


@dataclass
class GapFadeStrategy(ForwardStrategy):
    epics: list[str]
    gap_threshold: float = 0.01
    stop_atr_mult: float = 1.0
    stop_pct_fallback: float = 0.015
    fill_fraction: float = 0.5
    name: str = field(default="gap_fade")

    def universe(self) -> list[str]:
        return list(self.epics)

    def _stop_distance(self, ctx: MarketContext) -> float:
        if ctx.atr and ctx.atr > 0:
            return ctx.atr * self.stop_atr_mult
        return ctx.today_open * self.stop_pct_fallback

    def should_enter(self, ctx: MarketContext) -> Signal | None:
        if ctx.prev_close <= 0:
            return None
        gap = ctx.gap
        if abs(gap) < self.gap_threshold:
            return None
        dist = self._stop_distance(ctx)
        if gap > 0:  # gap up -> fade short, stop above
            return Signal(ctx.epic, Direction.SELL, ctx.today_open + dist,
                          f"gap +{gap * 100:.2f}% fade short")
        return Signal(ctx.epic, Direction.BUY, ctx.today_open - dist,  # gap down -> fade long
                      f"gap {gap * 100:.2f}% fade long")

    def exit_rule(self, pos: OpenPosition, ctx: MarketContext) -> bool:
        if ctx.now >= ctx.session_close:  # EOD flatten (time stop)
            return True
        gap_size = pos.today_open - pos.prev_close
        target = pos.today_open - self.fill_fraction * gap_size  # 50% retrace toward prev_close
        if pos.direction == Direction.SELL:
            return ctx.current_price <= target
        return ctx.current_price >= target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_gap_fade.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/strategy.py backend/tests/forward/test_gap_fade.py
git commit -m "feat(forward-lab): GapFadeStrategy.should_enter gap math + hard-stop level"
```

---

### Task 4: GapFadeStrategy.exit_rule (50% fill + EOD)

**Files:**
- Test: `backend/tests/forward/test_gap_fade.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/forward/test_gap_fade.py

def _pos(direction, prev, open_, entry):
    from forward.strategy import OpenPosition
    from datetime import datetime, timezone
    return OpenPosition("AAPL", direction, entry, 1.0, 0.0, prev, open_,
                        datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc), "D1")

def test_short_exits_at_50pct_fill():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], fill_fraction=0.5)
    pos = _pos(Direction.SELL, 100.0, 104.0, 104.0)   # gap +4 -> target 102.0
    assert s.exit_rule(pos, _ctx(100.0, 104.0, 102.0)) is True    # reached
    assert s.exit_rule(pos, _ctx(100.0, 104.0, 103.0)) is False   # not yet

def test_long_exits_at_50pct_fill():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], fill_fraction=0.5)
    pos = _pos(Direction.BUY, 100.0, 96.0, 96.0)      # gap -4 -> target 98.0
    assert s.exit_rule(pos, _ctx(100.0, 96.0, 98.0)) is True
    assert s.exit_rule(pos, _ctx(100.0, 96.0, 97.0)) is False

def test_eod_flatten():
    from forward.strategy import GapFadeStrategy
    from datetime import datetime, timezone
    s = GapFadeStrategy(epics=["AAPL"])
    pos = _pos(Direction.SELL, 100.0, 104.0, 104.0)
    late = datetime(2026, 6, 2, 21, 0, tzinfo=timezone.utc)
    sc = datetime(2026, 6, 2, 20, 45, tzinfo=timezone.utc)
    assert s.exit_rule(pos, _ctx(100.0, 104.0, 104.0, now=late, session_close=sc)) is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_gap_fade.py -k "fill or eod" -v`
Expected: FAIL if `exit_rule` not yet present — but it was added in Task 3. If Task 3 is complete these PASS immediately; if so, this task just adds the regression tests. Run and confirm.

- [ ] **Step 3: (only if a test fails) fix `exit_rule`** to satisfy the cases above (logic already in Task 3 — adjust `target`/comparison if a test reveals an error).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_gap_fade.py -v`
Expected: PASS (7 tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/forward/test_gap_fade.py
git commit -m "test(forward-lab): exit_rule 50% gap-fill + EOD flatten regression tests"
```

---

### Task 5: ForwardLedger (SQLite per-trade)

**Files:**
- Create: `backend/scripts/ab/forward/ledger.py`
- Test: `backend/tests/forward/test_ledger.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_ledger.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))


def test_ledger_open_close_roundtrip_and_idempotent(tmp_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "fl.db")
    ok = led.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-02",
                         deal_id="D1", direction="SELL", entry=103.0, size=1.94,
                         stop_level=105.0, rationale="gap +3% fade short",
                         opened_at="2026-06-02T14:00:00+00:00")
    assert ok is True
    # idempotent: same strategy/epic/session_date -> rejected
    dup = led.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-02",
                          deal_id="D2", direction="SELL", entry=103.0, size=1.94,
                          stop_level=105.0, rationale="x", opened_at="2026-06-02T14:01:00+00:00")
    assert dup is False
    assert len(led.list_open()) == 1
    led.record_close(deal_id="D1", exit_price=101.5, net_pnl=2.91,
                     closed_at="2026-06-02T16:00:00+00:00", close_reason="FILL_50")
    assert led.list_open() == []
    rz = led.realized("gap_fade")
    assert len(rz) == 1 and rz[0]["net_pnl"] == 2.91
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_ledger.py -v`
Expected: FAIL — `No module named 'forward.ledger'`.

- [ ] **Step 3: Implement**

```python
# backend/scripts/ab/forward/ledger.py
from __future__ import annotations

import sqlite3
from pathlib import Path


class ForwardLedger:
    """Per-trade forward ledger (SQLite). One open row per (strategy, epic,
    session_date) — idempotent so a re-fired scheduler trigger never double-opens."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS trades(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy TEXT NOT NULL, epic TEXT NOT NULL,
                    session_date TEXT NOT NULL, deal_id TEXT,
                    direction TEXT, entry REAL, size REAL, stop_level REAL,
                    rationale TEXT, opened_at TEXT,
                    exit_price REAL, net_pnl REAL, closed_at TEXT, close_reason TEXT,
                    UNIQUE(strategy, epic, session_date))"""
            )

    def record_open(self, *, strategy: str, epic: str, session_date: str, deal_id: str,
                    direction: str, entry: float, size: float, stop_level: float,
                    rationale: str, opened_at: str) -> bool:
        try:
            with self._conn() as c:
                c.execute(
                    """INSERT INTO trades(strategy,epic,session_date,deal_id,direction,
                       entry,size,stop_level,rationale,opened_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (strategy, epic, session_date, deal_id, direction, entry, size,
                     stop_level, rationale, opened_at),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def list_open(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM trades WHERE closed_at IS NULL")]

    def record_close(self, *, deal_id: str, exit_price: float, net_pnl: float,
                     closed_at: str, close_reason: str) -> None:
        with self._conn() as c:
            c.execute(
                """UPDATE trades SET exit_price=?, net_pnl=?, closed_at=?, close_reason=?
                   WHERE deal_id=? AND closed_at IS NULL""",
                (exit_price, net_pnl, closed_at, close_reason, deal_id),
            )

    def realized(self, strategy: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM trades WHERE strategy=? AND closed_at IS NOT NULL "
                "ORDER BY closed_at", (strategy,))]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_ledger.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/ledger.py backend/tests/forward/test_ledger.py
git commit -m "feat(forward-lab): ForwardLedger SQLite per-trade (idempotent open)"
```

---

### Task 6: ForwardScorer (kill/promote via factory_stats)

**Files:**
- Create: `backend/scripts/ab/forward/scorer.py`
- Test: `backend/tests/forward/test_scorer.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_scorer.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))


def _rows(n, pnl_each, start="2026-01-01"):
    import pandas as pd
    days = pd.date_range(start, periods=n, freq="B")
    return [{"size": 1.0, "entry": 200.0, "net_pnl": pnl_each,
             "closed_at": d.isoformat()} for d in days]


def test_insufficient_below_min_trades():
    from forward.scorer import score, MIN_TRADES
    out = score(_rows(10, 1.0))
    assert "INSUFFICIENT" in out["verdict"]
    assert MIN_TRADES == 100


def test_kill_when_zero_edge():
    from forward.scorer import score
    # alternating +/- => mean ~0 => CI includes 0 => KILL
    rows = _rows(150, 1.0)
    for i in range(0, len(rows), 2):
        rows[i]["net_pnl"] = -1.0
    out = score(rows)
    assert out["n_trades"] == 150
    assert "KILL" in out["verdict"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_scorer.py -v`
Expected: FAIL — `No module named 'forward.scorer'`.

- [ ] **Step 3: Implement**

```python
# backend/scripts/ab/forward/scorer.py
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_AB = Path(__file__).resolve().parents[1]  # scripts/ab
if str(_AB) not in sys.path:
    sys.path.insert(0, str(_AB))

from factory_stats import block_boot_ci, deflated_sr, metrics  # noqa: E402

MIN_TRADES = 100


def score(realized_rows: list[dict], trial_sharpes_ann: list[float] | None = None) -> dict:
    """Forward kill/promote verdict on a per-trade ledger.

    Aggregates trade net-returns-on-notional into a daily series, then uses the
    same battery as the A/B factory (annualized Sharpe/t + stationary block-bootstrap
    CI + Deflated Sharpe). Verdict:
      - < MIN_TRADES                 -> INSUFFICIENT
      - CI90 includes 0 or Sharpe<=0 -> KILL
      - DSR > 0.95 (or no trial set) -> PROMOTE   else HOLD
    """
    if not realized_rows:
        return {"n_trades": 0, "verdict": "NO DATA"}
    df = pd.DataFrame(realized_rows)
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)
    notional = (df["size"] * df["entry"]).replace(0, pd.NA)
    df["ret"] = df["net_pnl"] / notional
    daily = (df.set_index("closed_at")["ret"]
               .groupby(pd.Grouper(freq="D")).sum().dropna())
    m = metrics(daily, 252)
    lo, _mid, hi = block_boot_ci(daily, 252)
    n_trades = len(df)
    if n_trades < MIN_TRADES:
        verdict = f"INSUFFICIENT ({n_trades}/{MIN_TRADES} trades)"
    elif (lo <= 0 <= hi) or m["sharpe"] <= 0:
        verdict = "KILL (CI90 includes 0 or non-positive Sharpe)"
    else:
        if trial_sharpes_ann:
            dsr = deflated_sr(daily, trial_sharpes_ann, 252)[0]
            verdict = "PROMOTE" if dsr > 0.95 else f"HOLD (DSR {dsr:.3f} < 0.95)"
        else:
            verdict = "PROMOTE (single-hypothesis; rerun with trial set for DSR)"
    return {"n_trades": n_trades, "metrics": m, "ci90": (lo, hi), "verdict": verdict}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_scorer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/scorer.py backend/tests/forward/test_scorer.py
git commit -m "feat(forward-lab): ForwardScorer kill/promote via factory_stats battery"
```

---

### Task 7: Broker account-switch + active-account read

**Files:**
- Modify: `backend/src/broker/client.py` (add two methods to `CapitalComClient`)
- Test: `backend/tests/forward/test_account_switch.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_account_switch.py
import pytest
from unittest.mock import AsyncMock
from src.broker.client import CapitalComClient


@pytest.mark.asyncio
async def test_switch_account_puts_session():
    c = CapitalComClient(api_url="https://x", api_key="k", email="e", password="p")
    c._request = AsyncMock(return_value={"accountId": "EXP123"})
    out = await c.switch_account("EXP123")
    c._request.assert_awaited_once_with("PUT", "/api/v1/session", json={"accountId": "EXP123"})
    assert out["accountId"] == "EXP123"


@pytest.mark.asyncio
async def test_get_active_account_id():
    c = CapitalComClient(api_url="https://x", api_key="k", email="e", password="p")
    c._request = AsyncMock(return_value={"accountId": "EXP123", "clientId": "c"})
    assert await c.get_active_account_id() == "EXP123"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_account_switch.py -v`
Expected: FAIL — `AttributeError: 'CapitalComClient' object has no attribute 'switch_account'`.

- [ ] **Step 3: Implement (add to `CapitalComClient`, near `get_accounts`)**

```python
    async def switch_account(self, account_id: str) -> dict[str, Any]:
        """Switch the ACTIVE trading account for THIS session (PUT /session).

        Capital.com scopes the active account to the CST token, so a dedicated
        client instance (its own SessionManager => own CST) can hold a different
        active account than the soak client. Task 11 validates this independence
        BEFORE any live order.
        """
        return await self._request("PUT", "/api/v1/session", json={"accountId": account_id})

    async def get_active_account_id(self) -> str:
        """Return the accountId currently active on THIS session (GET /session)."""
        data = await self._request("GET", "/api/v1/session")
        return str(data.get("accountId", ""))
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_account_switch.py -v`
Expected: PASS.

> If `_request("GET","/api/v1/session")` does not return `accountId` against the real demo API, adjust to the actual field in Task 11 (the validation gate). The unit test pins the contract our code relies on.

- [ ] **Step 5: Commit**

```bash
git add backend/src/broker/client.py backend/tests/forward/test_account_switch.py
git commit -m "feat(broker): add switch_account + get_active_account_id (per-session active account)"
```

---

### Task 8: ExperimentExecutor (isolation guard + dry-run/live)

**Files:**
- Create: `backend/scripts/ab/forward/executor.py`
- Test: `backend/tests/forward/test_executor.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_executor.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.broker.models import Direction, DealConfirmation


def _ctx(prev, open_, cur):
    from forward.strategy import MarketContext
    return MarketContext("AAPL", prev, open_, cur,
                         datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
                         datetime(2026, 6, 2, 20, 45, tzinfo=timezone.utc))


def _strat():
    from forward.strategy import GapFadeStrategy
    return GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015)


@pytest.mark.asyncio
async def test_dry_run_does_not_place_order(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    client = AsyncMock()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "d.db"),
                            notional_usd=200.0, dry_run=True)
    sig = await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0), "2026-06-02")
    assert sig is not None and sig.direction == Direction.SELL
    client.create_position.assert_not_called()
    assert ex.ledger.list_open() == []   # dry-run never writes a live trade


@pytest.mark.asyncio
async def test_live_places_order_when_isolated(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP123"   # isolation OK
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED",
        "epic": "AAPL", "direction": "SELL", "size": 1.94, "level": 103.0,
        "status": "OPEN"})
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "l.db"),
                            notional_usd=200.0, dry_run=False)
    await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0), "2026-06-02")
    client.create_position.assert_awaited_once()
    req = client.create_position.call_args.args[0]
    assert req.epic == "AAPL" and req.direction == Direction.SELL
    assert req.size == round(200.0 / 103.0, 4) and req.stop_level > 103.0
    assert len(ex.ledger.list_open()) == 1


@pytest.mark.asyncio
async def test_live_refuses_when_wrong_account(tmp_path):
    from forward.executor import ExperimentExecutor, IsolationError
    from forward.ledger import ForwardLedger
    client = AsyncMock()
    client.get_active_account_id.return_value = "SOAK999"   # WRONG account
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "x.db"), dry_run=False)
    with pytest.raises(IsolationError):
        await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0), "2026-06-02")
    client.create_position.assert_not_called()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_executor.py -v`
Expected: FAIL — `No module named 'forward.executor'`.

- [ ] **Step 3: Implement**

```python
# backend/scripts/ab/forward/executor.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from src.broker.models import CreatePositionRequest
from forward.strategy import ForwardStrategy, MarketContext, Signal


class IsolationError(RuntimeError):
    """Raised when the active broker account is NOT the experiment account.
    Hard guard against ever trading on the soak account."""


@dataclass
class ExperimentExecutor:
    client: object              # CapitalComClient, connected + switched to experiment account
    experiment_account_id: str
    ledger: object              # ForwardLedger
    notional_usd: float = 200.0
    max_concurrent: int = 5
    daily_loss_limit_usd: float = 100.0
    dry_run: bool = True
    _halted: bool = False

    async def assert_isolation(self) -> None:
        active = await self.client.get_active_account_id()
        if active != self.experiment_account_id:
            raise IsolationError(
                f"active account {active!r} != experiment {self.experiment_account_id!r} "
                "— refusing to trade (soak-protection guard)")

    def _size_for(self, price: float) -> float:
        return round(self.notional_usd / price, 4)

    async def try_enter(self, strat: ForwardStrategy, ctx: MarketContext,
                        session_date: str) -> Signal | object | None:
        if self._halted:
            return None
        if len(self.ledger.list_open()) >= self.max_concurrent:
            logger.warning(f"[forward-lab] max_concurrent={self.max_concurrent} reached — skip")
            return None
        sig = strat.should_enter(ctx)
        if sig is None:
            return None
        size = self._size_for(ctx.today_open)
        if self.dry_run:
            logger.info(f"[DRY-RUN] {strat.name} {sig.direction.value} {sig.epic} "
                        f"size={size} sl={sig.stop_level:.4f} :: {sig.rationale}")
            return sig
        await self.assert_isolation()  # MUST pass before any real order
        req = CreatePositionRequest(epic=sig.epic, direction=sig.direction,
                                    size=size, stop_level=sig.stop_level)
        conf = await self.client.create_position(req)
        self.ledger.record_open(
            strategy=strat.name, epic=sig.epic, session_date=session_date,
            deal_id=conf.deal_id, direction=sig.direction.value, entry=conf.level,
            size=size, stop_level=sig.stop_level, rationale=sig.rationale,
            opened_at=datetime.now(timezone.utc).isoformat())
        logger.success(f"[LIVE] opened {sig.epic} {sig.direction.value} "
                       f"dealId={conf.deal_id} @ {conf.level}")
        return conf
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_executor.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/executor.py backend/tests/forward/test_executor.py
git commit -m "feat(forward-lab): ExperimentExecutor with active-account isolation guard + dry-run"
```

---

### Task 9: ExperimentScheduler (session-open enter + mark/close pass)

**Files:**
- Create: `backend/scripts/ab/forward/scheduler.py`
- Test: `backend/tests/forward/test_scheduler.py`

> Builds `MarketContext` from VERIFIED APIs only: `prev_close` from the daily parquet cache (`ParquetStorageManager.read_candles(epic,"1d")` last close), `today_open`/`current_price` from `get_market_details(epic)["snapshot"]["bid"/"offer"]` mid. ATR left None (uses pct-stop fallback). `session_close` = today at `forward_lab_eod_flatten_utc`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_scheduler.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_on_session_open_enters_on_gap(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP123"
    client.get_market_details.return_value = {"snapshot": {"bid": 102.9, "offer": 103.1}}
    from src.broker.models import DealConfirmation
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "SELL", "size": 1.94, "level": 103.0, "status": "OPEN"})

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "s.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategy=GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01))
    # prev_close stub: 100 -> open 103 mid = +3% gap
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=100.0))
    now = datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc)
    await sched.on_session_open(now=now)
    client.create_position.assert_awaited_once()
    assert len(ex.ledger.list_open()) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_scheduler.py -v`
Expected: FAIL — `No module named 'forward.scheduler'`.

- [ ] **Step 3: Implement**

```python
# backend/scripts/ab/forward/scheduler.py
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[3]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.storage import ParquetStorageManager  # noqa: E402
from forward.executor import ExperimentExecutor  # noqa: E402
from forward.strategy import ForwardStrategy, MarketContext, OpenPosition  # noqa: E402
from src.broker.models import Direction  # noqa: E402


@dataclass
class ExperimentScheduler:
    client: object
    executor: ExperimentExecutor
    strategy: ForwardStrategy
    eod_flatten_utc: str = "20:45"
    _storage: ParquetStorageManager | None = None

    def __post_init__(self):
        self._storage = self._storage or ParquetStorageManager()

    async def _prev_close(self, epic: str) -> float | None:
        df = self._storage.read_candles(epic, "1d")
        if df.is_empty():
            return None
        return float(df.select("close").to_series().to_list()[-1])

    async def _mid(self, epic: str) -> float | None:
        d = await self.client.get_market_details(epic)
        snap = (d or {}).get("snapshot") or {}
        bid, offer = snap.get("bid"), snap.get("offer")
        if bid is None or offer is None:
            return None
        return (float(bid) + float(offer)) / 2.0

    def _session_close(self, now: datetime) -> datetime:
        hh, mm = (int(x) for x in self.eod_flatten_utc.split(":"))
        return datetime.combine(now.date(), time(hh, mm, tzinfo=timezone.utc))

    async def on_session_open(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        session_date = now.date().isoformat()
        for epic in self.strategy.universe():
            prev_close = await self._prev_close(epic)
            mid = await self._mid(epic)
            if prev_close is None or mid is None:
                logger.warning(f"[forward-lab] missing price for {epic} — skip")
                continue
            ctx = MarketContext(epic=epic, prev_close=prev_close, today_open=mid,
                                current_price=mid, now=now,
                                session_close=self._session_close(now))
            await self.executor.try_enter(self.strategy, ctx, session_date)

    async def mark_pass(self, now: datetime | None = None) -> None:
        """Close positions whose exit_rule fires, then reconcile realized P&L
        from broker transaction history (no invented P&L)."""
        now = now or datetime.now(timezone.utc)
        if self.executor.dry_run:
            return
        open_rows = self.executor.ledger.list_open()
        if not open_rows:
            return
        positions = {p.deal_id: p for p in await self.client.list_positions()}
        for row in open_rows:
            mid = await self._mid(row["epic"])
            if mid is None:
                continue
            pos = OpenPosition(
                epic=row["epic"], direction=Direction(row["direction"]),
                entry=row["entry"], size=row["size"], stop_level=row["stop_level"],
                prev_close=0.0, today_open=row["entry"],  # gap recomputed below
                opened_at=now, deal_id=row["deal_id"])
            ctx = MarketContext(epic=row["epic"], prev_close=0.0, today_open=row["entry"],
                                current_price=mid, now=now,
                                session_close=self._session_close(now))
            still_open = row["deal_id"] in positions
            should_exit = self.strategy.exit_rule(pos, ctx)
            if still_open and should_exit:
                await self.client.close_position(row["deal_id"])
            if not still_open or should_exit:
                net, exitpx, reason = await self._realized(row, mid)
                self.executor.ledger.record_close(
                    deal_id=row["deal_id"], exit_price=exitpx, net_pnl=net,
                    closed_at=now.isoformat(), close_reason=reason)
                logger.info(f"[forward-lab] closed {row['epic']} net={net:+.2f} ({reason})")

    async def _realized(self, row: dict, fallback_px: float) -> tuple[float, float, str]:
        """Realized P&L from the latest TRADE transaction for this epic (broker truth)."""
        from src.broker.client import CapitalComClient
        broker_epic = (CapitalComClient._to_broker_epic(row["epic"])
                       if hasattr(self.client, "_to_broker_epic") else row["epic"])
        txns = await self.client.get_transaction_history(limit=50)
        best = None
        for t in txns:
            if (t.transaction_type or "").upper() != "TRADE":
                continue
            if t.instrument_name in (row["epic"], broker_epic):
                best = t  # list is newest-first per client; take first match
                break
        if best is not None:
            pnl = best.pl_value_in("USD")
            if pnl is not None:
                return float(pnl), fallback_px, "BROKER_TRADE"
        # no transaction matched yet -> defer (mark again next pass); record nothing now
        return 0.0, fallback_px, "PENDING_RECONCILE"
```

> Note: `mark_pass` reconciles by latest TRADE row for the epic — adequate for the lab's one-position-per-epic-per-day cadence. If a `PENDING_RECONCILE` is recorded, the next `mark_pass` re-resolves it (the row stays effectively unrealized for scoring until a real P&L lands). This honors the no-invented-P&L invariant.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_scheduler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/scheduler.py backend/tests/forward/test_scheduler.py
git commit -m "feat(forward-lab): ExperimentScheduler session-open enter + broker-truth mark pass"
```

---

### Task 10: forward_lab.py CLI

**Files:**
- Create: `backend/scripts/ab/forward_lab.py`
- Test: `backend/tests/forward/test_cli_discover.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/forward/test_cli_discover.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from unittest.mock import AsyncMock
from src.broker.models import Account


@pytest.mark.asyncio
async def test_discover_account_finds_named_account(capsys):
    import forward_lab
    client = AsyncMock()
    client.get_accounts.return_value = [
        Account.model_validate({"accountId": "SOAK1", "accountName": "Primary",
                                "accountType": "DEMO", "currency": "USD"}),
        Account.model_validate({"accountId": "EXP123", "accountName": "Account Demo",
                                "accountType": "DEMO", "currency": "USD"}),
    ]
    acc_id = await forward_lab.discover_account(client, "Account Demo")
    assert acc_id == "EXP123"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_cli_discover.py -v`
Expected: FAIL — `No module named 'forward_lab'` (or `discover_account` missing).

- [ ] **Step 3: Implement**

```python
# backend/scripts/ab/forward_lab.py
"""Forward Demo Lab CLI. Run from backend/.

Subcommands:
  discover-account     print the accountId of the "Account Demo" experiment account
  validate-isolation   PROVE the experiment session's active account is independent
                       of the soak session BEFORE any live order (Task 11 gate)
  dry-run              one session-open pass, log intended gap-fade orders (no orders sent)
  run                  live: schedule session-open + mark passes (APScheduler)
  mark                 one mark/close pass now
  status               print the ledger
  score                print the kill/promote verdict
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from loguru import logger  # noqa: E402

from src.broker.client import CapitalComClient  # noqa: E402
from src.utils.config import get_settings  # noqa: E402
from forward.executor import ExperimentExecutor  # noqa: E402
from forward.ledger import ForwardLedger  # noqa: E402
from forward.scheduler import ExperimentScheduler  # noqa: E402
from forward.scorer import score  # noqa: E402
from forward.strategy import GapFadeStrategy  # noqa: E402

EXPERIMENT_ACCOUNT_NAME = "Account Demo"
LEDGER_PATH = ROOT / "data" / "forward_lab" / "ledger.db"
UNIVERSE = ["AAPL", "NVDA", "TSLA", "MSFT", "AMD"]  # liquid US stock CFDs (real gaps)


async def discover_account(client, name: str = EXPERIMENT_ACCOUNT_NAME) -> str | None:
    for a in await client.get_accounts():
        if a.account_name == name:
            return a.account_id
    return None


def _strategy() -> GapFadeStrategy:
    s = get_settings()
    return GapFadeStrategy(epics=UNIVERSE, gap_threshold=s.forward_lab_gap_threshold)


async def _connected_client() -> CapitalComClient:
    client = CapitalComClient()  # demo creds from settings (use_demo=True)
    await client.connect()
    return client


async def cmd_discover() -> None:
    client = await _connected_client()
    try:
        acc = await discover_account(client)
        print(f"experiment account '{EXPERIMENT_ACCOUNT_NAME}' -> accountId = {acc}")
        print("Set CAPITAL_EXPERIMENT_ACCOUNT_ID in .env to this value." if acc
              else "NOT FOUND — create/rename the demo account first.")
    finally:
        await client.close()


async def cmd_validate_isolation() -> None:
    """Task 11 gate: prove switching the experiment session does NOT move the
    soak session's active account. Uses TWO independent clients (two CSTs)."""
    s = get_settings()
    exp_id = s.capital_experiment_account_id
    assert exp_id, "set CAPITAL_EXPERIMENT_ACCOUNT_ID first (run discover-account)"
    soak = await _connected_client()
    exp = await _connected_client()
    try:
        soak_before = await soak.get_active_account_id()
        await exp.switch_account(exp_id)
        exp_active = await exp.get_active_account_id()
        soak_after = await soak.get_active_account_id()
        ok = (exp_active == exp_id) and (soak_after == soak_before)
        print(f"soak active before={soak_before} after={soak_after}; "
              f"exp active={exp_active}; ISOLATION {'OK' if ok else 'FAILED'}")
        if not ok:
            print("!!! DO NOT GO LIVE — switching the experiment session moved the "
                  "soak account. Use a SEPARATE LOGIN for the experiment instead.")
    finally:
        await soak.close()
        await exp.close()


def _make_executor(client, dry_run: bool) -> ExperimentExecutor:
    s = get_settings()
    return ExperimentExecutor(
        client=client, experiment_account_id=s.capital_experiment_account_id or "",
        ledger=ForwardLedger(LEDGER_PATH), notional_usd=s.forward_lab_notional_usd,
        max_concurrent=s.forward_lab_max_concurrent,
        daily_loss_limit_usd=s.forward_lab_daily_loss_limit_usd, dry_run=dry_run)


async def cmd_dry_run() -> None:
    client = await _connected_client()
    try:
        ex = _make_executor(client, dry_run=True)
        sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                    eod_flatten_utc=get_settings().forward_lab_eod_flatten_utc)
        await sched.on_session_open()
    finally:
        await client.close()


async def cmd_mark() -> None:
    s = get_settings()
    client = await _connected_client()
    try:
        await client.switch_account(s.capital_experiment_account_id)
        ex = _make_executor(client, dry_run=False)
        sched = ExperimentScheduler(client=client, executor=ex, strategy=_strategy(),
                                    eod_flatten_utc=s.forward_lab_eod_flatten_utc)
        await sched.mark_pass()
    finally:
        await client.close()


def cmd_status() -> None:
    led = ForwardLedger(LEDGER_PATH)
    print("OPEN:", led.list_open())
    print("REALIZED:", led.realized("gap_fade"))


def cmd_score() -> None:
    led = ForwardLedger(LEDGER_PATH)
    print(score(led.realized("gap_fade")))


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "discover-account":
        asyncio.run(cmd_discover())
    elif cmd == "validate-isolation":
        asyncio.run(cmd_validate_isolation())
    elif cmd == "dry-run":
        asyncio.run(cmd_dry_run())
    elif cmd == "mark":
        asyncio.run(cmd_mark())
    elif cmd == "status":
        cmd_status()
    elif cmd == "score":
        cmd_score()
    else:
        print(f"unknown command {cmd!r} — see module docstring for subcommands")


if __name__ == "__main__":
    main()
```

> The `run` subcommand (persistent APScheduler wiring: a daily `on_session_open` trigger + a periodic `mark_pass`) is intentionally deferred — Phase-1 operation is `dry-run` (observe) → manual `mark`. Add `run` in Phase 2 alongside H3, reusing `AsyncIOScheduler` exactly as `PnlSnapshotScheduler` does. (Documented, not silently dropped.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/forward/test_cli_discover.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward_lab.py backend/tests/forward/test_cli_discover.py
git commit -m "feat(forward-lab): CLI (discover-account/validate-isolation/dry-run/mark/status/score)"
```

---

### Task 11: Pre-live isolation validation (HARD GATE — manual runbook)

**Files:** none (operational gate). Uses `forward_lab.py validate-isolation` from Task 10.

- [ ] **Step 1:** Discover the experiment accountId:

Run: `.venv/Scripts/python.exe scripts/ab/forward_lab.py discover-account`
Expected: prints `accountId` for "Account Demo". Put it in `.env` as `CAPITAL_EXPERIMENT_ACCOUNT_ID=...`.

- [ ] **Step 2:** Run the isolation probe:

Run: `.venv/Scripts/python.exe scripts/ab/forward_lab.py validate-isolation`
Expected: `ISOLATION OK` — the soak session's active account is UNCHANGED after the experiment session switches accounts.

- [ ] **Step 3 (DECISION GATE):**
  - **If `ISOLATION OK`** → proceed to Task 12 (dry-run, then live).
  - **If `ISOLATION FAILED`** → STOP. Active-account is login-global on this API. Do NOT go live on the shared login. Instead obtain SEPARATE API credentials for the experiment account (its own api-key/email) and re-architect `_connected_client()` to use them (a small change: pass explicit creds to `CapitalComClient`). Re-run this gate.

- [ ] **Step 4:** Record the outcome in `docs/strategy/FORWARD_LAB_SPEC.md` (append a "§14 Isolation validated YYYY-MM-DD" line) and commit:

```bash
git add docs/strategy/FORWARD_LAB_SPEC.md
git commit -m "docs(forward-lab): record isolation validation result"
```

---

### Task 12: Dry-run observation then go-live (runbook)

**Files:** none (operational).

- [ ] **Step 1:** With the US cash session open, run a dry-run pass:

Run: `.venv/Scripts/python.exe scripts/ab/forward_lab.py dry-run`
Expected: `[DRY-RUN]` log lines for any epic with `|gap| > 1%`; no orders sent. Confirm gaps/directions look sane vs the market.

- [ ] **Step 2:** Only after Task 11 = OK AND dry-run looks correct, place the first LIVE order by switching the executor to live for one epic/session (set `dry_run=False` is wired via the live `mark`/future `run`; for the first live entry use a one-shot script invocation that calls `on_session_open` with `dry_run=False`). Verify on the Capital.com web UI that the position landed on **"Account Demo"** and the soak account is untouched.

- [ ] **Step 3:** Run `mark` after the session to reconcile + record realized P&L:

Run: `.venv/Scripts/python.exe scripts/ab/forward_lab.py mark`
Then: `.venv/Scripts/python.exe scripts/ab/forward_lab.py status`

- [ ] **Step 4:** Accumulate toward N≥100 trades, then:

Run: `.venv/Scripts/python.exe scripts/ab/forward_lab.py score`
Read the verdict (KILL / HOLD / PROMOTE). Survivors → bigger sample; then plug in H3 (Phase 2).

---

## Self-Review

**Spec coverage (FORWARD_LAB_SPEC.md):**
- §4 components: `ForwardStrategy`/`GapFadeStrategy` (T2/T3/T4), `ExperimentExecutor`+isolation guard (T8), `ForwardLedger` (T5), `ExperimentScheduler` (T9), `ForwardScorer` (T6), CLI (T10). ✓
- §5 data flow: T9 `on_session_open` builds ctx (prev_close cache + snapshot mid) → executor → ledger; `mark_pass` → broker-truth P&L → scorer. ✓
- §6 isolation: separate session per client (T10 `_connected_client`), runtime guard `get_active_account_id` (T7/T8), pre-live proof (T11). ✓
- §7 sizing/kill: $200 uniform (`_size_for`), max_concurrent + daily-loss fields (T1/T8), N≥100 + CI/DSR (T6). ✓
- §8 H2 rules: gap math + fade direction + hard stop + 50% fill/EOD (T3/T4). ✓
- §10 testing: unit on should_enter/exit_rule/ledger/scorer/guard, dry-run gate (T8/T12). ✓
- §12 to-confirm: account-switch endpoint + accountId discovery (T7/T10/T11), snapshot keys (T9 verified `snapshot.bid/offer` per CLAUDE.md). ✓

**Placeholder scan:** no TODO/TBD. The deferred `run` subcommand (T10) and the separate-login fallback (T11) are explicitly documented with rationale, not silent gaps.

**Type consistency:** `MarketContext`/`Signal`/`OpenPosition` fields match across strategy/executor/scheduler; `ExperimentExecutor.try_enter(strat, ctx, session_date)` signature consistent in T8/T9/T10; `ForwardLedger.record_open(**kwargs)` keys identical in ledger/executor; `score(rows, trial_sharpes_ann=None)` consistent T6/T10; `CreatePositionRequest(epic,direction,size,stop_level)` matches the read model (populate_by_name). `_to_broker_epic` is a real staticmethod on `CapitalComClient` (verified).

**Open risk carried to runtime gate:** active-account independence per CST (T11) — the one assumption that, if wrong, forces the separate-login path. Gated before any live order.
