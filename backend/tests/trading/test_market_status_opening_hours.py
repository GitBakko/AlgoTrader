"""Unit tests for `PaperTradingLoop._status_from_opening_hours`.

Closes the test-gap flagged by the final code review on commit
`48c6128` — the helper was added alongside the correlation-refresh split
but had no direct unit coverage (only exercised through integration in
`_resolve_market_status`).

Reference: `project_market_status_authoritative_2026-05-19.md` memory —
Capital.com snapshot.marketStatus returns CLOSED for US stocks during
regular hours while prices stream live; the per-instrument openingHours
map (zone: UTC) is the authoritative signal.
"""

from datetime import UTC, datetime

from src.trading.paper_loop import PaperTradingLoop


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# --- TRADEABLE path ---


def test_tradeable_inside_window() -> None:
    """US stock-equivalent window 13:30-20:00 UTC, query at 15:00 UTC."""
    opening_hours = {
        "zone": "UTC",
        "mon": ["13:30 - 20:00"],
    }
    now = _ts(2026, 5, 25, 15, 0)  # Monday 15:00 UTC
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "TRADEABLE"


def test_tradeable_at_window_start() -> None:
    opening_hours = {"zone": "UTC", "mon": ["08:00 - 20:00"]}
    now = _ts(2026, 5, 25, 8, 0)
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "TRADEABLE"


# --- CLOSED path ---


def test_closed_before_window() -> None:
    opening_hours = {"zone": "UTC", "mon": ["13:30 - 20:00"]}
    now = _ts(2026, 5, 25, 10, 0)  # 10:00 UTC, before 13:30 open
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "CLOSED"


def test_closed_after_window() -> None:
    opening_hours = {"zone": "UTC", "mon": ["13:30 - 20:00"]}
    now = _ts(2026, 5, 25, 21, 0)  # 21:00 UTC, after 20:00 close
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "CLOSED"


def test_closed_at_window_end_is_exclusive() -> None:
    """`if start <= now_minutes < end` makes the closing minute exclusive."""
    opening_hours = {"zone": "UTC", "mon": ["08:00 - 20:00"]}
    now = _ts(2026, 5, 25, 20, 0)  # exactly at close
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "CLOSED"


def test_closed_when_weekday_has_no_window() -> None:
    """Weekend day with empty windows list."""
    opening_hours = {
        "zone": "UTC",
        "mon": ["13:30 - 20:00"],
        "sat": [],
        "sun": [],
    }
    now = _ts(2026, 5, 30, 15, 0)  # Saturday
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "CLOSED"


# --- Overnight "00:00 = 24:00" semantics ---


def test_overnight_window_end_at_midnight_means_end_of_day() -> None:
    """Capital.com encodes overnight windows like "08:00 - 00:00" — `end=00:00`
    must be treated as 24:00 (end of same day), not 0:00 (which would yield
    an empty interval)."""
    opening_hours = {"zone": "UTC", "mon": ["08:00 - 00:00"]}
    now = _ts(2026, 5, 25, 23, 59)
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "TRADEABLE"


# --- Multi-window day (e.g. forex pause around bank rollover) ---


def test_multi_window_tradeable_in_second_window() -> None:
    opening_hours = {
        "zone": "UTC",
        "mon": ["00:00 - 21:00", "22:00 - 00:00"],
    }
    now = _ts(2026, 5, 25, 23, 0)  # 23:00 — inside the second window
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "TRADEABLE"


def test_multi_window_closed_between_windows() -> None:
    opening_hours = {
        "zone": "UTC",
        "mon": ["00:00 - 21:00", "22:00 - 00:00"],
    }
    now = _ts(2026, 5, 25, 21, 30)  # 21:30 — between windows
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "CLOSED"


# --- Malformed / None fallback ---


def test_returns_none_when_opening_hours_missing() -> None:
    """Caller falls back to snapshot.marketStatus on None."""
    now = _ts(2026, 5, 25, 15, 0)
    assert PaperTradingLoop._status_from_opening_hours(None, now) is None


def test_returns_none_when_zone_not_utc() -> None:
    """We only trust UTC-zoned schedules — anything else returns None so
    the caller falls back to snapshot.marketStatus."""
    opening_hours = {"zone": "America/New_York", "mon": ["09:30 - 16:00"]}
    now = _ts(2026, 5, 25, 15, 0)
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) is None


def test_skips_malformed_window_string() -> None:
    """A window string that doesn't split on `-` is skipped; the rest
    still evaluated."""
    opening_hours = {
        "zone": "UTC",
        "mon": ["malformed", "13:30 - 20:00"],
    }
    now = _ts(2026, 5, 25, 15, 0)
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "TRADEABLE"


def test_skips_window_with_non_hhmm_time() -> None:
    """Non-numeric time component is skipped."""
    opening_hours = {
        "zone": "UTC",
        "mon": ["abc:def - 20:00"],
    }
    now = _ts(2026, 5, 25, 15, 0)
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "CLOSED"


def test_default_zone_treated_as_utc() -> None:
    """Capital.com omits `zone` for many instruments → defaults to UTC
    in the helper (`opening_hours.get('zone', 'UTC')`)."""
    opening_hours = {"mon": ["13:30 - 20:00"]}
    now = _ts(2026, 5, 25, 15, 0)
    assert PaperTradingLoop._status_from_opening_hours(opening_hours, now) == "TRADEABLE"
