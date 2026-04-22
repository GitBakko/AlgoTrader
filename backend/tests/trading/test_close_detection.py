"""Tests for close detection matching strategies in paper_loop."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

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


def test_match_strategy_1_deal_id_deterministic_live_schema(paper_loop):
    """Strategy 1 matches via the live Capital.com `dealId` field.

    Verified against demo-api 2026-04-21: TRADE rows expose the Position
    deal_id under `dealId`; the `reference` field is an internal txn id.
    """
    txns = [
        Transaction(
            date=datetime(2026, 4, 20, 17, 32, 45),
            transactionType="TRADE",
            note="Trade closed",
            reference="125579931413917",
            dealId="00018509-0055-311e-0000-00008262416d",
            instrumentName="OIL_CRUDE",
            size="79.37",
            currency="USDd",
        ),
    ]
    exit_price, pnl, reason = paper_loop._match_transaction(
        transactions=txns,
        deal_id="00018509-0055-311e-0000-00008262416d",
        deal_reference=None,
        epic="WTIUSD",
        entry_price=86.21,
    )
    assert pnl == pytest.approx(79.37)
    assert reason == "TP"
    # Live schema has no closeLevel → exit_price falls back to entry_price
    assert exit_price == pytest.approx(86.21)


def test_match_strategy_2_legacy_reference_match(paper_loop):
    """Strategy 2 matches when `txn.reference == deal_reference` on legacy
    payloads where the Position deal_reference is stored as the broker
    transaction reference (pre-2026-04-21 schema)."""
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
    assert reason == "TP"


def test_match_falls_through_to_reference_when_dealId_absent(paper_loop):
    """If the broker payload has no `dealId` (legacy schema), Strategy 1
    skips and Strategy 2 still matches by reference."""
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


def test_strategy_3_fuzzy_match_is_deleted(paper_loop):
    """Step 8 of close-detection v2: `_match_transaction` must NOT match on
    normalized instrument name + entry tolerance. Broker-initiated closes are
    now resolved by `CloseDetector` via `/history/activity` (activity-as-SoT),
    and the fuzzy name match was the vector for P&L-to-ghost-position leaks
    flagged in the 2026-04-21 audit.

    Regression guard: a TRADE row with matching instrumentName + openLevel
    but neither dealId nor reference must be rejected.
    """
    txns = [
        _txn(
            reference="unrelated-ref",
            instrumentName="Oil - Crude",
            openLevel=84.50,
            closeLevel=84.87,
            profitAndLoss="USD246.86",
        )
    ]
    result = paper_loop._match_transaction(
        transactions=txns,
        deal_id="deal-not-in-txns",
        deal_reference="ref-not-in-txns",
        epic="WTIUSD",
        entry_price=84.50,
    )
    assert result == (None, None, None)


def test_strategy_3_fuzzy_match_source_is_deleted(paper_loop):
    """Static guard: source of `_match_transaction` no longer contains the
    Strategy 3 fuzzy-match code markers. Prevents a quiet revert of Step 8.
    (Docstring may still reference the historical name — we guard the code,
    not the prose.)"""
    import inspect

    src = inspect.getsource(paper_loop._match_transaction)
    assert "norm_epic" not in src
    assert "norm_name" not in src
    assert "name_hit" not in src
    assert "entry_hit" not in src
    assert "EPIC_TO_BROKER" not in src  # no longer imported, no epic normalization


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


# ---------------------------------------------------------------------------
# Integration-style tests for the three-tier _detect_broker_closed flow
# ---------------------------------------------------------------------------

from datetime import UTC, timedelta

from src.trading.paper_loop import PaperTradingLoop, PendingClose


class _AsyncCM:
    """Async context manager yielding a mock DB session that returns [] for execute."""

    async def __aenter__(self):
        session = AsyncMock()
        result = MagicMock()
        result.all = MagicMock(return_value=[])
        session.execute = AsyncMock(return_value=result)
        return session

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.fixture
def loop_with_mocks(monkeypatch):
    """PaperTradingLoop with all external deps mocked for _detect_broker_closed."""
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop._previous_positions = {}
    loop._pending_close_detections = {}
    loop._broker_closed_deals = set()
    loop.execution_engine = MagicMock()

    class _ModeEnum:
        PAPER = "PAPER"
        DEMO = "DEMO"

    loop.execution_engine.mode = _ModeEnum.DEMO

    loop.broker = AsyncMock()
    loop.risk_manager = MagicMock()
    loop.trailing_stop_manager = MagicMock()
    loop.trailing_stop_manager.tracked_positions = {}
    loop._fetch_equity = AsyncMock(return_value=10000.0)
    loop._persist_position_close = AsyncMock()
    loop._on_position_closed = MagicMock()
    loop._log_source = "demo_trading"
    loop._fetch_recent_transactions = AsyncMock(return_value=[])

    # Use the real ExecutionMode so the mode check works
    monkeypatch.setattr(
        "src.trading.paper_loop.ExecutionMode",
        _ModeEnum,
        raising=False,
    )

    # Patch _db_session_factory to return an async context manager with empty DB
    loop._db_session_factory = lambda: _AsyncCM()

    return loop


@pytest.mark.asyncio
async def test_deferred_when_no_match_on_first_iteration(loop_with_mocks):
    """Position disappears, no matching txn → enters pending, no DB write, no alert."""
    loop = loop_with_mocks
    prev_pos = {
        "deal_id": "deal-1",
        "epic": "WTIUSD",
        "direction": "BUY",
        "size": 10.0,
        "level": 84.50,
    }
    loop._previous_positions = {"deal-1": prev_pos}
    loop._fetch_recent_transactions.return_value = []

    await loop._detect_broker_closed(current_positions=[])

    assert "deal-1" in loop._pending_close_detections
    pending = loop._pending_close_detections["deal-1"]
    assert pending.retry_count == 0
    loop._persist_position_close.assert_not_awaited()
    loop._on_position_closed.assert_not_called()


@pytest.mark.asyncio
async def test_unreconciled_after_timeout(loop_with_mocks):
    """After 10min without match → persist with pnl=None, close_reason=UNRECONCILED."""
    loop = loop_with_mocks
    past = datetime.now(UTC) - timedelta(seconds=601)
    loop._pending_close_detections["deal-1"] = PendingClose(
        deal_id="deal-1",
        deal_reference=None,
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

    loop._persist_position_close.assert_awaited_once()
    call_kwargs = loop._persist_position_close.await_args.kwargs
    assert call_kwargs["pnl"] is None
    assert call_kwargs["close_reason"] == "UNRECONCILED"
    loop._on_position_closed.assert_not_called()
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
        first_seen=datetime.now(UTC),
        retry_count=2,
    )
    loop._fetch_recent_transactions.return_value = [
        _txn(reference="ref-1", openLevel=84.50, closeLevel=85.60, profitAndLoss="USD246.86")
    ]

    await loop._detect_broker_closed(current_positions=[])

    loop._persist_position_close.assert_awaited_once()
    kwargs = loop._persist_position_close.await_args.kwargs
    assert kwargs["pnl"] == pytest.approx(246.86)
    assert kwargs["close_reason"] == "TP"
    loop._on_position_closed.assert_called_once()
    assert "deal-1" not in loop._pending_close_detections
