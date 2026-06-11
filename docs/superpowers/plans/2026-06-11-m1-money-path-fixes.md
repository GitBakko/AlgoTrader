# M1 Money-Path Correctness Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 10 audit-verified correctness/security gaps on the trading money path (spec: `docs/superpowers/specs/2026-06-11-m1-money-path-fixes-design.md`).

**Architecture:** Surgical fixes inside the existing layering (api → strategy → risk → execution → broker). One structural extraction only (`_finalize_entry` in paper_loop, Task 7). No `src/broker/` edits (forward-lab runs 24/7 from this tree and imports only src.broker + config).

**Tech Stack:** Python 3.12 / pytest 9 (asyncio auto mode) / SQLAlchemy async / Angular 21 + Vitest 4.

---

## Conventions for every task

- Working dir for backend commands: `D:\Develop\AI\_ClaudeCode\AlgoTrader\backend`. Python: `.venv/Scripts/python.exe`.
- Run a test file: `.venv/Scripts/python.exe -m pytest <file> --no-cov -q -p no:cacheprovider`
- **Line numbers below are approximate** (the evolution-cleanup commit shifted paper_loop by ~-40 lines vs the audit). Always locate by the quoted content anchor, never by blind line number.
- Lint before each commit: `.venv/Scripts/python.exe -m ruff check src/ tests/ && .venv/Scripts/python.exe -m black --check --line-length=100 <touched files>`
- Commit format: one task per commit, prefix `fix:`/`test:`, body explains the failure mode. End with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Existing test fixtures: `tests/trading/test_close_no_synthetic_pnl.py` shows the `__new__`-constructed PaperTradingLoop stub pattern (`mock_paper_loop` fixture) — reuse that pattern where a loop instance is needed.
- Global autouse fixture (tests/conftest.py) disables MR/ML primaries — irrelevant for these tasks but explains settings mocking conventions: patch `src.<module>.get_settings` at the consuming module.

---

### Task 1 (M1.1): Kelly deque slice + `seed_trade_history` public API

**Files:**
- Modify: `src/risk/kelly_sizer.py` (compute_stats, anchor: `recent = trade_history[-self.lookback_trades :]`)
- Modify: `src/trading/paper_loop.py` (add public method near `__init__` helpers)
- Modify: `src/api/main.py` (anchor: `app.state.paper_loop._trade_history = trade_history`)
- Test: `tests/risk/test_kelly_sizer_deque.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Regression: KellySizer must accept a deque trade_history (audit M1.1).

paper_loop keeps self._trade_history as deque(maxlen=200) and passes it raw
to RiskManager -> KellySizer. collections.deque does not support slicing:
on HEAD the 30th in-session trade arms a TypeError in compute_stats and
every subsequent check_trade fails for ALL epics until restart.
"""
from collections import deque

from src.risk.kelly_sizer import AdaptiveKellySizer


def _mk_history(n: int) -> list[dict]:
    # Alternate wins/losses so stats are well-defined
    return [{"pnl": 10.0 if i % 2 == 0 else -5.0} for i in range(n)]


class TestKellyDequeSupport:
    def test_compute_stats_accepts_deque(self):
        sizer = AdaptiveKellySizer(min_trades=30, lookback_trades=100)
        history = deque(_mk_history(35), maxlen=200)
        stats = sizer.compute_stats(history)
        assert stats is not None
        assert 0.0 < stats.win_rate < 1.0

    def test_compute_stats_deque_below_min_returns_none(self):
        sizer = AdaptiveKellySizer(min_trades=30)
        assert sizer.compute_stats(deque(_mk_history(10))) is None


class TestSeedTradeHistory:
    def test_seed_trade_history_keeps_maxlen_contract(self):
        """main.py recovery injection must preserve the 200-trade bound."""
        from src.trading.paper_loop import PaperTradingLoop

        loop = PaperTradingLoop.__new__(PaperTradingLoop)
        loop.seed_trade_history(_mk_history(500))
        assert len(loop._trade_history) == 200
        assert isinstance(loop._trade_history, deque)
        # Most recent entries are kept (history list is chronological)
        assert loop._trade_history[-1] == _mk_history(500)[-1]
```

NOTE: check the actual sizer class name first (`grep -n "class.*KellySizer" src/risk/kelly_sizer.py`); the audit references `AdaptiveKellySizer` wired in dependencies.py — adjust the import if the class is named differently.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/risk/test_kelly_sizer_deque.py --no-cov -q -p no:cacheprovider`
Expected: `test_compute_stats_accepts_deque` FAILS with `TypeError: sequence index must be integer, not 'slice'`; `test_seed_trade_history_keeps_maxlen_contract` FAILS with `AttributeError: ... has no attribute 'seed_trade_history'`.

- [ ] **Step 3: Implement**

In `src/risk/kelly_sizer.py`, `compute_stats`, replace:

```python
        # Use only recent trades
        recent = trade_history[-self.lookback_trades :]
```

with:

```python
        # Use only recent trades. list() first: paper_loop supplies a
        # deque(maxlen=200) and deques do not support slice indexing
        # (TypeError after the min_trades-th in-session trade — audit M1.1).
        recent = list(trade_history)[-self.lookback_trades :]
```

Also check the `len(trade_history)` call above it works for deques (it does — no change).

In `src/trading/paper_loop.py`, add right after the `__init__` method (locate `def __init__` end / first method after it):

```python
    def seed_trade_history(self, history: list[dict]) -> None:
        """Replace the in-memory trade history (state recovery injection).

        Public API for the composition root: preserves the deque(maxlen=200)
        contract that direct assignment of a plain list silently dropped
        (the maxlen loss + deque/list type-swap was the root cause of the
        Kelly TypeError class — audit M1.1).
        """
        from collections import deque as _deque

        self._trade_history = _deque(history, maxlen=200)
```

In `src/api/main.py`, replace (anchor search `_trade_history = trade_history`):

```python
                    app.state.paper_loop._trade_history = trade_history
```

with:

```python
                    app.state.paper_loop.seed_trade_history(trade_history)
```

(keep surrounding log lines untouched).

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/risk/test_kelly_sizer_deque.py tests/risk/test_kelly_sizer.py tests/risk/test_kelly_sizer_edge_cases.py --no-cov -q -p no:cacheprovider`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/risk/kelly_sizer.py backend/src/trading/paper_loop.py backend/src/api/main.py backend/tests/risk/test_kelly_sizer_deque.py
git commit -m "fix(risk): Kelly sizer accepts deque history; seed_trade_history preserves maxlen (audit M1.1)"
```

---

### Task 2 (M1.2): Risk caps see in-flight opens within one iteration

**Files:**
- Modify: `src/trading/paper_loop.py` (`_run_iteration` per-epic loop + `_process_epic` success branch)
- Test: `tests/trading/test_intra_tick_risk_caps.py` (new)

**Mechanics:** `_run_iteration` fetches `current_positions` once and passes the same list to every `_process_epic(epic, current_positions)`; `check_trade` receives it as `open_positions`. Fix = after a successful open, append a minimal stub dict to that shared list. `check_trade` reads only `len()` and, for exposure, `_position_notional_account_ccy(p)` which uses keys `size`, `level`/`entry_price`, `currency`, `epic` (see `src/risk/risk_manager.py::_position_notional_account_ccy`).

- [ ] **Step 1: Write the failing test**

```python
"""Regression: one iteration must not open past max_total_open_positions.

On HEAD the same tick-start position list is passed to every epic, so with
9 open and a cap of 10, every signal in a multi-signal tick sees 9<10 and
is approved (audit M1.2 / finding H3).

Strategy under test: the stub appended by _process_epic after a successful
open. We test the helper contract directly: _register_intra_tick_open()
must mutate the SHARED list in place with a stub check_trade can consume.
"""
from src.trading.paper_loop import PaperTradingLoop


class TestIntraTickRiskCaps:
    def test_register_intra_tick_open_appends_stub_in_place(self):
        loop = PaperTradingLoop.__new__(PaperTradingLoop)
        shared: list[dict] = [{"epic": "XAUUSD", "size": 1.0, "level": 2000.0,
                               "direction": "BUY"}]
        same_ref = shared
        loop._register_intra_tick_open(
            shared, epic="NVDA", direction="BUY", size=2.0, entry_price=500.0
        )
        assert shared is same_ref
        assert len(shared) == 2
        stub = shared[-1]
        assert stub["epic"] == "NVDA"
        assert stub["direction"] == "BUY"
        assert stub["size"] == 2.0
        # _position_notional_account_ccy reads level/entry_price
        assert stub["level"] == 500.0

    def test_risk_manager_counts_stub_against_cap(self):
        """End-to-end: a stub appended mid-tick trips the count cap."""
        from src.risk.risk_manager import _position_notional_account_ccy

        stub = {"epic": "NVDA", "direction": "BUY", "size": 2.0,
                "level": 500.0, "currency": "USD"}
        assert _position_notional_account_ccy(stub) == 1000.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/trading/test_intra_tick_risk_caps.py --no-cov -q -p no:cacheprovider`
Expected: FAIL `AttributeError: ... no attribute '_register_intra_tick_open'`.

- [ ] **Step 3: Implement**

In `src/trading/paper_loop.py` add next to `seed_trade_history`:

```python
    @staticmethod
    def _register_intra_tick_open(
        open_positions: list[dict],
        *,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
    ) -> None:
        """Append a just-opened position stub to the SHARED tick list.

        _run_iteration fetches positions once per tick and hands the same
        list to every _process_epic; without this, N simultaneous signals
        all see the tick-start count and can blow through
        max_total_open_positions / max_total_exposure together (audit M1.2).
        Keys mirror what RiskManager reads: len() for the count cap and
        size/level/currency/epic for _position_notional_account_ccy.
        """
        open_positions.append(
            {
                "epic": epic,
                "direction": direction,
                "size": float(size),
                "level": float(entry_price),
                "entry_price": float(entry_price),
                "currency": "USD",
                "_intra_tick_stub": True,
            }
        )
```

Then in `_process_epic`, in the `exec_result.success` branch — anchor: the block where `signal_info["status"] = "executed"` is set (search `"executed"` assignments right after the successful execute) — add immediately after the status assignment:

```python
            # Audit M1.2: make this open visible to risk checks of the
            # remaining epics in the SAME iteration.
            self._register_intra_tick_open(
                open_positions,
                epic=epic,
                direction=signal.direction.value,
                size=risk_result.position_size,
                entry_price=actual_entry if "actual_entry" in dir() else signal.entry_price,
            )
```

CAREFUL: inside `_process_epic` the fill price variable is `actual_entry` (drift-adjusted). Verify with `grep -n "actual_entry" src/trading/paper_loop.py` and use it directly (drop the `dir()` guard — resolve at implementation time which name is in scope at that point; if `actual_entry` is defined above the success branch unconditionally, use it plainly).

Also handle the min-size retry-success branch (anchor `elif exec_result.error_detail ... "min_size"` → its success path): add the same call there — UNLESS Task 7 has already unified the paths (`_finalize_entry`), in which case the single call lives inside `_finalize_entry`. Task order puts this first, so: add to BOTH branches now; Task 7 will collapse them.

Additionally update the early-exit count check: anchor `if len(current_positions) >= max_positions:` — no change needed (the shared list grows, and the per-epic risk check is the real gate), but ADD a re-check inside the per-epic loop, right before `await self._process_epic(epic, current_positions)`:

```python
            if len(current_positions) >= max_positions:
                logger.info(
                    f"Intra-tick max positions reached "
                    f"({len(current_positions)}/{max_positions}) — stopping epic scan"
                )
                break
```

(`max_positions` is already computed above in `_run_iteration`; verify it is still in scope at the loop.)

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/trading/test_intra_tick_risk_caps.py tests/trading --no-cov -q -p no:cacheprovider`
Expected: new tests PASS, no regressions in tests/trading.

- [ ] **Step 5: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/tests/trading/test_intra_tick_risk_caps.py
git commit -m "fix(trading): intra-tick opens count against risk caps (audit M1.2)"
```

---

### Task 3 (M1.3): `_live_fill` retry requires broker-confirmed rejection

**Files:**
- Modify: `src/execution/order_manager.py` (anchor: `except Exception:` + `pass  # Fall through to no-stops retry`, and the no-stops retry block)
- Test: `tests/execution/test_live_fill_retry_confirmation.py` (new)

**Mechanics:** `_send_position_request` returns `None` on a 10s timeout (`asyncio.wait_for`). Capital.com creates are two-phase (POST then confirm) — a timeout does NOT mean rejected; the order may have filled. On HEAD, `None` falls through to an unconditional no-stops re-create → possible duplicate live position. Fix: before the no-stops retry, if the previous attempt returned `None` (timeout), query `self._broker.list_positions()` and look for a position matching epic+direction+size opened recently; if found, treat as filled.

- [ ] **Step 1: Write the failing test**

```python
"""Regression: a timed-out create that actually FILLED must not be re-sent.

Audit M1.3 / finding H2: confirmation=None (timeout) is not a rejection.
On HEAD the SL/TP-retry chain falls through to an unconditional
'retry without stops' second create_position -> duplicate live position.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.order_manager import OrderManager
from src.execution.schemas import ExecutionMode, ExecutionOrder


def _order() -> ExecutionOrder:
    return ExecutionOrder(
        epic="NVDA", direction="BUY", size=2.0, entry_price=500.0,
        stop_loss=490.0, take_profit=520.0,
    )


def _filled_broker_position(deal_id="DEAL-FILLED-1"):
    pos = MagicMock()
    pos.deal_id = deal_id
    pos.epic = "NVDA"
    pos.direction = MagicMock(value="BUY")
    pos.size = 2.0
    pos.level = 500.1
    return pos


@pytest.mark.asyncio
async def test_timeout_after_fill_does_not_duplicate_position():
    broker = MagicMock()
    # First create (with stops) raises a CapitalComError-shaped SL/TP error,
    # corrected-levels retry TIMES OUT (None), but the broker actually filled:
    from src.broker.exceptions import CapitalComError

    broker.create_position = AsyncMock(
        side_effect=[CapitalComError("error.invalid.stoploss.maxvalue"),
                     TimeoutError()]  # second call wrapped by wait_for -> None
    )
    broker.list_positions = AsyncMock(return_value=[_filled_broker_position()])
    broker.update_position = AsyncMock()

    om = OrderManager(broker=broker, mode=ExecutionMode.DEMO)
    result = await om._live_fill(_order())

    # The fill was found on the broker: success, the timed-out create's
    # position is adopted, and NO third create_position is sent.
    assert result.success is True
    assert result.deal_id == "DEAL-FILLED-1"
    assert broker.create_position.await_count == 2  # NOT 3


@pytest.mark.asyncio
async def test_timeout_with_no_fill_still_retries_no_stops():
    from src.broker.exceptions import CapitalComError

    confirmation = MagicMock()
    confirmation.deal_status = "OPEN"
    confirmation.deal_id = "DEAL-NS-1"
    confirmation.deal_reference = "ref-1"
    confirmation.level = 500.2

    broker = MagicMock()
    broker.create_position = AsyncMock(
        side_effect=[CapitalComError("error.invalid.stoploss.maxvalue"),
                     TimeoutError(),       # corrected retry times out
                     confirmation]         # no-stops retry succeeds
    )
    broker.list_positions = AsyncMock(return_value=[])  # nothing filled
    broker.update_position = AsyncMock()

    om = OrderManager(broker=broker, mode=ExecutionMode.DEMO)
    result = await om._live_fill(_order())

    assert result.success is True
    assert broker.create_position.await_count == 3
```

ADAPT at implementation time: check `OrderManager.__init__` signature (`grep -n "def __init__" src/execution/order_manager.py`), the real `CapitalComError` import path (`src/broker/exceptions.py`), how `_live_fill` is invoked (maybe via `submit_order`), and the Position model attrs (`direction` may be a str or enum — mirror what `_live_fill`'s adoption code will read). The two assertions that matter: `await_count == 2` (no duplicate) and adopted deal_id.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/execution/test_live_fill_retry_confirmation.py --no-cov -q -p no:cacheprovider`
Expected: first test FAILS with `await_count == 3` (duplicate create sent) or with the result adopting the wrong position.

- [ ] **Step 3: Implement**

In `src/execution/order_manager.py`:

(a) Add a helper method:

```python
    async def _find_recent_fill(
        self, epic: str, direction: str, size: float
    ):
        """After a create timeout, check whether the order actually filled.

        A 10s confirm timeout does NOT mean the broker rejected the create
        (two-phase POST+confirm). Re-submitting blindly opened duplicate
        positions (audit M1.3). Match on epic+direction+size — the position
        opened by the timed-out request, if any.
        Returns the broker Position or None.
        """
        try:
            positions = await asyncio.wait_for(self._broker.list_positions(), timeout=10.0)
        except Exception as e:
            logger.warning(f"[{epic}] Post-timeout fill check failed: {e}")
            return None
        for pos in positions or []:
            pos_dir = getattr(pos.direction, "value", pos.direction)
            if (
                pos.epic == epic
                and str(pos_dir) == direction
                and abs(float(pos.size) - float(size)) < 1e-9
            ):
                return pos
        return None
```

(b) In the corrected-SL/TP retry branch, replace:

```python
                    except Exception:
                        pass  # Fall through to no-stops retry
```

with:

```python
                    except CapitalComError as e2:
                        logger.warning(
                            f"[{order.epic}] Corrected SL/TP create rejected: {e2}"
                        )
```

(verify `CapitalComError` is already imported in the module; it is — the outer branch catches it).

(c) Immediately BEFORE the "Second attempt: retry without SL/TP entirely" block, insert a timeout-fill check. The corrected-retry result variable is `confirmation`; `None` means timeout:

```python
                # Audit M1.3: confirmation=None means the confirm timed out,
                # NOT that the broker rejected the create. Check for a fill
                # before re-submitting — blind re-create duplicated positions.
                if confirmation is None:
                    filled = await self._find_recent_fill(
                        order.epic, order.direction, order.size
                    )
                    if filled is not None:
                        logger.warning(
                            f"[{order.epic}] Timed-out create actually FILLED "
                            f"(deal {filled.deal_id}) — adopting, no re-submit"
                        )
                        applied_sl, applied_tp = None, None
                        try:
                            applied_sl, applied_tp = await self._set_stops_after_fill(
                                deal_id=filled.deal_id,
                                epic=order.epic,
                                direction=order.direction,
                                fill_price=float(filled.level),
                                original_sl=order.stop_loss,
                                original_tp=order.take_profit,
                            )
                        except Exception as ex:
                            logger.warning(f"[{order.epic}] Stops push after adopt failed: {ex}")
                        return ExecutionResult(
                            success=True,
                            deal_id=filled.deal_id,
                            fill_price=float(filled.level),
                            slippage=abs(float(filled.level) - order.entry_price),
                            actual_stop_loss=applied_sl,
                            actual_take_profit=applied_tp,
                        )
```

ADAPT: check `_set_stops_after_fill` signature/return (read its def — it exists, anchor `async def _set_stops_after_fill`) and mirror how the existing no-stops success path calls it. Scope check: the same `confirmation is None` guard must ALSO cover the very first create attempt's timeout path — read the full `_live_fill` flow top-down and apply the same check before ANY re-submit that follows a `None` confirmation (there are two such fall-throughs: after the first create and after the corrected retry).

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/execution/test_live_fill_retry_confirmation.py tests/execution --no-cov -q -p no:cacheprovider`
Expected: ALL PASS (existing `test_order_manager` suite asserts per-error-subclass behavior — must stay green).

- [ ] **Step 5: Commit**

```bash
git add backend/src/execution/order_manager.py backend/tests/execution/test_live_fill_retry_confirmation.py
git commit -m "fix(execution): live-fill retry requires broker-confirmed rejection — no duplicate create after confirm timeout (audit M1.3)"
```

---

### Task 4 (M1.4): Reconciler outage must not substitute an empty book

**Files:**
- Modify: `src/trading/paper_loop.py` (anchor: `Reconciler position fetch failed`)
- Test: `tests/trading/test_reconciler_outage.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Regression: a broker fetch failure in DEMO/LIVE must SKIP the reconciler
tick, not run it against an empty book (audit M1.4 / finding H4).

On HEAD the except branch falls back to get_paper_positions(), which
returns [] for any non-PAPER mode; the empty list then unregisters every
trailing-stop state and (after 600s) arms false UNRECONCILED closes.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.schemas import ExecutionMode
from src.trading.paper_loop import PaperTradingLoop


@pytest.mark.asyncio
async def test_fetch_failure_skips_tick_in_demo_mode():
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop.execution_engine = MagicMock(mode=ExecutionMode.DEMO)
    loop.get_positions_async = AsyncMock(side_effect=TimeoutError("broker down"))
    loop._detect_broker_closed = AsyncMock()
    loop._update_trailing_stops = AsyncMock()
    loop._check_stop_losses = AsyncMock()
    loop._reconciler_skip_count = 0

    await loop._run_reconciler_tick()

    loop._detect_broker_closed.assert_not_awaited()
    loop._update_trailing_stops.assert_not_awaited()
    loop._check_stop_losses.assert_not_awaited()
    assert loop._reconciler_skip_count == 1


@pytest.mark.asyncio
async def test_fetch_failure_in_paper_mode_uses_local_cache():
    """PAPER mode has a genuine local book — the legacy fallback stays."""
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop.execution_engine = MagicMock(mode=ExecutionMode.PAPER)
    loop.get_positions_async = AsyncMock(side_effect=TimeoutError("broker down"))
    local_book = [{"deal_id": "P1", "epic": "XAUUSD"}]
    loop.get_paper_positions = MagicMock(return_value=local_book)
    loop._detect_broker_closed = AsyncMock()
    loop._update_trailing_stops = AsyncMock()
    loop._check_stop_losses = AsyncMock()
    loop._reconciler_skip_count = 0

    await loop._run_reconciler_tick()

    loop._detect_broker_closed.assert_awaited_once_with(local_book)
```

ADAPT: `_run_reconciler_tick` may reference more attributes on the stub (run and add MagicMocks until the two assertions can execute). `_reconciler_skip_count` is NEW state added in Step 3 — initialize in `__init__`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/trading/test_reconciler_outage.py --no-cov -q -p no:cacheprovider`
Expected: first test FAILS (`_detect_broker_closed` WAS awaited — with `[]`).

- [ ] **Step 3: Implement**

In `_run_reconciler_tick`, replace:

```python
        try:
            current_positions = await asyncio.wait_for(self.get_positions_async(), timeout=10.0)
        except (TimeoutError, Exception) as e:
            logger.warning(f"Reconciler position fetch failed ({e}), using local cache")
            current_positions = self.get_paper_positions()
```

with:

```python
        try:
            current_positions = await asyncio.wait_for(self.get_positions_async(), timeout=10.0)
        except (TimeoutError, Exception) as e:
            from src.execution.schemas import ExecutionMode as _EM

            if self.execution_engine.mode == _EM.PAPER:
                # PAPER keeps a genuine local book — safe fallback.
                logger.warning(f"Reconciler position fetch failed ({e}), using local cache")
                current_positions = self.get_paper_positions()
            else:
                # DEMO/LIVE: get_paper_positions() returns [] here. Running
                # the tick against an empty book unregisters every trailing
                # state and arms false UNRECONCILED closes (audit M1.4).
                # Skip the tick; the next one (15s) retries.
                self._reconciler_skip_count = getattr(self, "_reconciler_skip_count", 0) + 1
                logger.warning(
                    f"Reconciler position fetch failed ({e}) — skipping tick "
                    f"#{self._reconciler_skip_count} (no local book in "
                    f"{self.execution_engine.mode.value} mode)"
                )
                return
```

And in `__init__` (near the other reconciler state, anchor `self._reconciler_lock`):

```python
        self._reconciler_skip_count: int = 0
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/trading/test_reconciler_outage.py tests/trading/test_reconciler_lifecycle.py --no-cov -q -p no:cacheprovider`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/tests/trading/test_reconciler_outage.py
git commit -m "fix(trading): reconciler skips tick on broker fetch failure in DEMO/LIVE — no empty-book wipe (audit M1.4)"
```

---

### Task 5 (M1.7): SL/TP side validation at the risk gate

**Files:**
- Modify: `src/risk/risk_manager.py` (anchor: `# 4-ter. Backstop R:R floor`)
- Test: `tests/risk/test_sl_tp_side_validation.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Regression: side-inverted SL/TP must be REJECTED at the risk gate.

Audit M1.7: check_trade trusted the strategy pair verbatim and the R:R
floor used abs() distances, so a BUY with SL above entry sailed through —
the exact class of the 2026-04-28 R:R-inversion incident.
"""
import pytest

# Build a minimal approved-path signal; mirror the fixture style of
# tests/risk/test_risk_manager.py (import its helpers/fixtures if present
# rather than redefining: check that file FIRST and reuse its RiskManager
# construction + TradingSignal factory).
from tests.risk.test_risk_manager import *  # noqa: F401,F403 — reuse fixtures


@pytest.mark.parametrize(
    "direction,entry,sl,tp",
    [
        ("BUY", 100.0, 105.0, 110.0),   # SL above entry on a BUY
        ("BUY", 100.0, 95.0, 98.0),     # TP below entry on a BUY -> also wrong side? NO: tp<entry is inverted for BUY
        ("SELL", 100.0, 95.0, 90.0),    # SL below entry on a SELL
        ("SELL", 100.0, 105.0, 110.0),  # TP above entry on a SELL
    ],
)
def test_inverted_levels_rejected(direction, entry, sl, tp, make_risk_manager, make_signal):
    rm = make_risk_manager()
    signal = make_signal(direction=direction, entry_price=entry,
                         suggested_stop=sl, suggested_tp=tp)
    result = rm.check_trade(signal=signal, equity=10_000.0, atr=1.0,
                            open_positions=[])
    assert result.approved is False
    assert "side" in (result.rejection_reason or "").lower()
```

ADAPT (mandatory): open `tests/risk/test_risk_manager.py` first and mirror its actual construction of RiskManager and TradingSignal (the `make_risk_manager`/`make_signal` factories above are illustrative — if no such fixtures exist, inline the construction copied from an existing approval test in that file). The 4 parametrized cases must each hit the gate with BOTH suggested_stop and suggested_tp set (the §4-bis trusted-pair path).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/risk/test_sl_tp_side_validation.py --no-cov -q -p no:cacheprovider`
Expected: FAIL — inverted signals come back `approved=True` (or rejected for an unrelated reason; assert message check fails).

- [ ] **Step 3: Implement**

In `src/risk/risk_manager.py`, immediately BEFORE the `# 4-ter. Backstop R:R floor` block, insert:

```python
        # 4-quater. Side validation (audit M1.7). A side-inverted pair —
        # BUY with SL>=entry or TP<=entry; SELL mirrored — passed every
        # gate because the R:R floor below uses abs() distances. This is
        # the 2026-04-28 inversion class: reject, never silently repair.
        _is_buy = signal.direction.value == "BUY"
        _sl_wrong = (stop_loss >= signal.entry_price) if _is_buy else (
            stop_loss <= signal.entry_price
        )
        _tp_wrong = (take_profit <= signal.entry_price) if _is_buy else (
            take_profit >= signal.entry_price
        )
        if _sl_wrong or _tp_wrong:
            reason = (
                f"SL/TP on wrong side of entry for {signal.direction.value}: "
                f"entry={signal.entry_price:.5f} SL={stop_loss:.5f} "
                f"TP={take_profit:.5f}"
            )
            logger.warning(f"[{signal.epic}] Trade rejected: {reason}")
            return self._reject(signal, reason, audit)
```

ADAPT: mirror how the 4-ter rejection actually returns (read the lines right after the `rr_check < min_rr` reason — copy that exact return/audit pattern instead of the illustrative `self._reject(...)`). Place AFTER §4-bis (so `stop_loss`/`take_profit` are the final pair) and BEFORE §4-ter.

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/risk/test_sl_tp_side_validation.py tests/risk --no-cov -q -p no:cacheprovider`
Expected: ALL PASS (watch `test_stop_loss_direction_fix.py` and `test_risk_manager.py` for interactions).

- [ ] **Step 5: Commit**

```bash
git add backend/src/risk/risk_manager.py backend/tests/risk/test_sl_tp_side_validation.py
git commit -m "fix(risk): reject side-inverted SL/TP at the gate (audit M1.7)"
```

---

### Task 6 (M1.9): CLOSE Trade row P&L backfill on idempotent re-finalize

**Files:**
- Modify: `src/trading/paper_loop.py` (anchor: `Skip duplicate CLOSE Trade row`)
- Modify: `src/execution/execution_engine.py` (anchor: `Idempotent CLOSE Trade row (Invariant #10)`)
- Test: `tests/trading/test_close_row_pnl_backfill.py` (new)

**Mechanics:** locally-initiated closes insert the CLOSE Trade row with `profit_loss=NULL` (engine path, broker P&L unknown yet). When the reconciler later resolves real P&L, both idempotency guards find the existing row and skip — the NULL is never repaired (audit M1.9).

- [ ] **Step 1: Write the failing test**

```python
"""Regression: the idempotency guard must BACKFILL profit_loss/price on the
existing CLOSE Trade row instead of skip-only (audit M1.9)."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_loop_guard_backfills_null_pnl():
    """_persist_position_close: existing CLOSE row with NULL pnl gets the
    reconciled values written onto it."""
    from src.trading.paper_loop import PaperTradingLoop

    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    # ... construct via the established pattern in
    # tests/trading/test_close_detection.py (__new__ + minimal attrs +
    # mocked session factory). The session must return:
    #   - a Position row (so the update path runs)
    #   - an existing CLOSE Trade row with profit_loss=None, price=entry
    existing_trade = MagicMock()
    existing_trade.id = 7
    existing_trade.profit_loss = None
    existing_trade.price = Decimal("2000.0")
    # ... wire (await session.execute(...)).scalar_one_or_none() -> existing_trade
    #     for the trades SELECT; follow test_close_detection.py's session stub.

    await loop._persist_position_close(
        deal_id="POS-1", epic="XAUUSD", direction="BUY", size=1.0,
        entry_price=2000.0, exit_price=2010.0, pnl=10.0, close_reason="SL",
    )

    assert existing_trade.profit_loss == Decimal("10.0")
    assert existing_trade.price == Decimal("2010.0")
```

ADAPT (mandatory): `_persist_position_close`'s real signature and the session-stub wiring must be copied from `tests/trading/test_close_detection.py` / `test_close_no_synthetic_pnl.py` (they already stub the async session + repositories for this exact method). The assertion contract is the only fixed part: existing row's `profit_loss`/`price` mutated when the incoming pnl is not None. Add a second test: incoming `pnl=None` must NOT clobber an existing non-NULL value.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/trading/test_close_row_pnl_backfill.py --no-cov -q -p no:cacheprovider`
Expected: FAIL — `existing_trade.profit_loss` is still `None` (guard skipped).

- [ ] **Step 3: Implement**

In `src/trading/paper_loop.py`, the guard branch:

```python
                if existing_close is not None:
                    await session.commit()
                    logger.info(
                        f"Skip duplicate CLOSE Trade row for {deal_id} — ..."
                    )
```

becomes:

```python
                if existing_close is not None:
                    # Audit M1.9: locally-initiated closes insert this row
                    # with profit_loss=NULL (engine path, broker P&L not yet
                    # known). Backfill once reconciliation has real values —
                    # never clobber a non-NULL value with NULL.
                    backfilled = False
                    if pnl_decimal is not None and existing_close.profit_loss is None:
                        existing_close.profit_loss = pnl_decimal
                        backfilled = True
                    if exit_price and existing_close.price != Decimal(str(exit_price)):
                        existing_close.price = Decimal(str(exit_price))
                        backfilled = True
                    await session.commit()
                    logger.info(
                        f"{'Backfilled' if backfilled else 'Skip duplicate'} "
                        f"CLOSE Trade row for {deal_id} — position {pos.id} "
                        f"trade {existing_close.id} (idempotency guard)"
                    )
```

(verify the local variable names `pnl_decimal`, `exit_price`, `pos` from the surrounding code — they are in scope per the current implementation.)

In `src/execution/execution_engine.py`, mirror: the `if existing_close.scalar_one_or_none() is None:` INSERT branch gets an `else` that backfills the same two fields from `position_db.profit_loss` / `fill_price` under the same never-clobber-with-NULL rule (assign the scalar to a variable first: `_existing = existing_close.scalar_one_or_none()`).

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/trading/test_close_row_pnl_backfill.py tests/trading/test_close_detection.py tests/trading/test_close_no_synthetic_pnl.py --no-cov -q -p no:cacheprovider`
Expected: ALL PASS. The duplicate-row invariant (#10, `ce2c3e1`) must stay intact: no new INSERT in the guard branch.

- [ ] **Step 5: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/src/execution/execution_engine.py backend/tests/trading/test_close_row_pnl_backfill.py
git commit -m "fix(trading): idempotency guard backfills CLOSE-row P&L instead of skip-only (audit M1.9)"
```

---

### Task 7 (M1.5): Min-size lift bounded + unified `_finalize_entry`

**Files:**
- Modify: `src/trading/paper_loop.py` (anchors: `"If size is close to minimum"` comment + `risk_result.position_size = min_deal_size`; the retry block `error_type") == "min_size"`; the main success branch after `exec_result.success`)
- Test: `tests/trading/test_min_size_lift_bounded.py` (new), `tests/trading/test_entry_paths_parity.py` (new)

**Two sub-fixes:**

(a) **Bounded lift.** The lift to broker minimum is unconditional; re-bound it with the risk manager's exposure cap (7-bis pattern: `final = min(lifted, cap)` and reject if the cap itself is below the broker minimum).

(b) **Unified success path.** The min-size retry-success block (~70 lines after the retry `execute_signal`) is a hand-copied subset of the main success branch missing: broker `update_stops` align, `_level_deviations` tracking, "SUSPICIOUS LEVELS" R:R check, trade-logger EXECUTED rows, EXECUTED signal-audit persistence. Extract the main branch's post-fill sequence into `async def _finalize_entry(self, *, epic, signal, signal_info, risk_result, exec_result, market_data, open_positions, equity, signal_id) -> None` and call it from BOTH branches.

- [ ] **Step 1: Write the failing tests**

`tests/trading/test_min_size_lift_bounded.py`:

```python
"""Regression: lifting size to the broker minimum must re-check the
exposure cap (audit M1.5a). Approved 0.2 units with broker min 1.0 was
executed at 5x the risk-approved size, silently."""
from src.trading.paper_loop import PaperTradingLoop


def test_bounded_lift_helper_caps_at_exposure_limit():
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    # cap allows 0.8 units; broker minimum is 1.0 -> lift NOT allowed
    final, ok = loop._bounded_min_size_lift(
        approved_size=0.2, min_deal_size=1.0, max_size_by_exposure=0.8
    )
    assert ok is False

    # cap allows 3.0 -> lift to exactly the broker minimum
    final, ok = loop._bounded_min_size_lift(
        approved_size=0.2, min_deal_size=1.0, max_size_by_exposure=3.0
    )
    assert ok is True and final == 1.0
```

`tests/trading/test_entry_paths_parity.py`:

```python
"""Regression: the min-size retry success path must produce the same
post-fill side effects as the main success path (audit M1.5b). On HEAD it
is a diverged copy missing stops-align, _level_deviations, the SUSPICIOUS
LEVELS check, EXECUTED trade-log rows and the signal-audit link.

Contract test: both branches call the SAME _finalize_entry method."""
import inspect

from src.trading.paper_loop import PaperTradingLoop


def test_finalize_entry_exists_and_both_branches_use_it():
    assert hasattr(PaperTradingLoop, "_finalize_entry")
    src = inspect.getsource(PaperTradingLoop._process_epic)
    assert src.count("_finalize_entry(") >= 2, (
        "both the main success branch and the min-size retry success branch "
        "must delegate to _finalize_entry"
    )
    # The retry branch must no longer carry its own copy of the
    # suspicious-levels check (it lives once, inside _finalize_entry).
    finalize_src = inspect.getsource(PaperTradingLoop._finalize_entry)
    assert "SUSPICIOUS" in finalize_src
    assert src.count("SUSPICIOUS") == 0
```

(Source-inspection guard mirrors the repo's established anti-regression pattern, e.g. `test_strategy_3_fuzzy_match_source_is_deleted`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/trading/test_min_size_lift_bounded.py tests/trading/test_entry_paths_parity.py --no-cov -q -p no:cacheprovider`
Expected: both FAIL (`_bounded_min_size_lift`/`_finalize_entry` don't exist).

- [ ] **Step 3a: Implement bounded lift**

Add helper:

```python
    @staticmethod
    def _bounded_min_size_lift(
        *, approved_size: float, min_deal_size: float, max_size_by_exposure: float
    ) -> tuple[float, bool]:
        """Lift an approved size to the broker minimum WITHOUT exceeding the
        exposure cap (audit M1.5a — mirrors RiskManager step 7-bis bounding).

        Returns (final_size, ok). ok=False means even the broker minimum
        violates the cap: the trade must be rejected, not silently lifted.
        """
        if approved_size >= min_deal_size:
            return approved_size, True
        if min_deal_size > max_size_by_exposure:
            return approved_size, False
        return min_deal_size, True
```

At BOTH lift sites (`risk_result.position_size = min_deal_size` after the "close to minimum" comment, and the retry-path `risk_result.position_size = broker_min`):
- compute `max_size_by_exposure` the way RiskManager does (read `risk_manager.py` step 7-bis for the formula source: `risk_result.audit` carries `max_size_by_exposure` when sizing ran — use `risk_result.audit.get("sizing", {}).get("max_size_by_exposure")`; verify the actual audit key by grepping `max_size_by_exposure` in risk_manager.py; if absent from the audit payload, add it there as part of this task);
- call the helper; on `ok=False` set `signal_info["status"]="rejected"`, `rejection_reason="broker minimum exceeds exposure cap"`, log, and `return`;
- fix the stale comment: replace `# If size is close to minimum (>=80%), round up instead of rejecting` with `# Lift to broker minimum, bounded by the exposure cap (audit M1.5a).`

- [ ] **Step 3b: Extract `_finalize_entry`**

Mechanical extraction from `_process_epic`'s main success branch (the block running after `exec_result.success` from the broker `update_stops` alignment down to and including the EXECUTED signal-audit persistence — the audit's anchors: stops-align `update_stops`, `_level_deviations`, `SUSPICIOUS LEVELS`, `log_signal/log_execution` EXECUTED, signal-audit EXECUTED + position link, and the Task-2 `_register_intra_tick_open` call):

1. Cut that contiguous region into `async def _finalize_entry(self, *, epic, signal, signal_info, risk_result, exec_result, market_data, open_positions, equity, signal_id) -> None`, placed right after `_process_epic`.
2. Pass every free variable as a keyword parameter; do NOT reach back into `_process_epic` locals. Run `ruff check` — `F821 undefined name` errors enumerate any missed parameter.
3. Replace the cut region with `await self._finalize_entry(epic=epic, signal=signal, ...)`.
4. Delete the retry-success block's hand copy entirely and call `await self._finalize_entry(...)` with the retry-scope variables.
5. The drift-adjust + side-validation code at the TOP of the retry block (the `_validate_sl_side` section) stays where it is — only the post-fill duplication is unified.

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/trading --no-cov -q -p no:cacheprovider`
Expected: ALL PASS — this is the highest-risk task; the full tests/trading suite is the gate, plus ruff/black on paper_loop.py.

- [ ] **Step 5: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/tests/trading/test_min_size_lift_bounded.py backend/tests/trading/test_entry_paths_parity.py
git commit -m "fix(trading): bound min-size lift by exposure cap + unify entry finalization (audit M1.5)"
```

---

### Task 8 (M1.6): `partial_close` honesty

**Files:**
- Modify: `src/execution/execution_engine.py` (anchor: `remaining_size = round(original_size * (1.0 - close_pct), 6)` and the reopen-failure `return ExecutionResult(success=True, ...)`)
- Modify: `src/trading/paper_loop.py` (anchor: the `partial_close` caller in `_update_trailing_stops`, checks `result.success`)
- Modify: `src/execution/schemas.py` (ExecutionResult: add optional field)
- Test: `tests/execution/test_partial_close_honesty.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Regression: partial_close must not report success when the reopen leg
failed (the position is FULLY closed — the runner is gone), and must refuse
scale-outs whose remainder is below the broker minimum (audit M1.6)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode, ExecutionResult


@pytest.mark.asyncio
async def test_reopen_failure_reports_degenerate_full_close():
    engine = ExecutionEngine(mode=ExecutionMode.DEMO)
    # wire engine._order_manager with: close leg OK, reopen leg FAILS
    om = MagicMock()
    om.submit_order = AsyncMock(side_effect=[
        ExecutionResult(success=True, deal_id="D1", fill_price=100.0),  # close
        ExecutionResult(success=False, error="rejected"),               # reopen
    ])
    engine._order_manager = om

    result = await engine.partial_close(deal_id="D1", close_pct=0.5)

    assert result.success is False
    assert result.error_detail and result.error_detail.get("degenerate_full_close") is True


@pytest.mark.asyncio
async def test_remainder_below_min_deal_size_refused():
    engine = ExecutionEngine(mode=ExecutionMode.DEMO)
    om = MagicMock()
    om.submit_order = AsyncMock()
    engine._order_manager = om

    result = await engine.partial_close(
        deal_id="D1", close_pct=0.5, min_deal_size=1.0,  # remainder 0.5 < 1.0
    )

    assert result.success is False
    om.submit_order.assert_not_awaited()  # nothing closed
```

ADAPT (mandatory): read `partial_close`'s real signature first (`grep -n "async def partial_close" src/execution/execution_engine.py`) — it takes more args (position info, size); mirror them in the tests. If it has no `min_deal_size` param, the test defines the NEW contract: add the optional param (None = skip check, preserving callers that can't supply it) and have the trailing-stop caller pass `self._min_deal_size_cache.get(epic)`.

- [ ] **Step 2: Run tests to verify they fail**

Expected: first FAILS (`success is True` today); second FAILS (`TypeError: unexpected keyword` or order submitted).

- [ ] **Step 3: Implement**

(a) `src/execution/schemas.py`: ExecutionResult already carries `error_detail: dict | None` (verify; if not, add `error_detail: dict | None = None`).

(b) `partial_close`: at the top, after computing `remaining_size`:

```python
        if min_deal_size is not None and remaining_size < float(min_deal_size):
            msg = (
                f"Partial close refused: remainder {remaining_size:.4f} < "
                f"broker minimum {min_deal_size} — scale-out would degenerate "
                f"to a full close (audit M1.6)"
            )
            logger.warning(f"[{deal_id}] {msg}")
            return ExecutionResult(success=False, deal_id=deal_id, error=msg)
```

(c) Reopen-failure return: replace `success=True` with:

```python
        return ExecutionResult(
            success=False,
            deal_id=deal_id,
            fill_price=close_result.fill_price,
            error=f"Reopen of remaining {remaining_size:.4f} failed: {reopen_result.error}",
            error_detail={"degenerate_full_close": True},
        )
```

(d) Caller in `paper_loop._update_trailing_stops` (anchor `if result.success` after the partial-close call): add an else-branch:

```python
            else:
                detail = result.error_detail or {}
                if detail.get("degenerate_full_close"):
                    logger.error(
                        f"🚨 [{epic}] TP1 scale-out degenerated to FULL close "
                        f"({deal_id}): runner is gone — {result.error}"
                    )
                    # The position no longer exists at the broker: let the
                    # reconciler's close detection finalize it with real P&L.
                else:
                    logger.warning(f"[{epic}] Partial close failed: {result.error}")
```

ADAPT: mirror the audit-record call the success branch makes ("TP1 partial close 50%") — the degenerate branch must NOT write that audit string; check what the success branch persists and ensure the failure branch records nothing misleading.

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/execution/test_partial_close_honesty.py tests/execution tests/trading/test_trailing_stop_gap_scenarios.py --no-cov -q -p no:cacheprovider`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/execution/execution_engine.py backend/src/execution/schemas.py backend/src/trading/paper_loop.py backend/tests/execution/test_partial_close_honesty.py
git commit -m "fix(execution): partial_close refuses sub-minimum remainders and reports degenerate full closes honestly (audit M1.6)"
```

---

### Task 9 (M1.8 partial): SECRET_KEY hard-fail + execution-mode mismatch raise

**Files:**
- Modify: `src/utils/config.py` (anchor: `Using default SECRET_KEY` warning validator ~643-655)
- Modify: `src/api/main.py` (anchor: `use_demo = desired == "DEMO" and settings.use_demo`)
- Test: `tests/api/test_boot_guards.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Regression: two silent boot misconfigurations must hard-fail (audit M1.8).

1. Non-demo (LIVE-capable) settings with the default SECRET_KEY would mint
   forgeable JWTs guarding the kill-switch.
2. EXECUTION_MODE=LIVE + USE_DEMO=true silently left the throwaway PAPER
   engine simulating fills while the dashboard showed trading activity.
"""
import pytest


def test_default_secret_key_rejected_when_not_demo(monkeypatch):
    from src.utils.config import Settings

    with pytest.raises(Exception) as exc_info:
        Settings(
            use_demo=False,
            secret_key="dev_secret_key_change_in_production",
            auth_required=True,
            _env_file=None,  # do not read backend/.env
        )
    assert "SECRET_KEY" in str(exc_info.value)


def test_default_secret_key_only_warns_in_demo():
    from src.utils.config import Settings

    s = Settings(use_demo=True,
                 secret_key="dev_secret_key_change_in_production",
                 _env_file=None)
    assert s.use_demo is True  # constructed fine


def test_execution_mode_mismatch_raises():
    from src.api.main import _validate_execution_mode_request

    with pytest.raises(RuntimeError, match="EXECUTION_MODE"):
        _validate_execution_mode_request(desired="LIVE", use_demo=True)
    with pytest.raises(RuntimeError, match="EXECUTION_MODE"):
        _validate_execution_mode_request(desired="DEMO", use_demo=False)
    # coherent combos pass
    _validate_execution_mode_request(desired="DEMO", use_demo=True)
    _validate_execution_mode_request(desired="LIVE", use_demo=False)
    _validate_execution_mode_request(desired="PAPER", use_demo=True)
```

ADAPT: `Settings` may require other mandatory fields without `.env` — pass the minimum or use `monkeypatch.setenv`. Check how existing config tests construct Settings (`grep -rn "Settings(" tests/ | grep -v mock | head`).

- [ ] **Step 2: Run tests to verify they fail**

Expected: test 1 FAILS (no exception — validator only warns); test 3 FAILS (`ImportError: _validate_execution_mode_request`).

- [ ] **Step 3: Implement**

(a) `config.py` validator (currently warn-only): inside the existing SECRET_KEY validator, after the warning, add the hard gate. The validator likely lacks access to `use_demo` (field validators run per-field) — use a `model_validator(mode="after")`:

```python
    @model_validator(mode="after")
    def _enforce_secret_key_outside_demo(self):
        if not self.use_demo and self.secret_key == "dev_secret_key_change_in_production":
            raise ValueError(
                "SECRET_KEY is still the default in a non-demo configuration. "
                "Every JWT (kill-switch, order endpoints) would be forgeable. "
                "Set SECRET_KEY before any LIVE deploy (audit M1.8)."
            )
        return self
```

(verify `model_validator` is imported from pydantic; keep the existing warning for demo mode untouched).

(b) `main.py`: add a module-level helper above `lifespan`:

```python
def _validate_execution_mode_request(*, desired: str, use_demo: bool) -> None:
    """Refuse silently-incoherent mode combos (audit M1.8).

    EXECUTION_MODE=LIVE with USE_DEMO=true previously no-op'd the engine
    upgrade: the backend kept simulating fills on the throwaway PAPER
    engine with zero warning.
    """
    if desired == "LIVE" and use_demo:
        raise RuntimeError(
            "EXECUTION_MODE=LIVE requires USE_DEMO=false — refusing to boot "
            "into silent PAPER simulation."
        )
    if desired == "DEMO" and not use_demo:
        raise RuntimeError(
            "EXECUTION_MODE=DEMO requires USE_DEMO=true — refusing to boot "
            "into silent PAPER simulation."
        )
```

and call it in lifespan right before the `use_demo = desired == "DEMO" and ...` block:

```python
            _validate_execution_mode_request(desired=desired, use_demo=settings.use_demo)
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/api/test_boot_guards.py tests/api/test_broker_connect_retry.py tests/utils --no-cov -q -p no:cacheprovider`
Expected: ALL PASS. ALSO sanity-check the running config still constructs: `.venv/Scripts/python.exe -c "from src.utils.config import get_settings; print(get_settings().use_demo)"` → `True` (current .env is demo: must NOT raise).

- [ ] **Step 5: Commit**

```bash
git add backend/src/utils/config.py backend/src/api/main.py backend/tests/api/test_boot_guards.py
git commit -m "fix(security): hard-fail boot on default SECRET_KEY outside demo + on EXECUTION_MODE/USE_DEMO mismatch (audit M1.8 partial)"
```

---

### Task 10 (M1.10): Frontend — safe-method-only retry + envelope error surfacing

**Files:**
- Modify: `frontend/src/app/core/interceptors/error.interceptor.ts` (anchor: `RETRYABLE_STATUSES.has(status) && attempt < MAX_RETRIES`)
- Modify: `frontend/src/app/core/services/api.service.ts` (all four `.pipe(map(res => res.data))`)
- Test: `frontend/src/app/core/interceptors/error.interceptor.spec.ts` (new), extend `frontend/src/app/core/services/api.service.spec.ts` (create — none exists)

Run frontend tests with: `cd frontend && npx ng test --watch=false` (Vitest; globals describe/it/expect/vi available, jsdom).

- [ ] **Step 1: Write the failing tests**

`error.interceptor.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withInterceptors, HttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { errorInterceptor } from './error.interceptor';

describe('errorInterceptor retry policy', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => ctrl.verify());

  it('does NOT retry a POST on a retryable status', () => {
    let error: unknown;
    http.post('/api/trading/emergency-stop', {}).subscribe({ error: e => (error = e) });
    ctrl.expectOne('/api/trading/emergency-stop')
        .flush('', { status: 503, statusText: 'Service Unavailable' });
    // a second request would throw 'expected none' in ctrl.verify()
    expect(error).toBeTruthy();
  });

  it('retries a GET on a retryable status', async () => {
    vi.useFakeTimers();
    let value: unknown;
    http.get('/api/dashboard').subscribe({ next: v => (value = v) });
    ctrl.expectOne('/api/dashboard')
        .flush('', { status: 503, statusText: 'Service Unavailable' });
    await vi.advanceTimersByTimeAsync(1000); // 2^0 * 1000 backoff
    ctrl.expectOne('/api/dashboard').flush({ ok: true });
    expect(value).toEqual({ ok: true });
    vi.useRealTimers();
  });
});
```

(NOTE: interceptor name — check the export in error.interceptor.ts; ToastService is injected via `inject()`: provide a stub `{ provide: ToastService, useValue: { error: vi.fn(), warning: vi.fn() } }` if TestBed errors on it.)

`api.service.spec.ts` (new file):

```typescript
import { TestBed } from '@angular/core/testing';
import { provideHttpClient, HttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ApiService } from './api.service';

describe('ApiService envelope handling', () => {
  let api: ApiService;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => ctrl.verify());

  it('throws when the envelope reports success:false at HTTP 200', () => {
    let error: Error | undefined;
    api.get('/test').subscribe({ error: e => (error = e) });
    ctrl.expectOne(req => req.url.endsWith('/test'))
        .flush({ success: false, data: null, error: 'backend says no' });
    expect(error?.message).toContain('backend says no');
  });

  it('unwraps data when success:true', () => {
    let value: unknown;
    api.get('/test').subscribe(v => (value = v));
    ctrl.expectOne(req => req.url.endsWith('/test'))
        .flush({ success: true, data: { x: 1 } });
    expect(value).toEqual({ x: 1 });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false`
Expected: 'does NOT retry a POST' FAILS (ctrl.verify finds an unexpected second request); 'throws when success:false' FAILS (value is `null`, no error emitted).

- [ ] **Step 3: Implement**

(a) `error.interceptor.ts` — add above `withRetry`:

```typescript
// Only idempotent reads are safe to replay: status 0 covers "request sent
// but response lost" — re-sending a POST can duplicate an order/backtest
// (audit M1.10).
const RETRYABLE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
```

and change the retry condition to:

```typescript
      if (
        RETRYABLE_METHODS.has(req.method) &&
        RETRYABLE_STATUSES.has(status) &&
        attempt < MAX_RETRIES
      ) {
```

(b) `api.service.ts` — add a shared unwrap operator and use it in all four verbs:

```typescript
function unwrap<T>() {
  return map((res: ApiResponse<T>) => {
    if (res && res.success === false) {
      // Surface envelope failures that arrive at HTTP 200 — silently
      // returning res.data (null) fed `undefined as T` into signals
      // (audit M1.10).
      throw new Error(res.error || 'API returned success:false');
    }
    return res.data;
  });
}
```

then `.pipe(map(res => res.data))` → `.pipe(unwrap<T>())` in `get/post/put/delete` (NOT `getBlob` — no envelope).

- [ ] **Step 4: Run tests + build**

Run: `cd frontend && npx ng test --watch=false && npx ng build --configuration=development`
Expected: all spec files green (36 files now), build green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/core/interceptors/error.interceptor.ts frontend/src/app/core/interceptors/error.interceptor.spec.ts frontend/src/app/core/services/api.service.ts frontend/src/app/core/services/api.service.spec.ts
git commit -m "fix(frontend): retry only safe methods; surface success:false envelopes as errors (audit M1.10)"
```

---

## Final gate (after Task 10)

- [ ] Full backend suite: `.venv/Scripts/python.exe -m pytest tests/ -q --no-cov -p no:cacheprovider` → expect 0 failed (the 8 by-design skips remain).
- [ ] Lint: `ruff check src/ tests/` + `black --check --line-length=100 src/ tests/` → clean.
- [ ] Frontend: `npx ng test --watch=false` + `npx ng build --configuration=production` → green.
- [ ] Push: `git push . feature/forward-demo-lab:main && git push origin main feature/forward-demo-lab`; watch the CI run to completion (`gh run list -R GitBakko/AlgoTrader -b main -L 1`).
- [ ] Update memory: M1 shipped, commits list, anything deferred.
