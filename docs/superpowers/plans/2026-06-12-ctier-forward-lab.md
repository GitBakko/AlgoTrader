# C-tier Forward-Lab Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 4 approved C-tier forward-lab fixes (pre-call 429 pacing, M5-gate + hygiene, true exit_price + Tier-1 dealId rotation, EUR semantics + stateless daily-loss guard) plus a one-shot exit_price backfill script.

**Architecture:** All changes live in `backend/scripts/ab/forward/{scheduler,executor,ledger}.py` + one config default + one new script. **`src/broker/**` is untouchable** (shared import of the live lab process). Spec: `docs/superpowers/specs/2026-06-12-ctier-forward-lab-design.md`.

**Tech Stack:** Python 3.12, pytest + pytest-asyncio (AsyncMock), sqlite3, loguru. Tests in `backend/tests/forward/`. Run tests from `backend/` with `.venv/Scripts/python.exe -m pytest`.

**Conventions every task MUST follow:**
- Test files start with the `sys.path` bootstrap used by all `tests/forward/` files:
  ```python
  import sys, pathlib
  sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
  ```
- `OHLCCandle.model_validate({"snapshotTime": dt, "openPrice": x, "highPrice": x, "lowPrice": x, "closePrice": x})` — for M5 bars also pass the UTC field. **Check the exact alias of `OHLCCandle.timestamp_utc` in `backend/src/broker/models.py` before writing payloads** (expected `"snapshotTimeUTC"`); `scheduler` reads `c.timestamp_utc or c.timestamp`.
- `ActivityEvent.model_validate({...,"details": {"openPrice": p, "direction": "SELL", "level": l}})` — `level` is `ActivityEventDetails.level` (`models.py:535`).
- Commit prefix `fix:`/`feat:`/`test:` on branch `feature/forward-demo-lab`. One atomic commit per task.
- Never edit files while the full suite runs.

---

### Task 1: Pre-call pacing (429 burst fix)

**Files:**
- Modify: `backend/scripts/ab/forward/scheduler.py` (entry_pass region, lines ~225-256)
- Modify: `backend/src/utils/config.py:94`
- Test: `backend/tests/forward/test_scheduler_pacing.py` (create)

- [ ] **Step 1: Write the failing test**

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_pacing_sleep_precedes_every_per_epic_broker_get(tmp_path, monkeypatch):
    """Cold-cache gap-fade pass fires 3 GETs (_prev_close DAY, _mid, _session_open_price M5).
    A pacing sleep must come BEFORE each of them (pre-call), not only after _mid."""
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import OHLCCandle, Resolution

    events: list[str] = []

    async def fake_sleep(_s):
        events.append("SLEEP")

    monkeypatch.setattr("forward.scheduler.asyncio.sleep", fake_sleep)

    def _day(d, close):
        return OHLCCandle.model_validate(
            {"snapshotTime": d, "openPrice": close, "highPrice": close,
             "lowPrice": close, "closePrice": close})

    async def fake_hist(epic, resolution, max_candles=10):
        events.append("GET")
        if resolution == Resolution.DAY:
            return [_day(datetime(2026, 6, 11, 2, tzinfo=timezone.utc), 100.0)]
        return []  # M5: no bar yet (irrelevant for pacing assertion)

    async def fake_details(epic):
        events.append("GET")
        return {"snapshot": {"bid": 100.0, "offer": 100.2}}

    client = AsyncMock()
    client.get_historical_prices.side_effect = fake_hist
    client.get_market_details.side_effect = fake_details
    client.get_active_account_id.return_value = "EXP"

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "pace.db"), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AMD"])],
                                scan_pacing_s=0.2)
    # Friday 2026-06-12 14:30 UTC = 10:30 ET (in window)
    await sched.entry_pass(now=datetime(2026, 6, 12, 14, 30, tzinfo=timezone.utc))

    gets = events.count("GET")
    assert gets == 3, f"expected 3 broker GETs cold-cache, got {gets}: {events}"
    # every GET must be immediately preceded by a SLEEP
    for i, e in enumerate(events):
        if e == "GET":
            assert i > 0 and events[i - 1] == "SLEEP", f"GET at {i} not paced: {events}"


@pytest.mark.asyncio
async def test_pacing_zero_means_no_sleep(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    slept = []

    async def fake_sleep(_s):
        slept.append(_s)

    monkeypatch.setattr("forward.scheduler.asyncio.sleep", fake_sleep)
    client = AsyncMock()
    client.get_historical_prices.return_value = []
    client.get_market_details.return_value = {"snapshot": {"bid": 1.0, "offer": 1.0}}
    client.get_active_account_id.return_value = "EXP"
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "z.db"), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AMD"])],
                                scan_pacing_s=0.0)
    await sched.entry_pass(now=datetime(2026, 6, 12, 14, 30, tzinfo=timezone.utc))
    assert slept == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_scheduler_pacing.py -v`
Expected: FAIL — first test fails on the ordering assertion (current code sleeps only AFTER `_mid`).

- [ ] **Step 3: Implement**

In `scheduler.py`, add helper after `_in_window` (~line 115):

```python
    async def _paced(self) -> None:
        """Sleep scan_pacing_s BEFORE a per-epic broker GET (10 req/s limit).
        Cold-cache first pass fires up to ~3 GETs per epic; pacing must precede
        EVERY call or the M5 fetches burst the client token bucket (capacity 20)
        and draw 429s — observed 153x on 2026-06-05, 112x on 2026-06-08."""
        if self.scan_pacing_s:
            await asyncio.sleep(self.scan_pacing_s)
```

In `entry_pass`:
1. Before the `_prev_close` call (inside `if epic not in self._state.prev_close:`), add `await self._paced()`.
2. Before `mid = await self._mid(epic)`, add `await self._paced()`.
3. **Delete** the old post-`_mid` block:
```python
                if self.scan_pacing_s:  # pace per-epic GETs (10 req/s limit)
                    await asyncio.sleep(self.scan_pacing_s)
```
4. Before the `_session_open_price` call, add `await self._paced()`.
5. Before the `_opening_range` call (inside `if epic not in self._state.or_levels:`), add `await self._paced()`.

In `config.py:94`: `forward_lab_scan_pacing_s: float = 0.20  # pre-call per-epic GET pacing (10 req/s limit; was 0.12 post-_mid only)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_scheduler_pacing.py tests/forward/ -v`
Expected: new tests PASS, no regressions in `tests/forward/`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/scheduler.py backend/src/utils/config.py backend/tests/forward/test_scheduler_pacing.py
git commit -m "fix(forward-lab): pace BEFORE every per-epic broker GET (cold-cache 429 burst)"
```

---

### Task 2: Hygiene + M5 entry gate

**Files:**
- Modify: `backend/scripts/ab/forward/scheduler.py` (delete `on_session_open` ~280-298; gate in `entry_pass` ~245-249; `mark_pass` ctx ~354)
- Test: `backend/tests/forward/test_scheduler_m5_gate.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


def _mk(tmp_path, client, strategies, name="g.db"):
    from forward.scheduler import ExperimentScheduler
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / name), dry_run=True)
    return ExperimentScheduler(client=client, executor=ex, strategies=strategies), ex


def _day_candle(close):
    from src.broker.models import OHLCCandle
    return OHLCCandle.model_validate(
        {"snapshotTime": datetime(2026, 6, 11, 2, tzinfo=timezone.utc),
         "openPrice": close, "highPrice": close, "lowPrice": close, "closePrice": close})


def _m5_candle(ts_utc, open_):
    # NOTE: verify the UTC alias on OHLCCandle in src/broker/models.py
    # (expected "snapshotTimeUTC"); scheduler filters on timestamp_utc.
    from src.broker.models import OHLCCandle
    return OHLCCandle.model_validate(
        {"snapshotTime": ts_utc, "snapshotTimeUTC": ts_utc,
         "openPrice": open_, "highPrice": open_ + 0.5,
         "lowPrice": open_ - 0.5, "closePrice": open_ + 0.1})


NOW = datetime(2026, 6, 12, 14, 30, tzinfo=timezone.utc)  # Fri 10:30 ET
OPEN_BAR_TS = datetime(2026, 6, 12, 13, 30, tzinfo=timezone.utc)  # 09:30 ET


@pytest.mark.asyncio
async def test_gap_fade_skips_pass_when_m5_open_bar_missing(tmp_path):
    from forward.strategy import GapFadeStrategy
    from src.broker.models import Resolution

    async def hist(epic, resolution, max_candles=10):
        if resolution == Resolution.DAY:
            return [_day_candle(100.0)]
        return []  # no M5 bar yet

    client = AsyncMock()
    client.get_historical_prices.side_effect = hist
    client.get_market_details.return_value = {"snapshot": {"bid": 102.9, "offer": 103.1}}
    client.get_active_account_id.return_value = "EXP"
    sched, ex = _mk(tmp_path, client, [GapFadeStrategy(epics=["AMD"])])
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=NOW)
    ex.try_enter.assert_not_awaited()  # gated: no entry on mid-fallback gap


@pytest.mark.asyncio
async def test_gap_fade_enters_with_true_m5_open_when_bar_present(tmp_path):
    from forward.strategy import GapFadeStrategy
    from src.broker.models import Resolution

    async def hist(epic, resolution, max_candles=10):
        if resolution == Resolution.DAY:
            return [_day_candle(100.0)]
        return [_m5_candle(OPEN_BAR_TS, 103.0)]

    client = AsyncMock()
    client.get_historical_prices.side_effect = hist
    client.get_market_details.return_value = {"snapshot": {"bid": 102.9, "offer": 103.1}}
    client.get_active_account_id.return_value = "EXP"
    sched, ex = _mk(tmp_path, client, [GapFadeStrategy(epics=["AMD"])], "g2.db")
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=NOW)
    ex.try_enter.assert_awaited_once()
    ctx = ex.try_enter.await_args.args[1]
    assert ctx.today_open == 103.0  # true M5 open, not mid


@pytest.mark.asyncio
async def test_orb_not_gated_by_m5_open(tmp_path):
    """ORB (uses_today_open=False) must not be gated: M5 session-open fetch never
    happens for it; eligibility-gated path proceeds on or_levels alone."""
    from forward.strategy import ORBStrategy
    from src.broker.models import Resolution

    async def hist(epic, resolution, max_candles=10):
        # only MINUTE_5 ever requested for ORB (OR window); return bars in OR window
        assert resolution == Resolution.MINUTE_5
        return [_m5_candle(OPEN_BAR_TS, 103.0)]

    client = AsyncMock()
    client.get_historical_prices.side_effect = hist
    client.get_market_details.return_value = {"snapshot": {"bid": 104.9, "offer": 105.1}}
    client.get_active_account_id.return_value = "EXP"
    sched, ex = _mk(tmp_path, client, [ORBStrategy(epics=["AMD"])], "g3.db")
    sched._state.ensure_day(NOW.date())
    sched._state.eligible = {"AMD"}
    sched._state.rvol = {"AMD": 2.0}
    sched._state.screened = True
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=NOW)
    ex.try_enter.assert_awaited_once()


def test_on_session_open_deleted(tmp_path):
    from forward.scheduler import ExperimentScheduler
    assert not hasattr(ExperimentScheduler, "on_session_open")


@pytest.mark.asyncio
async def test_mark_pass_ctx_today_open_from_ledger_not_entry(tmp_path):
    from forward.strategy import GapFadeStrategy
    from forward.scheduler import ExperimentScheduler
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    seen = {}

    class SpyGapFade(GapFadeStrategy):
        def exit_rule(self, pos, ctx):
            seen["ctx_today_open"] = ctx.today_open
            seen["pos_today_open"] = pos.today_open
            return False

    client = AsyncMock()
    client.list_positions.return_value = []
    client.get_market_details.return_value = {"snapshot": {"bid": 101.9, "offer": 102.1}}
    client.get_active_account_id.return_value = "EXP"
    client.get_transaction_history.return_value = []
    client.get_activity_history.return_value = []
    led = ForwardLedger(tmp_path / "m.db")
    led.record_open(strategy="gap_fade", epic="AMD", session_date="2026-06-12",
                    deal_id="D1", direction="SELL", entry=103.0, size=1.0,
                    stop_level=104.5, rationale="t",
                    opened_at=datetime.now(timezone.utc).isoformat(),
                    prev_close=100.0, today_open=105.0)
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[SpyGapFade(epics=["AMD"])])
    await sched.mark_pass(now=NOW)
    assert seen["pos_today_open"] == 105.0
    assert seen["ctx_today_open"] == 105.0  # was row['entry']=103.0 before fix
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_scheduler_m5_gate.py -v`
Expected: FAIL — `test_gap_fade_skips_pass...` (entry proceeds on mid today), `test_on_session_open_deleted` (method exists), `test_mark_pass_ctx_today_open...` (ctx gets entry=103.0).

- [ ] **Step 3: Implement**

In `scheduler.py` `entry_pass`, replace the session-open block (current lines ~241-249, after Task 1 edits):

```python
                # today_open = the TRUE 09:30 cash-session open (historical M5 bar),
                # never the live mid: entering on a mid-fallback gap is the residual
                # restart wart. If the bar is not yet available (first minutes of the
                # session or fetch error), SKIP the epic this pass and retry in 5 min.
                if strat.uses_today_open:
                    if epic not in self._state.open_px:
                        await self._paced()
                        sop = await self._session_open_price(epic, now)
                        if sop is None:
                            logger.info(
                                f"[forward-lab] {epic} 09:30 M5 bar not yet available "
                                "— skip this pass, retry next"
                            )
                            continue
                        self._state.open_px[epic] = sop
                    today_open = self._state.open_px[epic]
                else:
                    today_open = mid  # ORB ignores today_open (exit_rule never reads it)
```

Delete the whole `on_session_open` method (lines ~280-298).

In `mark_pass`, change the ctx construction (~line 354):
```python
            ctx = MarketContext(
                epic=row["epic"],
                prev_close=0.0,
                today_open=row["today_open"] if row.get("today_open") is not None else row["entry"],
                current_price=mid,
                now=now,
                session_close=self._session_close(now),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/ -v`
Expected: all PASS (including Task 1 tests — the gate adds a paced M5 GET; `test_pacing_sleep_precedes_every_per_epic_broker_get` still expects 3 GETs since the M5 fetch still fires, then gates).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/scheduler.py backend/tests/forward/test_scheduler_m5_gate.py
git commit -m "fix(forward-lab): gate gap-fade on true M5 session open; drop dead on_session_open; mark_pass ctx.today_open from ledger"
```

---

### Task 3: Ledger groundwork — `close_deal_id` + `session_net`

**Files:**
- Modify: `backend/scripts/ab/forward/ledger.py`
- Test: append to `backend/tests/forward/test_ledger.py`

- [ ] **Step 1: Write the failing tests** (append to existing `test_ledger.py`; reuse its imports/bootstrap)

```python
def test_close_deal_id_migration_and_roundtrip(tmp_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "cd.db")
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-12",
                    deal_id="D1", direction="BUY", entry=100.0, size=1.0,
                    stop_level=99.0, rationale="t", opened_at="2026-06-12T14:00:00+00:00")
    led.set_close_deal_id("D1", "DROT")
    row = led.list_open()[0]
    assert row["close_deal_id"] == "DROT"
    # re-init on the same file must be idempotent (ADD COLUMN guarded)
    ForwardLedger(tmp_path / "cd.db")


def test_session_net_sums_only_closed_rows_of_that_day(tmp_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "sn.db")
    # closed today: -60 and -50; open today: ignored; closed yesterday: ignored
    for i, (sd, pnl, closed) in enumerate([
        ("2026-06-12", -60.0, True),
        ("2026-06-12", -50.0, True),
        ("2026-06-12", None, False),
        ("2026-06-11", -500.0, True),
    ]):
        led.record_open(strategy="orb", epic=f"E{i}", session_date=sd,
                        deal_id=f"D{i}", direction="BUY", entry=100.0, size=1.0,
                        stop_level=99.0, rationale="t",
                        opened_at=f"{sd}T14:00:00+00:00")
        if closed:
            led.record_close(deal_id=f"D{i}", exit_price=99.0, net_pnl=pnl,
                             closed_at=f"{sd}T19:45:00+00:00", close_reason="BROKER_TRADE")
    assert led.session_net("2026-06-12") == -110.0
    assert led.session_net("2026-06-10") == 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_ledger.py -v`
Expected: FAIL — `set_close_deal_id`/`session_net` don't exist; no `close_deal_id` column.

- [ ] **Step 3: Implement** in `ledger.py`

In `_init`, add the column to the CREATE TABLE (after `close_reason TEXT`, before the UNIQUE constraint): `close_deal_id TEXT,` — and extend the migration tuple:
```python
            for col in ("prev_close", "today_open", "close_deal_id"):
                if col not in existing:
                    try:
                        col_type = "REAL" if col in ("prev_close", "today_open") else "TEXT"
                        c.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
                    except sqlite3.OperationalError:
                        pass  # lost the migration race — column already added by a concurrent init
```

Add methods:
```python
    def set_close_deal_id(self, deal_id: str, close_deal_id: str) -> None:
        """Persist the broker's CURRENT dealId at the moment WE send the close
        (Capital.com may have rotated it vs the stored create-confirmation id).
        _realized Tier-1 then matches the TRADE row on either id."""
        with self._conn() as c:
            c.execute(
                "UPDATE trades SET close_deal_id=? WHERE deal_id=? AND closed_at IS NULL",
                (close_deal_id, deal_id),
            )

    def session_net(self, session_date: str) -> float:
        """Realized net P&L (account currency) of CLOSED rows for one session day."""
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(net_pnl), 0.0) FROM trades "
                "WHERE session_date=? AND closed_at IS NOT NULL",
                (session_date,),
            ).fetchone()
            return float(row[0])
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_ledger.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/ledger.py backend/tests/forward/test_ledger.py
git commit -m "feat(forward-lab): ledger close_deal_id column + session_net aggregate"
```

---

### Task 4: True exit_price (Tier-2 `level`) + Tier-1 rotation match

**Files:**
- Modify: `backend/scripts/ab/forward/scheduler.py` (`mark_pass` close branch ~361-379; `_realized` ~408-468)
- Test: append to `backend/tests/forward/test_realized_dealid.py`

- [ ] **Step 1: Write the failing tests** (append; reuse the existing `_txn`/`_activity` helpers — extend `_activity` with a `level` kwarg)

Replace the existing `_activity` helper with:
```python
def _activity(deal_id, open_price, epic="AAPL", source="SL", level=None):
    from src.broker.models import ActivityEvent

    details = {"openPrice": open_price, "direction": "SELL"}
    if level is not None:
        details["level"] = level
    return ActivityEvent.model_validate(
        {
            "date": "2026-06-03T16:00:00",
            "epic": epic,
            "source": source,
            "type": "POSITION",
            "status": "ACCEPTED",
            "dealId": deal_id,
            "details": details,
        }
    )
```

New tests:
```python
@pytest.mark.asyncio
async def test_tier2_exit_price_uses_activity_level(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DPOS1", "-7.50")]
    client.get_activity_history.return_value = [
        _activity("DPOS1", open_price=103.0, level=101.25)]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "lv.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DPOS", "entry": 103.0,
           "opened_at": "2026-06-03T14:30:00+00:00", "direction": "BUY"}
    net, px, reason = await sched._realized(row, fallback_px=100.0)
    assert reason == "BROKER_ACTIVITY" and px == 101.25  # broker close level, not mid


@pytest.mark.asyncio
async def test_tier2_exit_price_falls_back_to_mid_when_level_absent(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DPOS1", "-7.50")]
    client.get_activity_history.return_value = [_activity("DPOS1", open_price=103.0)]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "lv2.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DPOS", "entry": 103.0,
           "opened_at": "2026-06-03T14:30:00+00:00", "direction": "BUY"}
    net, px, reason = await sched._realized(row, fallback_px=100.0)
    assert reason == "BROKER_ACTIVITY" and px == 100.0


@pytest.mark.asyncio
async def test_tier1_matches_persisted_close_deal_id(tmp_path):
    """Our own close was sent with the broker's CURRENT (rotated) dealId; the TRADE
    row carries that id, not the stored create-confirmation id. Tier-1 must match
    via row['close_deal_id'] without any activity call."""
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DROT", "4.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "cdid.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DMINE", "close_deal_id": "DROT",
           "entry": 100.0, "opened_at": "2026-06-03T14:00:00+00:00",
           "direction": "SELL"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 4.00 and reason == "BROKER_TRADE"
    client.get_activity_history.assert_not_called()


@pytest.mark.asyncio
async def test_mark_pass_persists_close_deal_id_on_our_close(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Position

    client = AsyncMock()
    # broker position with ROTATED dealId vs the stored one; same epic+dir+level
    client.list_positions.return_value = [Position.model_validate({
        "dealId": "DCUR", "epic": "AAPL", "direction": "BUY",
        "size": 1.0, "level": 103.0})]
    client.get_market_details.return_value = {"snapshot": {"bid": 104.0, "offer": 104.2}}
    client.get_active_account_id.return_value = "EXP"
    led = ForwardLedger(tmp_path / "mp.db")
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-12",
                    deal_id="DSTORED", direction="BUY", entry=103.0, size=1.0,
                    stop_level=99.0, rationale="t",
                    opened_at="2026-06-12T14:00:00+00:00")
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    # past session_close (15:45 ET = 19:45 UTC) -> ORB exit_rule fires -> our close
    await sched.mark_pass(now=datetime(2026, 6, 12, 20, 0, tzinfo=timezone.utc))
    client.close_position.assert_awaited_once_with("DCUR")
    assert led.list_open()[0]["close_deal_id"] == "DCUR"
```

NOTE: if `Position.model_validate` requires extra mandatory fields, mirror the Position payload used in existing `tests/forward/test_scheduler.py` mark_pass tests.

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_realized_dealid.py -v`
Expected: 4 new tests FAIL (exit px = fallback, close_deal_id ignored/never persisted). Existing 7 must still pass.

- [ ] **Step 3: Implement** in `scheduler.py`

`mark_pass` close branch — persist the close-side dealId right after the close succeeds:
```python
                try:
                    await self.client.close_position(
                        matched.deal_id
                    )  # broker's CURRENT dealId, not the stored one
                    self.executor.ledger.set_close_deal_id(row["deal_id"], matched.deal_id)
                    logger.info(
                        f"[forward-lab] close sent for {row['epic']} ({row['strategy']}) "
                        "— reconcile deferred to next pass (broker history lag)"
                    )
```

`_realized` Tier-1 — match on either id:
```python
        # Tier 1 — exact dealId (our own close). The TRADE row may carry either the
        # stored create-confirmation id or the rotated id we used to send the close.
        own_ids = {row["deal_id"], row.get("close_deal_id")} - {None}
        for t in trades:
            if t.deal_id and t.deal_id in own_ids:
                pnl = t.pl_value_in("USD")
                if pnl is not None:
                    return float(pnl), fallback_px, "BROKER_TRADE"
```

`_realized` Tier-2 — read the broker close level:
```python
                for t in trades:
                    if t.deal_id and t.deal_id == a.deal_id:
                        pnl = t.pl_value_in("USD")
                        if pnl is not None:
                            level = a.details.level
                            if level is None:
                                logger.debug(
                                    f"[forward-lab] {row['epic']} close activity has no "
                                    "level — exit_price falls back to reconcile-time mid"
                                )
                            close_px = float(level) if level is not None else fallback_px
                            return float(pnl), close_px, "BROKER_ACTIVITY"
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/scheduler.py backend/tests/forward/test_realized_dealid.py
git commit -m "fix(forward-lab): exit_price from activity close level; Tier-1 matches persisted close_deal_id"
```

---

### Task 5: EUR semantics (`account_ccy`)

**Files:**
- Modify: `backend/scripts/ab/forward/executor.py` (new field)
- Modify: `backend/scripts/ab/forward/scheduler.py` (`_realized` both `pl_value_in` sites; close log label)
- Test: `backend/tests/forward/test_account_ccy.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


def _txn(deal_id, size, currency="EUR"):
    from src.broker.models import Transaction
    return Transaction(
        date=datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc),
        reference=f"r-{deal_id}", dealId=deal_id, transactionType="TRADE",
        instrumentName="AAPL", size=size, currency=currency)


@pytest.mark.asyncio
async def test_realized_passes_account_ccy_to_pl_value_in(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker import models as broker_models

    seen = []
    orig = broker_models.Transaction.pl_value_in

    def spy(self, account_currency):
        seen.append(account_currency)
        return orig(self, account_currency)

    monkeypatch.setattr(broker_models.Transaction, "pl_value_in", spy)
    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("D1", "3.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "c.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "D1"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert reason == "BROKER_TRADE" and net == 3.00
    assert seen == ["EUR"]  # executor default account_ccy, not hardcoded "USD"


def test_executor_default_account_ccy_is_eur(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=None, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "d.db"))
    assert ex.account_ccy == "EUR"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_account_ccy.py -v`
Expected: FAIL — `account_ccy` missing; `seen == ["USD"]`.

- [ ] **Step 3: Implement**

`executor.py` — add field after `daily_loss_limit_usd` (renamed in Task 6; if Task 6 already done, after `daily_loss_limit_eur`):
```python
    account_ccy: str = "EUR"   # experiment account denomination (broker P&L arrives in this ccy)
```

`scheduler.py` `_realized`: replace both `t.pl_value_in("USD")` occurrences with `t.pl_value_in(self.executor.account_ccy)`.

`mark_pass` close log — add the currency label:
```python
                logger.info(
                    f"[forward-lab] closed {row['epic']} ({row['strategy']}) "
                    f"net={net:+.2f} {self.executor.account_ccy} ({reason})"
                )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/ -v`
Expected: all PASS. NOTE: existing `test_realized_dealid.py` helpers create txns with `currency="USD"` — `pl_value_in("EUR")` logs a WARNING for them but still returns the value (verified behavior, `models.py:408-446`); assertions are on value/reason, so they stay green.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/executor.py backend/scripts/ab/forward/scheduler.py backend/tests/forward/test_account_ccy.py
git commit -m "fix(forward-lab): P&L currency = executor.account_ccy (EUR) — unmasks pl_value_in mismatch warning"
```

---

### Task 6: Stateless daily-loss guard

**Files:**
- Modify: `backend/scripts/ab/forward/executor.py` (guard in `try_enter`; remove `_halted`; rename limit field)
- Modify: `backend/scripts/ab/forward_lab.py:157` (`daily_loss_limit_eur=` kwarg)
- Modify: `backend/src/utils/config.py:93` (comment only)
- Test: `backend/tests/forward/test_daily_loss_guard.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.broker.models import DealConfirmation


def _ctx():
    from forward.strategy import MarketContext
    return MarketContext("AAPL", 100.0, 103.0, 103.0,
                         datetime(2026, 6, 12, 14, 0, tzinfo=timezone.utc),
                         datetime(2026, 6, 12, 19, 45, tzinfo=timezone.utc))


def _strat():
    from forward.strategy import GapFadeStrategy
    return GapFadeStrategy(epics=["AAPL"])


def _seed_closed(led, session_date, pnl, key):
    led.record_open(strategy="orb", epic=f"E{key}", session_date=session_date,
                    deal_id=f"D{key}", direction="BUY", entry=100.0, size=1.0,
                    stop_level=99.0, rationale="t",
                    opened_at=f"{session_date}T14:00:00+00:00")
    led.record_close(deal_id=f"D{key}", exit_price=99.0, net_pnl=pnl,
                     closed_at=f"{session_date}T19:45:00+00:00", close_reason="BROKER_TRADE")


@pytest.mark.asyncio
async def test_blocks_new_entries_at_daily_loss_limit(tmp_path):
    # NOTE: loguru does NOT propagate to std logging, so pytest's caplog can't see
    # it (no bridge in tests/conftest.py) — capture via a direct loguru sink.
    from loguru import logger as loguru_logger
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "g1.db")
    _seed_closed(led, "2026-06-12", -120.0, 1)
    client = AsyncMock()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, daily_loss_limit_eur=100.0, dry_run=False)
    records = []
    sink_id = loguru_logger.add(lambda m: records.append(m.record), level="CRITICAL")
    try:
        out = await ex.try_enter(_strat(), _ctx(), "2026-06-12")
    finally:
        loguru_logger.remove(sink_id)
    assert out is None
    client.create_position.assert_not_called()
    assert any(r["level"].name == "CRITICAL" for r in records)


@pytest.mark.asyncio
async def test_allows_entries_below_limit(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "g2.db")
    _seed_closed(led, "2026-06-12", -50.0, 1)
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED",
        "epic": "AAPL", "direction": "SELL", "size": 1.94, "level": 103.0,
        "status": "OPEN"})
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, daily_loss_limit_eur=100.0, dry_run=False)
    await ex.try_enter(_strat(), _ctx(), "2026-06-12")
    client.create_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_guard_is_stateless_day_rolls(tmp_path):
    """Yesterday's blowout must NOT block today (no persistent _halted flag)."""
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "g3.db")
    _seed_closed(led, "2026-06-11", -500.0, 1)
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D2", "dealReference": "R2", "dealStatus": "ACCEPTED",
        "epic": "AAPL", "direction": "SELL", "size": 1.94, "level": 103.0,
        "status": "OPEN"})
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, daily_loss_limit_eur=100.0, dry_run=False)
    await ex.try_enter(_strat(), _ctx(), "2026-06-12")
    client.create_position.assert_awaited_once()


def test_halted_field_removed(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=None, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "g4.db"))
    assert not hasattr(ex, "_halted")
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_daily_loss_guard.py -v`
Expected: FAIL — `daily_loss_limit_eur` unknown kwarg; `_halted` exists; no blocking.

- [ ] **Step 3: Implement**

`executor.py`:
- Rename field: `daily_loss_limit_usd: float = 100.0` → `daily_loss_limit_eur: float = 100.0`.
- Delete `_halted: bool = field(default=False, init=False, repr=False)` and the `if self._halted: return None` check (the `field` import may become unused — keep it only if `name`-style fields still use it; remove the import if dead, ruff will flag it).
- At the top of `try_enter`, before the `ledger.exists` check:
```python
        net_today = self.ledger.session_net(session_date)
        if net_today <= -self.daily_loss_limit_eur:
            logger.critical(
                f"[forward-lab] DAILY LOSS LIMIT: session {session_date} realized "
                f"{net_today:+.2f} {self.account_ccy} <= -{self.daily_loss_limit_eur:.2f} "
                "— blocking new entries (open positions keep broker SL + EOD flatten)")
            return None
```

`forward_lab.py` `_make_executor`: `daily_loss_limit_usd=s.forward_lab_daily_loss_limit_usd` → `daily_loss_limit_eur=s.forward_lab_daily_loss_limit_usd`.

`config.py:93` comment: `forward_lab_daily_loss_limit_usd: float = 100.0  # EUR-denominated despite the suffix (experiment acct is EUR); key name kept for .env compat`

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/ -v`
Expected: all PASS (existing executor tests construct without the renamed kwarg — they use defaults — and don't reference `_halted`).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/forward/executor.py backend/scripts/ab/forward_lab.py backend/src/utils/config.py backend/tests/forward/test_daily_loss_guard.py
git commit -m "feat(forward-lab): enforce daily loss limit (stateless, EUR) — was dead config since launch"
```

---

### Task 7: One-shot exit_price backfill script

**Files:**
- Create: `backend/scripts/ab/backfill_exit_price.py`
- Test: `backend/tests/forward/test_backfill_exit_price.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import sqlite3
import pytest
from unittest.mock import AsyncMock


def _seed(db_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(db_path)
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-05",
                    deal_id="D1", direction="BUY", entry=103.0, size=1.0,
                    stop_level=99.0, rationale="t",
                    opened_at="2026-06-05T14:00:00+00:00")
    led.record_close(deal_id="D1", exit_price=104.99, net_pnl=-7.5,
                     closed_at="2026-06-05T16:00:00+00:00", close_reason="BROKER_ACTIVITY")
    led.record_open(strategy="orb", epic="NVDA", session_date="2026-06-05",
                    deal_id="D2", direction="BUY", entry=900.0, size=1.0,
                    stop_level=890.0, rationale="t",
                    opened_at="2026-06-05T14:00:00+00:00")
    led.record_close(deal_id="D2", exit_price=905.0, net_pnl=5.0,
                     closed_at="2026-06-05T16:00:00+00:00", close_reason="BROKER_ACTIVITY")
    return led


def _close_event(epic, open_price, level):
    from src.broker.models import ActivityEvent
    return ActivityEvent.model_validate({
        "date": "2026-06-05T16:00:00", "epic": epic, "source": "SL",
        "type": "POSITION", "status": "ACCEPTED", "dealId": "DROT",
        "details": {"openPrice": open_price, "direction": "SELL", "level": level}})


@pytest.mark.asyncio
async def test_backfill_updates_matching_rows_and_reports(tmp_path):
    from backfill_exit_price import backfill

    db = tmp_path / "bf.db"
    _seed(db)

    async def acts(frm, to):
        return [_close_event("AAPL", 103.0, 101.25)]  # only AAPL resolvable

    client = AsyncMock()
    client.get_activity_history.side_effect = acts
    report = await backfill(db, client, dry_run=False)
    assert report["updated"] == 1 and report["total"] == 2
    with sqlite3.connect(db) as c:
        px_aapl = c.execute("SELECT exit_price FROM trades WHERE deal_id='D1'").fetchone()[0]
        px_nvda = c.execute("SELECT exit_price FROM trades WHERE deal_id='D2'").fetchone()[0]
    assert px_aapl == 101.25       # backfilled from activity level
    assert px_nvda == 905.0        # untouched (no matching close event)


@pytest.mark.asyncio
async def test_backfill_dry_run_touches_nothing(tmp_path):
    from backfill_exit_price import backfill

    db = tmp_path / "bf2.db"
    _seed(db)

    async def acts(frm, to):
        return [_close_event("AAPL", 103.0, 101.25)]

    client = AsyncMock()
    client.get_activity_history.side_effect = acts
    report = await backfill(db, client, dry_run=True)
    assert report["updated"] == 1  # WOULD update
    with sqlite3.connect(db) as c:
        px = c.execute("SELECT exit_price FROM trades WHERE deal_id='D1'").fetchone()[0]
    assert px == 104.99  # unchanged
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_backfill_exit_price.py -v`
Expected: FAIL — `ModuleNotFoundError: backfill_exit_price`.

- [ ] **Step 3: Implement** `backend/scripts/ab/backfill_exit_price.py`

```python
"""One-shot: backfill trades.exit_price with the broker close level from
/history/activity for historical BROKER_ACTIVITY closes (exit_price was the
reconcile-time mid before the 2026-06-12 fix).

Usage (from backend/):
  .venv/Scripts/python.exe scripts/ab/backfill_exit_price.py --dry-run
  .venv/Scripts/python.exe scripts/ab/backfill_exit_price.py

BACK UP THE LEDGER FIRST:
  copy data\\forward_lab\\ledger.db data\\forward_lab\\ledger.pre-backfill.db
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from loguru import logger  # noqa: E402

DEFAULT_DB = ROOT / "data" / "forward_lab" / "ledger.db"


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def backfill(db_path, client, dry_run: bool = True) -> dict:
    """For each closed BROKER_ACTIVITY row, find its close event in a <24h
    activity window ending at closed_at and rewrite exit_price = details.level.
    Same matching rule as scheduler._realized Tier-2 (epic + openPrice≈entry)."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, epic, entry, opened_at, closed_at, exit_price FROM trades "
        "WHERE closed_at IS NOT NULL AND close_reason='BROKER_ACTIVITY'"
    ).fetchall()
    report = {"total": len(rows), "updated": 0, "no_match": 0, "no_level": 0}
    for row in rows:
        closed = _parse_dt(row["closed_at"])
        act_from = closed - timedelta(hours=23)
        try:
            acts = await client.get_activity_history(act_from, closed)
        except Exception as e:  # noqa: BLE001 — per-row failure must not kill the run
            logger.warning(f"[backfill] {row['epic']} id={row['id']}: activity fetch failed: {e}")
            report["no_match"] += 1
            continue
        entry = float(row["entry"])
        tol = max(1e-6, abs(entry) * 1e-4)
        level = None
        for a in acts:
            if not a.is_close_event() or a.epic != row["epic"]:
                continue
            op = a.details.open_price
            if op is None or abs(float(op) - entry) > tol:
                continue
            level = a.details.level
            break
        if level is None:
            key = "no_level" if acts else "no_match"
            report[key] += 1
            logger.info(f"[backfill] {row['epic']} id={row['id']}: unresolved ({key})")
            continue
        logger.info(
            f"[backfill] {row['epic']} id={row['id']}: exit_price "
            f"{row['exit_price']} -> {float(level)}{' (dry-run)' if dry_run else ''}")
        report["updated"] += 1
        if not dry_run:
            con.execute("UPDATE trades SET exit_price=? WHERE id=?", (float(level), row["id"]))
            con.commit()
    con.close()
    logger.success(f"[backfill] done: {report}")
    return report


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from src.broker.client import CapitalComClient
    from src.utils.config import get_settings

    s = get_settings()
    client = CapitalComClient(api_key=s.capital_experiment_api_key,
                              email=s.capital_experiment_email,
                              password=s.capital_experiment_password)
    await client.connect()
    try:
        if s.capital_experiment_account_id and (
            await client.get_active_account_id() != s.capital_experiment_account_id
        ):
            await client.switch_account(s.capital_experiment_account_id)
        await backfill(Path(args.db), client, dry_run=args.dry_run)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/forward/test_backfill_exit_price.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ab/backfill_exit_price.py backend/tests/forward/test_backfill_exit_price.py
git commit -m "feat(forward-lab): one-shot exit_price backfill from activity close level"
```

---

### Task 8: Final gates + ship

- [ ] **Step 1: Lint** — `cd backend && .venv/Scripts/python.exe -m ruff check scripts/ab/forward/ scripts/ab/backfill_exit_price.py src/utils/config.py && .venv/Scripts/python.exe -m black --check scripts/ab/forward/ scripts/ab/backfill_exit_price.py`. Fix any findings, amend nothing — new `style:` commit if needed.
- [ ] **Step 2: Full backend suite** (~19 min, NO file edits while running) — `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`. Expected: 2268+new passed / 0 failed (baseline 2268/0 + new forward tests).
- [ ] **Step 3: Push** — `git push origin feature/forward-demo-lab`, then ff main: `git push . feature/forward-demo-lab:main && git push origin main`.
- [ ] **Step 4: Watch CI** — `"/c/Program Files/GitHub CLI/gh.exe" run list -R GitBakko/AlgoTrader --limit 3` until green.
- [ ] **Step 5 (USER-COORDINATED, not autonomous):** runbook from spec — ledger backup → `backfill_exit_price.py --dry-run` → review report with user → real run on user OK → lab restart OUTSIDE 09:30-12:00 ET window (kill `forward_lab.py` python process → `start_forward_lab.ps1` or watchdog). Post-restart: check first entry_pass logs (paced scan, no 429 burst) and first close (`net=… EUR`).
```
