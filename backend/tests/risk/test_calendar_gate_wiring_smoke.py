"""Smoke test for calendar gate wiring (QW4 follow-up 2026-05-18).

In production we observed ZERO `Calendar blackout` log lines across 3 days
of log_only mode. This test verifies the gate logic CAN fire when an event
is correctly positioned — if this passes but production still shows 0
matches, the issue is data-side (no events landing in eval windows), not
wiring-side.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.external.sil_schemas import CalendarEvent
from src.risk.economic_calendar_gate import EconomicCalendarGate


def _settings(enabled: bool = True, before: int = 30, after: int = 15):
    """Patch get_settings inside economic_calendar_gate."""
    m = patch("src.risk.economic_calendar_gate.get_settings")
    mock = m.start()
    mock.return_value.sil_calendar_gate_enabled = enabled
    mock.return_value.sil_calendar_minutes_before = before
    mock.return_value.sil_calendar_minutes_after = after
    mock.return_value.finnhub_api_key = "test"
    return m


@pytest.fixture
def gate():
    m = _settings()
    try:
        yield EconomicCalendarGate()
    finally:
        m.stop()


def _make_event(event_name: str, country: str, ts: datetime) -> CalendarEvent:
    return CalendarEvent(
        event=event_name,
        country=country,
        currency="USD",
        impact="high",
        event_time=ts,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_blackout_fires_inside_pre_window(gate):
    """Fed Rate Decision in 10 min → USD epic must enter blackout."""
    now = datetime.now(UTC)
    gate._events_cache = [_make_event("Fed Rate Decision", "US", now + timedelta(minutes=10))]
    gate._cache_date = now.strftime("%Y-%m-%d")
    is_blk, reason = await gate.is_blackout("XAUUSD", now=now)
    assert is_blk is True, f"Expected blackout, got reason={reason!r}"
    assert "Fed Rate Decision" in reason


@pytest.mark.unit
@pytest.mark.asyncio
async def test_blackout_fires_inside_post_window(gate):
    """CPI 10 min ago → USD epic still in post-window."""
    now = datetime.now(UTC)
    gate._events_cache = [_make_event("CPI", "US", now - timedelta(minutes=10))]
    gate._cache_date = now.strftime("%Y-%m-%d")
    is_blk, _ = await gate.is_blackout("XAUUSD", now=now)
    assert is_blk is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_blackout_outside_window(gate):
    """Event 2h away → no blackout."""
    now = datetime.now(UTC)
    gate._events_cache = [_make_event("NFP", "US", now + timedelta(hours=2))]
    gate._cache_date = now.strftime("%Y-%m-%d")
    is_blk, _ = await gate.is_blackout("XAUUSD", now=now)
    assert is_blk is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_eu_event_does_not_block_pure_usd_epic(gate):
    """ECB event must not blackout XAUUSD (USD only)."""
    now = datetime.now(UTC)
    gate._events_cache = [_make_event("ECB Rate Decision", "EU", now + timedelta(minutes=10))]
    gate._cache_date = now.strftime("%Y-%m-%d")
    is_blk, _ = await gate.is_blackout("XAUUSD", now=now)
    assert is_blk is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_eu_event_blocks_de40(gate):
    """ECB event must blackout DE40 (EUR)."""
    now = datetime.now(UTC)
    gate._events_cache = [_make_event("ECB Rate Decision", "EU", now + timedelta(minutes=10))]
    gate._cache_date = now.strftime("%Y-%m-%d")
    is_blk, _ = await gate.is_blackout("DE40", now=now)
    assert is_blk is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_crypto_blocked_only_on_fed_or_cpi(gate):
    """BTCUSD (USD_MAJOR) must block on Fed Rate but NOT on Retail Sales."""
    now = datetime.now(UTC)
    # Retail Sales should NOT block crypto
    gate._events_cache = [_make_event("Retail Sales", "US", now + timedelta(minutes=10))]
    gate._cache_date = now.strftime("%Y-%m-%d")
    is_blk, _ = await gate.is_blackout("BTCUSD", now=now)
    assert is_blk is False
    # Fed Rate DOES block crypto
    gate._events_cache = [_make_event("Fed Rate Decision", "US", now + timedelta(minutes=10))]
    is_blk, _ = await gate.is_blackout("BTCUSD", now=now)
    assert is_blk is True
