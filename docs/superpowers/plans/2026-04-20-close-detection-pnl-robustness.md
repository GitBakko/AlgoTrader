# Close Detection & P&L Robustness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate invented P&L writes by implementing a three-tier close detection path (primary Transaction History API → deferred retry → UNRECONCILED fail-safe), fixing the 2026-04-20 incident where `(exit - entry) * size` formula produced P&L values 45–30% off broker values on DE40 / WTIUSD / NATGAS.

**Architecture:** Three-tier close detection. Tier 1 (primary) hardens the existing Transaction History API path with timezone-correct ISO-8601 parameters, deterministic `deal_reference` matching (already persisted in `Position` model), and normalized instrument-name fallback. Tier 2 (deferred) keeps disappeared positions in-memory and retries the primary match every loop iteration for up to 10 minutes without writing to DB or alerting. Tier 3 (UNRECONCILED) writes the close with `pnl=NULL` and `close_reason='UNRECONCILED'` as a fail-safe, relying on a manual CLI for reconciliation. The legacy `_fallback_close_detection` function is removed.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, Pydantic v2, SQLModel + Alembic, Capital.com REST API, loguru, Prometheus client. Paths use `.venv/Scripts/python.exe` (Windows).

**Spec reference:** [docs/superpowers/specs/2026-04-20-close-detection-pnl-robustness-design.md](../specs/2026-04-20-close-detection-pnl-robustness-design.md)

**Pre-flight findings (captured during brainstorming):**
- `Position.deal_reference` field already exists in [backend/src/database/models.py:144](../../../backend/src/database/models.py#L144). **No Alembic migration needed.**
- `_on_position_closed` in [paper_loop.py:2793](../../../backend/src/trading/paper_loop.py#L2793) is the single chokepoint that feeds Kelly sizer, circuit breakers, equity-curve filter, and per-asset tracker. Guarding this with `if pnl is None: return` is sufficient to keep UNRECONCILED records out of all downstream stats.
- `close_reason` column is `VARCHAR(50)` — `'UNRECONCILED'` fits.
- `DealConfirmation` in [backend/src/broker/models.py](../../../backend/src/broker/models.py) already exposes both `deal_id` and `deal_reference`.

---

## Branch Strategy

All work lands on `fix/close-detection-robust` off `master`. Commit after each task. Open PR only after Phase 6 manual verification passes.

```bash
cd d:/Develop/AI/_ClaudeCode/AlgoTrader
git checkout master
git pull
git checkout -b fix/close-detection-robust
```

---

## Phase 1 — Broker Client Hardening (timezone + window)

Targets spec §3 Tier 1 fix, root cause of the empty transaction list in the 2026-04-20 incident.

### Task 1: Timezone-correct ISO 8601 in `get_transaction_history`

**Files:**
- Modify: `backend/src/broker/client.py:496-520`
- Test: `backend/tests/broker/test_client_transaction_history.py` *(new)*

- [ ] **Step 1: Write the failing test**

Create `backend/tests/broker/test_client_transaction_history.py`:

```python
"""Tests for CapitalComClient.get_transaction_history parameter serialization."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.broker.client import CapitalComClient
from src.broker.models import TransactionType


@pytest.mark.asyncio
async def test_transaction_history_sends_iso8601_utc_with_z_suffix():
    """from/to params MUST carry the 'Z' UTC suffix, otherwise Capital.com
    interprets them in server-local time and the window can miss recent
    closes (root cause of the 2026-04-20 incident)."""
    client = CapitalComClient.__new__(CapitalComClient)
    client._request = AsyncMock(return_value={"transactions": []})

    from_dt = datetime(2026, 4, 19, 20, 0, 0, tzinfo=timezone.utc)
    to_dt = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)

    await client.get_transaction_history(from_dt, to_dt, TransactionType.ALL_DEAL)

    assert client._request.await_count == 1
    _, kwargs = client._request.await_args
    params = kwargs["params"]
    assert params["from"].endswith("Z"), f"from must end with Z, got {params['from']!r}"
    assert params["to"].endswith("Z"), f"to must end with Z, got {params['to']!r}"
    assert params["from"] == "2026-04-19T20:00:00Z"
    assert params["to"] == "2026-04-20T00:00:00Z"
    assert params["type"] == TransactionType.ALL_DEAL.value
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/broker/test_client_transaction_history.py -v
```

Expected: FAIL with assertion error on the `Z` suffix (current code uses `strftime("%Y-%m-%dT%H:%M:%S")` without Z).

- [ ] **Step 3: Write minimal implementation**

Replace the body of `get_transaction_history` in `backend/src/broker/client.py:513-520`:

```python
        params = {
            "from": from_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": transaction_type.value,
        }
        response = await self._request("GET", "/api/v1/history/transactions", params=params)
        transactions_data = response.get("transactions", [])
        return [Transaction(**txn) for txn in transactions_data]
```

If `timezone` is not yet imported at the top of `client.py`, add:

```python
from datetime import datetime, timezone
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/broker/test_client_transaction_history.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/broker/client.py backend/tests/broker/test_client_transaction_history.py
git commit -m "fix(broker): ISO 8601 UTC 'Z' suffix on transaction history params"
```

---

### Task 2: Widen `_fetch_recent_transactions` window from 4h to 24h

**Files:**
- Modify: `backend/src/trading/paper_loop.py:780-807`

Rationale: even with timezone fixed, Capital.com's transaction history can lag by a few minutes. A 24h window costs nothing (response is small, cache is 30s) and tolerates any indexing delay or clock skew.

- [ ] **Step 1: Modify the window**

In `backend/src/trading/paper_loop.py`, locate `_fetch_recent_transactions` (around line 780) and change:

```python
            from_date = now - timedelta(hours=4)
```

to:

```python
            from_date = now - timedelta(hours=24)
```

- [ ] **Step 2: Extend the cache TTL**

In the same function, change:

```python
        if cached is not None and cached_ts and (now - cached_ts).total_seconds() < 30:
            return cached
```

to:

```python
        if cached is not None and cached_ts and (now - cached_ts).total_seconds() < 60:
            return cached
```

(60s cache is still well under the loop tick rate; halves API calls.)

- [ ] **Step 3: Run the full test suite to confirm no regression**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -x --ignore=tests/integration -q
```

Expected: all existing tests pass (this is a pure constant change).

- [ ] **Step 4: Commit**

```bash
git add backend/src/trading/paper_loop.py
git commit -m "fix(paper_loop): widen transaction history window to 24h, cache 60s"
```

---

## Phase 2 — Transaction Model: Currency Warning

Targets spec §6 case (g), defensive observability for cross-currency P&L.

### Task 3: Warn when `Transaction.pl_value` currency differs from account currency

**Files:**
- Modify: `backend/src/broker/models.py:260-285`
- Test: `backend/tests/broker/test_transaction_model.py` *(new)*

- [ ] **Step 1: Write the failing test**

Create `backend/tests/broker/test_transaction_model.py`:

```python
"""Tests for Transaction.pl_value currency handling."""
from __future__ import annotations

import logging

import pytest

from src.broker.models import Transaction


def _base_txn(**overrides):
    data = {
        "date": "2026-04-20T00:02:00",
        "type": "DEAL",
        "reference": "ref-123",
        "instrumentName": "Oil - Crude",
        "openLevel": 84.50,
        "closeLevel": 84.87,
        "profitAndLoss": "USD74.18",
        "size": 10.0,
        "currency": "USD",
    }
    data.update(overrides)
    return Transaction(**data)


def test_pl_value_parses_usd_prefix():
    txn = _base_txn(profitAndLoss="USD74.18")
    assert txn.pl_value == pytest.approx(74.18)


def test_pl_value_parses_negative_eur_prefix():
    txn = _base_txn(profitAndLoss="-EUR12.50", currency="EUR")
    assert txn.pl_value == pytest.approx(-12.50)


def test_pl_value_warns_when_currency_differs_from_account(caplog):
    """When account is USD but P&L arrives in EUR, we must log a WARNING
    (we do NOT convert — just flag for visibility)."""
    txn = _base_txn(profitAndLoss="EUR44.38", currency="EUR")
    with caplog.at_level(logging.WARNING, logger="src.broker.models"):
        value = txn.pl_value_in(account_currency="USD")
    assert value == pytest.approx(44.38)
    assert any(
        "currency mismatch" in record.message.lower() for record in caplog.records
    ), f"Expected WARNING about currency mismatch, got: {[r.message for r in caplog.records]}"


def test_pl_value_in_no_warning_when_currency_matches():
    txn = _base_txn(profitAndLoss="USD74.18", currency="USD")
    assert txn.pl_value_in("USD") == pytest.approx(74.18)


def test_pl_value_returns_none_for_empty():
    txn = _base_txn(profitAndLoss=None, amount=None)
    assert txn.pl_value is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/broker/test_transaction_model.py -v
```

Expected: FAIL. `pl_value_in` method does not exist.

- [ ] **Step 3: Add `pl_value_in` method to `Transaction` model**

In `backend/src/broker/models.py`, immediately after the existing `pl_value` property (around line 285), add:

```python
    def pl_value_in(self, account_currency: str) -> float | None:
        """Return parsed P&L, logging a WARNING if the currency prefix in
        profitAndLoss differs from account_currency.

        We DO NOT convert (a reliable FX feed is out of scope).
        The caller decides what to do with a mismatched value; at minimum
        the mismatch becomes observable in logs.
        """
        from loguru import logger

        value = self.pl_value
        if value is None:
            return None

        raw = (self.profit_and_loss or "").strip()
        prefix = ""
        for ch in raw.lstrip("-"):
            if ch.isdigit() or ch == ".":
                break
            prefix += ch
        prefix = prefix.upper()
        account = (account_currency or "").upper()

        if prefix and account and prefix != account:
            logger.warning(
                f"Transaction P&L currency mismatch: "
                f"txn={prefix}{value:+.2f} account={account} "
                f"(ref={self.reference}, instrument={self.instrument_name}) — "
                f"value used as-is, no FX conversion"
            )
        return value
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/broker/test_transaction_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/broker/models.py backend/tests/broker/test_transaction_model.py
git commit -m "feat(broker): warn on Transaction P&L currency mismatch"
```

---

## Phase 3 — Match Transaction: Three Strategies

Targets spec §3 Tier 1, §5.2 Strategy 1/2/3.

### Task 4: Refactor `_match_transaction` with Strategy 1 (`deal_reference`)

**Files:**
- Modify: `backend/src/trading/paper_loop.py:809-854`
- Test: `backend/tests/trading/test_close_detection.py` *(new)*

Background: `txn.reference` in Capital.com's transaction history is the **dealReference** (as confirmed by [backend/src/broker/models.py:250](../../../backend/src/broker/models.py#L250) comment). The existing `ref_match` compared it against `deal_id`, which is a different identifier. Fix by threading `deal_reference` (already stored on `Position`) through the matching.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/trading/test_close_detection.py`:

```python
"""Tests for close detection matching strategies in paper_loop."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.broker.models import Transaction


def _txn(**kw):
    defaults = {
        "date": datetime(2026, 4, 20, 0, 2, 0),
        "type": "DEAL",
        "reference": "ref-abc",
        "instrumentName": "Oil - Crude",
        "openLevel": 84.50,
        "closeLevel": 84.87,
        "profitAndLoss": "USD246.86",
        "size": 10.0,
        "currency": "USD",
    }
    defaults.update(kw)
    return Transaction(**defaults)


@pytest.fixture
def paper_loop():
    """Minimal paper_loop instance for testing _match_transaction in isolation."""
    from src.trading.paper_loop import PaperTradingLoop

    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    return loop


def test_match_strategy_1_deal_reference_deterministic(paper_loop):
    """When deal_reference matches txn.reference, return that transaction
    regardless of other fields."""
    txns = [
        _txn(reference="wrong-1", closeLevel=99.99, profitAndLoss="USD1.00"),
        _txn(reference="match-ref", closeLevel=84.87, profitAndLoss="USD246.86"),
        _txn(reference="wrong-2", closeLevel=50.00, profitAndLoss="USD5.00"),
    ]
    result = paper_loop._match_transaction(
        transactions=txns,
        deal_id="deal-xyz",
        deal_reference="match-ref",
        epic="WTIUSD",
        entry_price=84.50,
    )
    exit_price, pnl, reason = result
    assert exit_price == pytest.approx(84.87)
    assert pnl == pytest.approx(246.86)
    assert reason == "TP"  # positive pnl → TP


def test_match_strategy_1_skips_when_deal_reference_none(paper_loop):
    """Strategy 1 skipped if deal_reference is None (legacy positions);
    falls through to Strategy 2/3."""
    txns = [_txn(reference="some-ref", openLevel=84.50, profitAndLoss="USD100.00")]
    result = paper_loop._match_transaction(
        transactions=txns,
        deal_id="some-ref",  # deal_id equals reference in legacy data
        deal_reference=None,
        epic="WTIUSD",
        entry_price=84.50,
    )
    exit_price, pnl, _ = result
    assert exit_price is not None
    assert pnl == pytest.approx(100.00)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_close_detection.py -v
```

Expected: FAIL — `_match_transaction` signature does not accept `deal_reference`.

- [ ] **Step 3: Rewrite `_match_transaction` with the three-strategy structure**

Replace the entire `_match_transaction` method in `backend/src/trading/paper_loop.py` (currently at lines 809-854) with:

```python
    @staticmethod
    def _normalize_instrument_name(name: str) -> str:
        """Normalize instrument/epic names for fuzzy matching.

        Strips underscores, hyphens, whitespace; lowercases.
        'OIL_CRUDE' → 'oilcrude', 'Oil - Crude' → 'oilcrude'.
        """
        return "".join(ch for ch in (name or "").lower() if ch.isalnum())

    def _match_transaction(
        self,
        transactions: list,
        deal_id: str,
        deal_reference: str | None,
        epic: str,
        entry_price: float,
    ) -> tuple[float | None, float | None, str | None]:
        """Match a closed deal to a broker Transaction using three strategies
        in order of decreasing determinism.

        Returns (exit_price, pnl, close_reason) or (None, None, None).
        """
        from src.broker.client import EPIC_TO_BROKER

        broker_epic = EPIC_TO_BROKER.get(epic, epic)
        norm_epic = self._normalize_instrument_name(epic)
        norm_broker = self._normalize_instrument_name(broker_epic)

        def _finalize(txn) -> tuple[float | None, float | None, str | None]:
            exit_price = txn.close_level
            pnl = txn.pl_value
            if exit_price is None or pnl is None:
                return None, None, None
            if pnl > 0:
                reason = "TP"
            elif pnl < 0:
                reason = "SL"
            else:
                reason = "EXTERNAL"
            logger.info(
                f"[{epic}] Matched broker transaction: "
                f"exit={exit_price:.6f}, P&L=${pnl:.2f}, reason={reason} "
                f"(ref={txn.reference}, instrument={txn.instrument_name})"
            )
            return exit_price, pnl, reason

        # Strategy 1: deal_reference (deterministic, 1-to-1 with the open)
        if deal_reference:
            for txn in transactions:
                if txn.reference == deal_reference:
                    result = _finalize(txn)
                    if result[0] is not None:
                        return result

        # Strategy 2: deal_id (legacy path, still supported)
        if deal_id:
            for txn in transactions:
                if txn.reference == deal_id:
                    result = _finalize(txn)
                    if result[0] is not None:
                        return result

        # Strategy 3: normalized instrument name + entry tolerance
        candidates = []
        for txn in transactions:
            if not txn.instrument_name:
                continue
            norm_name = self._normalize_instrument_name(txn.instrument_name)
            name_hit = (
                norm_epic in norm_name
                or norm_name in norm_epic
                or norm_broker in norm_name
                or norm_name in norm_broker
            )
            entry_hit = (
                txn.open_level is not None
                and entry_price > 0
                and abs(txn.open_level - entry_price) / max(entry_price, 1e-9) < 0.001
            )
            if name_hit and entry_hit:
                candidates.append(txn)

        if len(candidates) > 1:
            logger.warning(
                f"[{epic}] Ambiguous match in Strategy 3: {len(candidates)} "
                f"candidates with same instrument+entry. Picking most recent."
            )
            candidates.sort(key=lambda t: t.date, reverse=True)

        if candidates:
            result = _finalize(candidates[0])
            if result[0] is not None:
                return result

        return None, None, None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_close_detection.py -v
```

Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/tests/trading/test_close_detection.py
git commit -m "feat(paper_loop): three-strategy transaction matching (deal_reference, deal_id, normalized name)"
```

---

### Task 5: Strategy 3 tests — normalized instrument name + ambiguity

**Files:**
- Modify: `backend/tests/trading/test_close_detection.py`

- [ ] **Step 1: Add tests for Strategy 3 and ambiguity**

Append to `backend/tests/trading/test_close_detection.py`:

```python
def test_match_strategy_3_normalized_oil_crude(paper_loop):
    """WTIUSD epic matches broker instrument 'Oil - Crude' after normalization."""
    txns = [_txn(reference="unrelated", instrumentName="Oil - Crude", openLevel=84.50)]
    exit_price, pnl, _ = paper_loop._match_transaction(
        transactions=txns,
        deal_id="d-1",
        deal_reference=None,
        epic="WTIUSD",
        entry_price=84.50,
    )
    assert exit_price is not None


def test_match_strategy_3_normalized_germany_40(paper_loop):
    """DE40 epic matches broker instrument 'Germany 40' after normalization."""
    txns = [
        _txn(
            reference="unrelated",
            instrumentName="Germany 40",
            openLevel=24510.0,
            closeLevel=24532.0,
            profitAndLoss="EUR44.38",
            currency="EUR",
        )
    ]
    exit_price, pnl, _ = paper_loop._match_transaction(
        transactions=txns,
        deal_id="d-1",
        deal_reference=None,
        epic="DE40",
        entry_price=24510.0,
    )
    assert exit_price == pytest.approx(24532.0)
    # Currency mismatch is logged elsewhere; here we just assert the numeric
    assert pnl == pytest.approx(44.38)


def test_match_strategy_3_entry_tolerance_rejects_distant_level(paper_loop):
    """Entry level > 0.1% away from txn.open_level is rejected."""
    txns = [_txn(reference="x", instrumentName="Oil - Crude", openLevel=80.00)]
    result = paper_loop._match_transaction(
        transactions=txns,
        deal_id="d-1",
        deal_reference=None,
        epic="WTIUSD",
        entry_price=84.50,
    )
    assert result == (None, None, None)


def test_match_strategy_3_ambiguous_picks_most_recent(paper_loop, caplog):
    """Two txns, same epic + same entry → pick most recent date, log WARNING."""
    import logging

    older = _txn(
        reference="r-old",
        instrumentName="Oil - Crude",
        openLevel=84.50,
        closeLevel=84.80,
        profitAndLoss="USD100.00",
        date=datetime(2026, 4, 20, 0, 1, 0),
    )
    newer = _txn(
        reference="r-new",
        instrumentName="Oil - Crude",
        openLevel=84.50,
        closeLevel=84.87,
        profitAndLoss="USD246.86",
        date=datetime(2026, 4, 20, 0, 2, 0),
    )
    with caplog.at_level(logging.WARNING):
        exit_price, pnl, _ = paper_loop._match_transaction(
            transactions=[older, newer],
            deal_id="d-1",
            deal_reference=None,
            epic="WTIUSD",
            entry_price=84.50,
        )
    assert exit_price == pytest.approx(84.87)  # newer wins
    assert pnl == pytest.approx(246.86)


def test_match_no_match_returns_all_none(paper_loop):
    result = paper_loop._match_transaction(
        transactions=[],
        deal_id="d-1",
        deal_reference="ref-1",
        epic="WTIUSD",
        entry_price=84.50,
    )
    assert result == (None, None, None)


def test_match_skips_transaction_with_none_pl(paper_loop):
    """Transaction with profitAndLoss=None is skipped, next candidate tried."""
    incomplete = _txn(reference="ref-match", profitAndLoss=None, amount=None)
    good = _txn(
        reference="ref-match",
        profitAndLoss="USD74.18",
        closeLevel=84.87,
    )
    # Same reference on two rows — first is incomplete, second is good
    result = paper_loop._match_transaction(
        transactions=[incomplete, good],
        deal_id="d-1",
        deal_reference="ref-match",
        epic="WTIUSD",
        entry_price=84.50,
    )
    # Strategy 1 finds incomplete first → skips → finds good
    assert result[0] is not None
    assert result[1] == pytest.approx(74.18)
```

Update the Strategy 1 loop in `_match_transaction` to continue on incomplete transactions instead of bailing out. In `backend/src/trading/paper_loop.py`, change:

```python
        # Strategy 1: deal_reference (deterministic, 1-to-1 with the open)
        if deal_reference:
            for txn in transactions:
                if txn.reference == deal_reference:
                    result = _finalize(txn)
                    if result[0] is not None:
                        return result
```

(already written that way in Task 4 — no change needed; the `continue`-like behavior comes from `if result[0] is not None: return result`.)

- [ ] **Step 2: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_close_detection.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/trading/test_close_detection.py
git commit -m "test(paper_loop): Strategy 3 normalized matching, ambiguity, incomplete txn"
```

---

## Phase 4 — Deferred Tier + UNRECONCILED Tier

Targets spec §3 Tier 2 and Tier 3, §5.3 and §5.4.

### Task 6: Add `PendingClose` dataclass and `_pending_close_detections` state

**Files:**
- Modify: `backend/src/trading/paper_loop.py` (top of file + `__init__`)

- [ ] **Step 1: Add the dataclass**

At the top of `backend/src/trading/paper_loop.py`, after existing imports, add:

```python
from dataclasses import dataclass, field


@dataclass
class PendingClose:
    """A position that disappeared from broker but whose close transaction
    has not yet been matched. Held in memory for retry during subsequent
    loop iterations, up to CLOSE_RECONCILIATION_TIMEOUT_SECONDS.
    """

    deal_id: str
    deal_reference: str | None
    epic: str
    direction: str
    size: float
    entry_price: float
    prev_pos: dict
    first_seen: datetime
    retry_count: int = 0
```

- [ ] **Step 2: Initialize the dict in `__init__`**

Locate `PaperTradingLoop.__init__` and add (near the existing `self._previous_positions = {}` initialization):

```python
        self._pending_close_detections: dict[str, PendingClose] = {}
```

- [ ] **Step 3: Add the timeout config**

In `backend/src/utils/config.py`, in the `Settings` class, add:

```python
    close_reconciliation_timeout_seconds: int = 600  # 10 minutes
```

- [ ] **Step 4: Smoke test — backend still starts**

```bash
cd backend && .venv/Scripts/python.exe -c "from src.trading.paper_loop import PaperTradingLoop, PendingClose; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/src/utils/config.py
git commit -m "feat(paper_loop): PendingClose dataclass + reconciliation timeout setting"
```

---

### Task 7: Rewrite `_detect_broker_closed` to use the three-tier flow

**Files:**
- Modify: `backend/src/trading/paper_loop.py:856-1007` (plus removal of `_fallback_close_detection`)
- Test: `backend/tests/trading/test_close_detection.py`

- [ ] **Step 1: Write failing tests for deferred flow and UNRECONCILED timeout**

Append to `backend/tests/trading/test_close_detection.py`:

```python
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from src.trading.paper_loop import PaperTradingLoop, PendingClose


@pytest.fixture
def loop_with_mocks():
    """PaperTradingLoop with all external deps mocked for _detect_broker_closed."""
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop._previous_positions = {}
    loop._pending_close_detections = {}
    loop._broker_closed_deals = set()
    loop.execution_engine = MagicMock()
    loop.execution_engine.mode = MagicMock()
    # Non-PAPER so detection runs
    loop.execution_engine.mode.__ne__ = lambda self, other: True
    loop.execution_engine.mode.__eq__ = lambda self, other: False
    loop.broker = AsyncMock()
    loop.risk_manager = MagicMock()
    loop.trailing_stop_manager = MagicMock()
    loop.trailing_stop_manager.tracked_positions = {}
    loop._fetch_equity = AsyncMock(return_value=10000.0)
    loop._persist_position_close = AsyncMock()
    loop._on_position_closed = MagicMock()
    loop._log_source = "demo_trading"
    loop._fetch_recent_transactions = AsyncMock(return_value=[])
    # Patch _emit_unreconciled_close and _persist for inspection
    return loop


@pytest.mark.asyncio
async def test_deferred_when_no_match_on_first_iteration(loop_with_mocks):
    """Position disappears, no matching txn → enters pending, no DB write, no alert."""
    loop = loop_with_mocks
    prev_pos = {
        "deal_id": "deal-1",
        "deal_reference": "ref-1",
        "epic": "WTIUSD",
        "direction": "BUY",
        "size": 10.0,
        "level": 84.50,
    }
    loop._previous_positions = {"deal-1": prev_pos}
    # Empty transaction list → no match
    loop._fetch_recent_transactions.return_value = []

    # Simulate: position disappeared from broker
    await loop._detect_broker_closed(current_positions=[])

    assert "deal-1" in loop._pending_close_detections
    pending = loop._pending_close_detections["deal-1"]
    assert pending.deal_reference == "ref-1"
    assert pending.retry_count == 0
    # NO DB persist, NO alert
    loop._persist_position_close.assert_not_awaited()
    loop._on_position_closed.assert_not_called()


@pytest.mark.asyncio
async def test_unreconciled_after_timeout(loop_with_mocks, monkeypatch):
    """After 10min without match → persist with pnl=None, close_reason=UNRECONCILED."""
    loop = loop_with_mocks
    past = datetime.now().astimezone() - timedelta(seconds=601)
    loop._pending_close_detections["deal-1"] = PendingClose(
        deal_id="deal-1",
        deal_reference="ref-1",
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        prev_pos={"level": 84.50, "deal_id": "deal-1"},
        first_seen=past,
        retry_count=120,
    )
    loop._fetch_recent_transactions.return_value = []

    await loop._detect_broker_closed(current_positions=[])

    # Persisted as UNRECONCILED with pnl=None
    loop._persist_position_close.assert_awaited_once()
    call_kwargs = loop._persist_position_close.await_args.kwargs
    assert call_kwargs["pnl"] is None
    assert call_kwargs["close_reason"] == "UNRECONCILED"
    # Kelly / CB guard: _on_position_closed must NOT be called when pnl is None
    loop._on_position_closed.assert_not_called()
    # Pending cleared
    assert "deal-1" not in loop._pending_close_detections


@pytest.mark.asyncio
async def test_reconciled_on_retry(loop_with_mocks):
    """Pending position gets matched on next iteration → persists real pnl."""
    loop = loop_with_mocks
    loop._pending_close_detections["deal-1"] = PendingClose(
        deal_id="deal-1",
        deal_reference="ref-1",
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        prev_pos={"level": 84.50, "deal_id": "deal-1"},
        first_seen=datetime.now().astimezone(),
        retry_count=2,
    )
    # Now the txn appears
    loop._fetch_recent_transactions.return_value = [
        _txn(reference="ref-1", openLevel=84.50, closeLevel=85.60, profitAndLoss="USD246.86")
    ]

    await loop._detect_broker_closed(current_positions=[])

    loop._persist_position_close.assert_awaited_once()
    kwargs = loop._persist_position_close.await_args.kwargs
    assert kwargs["pnl"] == pytest.approx(246.86)
    assert kwargs["close_reason"] == "TP"
    # Downstream stats updated
    loop._on_position_closed.assert_called_once()
    assert "deal-1" not in loop._pending_close_detections
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_close_detection.py -v -k "deferred or unreconciled or reconciled_on_retry"
```

Expected: FAIL (current `_detect_broker_closed` does not implement the flow).

- [ ] **Step 3: Rewrite `_detect_broker_closed`**

Replace the entire `_detect_broker_closed` method in `backend/src/trading/paper_loop.py` (currently lines 856-1007) with the following. **Also delete** `_fallback_close_detection` (currently lines 1009-1108) — it no longer exists.

```python
    async def _detect_broker_closed(self, current_positions: list[dict]) -> None:
        """Three-tier close detection.

        Tier 1 (primary):   Transaction History API match → write REAL data.
        Tier 2 (deferred):  no match → keep in _pending_close_detections,
                            retry on next loop iteration.
        Tier 3 (timeout):   10min without match → write UNRECONCILED record.
        """
        from src.utils.config import get_settings

        if self.execution_engine.mode == ExecutionMode.PAPER:
            return

        self._broker_closed_deals = set()
        now = datetime.now(UTC)
        timeout_sec = get_settings().close_reconciliation_timeout_seconds

        current_deals = {p.get("deal_id") for p in current_positions if p.get("deal_id")}

        # First loop iteration with positions: snapshot and return
        if not self._previous_positions:
            self._previous_positions = {
                p.get("deal_id"): p for p in current_positions if p.get("deal_id")
            }
            return

        # Combine newly-disappeared positions with those already pending
        newly_disappeared = [
            (did, ppos)
            for did, ppos in self._previous_positions.items()
            if did not in current_deals and did not in self._pending_close_detections
        ]
        retry_pending = list(self._pending_close_detections.items())

        if not newly_disappeared and not retry_pending:
            self._previous_positions = {
                p.get("deal_id"): p for p in current_positions if p.get("deal_id")
            }
            return

        transactions = await self._fetch_recent_transactions()
        if transactions:
            logger.info(
                f"Fetched {len(transactions)} recent transactions for "
                f"{len(newly_disappeared)} new + {len(retry_pending)} pending"
            )

        # ============ Handle retry of previously deferred closes ============
        for deal_id, pending in retry_pending:
            pending.retry_count += 1
            txn_exit, txn_pnl, txn_reason = self._match_transaction(
                transactions, deal_id, pending.deal_reference,
                pending.epic, pending.entry_price,
            )
            if txn_exit is not None and txn_pnl is not None:
                logger.info(
                    f"[{pending.epic}] Reconciled after {pending.retry_count} retries: "
                    f"exit={txn_exit:.6f}, P&L=${txn_pnl:.2f}"
                )
                await self._finalize_close(
                    deal_id=deal_id,
                    epic=pending.epic,
                    direction=pending.direction,
                    size=pending.size,
                    entry_price=pending.entry_price,
                    prev_pos=pending.prev_pos,
                    exit_price=txn_exit,
                    pnl=txn_pnl,
                    close_reason=txn_reason or "EXTERNAL",
                    metric_path="primary",
                    retry_count=pending.retry_count,
                )
                del self._pending_close_detections[deal_id]
                continue

            # Still no match — check timeout
            age = (now - pending.first_seen).total_seconds()
            if age > timeout_sec:
                await self._emit_unreconciled_close(pending)
                del self._pending_close_detections[deal_id]

        # ============ Handle newly-disappeared positions ============
        for deal_id, prev_pos in newly_disappeared:
            epic = prev_pos.get("epic", "UNKNOWN")
            direction = prev_pos.get("direction", "BUY")
            size = prev_pos.get("size", 0)
            entry_price = prev_pos.get("level", 0)
            deal_reference = prev_pos.get("deal_reference")

            txn_exit, txn_pnl, txn_reason = self._match_transaction(
                transactions, deal_id, deal_reference, epic, entry_price,
            )

            if txn_exit is not None and txn_pnl is not None:
                await self._finalize_close(
                    deal_id=deal_id,
                    epic=epic,
                    direction=direction,
                    size=size,
                    entry_price=entry_price,
                    prev_pos=prev_pos,
                    exit_price=txn_exit,
                    pnl=txn_pnl,
                    close_reason=txn_reason or "EXTERNAL",
                    metric_path="primary",
                    retry_count=0,
                )
            else:
                # Tier 2: defer
                logger.warning(
                    f"[{epic}] Close detected but no broker transaction match for "
                    f"{deal_id} — deferring (timeout {timeout_sec}s)"
                )
                self._pending_close_detections[deal_id] = PendingClose(
                    deal_id=deal_id,
                    deal_reference=deal_reference,
                    epic=epic,
                    direction=direction,
                    size=float(size or 0),
                    entry_price=float(entry_price or 0),
                    prev_pos=prev_pos,
                    first_seen=now,
                    retry_count=0,
                )
                try:
                    from src.monitoring.metrics import MetricsCollector
                    MetricsCollector.record_close_detection(path="deferred", epic=epic)
                except Exception:
                    pass

        # Refresh previous positions snapshot for next iteration
        self._previous_positions = {
            p.get("deal_id"): p for p in current_positions if p.get("deal_id")
        }
```

- [ ] **Step 4: Add the `_finalize_close` helper (factored from the old inline code)**

Immediately after `_detect_broker_closed`, add:

```python
    async def _finalize_close(
        self,
        *,
        deal_id: str,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        prev_pos: dict,
        exit_price: float,
        pnl: float,
        close_reason: str,
        metric_path: str = "primary",
        retry_count: int = 0,
    ) -> None:
        """Persist a matched close (Tier 1 success, immediate or via retry)."""
        logger.warning(
            f"[{epic}] Position {deal_id} closed by broker "
            f"(reason={close_reason}, exit={exit_price:.6f}, P&L=${pnl:.2f}, "
            f"retry={retry_count})"
        )

        self._broker_closed_deals.add(deal_id)
        self._on_position_closed(deal_id, pnl, epic=epic, close_reason=close_reason)

        try:
            fresh_equity = await self._fetch_equity()
            self.risk_manager.update_equity(fresh_equity)
            logger.info(f"[{epic}] Equity refreshed after close: ${fresh_equity:,.2f}")
        except Exception as eq_err:
            logger.debug(f"Post-close equity refresh failed: {eq_err}")

        await self._persist_position_close(
            deal_id=deal_id,
            epic=epic,
            direction=direction,
            size=size,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            close_reason=close_reason,
            opened_at=prev_pos.get("opened_at"),
        )

        if deal_id in self.trailing_stop_manager.tracked_positions:
            self.trailing_stop_manager.unregister_position(deal_id)

        try:
            from src.api.websocket import ws_manager
            await ws_manager.broadcast(
                "trades",
                {
                    "type": "trade_closed",
                    "deal_id": deal_id,
                    "epic": epic,
                    "direction": direction,
                    "pnl": round(pnl, 2),
                    "close_reason": close_reason,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as e:
            logger.debug(f"WS broadcast trade_closed failed: {e}")

        if self._log_source in ("demo_trading", "live_trading"):
            try:
                from src.monitoring.alerting.alert_manager import get_alert_manager
                from src.utils.config import get_settings
                if getattr(get_settings(), "alerts_enabled", False):
                    am = get_alert_manager()
                    await am.alert_trade_closed(
                        epic=epic,
                        direction=direction,
                        deal_id=deal_id,
                        exit_price=exit_price,
                        pnl=round(pnl, 2),
                        reason=close_reason,
                    )
            except Exception as alert_err:
                logger.warning(f"Trade close alert failed: {alert_err}")

        try:
            from src.monitoring.metrics import MetricsCollector
            MetricsCollector.record_close_detection(
                path=metric_path, epic=epic, retry_count=retry_count
            )
        except Exception:
            pass
```

- [ ] **Step 5: Add the `_emit_unreconciled_close` helper**

Also after `_finalize_close`, add:

```python
    async def _emit_unreconciled_close(self, pending: PendingClose) -> None:
        """Tier 3: persist a close we could not reconcile with broker data.
        pnl=NULL, close_reason='UNRECONCILED'. Downstream stats must skip it.
        """
        logger.error(
            f"[{pending.epic}] UNRECONCILED close after {pending.retry_count} "
            f"retries: deal_id={pending.deal_id}, prev_pos={pending.prev_pos}"
        )

        self._broker_closed_deals.add(pending.deal_id)
        exit_price = float(pending.prev_pos.get("level") or pending.entry_price)

        await self._persist_position_close(
            deal_id=pending.deal_id,
            epic=pending.epic,
            direction=pending.direction,
            size=pending.size,
            entry_price=pending.entry_price,
            exit_price=exit_price,
            pnl=None,
            close_reason="UNRECONCILED",
            opened_at=pending.prev_pos.get("opened_at"),
        )

        if pending.deal_id in self.trailing_stop_manager.tracked_positions:
            self.trailing_stop_manager.unregister_position(pending.deal_id)

        try:
            from src.api.websocket import ws_manager
            await ws_manager.broadcast(
                "trades",
                {
                    "type": "trade_closed",
                    "deal_id": pending.deal_id,
                    "epic": pending.epic,
                    "direction": pending.direction,
                    "pnl": None,
                    "close_reason": "UNRECONCILED",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as e:
            logger.debug(f"WS broadcast unreconciled close failed: {e}")

        if self._log_source in ("demo_trading", "live_trading"):
            try:
                from src.monitoring.alerting.alert_manager import get_alert_manager
                from src.utils.config import get_settings
                if getattr(get_settings(), "alerts_enabled", False):
                    am = get_alert_manager()
                    await am.alert_trade_closed(
                        epic=pending.epic,
                        direction=pending.direction,
                        deal_id=pending.deal_id,
                        exit_price=exit_price,
                        pnl=0.0,  # placeholder for alert template
                        reason=(
                            "UNRECONCILED — P&L not confirmed by broker. "
                            f"Run: python scripts/reconcile_position.py "
                            f"--deal-id {pending.deal_id}"
                        ),
                    )
            except Exception as alert_err:
                logger.warning(f"Unreconciled close alert failed: {alert_err}")

        try:
            from src.monitoring.metrics import MetricsCollector
            MetricsCollector.record_close_detection(
                path="unreconciled", epic=pending.epic,
                retry_count=pending.retry_count,
            )
        except Exception:
            pass
```

- [ ] **Step 6: Guard `_on_position_closed` against None pnl**

In `backend/src/trading/paper_loop.py`, locate `_on_position_closed` (around line 2793) and at the very top of the method body add:

```python
        if pnl is None:
            logger.debug(
                f"[{epic}] _on_position_closed called with pnl=None "
                f"(UNRECONCILED) — skipping Kelly/CB/equity-filter updates"
            )
            return
```

This protects against any callsite that forgets the filter.

- [ ] **Step 7: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_close_detection.py -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/tests/trading/test_close_detection.py
git commit -m "feat(paper_loop): three-tier close detection (primary / deferred / unreconciled)"
```

---

## Phase 5 — Observability + Downstream Filter

### Task 8: Add `record_close_detection` to `MetricsCollector`

**Files:**
- Modify: `backend/src/monitoring/metrics.py`

- [ ] **Step 1: Inspect existing metrics style**

```bash
cd backend && grep -n "def record_" src/monitoring/metrics.py | head -20
```

Note the return pattern and class-method vs staticmethod convention used for existing `record_*` methods.

- [ ] **Step 2: Add the counter and method**

In `backend/src/monitoring/metrics.py`, add (following the existing pattern for Prometheus counters):

```python
    # At the module-level where other Counter() instances are defined:
    close_detection_path_counter = Counter(
        "mantis_close_detection_path_total",
        "Close detection paths taken (primary, deferred, unreconciled)",
        ["path", "epic"],
    )
```

And inside `MetricsCollector`:

```python
    @classmethod
    def record_close_detection(
        cls, *, path: str, epic: str, retry_count: int = 0
    ) -> None:
        """Record the path taken for a close detection event.

        Args:
            path: 'primary' | 'deferred' | 'unreconciled'
            epic: asset epic (e.g. 'WTIUSD')
            retry_count: number of deferred retries before this path was taken
        """
        try:
            close_detection_path_counter.labels(path=path, epic=epic).inc()
            # retry_count intentionally not a label (would cardinality-explode)
            # — it is exposed through logs instead
        except Exception:
            pass
```

- [ ] **Step 3: Run existing metrics tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/monitoring/ -v -k metric
```

Expected: no regressions.

- [ ] **Step 4: Commit**

```bash
git add backend/src/monitoring/metrics.py
git commit -m "feat(metrics): mantis_close_detection_path_total counter"
```

---

### Task 9: Filter UNRECONCILED out of downstream stats

**Files:**
- Modify: `backend/src/database/repositories/position_repository.py`
- Modify: `backend/src/api/routers/dashboard.py` (win rate / P&L aggregations)
- Modify: `backend/src/api/routers/trading.py` (trade history endpoints)
- Test: `backend/tests/database/test_position_repository_filter.py` *(new)*

Rationale: spec §6.10. Primary filter lives in `_on_position_closed` (already guarded in Task 7), but SQL aggregations must also exclude UNRECONCILED rows to prevent NULL P&L from poisoning win-rate and P&L-per-asset calculations.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/database/test_position_repository_filter.py`:

```python
"""Tests that win-rate / P&L aggregations skip UNRECONCILED rows."""
from __future__ import annotations

import pytest

from src.database.repositories.position_repository import PositionRepository


@pytest.mark.asyncio
async def test_compute_win_rate_skips_unreconciled(async_session):
    repo = PositionRepository(async_session)
    # Seed: 2 wins, 1 loss, 1 UNRECONCILED
    await _seed_position(async_session, pnl=10.0, close_reason="TP")
    await _seed_position(async_session, pnl=20.0, close_reason="TP")
    await _seed_position(async_session, pnl=-5.0, close_reason="SL")
    await _seed_position(async_session, pnl=None, close_reason="UNRECONCILED")

    stats = await repo.compute_trade_stats()
    # 3 reconciled trades, 2 wins
    assert stats["total_trades"] == 3
    assert stats["win_rate"] == pytest.approx(2 / 3)
    assert stats["total_pnl"] == pytest.approx(25.0)


async def _seed_position(session, *, pnl, close_reason):
    """Helper to insert a closed Position with given pnl / close_reason."""
    from src.database.models import Position
    from datetime import datetime, timezone

    p = Position(
        deal_id=f"test-{id(pnl)}-{close_reason}",
        epic="WTIUSD",
        direction="BUY",
        size=1.0,
        entry_price=80.0,
        status="CLOSED",
        pnl=pnl,
        close_reason=close_reason,
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
        closed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(p)
    await session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/database/test_position_repository_filter.py -v
```

Expected: FAIL — `compute_trade_stats` either does not exist or does not filter UNRECONCILED.

- [ ] **Step 3: Add / update `compute_trade_stats` in the repository**

In `backend/src/database/repositories/position_repository.py`, add:

```python
    async def compute_trade_stats(self) -> dict:
        """Aggregate win-rate and P&L across CLOSED positions, excluding
        UNRECONCILED rows (where pnl is NULL)."""
        from sqlalchemy import select, func
        from src.database.models import Position

        stmt = select(
            func.count(Position.id).label("n"),
            func.sum(Position.pnl).label("total"),
            func.sum(
                func.cast(Position.pnl > 0, __import__("sqlalchemy").Integer)
            ).label("wins"),
        ).where(
            Position.status == "CLOSED",
            Position.close_reason != "UNRECONCILED",
            Position.pnl.is_not(None),
        )
        row = (await self.session.execute(stmt)).one()
        n = int(row.n or 0)
        wins = int(row.wins or 0)
        total = float(row.total or 0.0)
        return {
            "total_trades": n,
            "wins": wins,
            "win_rate": (wins / n) if n else 0.0,
            "total_pnl": total,
        }
```

- [ ] **Step 4: Update dashboard.py and trading.py aggregations**

Search existing win-rate / P&L queries:

```bash
cd backend && grep -rn "win_rate\|SUM(pnl)\|COUNT.*Position" src/api/routers/
```

For each SQL query that aggregates `Position.pnl` or counts closed trades, add the `close_reason != 'UNRECONCILED'` filter. Example change in `dashboard.py` (exact line varies by file):

```python
# BEFORE
stmt = select(func.sum(Position.pnl)).where(Position.status == "CLOSED")

# AFTER
stmt = select(func.sum(Position.pnl)).where(
    Position.status == "CLOSED",
    Position.close_reason != "UNRECONCILED",
    Position.pnl.is_not(None),
)
```

Apply consistently to every aggregation discovered. **Do not touch** queries that list individual positions (the UI should still show UNRECONCILED rows with a visible flag).

- [ ] **Step 5: Run all tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/database/ tests/api/ -v
```

Expected: PASS, including the new filter test.

- [ ] **Step 6: Commit**

```bash
git add backend/src/database/repositories/position_repository.py backend/src/api/routers/ backend/tests/database/test_position_repository_filter.py
git commit -m "feat(stats): exclude UNRECONCILED positions from win-rate and P&L aggregations"
```

---

## Phase 6 — State Recovery + CLI

### Task 10: Re-inject orphan positions on backend restart

**Files:**
- Modify: `backend/src/execution/state_recovery.py`
- Test: `backend/tests/execution/test_state_recovery_orphans.py` *(new)*

- [ ] **Step 1: Inspect current state_recovery flow**

```bash
cd backend && grep -n "def " src/execution/state_recovery.py | head -20
```

Identify the method called at startup that compares DB open positions vs broker open positions. This is where orphan detection belongs.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/execution/test_state_recovery_orphans.py`:

```python
"""Tests for orphan position re-injection into _pending_close_detections."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_orphans_reinjected_into_pending_close_detections(async_session):
    """DB has an OPEN position that broker no longer reports → at startup
    it must be inserted into paper_loop._pending_close_detections with
    first_seen=now so the deferred retry timer restarts cleanly."""
    from src.database.models import Position
    from src.execution.state_recovery import StateRecovery

    # Seed DB: one open position with deal_reference
    orphan = Position(
        deal_id="orphan-1",
        deal_reference="orphan-ref-1",
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        status="OPEN",
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    async_session.add(orphan)
    await async_session.commit()

    paper_loop = MagicMock()
    paper_loop._pending_close_detections = {}
    broker = AsyncMock()
    broker.get_positions = AsyncMock(return_value=[])  # no positions on broker

    recovery = StateRecovery(paper_loop=paper_loop, broker=broker, session=async_session)
    await recovery.reinject_orphans()

    assert "orphan-1" in paper_loop._pending_close_detections
    pending = paper_loop._pending_close_detections["orphan-1"]
    assert pending.deal_reference == "orphan-ref-1"
    assert pending.epic == "WTIUSD"
    assert pending.retry_count == 0
```

- [ ] **Step 3: Run the test**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/execution/test_state_recovery_orphans.py -v
```

Expected: FAIL — `reinject_orphans` does not exist.

- [ ] **Step 4: Implement `reinject_orphans`**

Add to `backend/src/execution/state_recovery.py`:

```python
    async def reinject_orphans(self) -> int:
        """For each Position in DB with status='OPEN' that the broker no
        longer reports, insert it into paper_loop._pending_close_detections
        so the three-tier close detection picks it up within 10 minutes.

        Returns:
            Number of positions re-injected.
        """
        from datetime import datetime, timezone
        from sqlalchemy import select
        from src.database.models import Position
        from src.trading.paper_loop import PendingClose

        broker_positions = await self.broker.get_positions()
        broker_deal_ids = {p.deal_id for p in broker_positions}

        stmt = select(Position).where(Position.status == "OPEN")
        db_open = (await self.session.execute(stmt)).scalars().all()

        orphans = [p for p in db_open if p.deal_id not in broker_deal_ids]
        now = datetime.now(timezone.utc)

        for p in orphans:
            self.paper_loop._pending_close_detections[p.deal_id] = PendingClose(
                deal_id=p.deal_id,
                deal_reference=p.deal_reference,
                epic=p.epic,
                direction=p.direction,
                size=float(p.size or 0),
                entry_price=float(p.entry_price or 0),
                prev_pos={
                    "deal_id": p.deal_id,
                    "deal_reference": p.deal_reference,
                    "epic": p.epic,
                    "direction": p.direction,
                    "size": float(p.size or 0),
                    "level": float(p.entry_price or 0),
                    "opened_at": p.opened_at,
                },
                first_seen=now,
                retry_count=0,
            )
            logger.warning(
                f"[{p.epic}] Re-injected orphan position {p.deal_id} "
                f"into pending close detection at startup"
            )
        return len(orphans)
```

(`logger` is already imported at module top via `loguru`; if not, add `from loguru import logger`.)

- [ ] **Step 5: Call `reinject_orphans` from the startup sequence**

Find the existing startup method that calls `StateRecovery`. Typical location: `backend/src/api/main.py` or inside `PaperTradingLoop.start()`. Add the call right after the existing position reconciliation:

```python
await state_recovery.reinject_orphans()
```

- [ ] **Step 6: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/execution/ -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/execution/state_recovery.py backend/tests/execution/test_state_recovery_orphans.py backend/src/api/main.py backend/src/trading/paper_loop.py
git commit -m "feat(state_recovery): re-inject orphan positions into deferred close detection"
```

---

### Task 11: CLI `reconcile_position.py`

**Files:**
- Create: `backend/scripts/reconcile_position.py`
- Test: `backend/tests/scripts/test_reconcile_position.py` *(new)*

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scripts/test_reconcile_position.py`:

```python
"""Tests for scripts/reconcile_position.py CLI."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from scripts.reconcile_position import reconcile_deal_id


@pytest.mark.asyncio
async def test_refuses_open_position(async_session):
    from src.database.models import Position

    p = Position(
        deal_id="still-open",
        epic="WTIUSD",
        direction="BUY",
        size=1.0,
        entry_price=80.0,
        status="OPEN",
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    async_session.add(p)
    await async_session.commit()

    broker = AsyncMock()
    result = await reconcile_deal_id(
        deal_id="still-open",
        session=async_session,
        broker=broker,
        assume_yes=True,
    )
    assert result["status"] == "refused"
    assert "OPEN" in result["message"]
    broker.get_transaction_history.assert_not_called()


@pytest.mark.asyncio
async def test_updates_unreconciled_when_match_found(async_session):
    from src.database.models import Position
    from src.broker.models import Transaction

    p = Position(
        deal_id="rec-1",
        deal_reference="ref-1",
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        status="CLOSED",
        pnl=None,
        close_reason="UNRECONCILED",
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
        closed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    async_session.add(p)
    await async_session.commit()

    broker = AsyncMock()
    broker.get_transaction_history.return_value = [
        Transaction(
            date=datetime(2026, 4, 20, 0, 2, 0),
            type="DEAL",
            reference="ref-1",
            instrumentName="Oil - Crude",
            openLevel=84.50,
            closeLevel=85.60,
            profitAndLoss="USD246.86",
            size=10.0,
            currency="USD",
        )
    ]

    result = await reconcile_deal_id(
        deal_id="rec-1",
        session=async_session,
        broker=broker,
        assume_yes=True,
    )
    assert result["status"] == "updated"
    assert result["pnl"] == pytest.approx(246.86)

    await async_session.refresh(p)
    assert p.pnl == pytest.approx(246.86)
    assert p.close_reason == "TP"
    assert p.exit_price == pytest.approx(85.60)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/scripts/test_reconcile_position.py -v
```

Expected: FAIL — `scripts/reconcile_position.py` does not exist.

- [ ] **Step 3: Create the CLI**

Create `backend/scripts/reconcile_position.py`:

```python
"""CLI to reconcile a single position against the broker's Transaction History.

Usage:
    python scripts/reconcile_position.py --deal-id <ID> [--days 7] [--yes]

Refuses to run on positions with status='OPEN'. For CLOSED positions
(typically close_reason='UNRECONCILED'), fetches the broker transaction
history over the last N days, re-applies the three-strategy matching
from paper_loop, and offers to UPDATE the row with the real data.

Exit codes:
    0  success (updated or user declined)
    1  position not found
    2  position still OPEN (refused)
    3  no match + user did not supply manual values
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select

from src.broker.client import CapitalComClient
from src.broker.models import TransactionType
from src.database.models import Position
from src.database.session import get_async_session_context
from src.trading.paper_loop import PaperTradingLoop
from src.utils.config import get_settings


async def reconcile_deal_id(
    *, deal_id: str, session, broker, assume_yes: bool = False, days: int = 7
) -> dict:
    """Core reconciliation logic. Returns a dict describing the outcome."""
    stmt = select(Position).where(Position.deal_id == deal_id)
    position = (await session.execute(stmt)).scalar_one_or_none()

    if position is None:
        return {"status": "not_found", "message": f"No position with deal_id={deal_id}"}

    if position.status == "OPEN":
        return {
            "status": "refused",
            "message": (
                f"Position {deal_id} is still OPEN on broker. "
                f"Close it via POST /api/positions/close/{deal_id} first."
            ),
        }

    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(days=days)
    transactions = await broker.get_transaction_history(
        from_dt, now, TransactionType.ALL_DEAL
    )

    # Re-use the same matching logic as the live loop
    match = PaperTradingLoop._match_transaction.__func__  # type: ignore[attr-defined]
    # Lightweight wrapper so we can call the bound method pattern
    class _Stub:
        _normalize_instrument_name = staticmethod(
            PaperTradingLoop._normalize_instrument_name
        )

    exit_price, pnl, reason = match(
        _Stub(),
        transactions,
        deal_id,
        position.deal_reference,
        position.epic,
        float(position.entry_price or 0),
    )

    if exit_price is None or pnl is None:
        print(
            f"No matching transaction found for deal_id={deal_id} in the "
            f"last {days} days."
        )
        if not assume_yes:
            manual_pnl = input("Enter P&L manually (blank to skip): ").strip()
            if not manual_pnl:
                return {"status": "skipped", "message": "No match and no manual value"}
            try:
                pnl = float(manual_pnl)
                exit_price = float(input("Enter exit price: ").strip())
                reason = (input("Enter close reason [EXTERNAL]: ").strip() or "EXTERNAL")
            except ValueError:
                return {"status": "skipped", "message": "Invalid manual input"}
        else:
            return {"status": "skipped", "message": "No match found, --yes auto-skip"}

    print(
        f"\nReconciliation diff for {deal_id} ({position.epic}):\n"
        f"  current: pnl={position.pnl}, exit_price={position.exit_price}, "
        f"close_reason={position.close_reason}\n"
        f"  broker:  pnl={pnl:.2f}, exit_price={exit_price:.6f}, "
        f"close_reason={reason}\n"
    )

    if not assume_yes:
        confirm = input("Apply UPDATE? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            return {"status": "cancelled", "message": "User declined"}

    position.pnl = pnl
    position.exit_price = exit_price
    position.close_reason = reason or "EXTERNAL"
    await session.commit()
    print(f"✓ Updated position {deal_id}")
    return {
        "status": "updated",
        "pnl": pnl,
        "exit_price": exit_price,
        "close_reason": reason,
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile a position with broker data.")
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--yes", action="store_true", help="Assume yes on prompts")
    args = parser.parse_args()

    settings = get_settings()
    broker = CapitalComClient(
        api_key=settings.capital_api_key,
        email=settings.capital_email,
        password=settings.capital_password_decrypted,
        demo=settings.capital_demo,
    )
    await broker.connect()

    try:
        async with get_async_session_context() as session:
            result = await reconcile_deal_id(
                deal_id=args.deal_id,
                session=session,
                broker=broker,
                assume_yes=args.yes,
                days=args.days,
            )
    finally:
        await broker.close()

    status = result["status"]
    if status == "updated" or status == "cancelled":
        return 0
    if status == "not_found":
        print(result["message"], file=sys.stderr)
        return 1
    if status == "refused":
        print(result["message"], file=sys.stderr)
        return 2
    if status == "skipped":
        print(result["message"], file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
```

- [ ] **Step 4: Run the CLI tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/scripts/test_reconcile_position.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/reconcile_position.py backend/tests/scripts/test_reconcile_position.py
git commit -m "feat(cli): reconcile_position.py for manual P&L reconciliation"
```

---

## Phase 7 — Integration Tests + Full Sweep

### Task 12: End-to-end deferred-then-reconciled scenario

**Files:**
- Create: `backend/tests/integration/test_close_reconciliation_e2e.py`

- [ ] **Step 1: Write the integration test**

```python
"""End-to-end scenario: broker returns [] for N iterations, then the
matching transaction, then verify: path=primary, retry_count=N, DB has
real P&L, no UNRECONCILED record."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.broker.models import Transaction


def _txn(**kw):
    defaults = dict(
        date=datetime(2026, 4, 20, 0, 2, 0),
        type="DEAL",
        reference="ref-e2e",
        instrumentName="Oil - Crude",
        openLevel=84.50,
        closeLevel=85.60,
        profitAndLoss="USD246.86",
        size=10.0,
        currency="USD",
    )
    defaults.update(kw)
    return Transaction(**defaults)


@pytest.mark.asyncio
async def test_defer_three_times_then_reconcile(monkeypatch):
    from src.trading.paper_loop import PaperTradingLoop

    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop._previous_positions = {
        "deal-e2e": {
            "deal_id": "deal-e2e",
            "deal_reference": "ref-e2e",
            "epic": "WTIUSD",
            "direction": "BUY",
            "size": 10.0,
            "level": 84.50,
        }
    }
    loop._pending_close_detections = {}
    loop._broker_closed_deals = set()
    loop.execution_engine = MagicMock()
    loop.execution_engine.mode = "DEMO"

    class _ModeEnum:
        PAPER = "PAPER"

    monkeypatch.setattr("src.trading.paper_loop.ExecutionMode", _ModeEnum)

    loop.broker = AsyncMock()
    loop.risk_manager = MagicMock()
    loop.trailing_stop_manager = MagicMock()
    loop.trailing_stop_manager.tracked_positions = {}
    loop._fetch_equity = AsyncMock(return_value=10000.0)
    loop._persist_position_close = AsyncMock()
    loop._on_position_closed = MagicMock()
    loop._log_source = "demo_trading"

    call_count = {"n": 0}

    async def _fetch_txns():
        call_count["n"] += 1
        if call_count["n"] < 4:
            return []
        return [_txn(reference="ref-e2e")]

    loop._fetch_recent_transactions = _fetch_txns

    # Simulate 4 loop iterations with the position disappeared each time
    for i in range(4):
        await loop._detect_broker_closed(current_positions=[])

    # After iteration 4: reconciled
    assert "deal-e2e" not in loop._pending_close_detections
    loop._persist_position_close.assert_awaited_once()
    kwargs = loop._persist_position_close.await_args.kwargs
    assert kwargs["pnl"] == pytest.approx(246.86)
    assert kwargs["close_reason"] == "TP"
    loop._on_position_closed.assert_called_once()
```

- [ ] **Step 2: Run**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/integration/test_close_reconciliation_e2e.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_close_reconciliation_e2e.py
git commit -m "test(integration): e2e defer-then-reconcile scenario"
```

---

### Task 13: Full test suite + lint

**Files:** none new

- [ ] **Step 1: Full pytest sweep**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: all tests pass, including pre-existing suite.

If any pre-existing test fails because it asserted on `_fallback_close_detection` behavior: update it to assert on the deferred / unreconciled behavior instead. Do NOT re-introduce the fallback.

- [ ] **Step 2: Ruff + black**

```bash
cd backend && .venv/Scripts/python.exe -m ruff check src/ tests/ scripts/
cd backend && .venv/Scripts/python.exe -m black --check src/ tests/ scripts/
```

Fix any findings with:

```bash
cd backend && .venv/Scripts/python.exe -m ruff check --fix src/ tests/ scripts/
cd backend && .venv/Scripts/python.exe -m black src/ tests/ scripts/
```

- [ ] **Step 3: Commit (if any lint fixes)**

```bash
git add -A
git diff --cached --quiet || git commit -m "style: ruff + black after close-detection refactor"
```

---

## Phase 8 — Manual Pre-Merge Verification (Demo)

### Task 14: Manual verification checklist

This task produces no commits. It is executed by Stefano against the demo account before merging to `master`.

- [ ] **Step 1: Deploy branch to running backend**

```bash
cd backend
git checkout fix/close-detection-robust
# Stop running backend, then:
.venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Open test positions — one per asset class**

Via UI `/paper-trading`, open a small position on each:
- Forex: EURUSD, size 1000
- Crypto: BTCUSD, size 0.01
- Index: DE40, size 0.1
- Commodity: WTIUSD, size 1

Note the `deal_id` and `deal_reference` from logs for each.

- [ ] **Step 3: Close all via Capital.com UI directly**

Log in to Capital.com demo web UI, close the four positions manually.

- [ ] **Step 4: Verify within 1 minute**

Check the backend logs for each position:

```
[EPIC] Matched broker transaction: exit=..., P&L=$..., reason=TP/SL
[EPIC] Position <deal_id> closed by broker (reason=..., exit=..., P&L=$..., retry=0)
```

Compare the P&L in the log against the Capital.com transaction history page. Tolerance: < $0.01.

Check the DB:

```sql
SELECT deal_id, epic, pnl, exit_price, close_reason
FROM positions
WHERE status='CLOSED'
ORDER BY closed_at DESC LIMIT 4;
```

All four rows must have:
- `pnl` matching broker UI
- `close_reason` in ('SL', 'TP', 'EXTERNAL')
- No row with `close_reason='UNRECONCILED'`

- [ ] **Step 5: Simulate transient API failure**

Temporarily disconnect your internet for ~30s while a position is open. Close it via Capital.com UI during the outage. Reconnect.

Expected log sequence (within the 10min timeout):
```
[EPIC] Close detected but no broker transaction match ... — deferring
...
[EPIC] Reconciled after N retries: exit=..., P&L=$...
```

The position ends up correctly persisted, no UNRECONCILED row.

- [ ] **Step 6: Simulate sustained API failure (UNRECONCILED path)**

Open a position. Close it via Capital.com UI. Immediately block the backend's network access to `*.backend-capital.com` for >10 minutes (e.g. via hosts file or firewall rule). Wait for the timeout.

Expected:
- DB row has `pnl=NULL`, `close_reason='UNRECONCILED'`.
- Telegram alert received with the reconciliation CLI command in the body.
- Prometheus counter `mantis_close_detection_path_total{path="unreconciled"}` incremented.

Restore network. Run:

```bash
cd backend && .venv/Scripts/python.exe scripts/reconcile_position.py --deal-id <ID>
```

Confirm the UPDATE prompt, verify `pnl` and `close_reason` are now correct in DB.

- [ ] **Step 7: Fix the 2026-04-20 corrupted records**

Run the CLI for each:

```bash
cd backend
.venv/Scripts/python.exe scripts/reconcile_position.py --deal-id 00018509-0055-311e-0000-0000825fab3a  # WTIUSD
.venv/Scripts/python.exe scripts/reconcile_position.py --deal-id 00018387-0055-311e-0000-000081d514a5  # NATGAS
.venv/Scripts/python.exe scripts/reconcile_position.py --deal-id 07101627-0015-549e-0000-00008103d503  # DE40
```

If the 24h window of transaction history no longer covers those closes (they happened at 00:01–00:09 on 2026-04-20), pass `--days 14` or larger. If still no match, enter the broker-reported P&L manually when prompted.

- [ ] **Step 8: Open the PR**

```bash
git push -u origin fix/close-detection-robust
gh pr create --title "fix: three-tier close detection (stop invented P&L writes)" --body "$(cat <<'EOF'
## Summary
- Replace the legacy `(exit - entry) * size` fallback with a three-tier close detection (primary → deferred → UNRECONCILED).
- Fix ISO 8601 UTC timezone on Capital.com Transaction History params (root cause of 2026-04-20 empty-list incident).
- Add `deal_reference`-deterministic matching (Strategy 1), `deal_id` legacy (Strategy 2), normalized instrument-name + entry tolerance (Strategy 3).
- Never invent P&L: unreconciled closes go to DB with `pnl=NULL` and `close_reason='UNRECONCILED'`, filtered out of win-rate / Kelly / equity-curve aggregations.
- New CLI: `scripts/reconcile_position.py` for manual fix of the three 2026-04-20 records (rows 2119, 2120, 2121) and any future UNRECONCILED.
- Prometheus counter `mantis_close_detection_path_total` for observability.

Spec: `docs/superpowers/specs/2026-04-20-close-detection-pnl-robustness-design.md`
Plan: `docs/superpowers/plans/2026-04-20-close-detection-pnl-robustness.md`

## Test plan
- [x] Unit tests: 3 matching strategies, deferred, timeout → UNRECONCILED, currency mismatch warning
- [x] Integration test: defer-then-reconcile after 4 iterations
- [x] Full pytest sweep + ruff + black
- [x] Manual verification step 2-6 on demo account
- [x] 2026-04-20 corrupted records fixed via CLI (step 7)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 9: Post-merge observation**

Monitor for 24h after merge:
- Prometheus: `rate(mantis_close_detection_path_total{path="primary"}[1h]) ≫ rate(..{path="deferred"}[1h])`.
- Zero UNRECONCILED records except planned chaos-testing.
- Telegram alerts all carry real P&L values.

---

## Self-Review Checklist (completed at plan authoring time)

**1. Spec coverage.** Every spec section mapped to tasks:
- §1 Problem — addressed by entire plan.
- §2 Goals G1–G7 — G1 (no invented P&L) → Task 7 removal of fallback + Task 9 filter. G2 primary hardening → Tasks 1, 4, 5. G3 retry → Task 7. G4 UNRECONCILED → Task 7. G5 downstream immunity → Task 7 (_on_position_closed guard) + Task 9 (SQL filter). G6 observability → Task 8. G7 retroactive fix → Task 14 step 7.
- §3 Three-tier architecture — Task 7.
- §4 Components affected — mapped table-to-tasks.
- §5 Data flow (5.1 open persistence) — pre-flight finding confirms `deal_reference` already exists and is persisted; prev_pos dict in paper_loop reads it at Task 7.
- §6 Edge cases — (a) broker down: Task 7 try/except; (b) restart: Task 10; (c) modify: Strategy 1 immune (Task 4); (d) incomplete txn: Task 5 test; (e) ambiguous: Task 5 test; (f) legacy: Task 4 `deal_reference=None` test; (g) currency: Task 3; (h) CLI guard: Task 11 test; (i) post-timeout txn: Task 11 CLI; (j) Kelly sizer filter: Task 7 step 6.
- §7 Testing — Tasks 4, 5, 7, 9, 10, 11, 12.
- §8 Rollout — Task 14.
- §9 Open questions — all three resolved in pre-flight: (Q1) `deal_reference` exists, no migration; (Q2) `_on_position_closed` is the chokepoint; (Q3) currency mismatch warn-only in Task 3.

**2. Placeholder scan.** No TBD / TODO / "similar to Task N". All code steps contain full code. All commands contain exact bash.

**3. Type consistency.** `_match_transaction(transactions, deal_id, deal_reference, epic, entry_price)` is consistent across Tasks 4, 5, 7, 11. `PendingClose` fields match between Task 6 definition, Task 7 usage, Task 10 re-injection. `MetricsCollector.record_close_detection(path, epic, retry_count)` kwargs consistent across Tasks 7, 8.
