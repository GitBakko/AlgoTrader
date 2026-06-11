"""
Tests for _live_fill() retry behavior after a confirm timeout (audit M1.3).

Capital.com position creates are TWO-PHASE (POST then confirm): a 10s confirm
timeout does NOT mean the broker rejected the create — it may have FILLED
server-side. These tests pin that the corrected-SL/TP retry path only falls
through to the no-stops re-submit when the broker CONFIRMED a rejection, and
that after a timeout the order manager checks for (and adopts) an actual fill
instead of blindly re-submitting a duplicate position.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.broker.exceptions import CapitalComError
from src.broker.models import Direction, Position
from src.execution.order_manager import OrderManager
from src.execution.schemas import ExecutionMode, ExecutionOrder

# Exact error shape the production corrected-SL/TP branch matches on:
# "stoploss" substring + "stoploss.minvalue" + a ": <number>" broker limit.
SLTP_ERROR = "error.invalid.stoploss.minvalue: 498.0"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Neutralize the broker-propagation sleeps in _set_stops_after_fill.

    order_manager resolves ``asyncio.sleep`` through the module at call time,
    so patch at the source module (testing convention). Saves ~7s per
    adoption/no-stops test.
    """

    async def _instant(_seconds):
        return None

    monkeypatch.setattr("src.execution.order_manager.asyncio.sleep", _instant)


@pytest.fixture
def mock_broker():
    """Create a mock broker client with async methods."""
    broker = MagicMock()
    broker.create_position = AsyncMock()
    broker.close_position = AsyncMock()
    broker.modify_position = AsyncMock()
    broker.list_positions = AsyncMock(return_value=[])
    return broker


@pytest.fixture
def live_order_manager(mock_broker):
    """OrderManager in LIVE mode with a mocked broker."""
    return OrderManager(broker=mock_broker, mode=ExecutionMode.LIVE)


@pytest.fixture
def sample_order():
    """A sample ExecutionOrder whose SL the broker will reject."""
    return ExecutionOrder(
        epic="TSLA",
        direction="BUY",
        size=1.0,
        entry_price=500.0,
        stop_loss=499.0,
        take_profit=506.0,
    )


def _filled_position(deal_id="DEAL-FILLED-1", level=500.1, age_seconds=5.0, size=1.0):
    """Broker position matching sample_order epic/direction/size.

    ``age_seconds`` controls creation recency: the adoption guard only
    accepts positions created within the last 120 seconds. ``size`` is the
    broker-held size (already rounded to 4dp by CreatePositionRequest).
    """
    return Position(
        deal_id=deal_id,
        epic="TSLA",
        direction=Direction.BUY,
        size=size,
        level=level,
        currency="USD",
        created_date=datetime.now(UTC) - timedelta(seconds=age_seconds),
    )


def _open_confirmation(deal_id, level=500.3):
    """A successful (non-REJECTED) deal confirmation mock."""
    return MagicMock(
        deal_status="OPEN",
        deal_id=deal_id,
        deal_reference=f"REF-{deal_id}",
        level=level,
        status="OPEN",
        reason=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.execution
class TestLiveFillRetryConfirmation:
    """Corrected-SL/TP retry must require a broker-confirmed rejection
    before falling through to the no-stops re-submit."""

    async def test_timeout_after_fill_does_not_duplicate_position(
        self, live_order_manager, sample_order, mock_broker
    ):
        """Corrected retry times out but actually FILLED server-side:
        adopt the fill, do NOT send a third (duplicate) create."""
        mock_broker.create_position.side_effect = [
            CapitalComError(SLTP_ERROR),  # first create: SL/TP rejected
            TimeoutError(),  # corrected retry: confirm timeout
            # If the (buggy) no-stops re-submit fires anyway, it "succeeds"
            # with a different deal — making the duplicate visible.
            _open_confirmation("DEAL-DUP-2"),
        ]
        # The timed-out corrected create actually filled on the broker
        # moments ago (fresh: created now-5s, within the recency window).
        mock_broker.list_positions.return_value = [
            _filled_position(deal_id="DEAL-FILLED-1", level=500.1, age_seconds=5.0)
        ]

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is True
        assert result.deal_id == "DEAL-FILLED-1"
        assert mock_broker.create_position.await_count == 2  # NOT 3
        # Adoption must push stops onto the adopted deal (the position was
        # opened by a request whose original SL the broker had rejected).
        assert mock_broker.modify_position.await_count == 1
        assert mock_broker.modify_position.await_args.args[0] == "DEAL-FILLED-1"
        assert result.actual_stop_loss is not None
        assert result.actual_take_profit is not None

    async def test_timeout_with_no_fill_still_retries_no_stops(
        self, live_order_manager, sample_order, mock_broker
    ):
        """Corrected retry times out and NO fill exists on the broker:
        the no-stops re-submit must still proceed."""
        mock_broker.create_position.side_effect = [
            CapitalComError(SLTP_ERROR),  # first create: SL/TP rejected
            TimeoutError(),  # corrected retry: confirm timeout
            _open_confirmation("DEAL-3RD"),  # no-stops retry succeeds
        ]
        mock_broker.list_positions.return_value = []  # nothing filled

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is True
        assert result.deal_id == "DEAL-3RD"
        assert mock_broker.create_position.await_count == 3

    async def test_confirmed_rejection_still_falls_through(
        self, live_order_manager, sample_order, mock_broker
    ):
        """Corrected retry raises CapitalComError again (broker-CONFIRMED
        rejection, not a timeout): no fill-check needed, the no-stops
        re-submit proceeds as before."""
        mock_broker.create_position.side_effect = [
            CapitalComError(SLTP_ERROR),  # first create: SL/TP rejected
            CapitalComError(SLTP_ERROR),  # corrected retry: rejected again
            _open_confirmation("DEAL-NOSTOPS"),  # no-stops retry succeeds
        ]
        mock_broker.list_positions.return_value = []

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is True
        assert result.deal_id == "DEAL-NOSTOPS"
        assert mock_broker.create_position.await_count == 3

    async def test_stale_position_not_adopted(self, live_order_manager, sample_order, mock_broker):
        """A PRE-EXISTING position matching epic/direction/size (created 1h
        ago) must NOT be adopted as the timed-out create's fill — adopting
        it would overwrite ITS stops with the new order's levels. The
        no-stops re-submit proceeds instead."""
        mock_broker.create_position.side_effect = [
            CapitalComError(SLTP_ERROR),  # first create: SL/TP rejected
            TimeoutError(),  # corrected retry: confirm timeout
            _open_confirmation("DEAL-NOSTOPS-FRESH"),  # no-stops retry succeeds
        ]
        # Only a STALE same-epic/dir/size position exists on the broker.
        mock_broker.list_positions.return_value = [
            _filled_position(deal_id="DEAL-STALE-OLD", level=480.0, age_seconds=3600.0)
        ]

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is True
        assert result.deal_id == "DEAL-NOSTOPS-FRESH"  # NOT the stale deal
        assert mock_broker.create_position.await_count == 3

    async def test_adoption_matches_broker_rounded_size(self, live_order_manager, mock_broker):
        """Sizer outputs are unrounded floats but CreatePositionRequest rounds
        to 4dp before submission — the broker position holds the ROUNDED size.
        The fill-check must match against the submitted (rounded) value, or
        adoption never fires for typical sizer-derived sizes."""
        order = ExecutionOrder(
            epic="TSLA",
            direction="BUY",
            size=14.367823456,  # raw sizer output
            entry_price=500.0,
            stop_loss=499.0,
            take_profit=506.0,
        )
        mock_broker.create_position.side_effect = [
            CapitalComError(SLTP_ERROR),  # first create: SL/TP rejected
            TimeoutError(),  # corrected retry: confirm timeout
            _open_confirmation("DEAL-DUP-2"),  # duplicate visible if guard misses
        ]
        # Broker holds the 4dp-rounded size from the submitted request.
        mock_broker.list_positions.return_value = [
            _filled_position(deal_id="DEAL-FILLED-1", level=500.1, size=14.3678)
        ]

        result = await live_order_manager.submit_order(order)

        assert result.success is True
        assert result.deal_id == "DEAL-FILLED-1"
        assert mock_broker.create_position.await_count == 2  # adoption fired

    async def test_unknown_fill_state_fails_closed(
        self, live_order_manager, sample_order, mock_broker
    ):
        """If the post-timeout fill check itself fails (list_positions raises),
        the fill state is UNKNOWN — confirm-timeout and list failure are
        correlated broker degradation. Must FAIL CLOSED: no third create."""
        mock_broker.create_position.side_effect = [
            CapitalComError(SLTP_ERROR),  # first create: SL/TP rejected
            TimeoutError(),  # corrected retry: confirm timeout
        ]
        mock_broker.list_positions.side_effect = CapitalComError("503 service unavailable")

        result = await live_order_manager.submit_order(sample_order)

        assert result.success is False
        assert "duplicate guard" in (result.error or "")
        assert mock_broker.create_position.await_count == 2  # NO re-submit
