"""End-to-end test: broker returns [] for N iterations, then the matching
transaction; verify the three-tier flow resolves to a primary path match
with the real broker P&L (no UNRECONCILED record, no invented P&L)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.broker.models import Transaction
from src.execution.schemas import ExecutionMode


def _txn(**kw):
    defaults = {
        "date": datetime(2026, 4, 20, 0, 2, 0),
        "transactionType": "TRADE",
        "reference": "ref-e2e",
        # Step 8 (close-detection v2): deterministic dealId match only —
        # Strategy 3 fuzzy instrumentName matching was removed. The e2e
        # fixture now mirrors current Capital.com live schema where each
        # TRADE row carries the Position.dealId on user-initiated closes.
        "dealId": "deal-e2e",
        "instrumentName": "Oil - Crude",
        "openLevel": 84.50,
        "closeLevel": 85.60,
        "profitAndLoss": "USD246.86",
        "size": 10.0,
        "currency": "USD",
    }
    defaults.update(kw)
    return Transaction(**defaults)


@pytest.fixture
def loop_for_e2e():
    """PaperTradingLoop instance with all external deps mocked for e2e flow."""
    from src.trading.paper_loop import PaperTradingLoop

    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop._previous_positions = {
        "deal-e2e": {
            "deal_id": "deal-e2e",
            "epic": "WTIUSD",
            "direction": "BUY",
            "size": 10.0,
            "level": 84.50,
        }
    }
    loop._pending_close_detections = {}
    loop._broker_closed_deals = set()
    # bypass DB bridge — deal_ref_map stays empty; Strategy 1 dealId match
    # does the work post-Step-8 (Strategy 3 fuzzy removed).
    loop._db_session_factory = None

    loop.execution_engine = MagicMock()
    loop.execution_engine.mode = ExecutionMode.DEMO  # use real enum so mode check passes

    loop.risk_manager = MagicMock()
    loop.trailing_stop_manager = MagicMock()
    loop.trailing_stop_manager.tracked_positions = {}
    loop._fetch_equity = AsyncMock(return_value=10000.0)
    loop._persist_position_close = AsyncMock()
    loop._on_position_closed = MagicMock()
    loop._log_source = "demo_trading"

    return loop


@pytest.mark.asyncio
async def test_defer_three_times_then_reconcile(loop_for_e2e):
    """Broker returns [] for 3 iterations, then the match on 4th.
    Verify:
    - iteration 1: enters _pending_close_detections
    - iterations 2-3: retry_count increments, still pending
    - iteration 4: primary path fires (reconciled), real pnl written
    - _on_position_closed called exactly once
    - pending dict is empty after reconciliation
    """
    loop = loop_for_e2e

    call_count = {"n": 0}

    async def _fetch_txns():
        call_count["n"] += 1
        if call_count["n"] < 4:
            return []
        return [
            _txn(
                reference="ref-e2e",
                openLevel=84.50,
                closeLevel=85.60,
                profitAndLoss="USD246.86",
            )
        ]

    loop._fetch_recent_transactions = _fetch_txns

    # --- Iteration 1: position disappeared, no transaction yet → defer ---
    await loop._detect_broker_closed(current_positions=[])
    assert (
        "deal-e2e" in loop._pending_close_detections
    ), "Position should be queued in pending on first miss"
    loop._persist_position_close.assert_not_awaited()
    loop._on_position_closed.assert_not_called()

    # --- Iterations 2 & 3: still no transaction → retry_count increments ---
    for _ in range(2):
        await loop._detect_broker_closed(current_positions=[])
    assert (
        "deal-e2e" in loop._pending_close_detections
    ), "Position should remain pending while broker still returns []"
    pending = loop._pending_close_detections["deal-e2e"]
    assert (
        pending.retry_count >= 2
    ), f"Expected retry_count >= 2 after 2 retries, got {pending.retry_count}"
    loop._persist_position_close.assert_not_awaited()

    # --- Iteration 4: broker returns the matching transaction → primary path ---
    await loop._detect_broker_closed(current_positions=[])

    # Reconciled: pending entry removed
    assert (
        "deal-e2e" not in loop._pending_close_detections
    ), "Pending entry should be removed after successful reconciliation"

    # _persist_position_close called exactly once with real data
    loop._persist_position_close.assert_awaited_once()
    kwargs = loop._persist_position_close.await_args.kwargs
    assert kwargs["pnl"] == pytest.approx(
        246.86
    ), f"Expected real broker P&L 246.86, got {kwargs['pnl']}"
    assert (
        kwargs["close_reason"] == "TP"
    ), f"Expected close_reason='TP', got {kwargs['close_reason']}"
    assert kwargs["exit_price"] == pytest.approx(
        85.60
    ), f"Expected exit_price=85.60 from broker closeLevel, got {kwargs['exit_price']}"

    # _on_position_closed called exactly once (Kelly/CB update)
    loop._on_position_closed.assert_called_once()


@pytest.mark.asyncio
async def test_deferred_then_unreconciled_after_timeout(loop_for_e2e):
    """Broker returns [] forever. A pre-aged pending entry exceeds the timeout.
    Verify:
    - UNRECONCILED is emitted (pnl=None, close_reason='UNRECONCILED')
    - _on_position_closed NOT called (no Kelly/CB update for unreconciled)
    - pending dict is empty after timeout handling
    """
    from src.trading.paper_loop import PendingClose

    loop = loop_for_e2e
    # Clear _previous_positions so no new disappearance fires — only the pre-aged pending
    loop._previous_positions = {}

    past = datetime.now(UTC) - timedelta(seconds=601)
    loop._pending_close_detections["deal-timeout"] = PendingClose(
        deal_id="deal-timeout",
        deal_reference=None,
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        prev_pos={"level": 84.50, "deal_id": "deal-timeout"},
        first_seen=past,
        retry_count=120,
    )
    loop._fetch_recent_transactions = AsyncMock(return_value=[])

    await loop._detect_broker_closed(current_positions=[])

    # UNRECONCILED path: _persist_position_close called with pnl=None
    loop._persist_position_close.assert_awaited_once()
    kwargs = loop._persist_position_close.await_args.kwargs
    assert kwargs["pnl"] is None, f"Expected pnl=None for UNRECONCILED, got {kwargs['pnl']}"
    assert (
        kwargs["close_reason"] == "UNRECONCILED"
    ), f"Expected close_reason='UNRECONCILED', got {kwargs['close_reason']}"

    # _on_position_closed must NOT be called for UNRECONCILED
    loop._on_position_closed.assert_not_called()

    # Pending dict emptied
    assert (
        "deal-timeout" not in loop._pending_close_detections
    ), "Timed-out pending entry should be removed"
