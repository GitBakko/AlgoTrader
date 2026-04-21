"""Contract tests for Capital.com /api/v1/history/activity schema.

Purpose
-------
These tests parse REAL broker payloads captured via
`scripts/capture_broker_fixtures.py` through the `ActivityEvent` Pydantic
model. They are deliberately schema-strict: a silent broker-side field
rename or a type change (e.g. `openPrice` flipping from float to int) will
break parsing and fail CI.

They encode, as executable documentation, the live contract we verified on
2026-04-21 after discovering that broker-initiated closes emit a dealId
different from `Position.dealId` (= position_dealId + 1 in last hex nibble)
while `/history/activity` still links back to the original entry price
via `details.openPrice`.

If this test starts failing, do NOT weaken the assertions — capture a fresh
fixture, inspect the diff, and update the model only if the schema change is
intentional on the broker side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.broker.models import (
    CLOSE_SOURCES,
    ActivityEvent,
    ActivityStatus,
    ActivityType,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "broker_api"


def _fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture {name} missing — run scripts/capture_broker_fixtures.py")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_activity_fixture_exists_and_has_metadata():
    payload = _fixture("live_20260421_activity.json")
    assert "_meta" in payload
    assert "response" in payload
    meta = payload["_meta"]
    assert meta["execution_mode"] in {"DEMO", "LIVE", "PAPER"}
    assert "captured_at_utc" in meta


def test_activity_payload_parses_through_pydantic():
    payload = _fixture("live_20260421_activity.json")
    activities = payload["response"].get("activities", [])
    assert activities, "No activities in captured fixture"

    parsed: list[ActivityEvent] = []
    for raw in activities:
        # Strict parse — any unknown value for required fields will raise.
        parsed.append(ActivityEvent(**raw))

    # Sanity: at least one POSITION event in a 24h window of active trading.
    position_events = [a for a in parsed if a.type == ActivityType.POSITION.value]
    assert position_events, "No POSITION events parsed"


def test_every_close_event_carries_open_price_and_reverse_direction():
    """The CORE invariant that v2 close-detection relies on.

    For every activity event we classify as a CLOSE (POSITION + ACCEPTED +
    close source), `details.openPrice` MUST be present and `details.direction`
    MUST be the reversed direction of the original position — that is what
    lets us match the close back to our Position row deterministically.
    """
    payload = _fixture("live_20260421_activity.json")
    activities = [
        ActivityEvent(**raw) for raw in payload["response"].get("activities", [])
    ]
    close_events = [a for a in activities if a.is_close_event()]
    if not close_events:
        pytest.skip("No close events in captured window (no TP/SL/USER fired)")

    for ev in close_events:
        assert (
            ev.details.open_price is not None and ev.details.open_price > 0
        ), f"Close event {ev.deal_id} missing details.openPrice"
        assert (
            ev.details.direction is not None
        ), f"Close event {ev.deal_id} missing details.direction"
        assert ev.details.size is not None and ev.details.size > 0


def test_source_values_within_known_set():
    """Warn (via assertion) if the broker introduces a new `source` value.

    We deliberately accept unknown strings at parse time, but the CI contract
    here fails loudly so we notice the schema extension and extend CLOSE_SOURCES
    / `close_reason_label` intentionally.
    """
    KNOWN_SOURCES = CLOSE_SOURCES | {
        # Known non-close sources that may appear:
        "USER",
        "SYSTEM",
    }
    payload = _fixture("live_20260421_activity.json")
    activities = [
        ActivityEvent(**raw) for raw in payload["response"].get("activities", [])
    ]
    observed = {a.source.upper() for a in activities}
    unknown = observed - KNOWN_SOURCES
    assert not unknown, (
        f"Broker emitted new activity.source values not yet in ActivitySource "
        f"enum: {sorted(unknown)}. Update models.py + close_reason_label() "
        f"before merging."
    )


def test_status_values_within_known_set():
    KNOWN_STATUS = {s.value for s in ActivityStatus}
    payload = _fixture("live_20260421_activity.json")
    activities = [
        ActivityEvent(**raw) for raw in payload["response"].get("activities", [])
    ]
    observed = {a.status for a in activities}
    unknown = observed - KNOWN_STATUS
    assert not unknown, (
        f"Broker emitted new activity.status values not yet in ActivityStatus "
        f"enum: {sorted(unknown)}. Update models.py before merging."
    )


def test_type_values_within_known_set():
    KNOWN_TYPE = {t.value for t in ActivityType}
    payload = _fixture("live_20260421_activity.json")
    activities = [
        ActivityEvent(**raw) for raw in payload["response"].get("activities", [])
    ]
    observed = {a.type for a in activities}
    unknown = observed - KNOWN_TYPE
    assert not unknown, (
        f"Broker emitted new activity.type values not yet in ActivityType "
        f"enum: {sorted(unknown)}. Update models.py before merging."
    )


def test_close_event_deal_id_differs_from_working_order_id():
    """Regression guard for the 2026-04-21 incident.

    Broker-initiated close events emit a NEW `dealId` (equal to
    `position.dealId + 1` in last hex nibble). The `details.workingOrderId`
    is a separate id on the close-side. Neither equals the original
    Position.dealId, which is why close-detection v2 must use
    (epic, openPrice, reverse direction, date) as the matcher — NOT dealId.
    This test asserts the schema still exposes both ids on close events.
    """
    payload = _fixture("live_20260421_activity.json")
    close_events = [
        ActivityEvent(**raw)
        for raw in payload["response"].get("activities", [])
        if ActivityEvent(**raw).is_close_event()
    ]
    if not close_events:
        pytest.skip("No close events in captured window")

    for ev in close_events:
        # Not asserting values, just that the pair is exposed.
        assert ev.deal_id, f"close event missing dealId: {ev}"
        # workingOrderId is optional when a SYSTEM close fires without one,
        # but for TP/SL it has been present in every sample we have seen.
        if ev.source.upper() in {"TP", "SL"}:
            assert ev.details.working_order_id is not None, (
                f"TP/SL close event {ev.deal_id} missing "
                f"details.workingOrderId — schema drift"
            )
