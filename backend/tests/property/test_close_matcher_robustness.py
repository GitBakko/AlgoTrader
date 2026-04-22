"""Property-based robustness tests for CloseDetector matching.

Step 9 of close-detection v2 (plan `calm-questing-quail.md`).

Invariant under test:

    If a close activity satisfies
        (epic, details.openPrice ≈ entry, reverse direction, date > opened_at)
    then CloseDetector MUST pair it with the disappeared Position **regardless
    of the activity's dealId**. Capital.com emits a NEW dealId on broker-
    initiated closes (TP / SL / STOP_OUT) equal to
    ``position.dealId + 1`` in the last hex nibble; we have also observed
    truncated and case-mutated ids on legacy fixtures. A robust matcher
    never depends on dealId equality between the Position and the activity.

Companion invariants (anti-properties) are also asserted:
    * epic mismatch → no match
    * same direction (non-reverse) → no match
    * date ≤ opened_at → no match
    * entry price outside tolerance → no match

The detector is exercised directly with injected lists (no broker, no FX
HTTP) so each Hypothesis example runs in <10 ms.
"""

from __future__ import annotations

import asyncio
import string
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from src.broker.fx import FxConverter
from src.broker.models import ActivityEvent, Transaction
from src.trading.close_detector import CloseDetector, Reconciled


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _NoopFx(FxConverter):
    """FxConverter stub — returns the amount untouched, never touches FRED.

    Property tests fix txn currency and account currency to the same value
    so conversion is a passthrough; this subclass makes the independence
    from the real network explicit.
    """

    def __init__(self) -> None:  # no super().__init__ → no FREDClient built
        self._cache = {}  # type: ignore[assignment]
        self._fred = None  # type: ignore[assignment]

    async def convert(self, amount, from_ccy, to_ccy, at=None):  # type: ignore[override]
        return float(amount)


EPICS = ["DE40", "OIL_CRUDE", "XAUUSD", "BTCUSD", "EURUSD", "NATURALGAS"]
CLOSE_SOURCES_FOR_TESTING = ["TP", "SL", "STOP_OUT", "USER", "SYSTEM"]


def _hex_rotate_last(deal_id: str, delta: int) -> str:
    """Mutate the final hex nibble of a Capital.com-shaped dealId."""
    if not deal_id:
        return deal_id
    last = deal_id[-1]
    if last in string.hexdigits:
        value = int(last, 16)
        rotated = format((value + delta) % 16, "x")
        return deal_id[:-1] + (rotated if last.islower() else rotated.upper())
    return deal_id + format(delta % 16, "x")


DEAL_ID_MUTATIONS = [
    lambda s: s,  # identity
    lambda s: _hex_rotate_last(s, 1),  # +1 (broker close mutation, 2026-04-21)
    lambda s: _hex_rotate_last(s, 2),
    lambda s: _hex_rotate_last(s, -1),
    lambda s: s[:-4] + "abcd",  # tail replace
    lambda s: s[:-1] + s[-1].swapcase(),  # case flip
    lambda s: s[: max(len(s) - 6, 1)],  # truncated id
]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def position_strategy(draw):
    """Generate a believable disappeared-Position dict."""
    deal_id = draw(
        st.from_regex(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            fullmatch=True,
        )
    )
    epic = draw(st.sampled_from(EPICS))
    direction = draw(st.sampled_from(["BUY", "SELL"]))
    # Keep prices in a sensible band so the 0.1% tolerance arithmetic is stable.
    entry_price = draw(
        st.floats(min_value=1.0, max_value=50000.0, allow_nan=False, allow_infinity=False)
    )
    opened_offset_minutes = draw(st.integers(min_value=1, max_value=240))
    now = datetime.now(UTC)
    opened_at = now - timedelta(minutes=opened_offset_minutes)
    size = draw(st.floats(min_value=0.01, max_value=100.0, allow_nan=False))
    return {
        "deal_id": deal_id,
        "epic": epic,
        "direction": direction,
        "level": entry_price,
        "size": size,
        "opened_at": opened_at.isoformat(),
    }


def _build_close_activity(
    *,
    pos: dict,
    activity_deal_id: str,
    close_source: str = "TP",
    entry_shift_pct: float = 0.0,
    minutes_after_open: int = 1,
    override_epic: str | None = None,
    override_direction: str | None = None,
    before_opened_at: bool = False,
) -> ActivityEvent:
    """Construct a close ActivityEvent aligned with a Position dict."""
    base_entry = float(pos["level"])
    open_price = base_entry * (1.0 + entry_shift_pct)
    reverse = "SELL" if pos["direction"] == "BUY" else "BUY"
    direction = override_direction or reverse
    opened_dt = datetime.fromisoformat(pos["opened_at"])
    if before_opened_at:
        act_date = opened_dt - timedelta(minutes=1)
    else:
        act_date = opened_dt + timedelta(minutes=minutes_after_open)
    return ActivityEvent(
        date=act_date,
        dateUTC=act_date,
        epic=override_epic or pos["epic"],
        source=close_source,
        type="POSITION",
        status="ACCEPTED",
        dealId=activity_deal_id,
        details={
            "openPrice": open_price,
            "level": open_price * 1.001,  # exit ≠ entry so P&L is non-zero
            "direction": direction,
            "size": pos["size"],
            "currency": "USD",
        },
    )


def _build_matching_trade(*, activity_deal_id: str, pnl: float = 42.0) -> Transaction:
    return Transaction(
        date=datetime.now(UTC),
        transactionType="TRADE",
        note="Trade closed",
        reference="ref-irrelevant",
        dealId=activity_deal_id,
        instrumentName="",
        size=str(pnl),
        currency="USD",
    )


async def _detect_one(pos: dict, activity: ActivityEvent, txn: Transaction):
    detector = CloseDetector(
        broker=None, fx_converter=_NoopFx(), account_currency="USD"
    )
    return await detector.detect(
        previous={pos["deal_id"]: pos},
        current=[],
        activities=[activity],
        transactions=[txn],
    )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@settings(
    max_examples=75,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(pos=position_strategy(), mutation_idx=st.integers(min_value=0, max_value=len(DEAL_ID_MUTATIONS) - 1))
def test_match_is_independent_of_dealid_mutation(pos, mutation_idx):
    """Any dealId mutation on the activity side must not prevent the match
    as long as (epic, openPrice≈entry, reverse direction, date > opened_at)
    hold. This is the core invariant exposed by the 2026-04-21 production
    regression: broker emits dealId = position.dealId + 1 on TP closes."""
    activity_deal_id = DEAL_ID_MUTATIONS[mutation_idx](pos["deal_id"])
    activity = _build_close_activity(pos=pos, activity_deal_id=activity_deal_id)
    txn = _build_matching_trade(activity_deal_id=activity.deal_id, pnl=13.5)

    outcomes = asyncio.run(_detect_one(pos, activity, txn))

    assert len(outcomes) == 1
    oc = outcomes[0]
    assert isinstance(oc, Reconciled), f"unexpected outcome {type(oc).__name__}"
    assert oc.deal_id == pos["deal_id"]
    assert oc.close_dealid == activity.deal_id


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pos=position_strategy())
def test_entry_price_inside_tolerance_matches(pos):
    """Open price within the 0.1% tolerance must still match."""
    # Shift by 0.05% — inside default 0.1% tolerance
    activity = _build_close_activity(
        pos=pos, activity_deal_id=pos["deal_id"], entry_shift_pct=0.0005
    )
    txn = _build_matching_trade(activity_deal_id=activity.deal_id)

    outcomes = asyncio.run(_detect_one(pos, activity, txn))

    assert len(outcomes) == 1
    assert isinstance(outcomes[0], Reconciled)


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pos=position_strategy())
def test_entry_price_outside_tolerance_does_not_match(pos):
    """Open price 1% away from entry must NOT match (tolerance is 0.1%)."""
    activity = _build_close_activity(
        pos=pos, activity_deal_id=pos["deal_id"], entry_shift_pct=0.01
    )
    txn = _build_matching_trade(activity_deal_id=activity.deal_id)

    outcomes = asyncio.run(_detect_one(pos, activity, txn))

    assert len(outcomes) == 1
    # No activity match → Deferred (no_activity_event)
    from src.trading.close_detector import Deferred

    assert isinstance(outcomes[0], Deferred)


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pos=position_strategy(), other_epic=st.sampled_from(EPICS))
def test_epic_mismatch_never_matches(pos, other_epic):
    """If the activity epic differs from the Position's, no match is allowed."""
    if other_epic == pos["epic"]:
        return  # shrink: skip degenerate case
    activity = _build_close_activity(
        pos=pos, activity_deal_id=pos["deal_id"], override_epic=other_epic
    )
    txn = _build_matching_trade(activity_deal_id=activity.deal_id)

    outcomes = asyncio.run(_detect_one(pos, activity, txn))

    from src.trading.close_detector import Deferred

    assert len(outcomes) == 1
    assert isinstance(outcomes[0], Deferred)


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pos=position_strategy())
def test_same_direction_activity_never_matches(pos):
    """Close activities carry the REVERSE direction. Same direction ⇒ not a
    close of this Position (likely an open event on the same instrument)."""
    activity = _build_close_activity(
        pos=pos,
        activity_deal_id=pos["deal_id"],
        override_direction=pos["direction"],  # same, not reverse
    )
    txn = _build_matching_trade(activity_deal_id=activity.deal_id)

    outcomes = asyncio.run(_detect_one(pos, activity, txn))

    from src.trading.close_detector import Deferred

    assert len(outcomes) == 1
    assert isinstance(outcomes[0], Deferred)


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pos=position_strategy())
def test_activity_before_opened_at_never_matches(pos):
    """Activity.date ≤ position.opened_at cannot belong to this Position."""
    activity = _build_close_activity(
        pos=pos, activity_deal_id=pos["deal_id"], before_opened_at=True
    )
    txn = _build_matching_trade(activity_deal_id=activity.deal_id)

    outcomes = asyncio.run(_detect_one(pos, activity, txn))

    from src.trading.close_detector import Deferred

    assert len(outcomes) == 1
    assert isinstance(outcomes[0], Deferred)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    pos=position_strategy(),
    close_source=st.sampled_from(CLOSE_SOURCES_FOR_TESTING),
)
def test_all_close_sources_are_accepted(pos, close_source):
    """Every declared close source (TP/SL/STOP_OUT/USER/SYSTEM) must trigger
    a match when all other conditions hold."""
    activity = _build_close_activity(
        pos=pos, activity_deal_id=pos["deal_id"], close_source=close_source
    )
    txn = _build_matching_trade(activity_deal_id=activity.deal_id)

    outcomes = asyncio.run(_detect_one(pos, activity, txn))

    assert len(outcomes) == 1
    assert isinstance(outcomes[0], Reconciled)
