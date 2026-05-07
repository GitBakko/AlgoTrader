"""Unit tests for the strategy-loop bar-alignment helpers."""

from datetime import UTC, datetime

import pytest

from src.trading.paper_loop import (
    _resolution_to_seconds,
    _seconds_to_next_aligned_slot,
)


class TestResolutionToSeconds:
    @pytest.mark.parametrize(
        "resolution,expected",
        [
            ("1min", 60),
            ("5min", 300),
            ("15min", 900),
            ("30min", 1800),
            ("1h", 3600),
            ("2h", 7200),
            ("4h", 14400),
            ("1d", 86400),
            ("day", 86400),
            ("4H", 14400),  # case-insensitive
            ("  4h  ", 14400),  # whitespace tolerated
        ],
    )
    def test_known_resolutions(self, resolution, expected):
        assert _resolution_to_seconds(resolution) == expected

    @pytest.mark.parametrize("resolution", ["foo", "3h", "1week", "", "tick"])
    def test_unknown_returns_none(self, resolution):
        assert _resolution_to_seconds(resolution) is None


class TestSecondsToNextAlignedSlot:
    """4h grid → slots at 00/04/08/12/16/20 UTC + offset."""

    GRID_4H = 14400
    OFFSET = 10

    @pytest.mark.parametrize(
        "now_iso,expected_iso",
        [
            # Just before a 4h boundary
            ("2026-05-07T03:59:50", "2026-05-07T04:00:10+00:00"),
            ("2026-05-07T03:00:00", "2026-05-07T04:00:10+00:00"),
            # At exact boundary — already past, wait for the *next* slot
            ("2026-05-07T04:00:00", "2026-05-07T08:00:10+00:00"),
            # Within the offset window — still wait for the next full slot
            ("2026-05-07T04:00:09", "2026-05-07T08:00:10+00:00"),
            # Mid-day cases
            ("2026-05-07T20:00:00", "2026-05-08T00:00:10+00:00"),
            ("2026-05-07T23:59:59", "2026-05-08T00:00:10+00:00"),
        ],
    )
    def test_4h_grid_lands_on_canonical_utc_slot(self, now_iso, expected_iso):
        now = datetime.fromisoformat(now_iso).replace(tzinfo=UTC)
        s = _seconds_to_next_aligned_slot(now, self.GRID_4H, self.OFFSET)
        landed = datetime.fromtimestamp(now.timestamp() + s, tz=UTC)
        assert landed.isoformat() == expected_iso

    def test_1h_grid(self):
        now = datetime(2026, 5, 7, 3, 30, 0, tzinfo=UTC)
        s = _seconds_to_next_aligned_slot(now, 3600, 10)
        landed = datetime.fromtimestamp(now.timestamp() + s, tz=UTC)
        assert landed == datetime(2026, 5, 7, 4, 0, 10, tzinfo=UTC)

    def test_returns_at_least_one_second(self):
        # Even right on a slot boundary, sleep returns >= 1.0 to avoid
        # busy-looping with zero-duration awaits.
        now = datetime(2026, 5, 7, 4, 0, 10, tzinfo=UTC)
        s = _seconds_to_next_aligned_slot(now, self.GRID_4H, self.OFFSET)
        assert s >= 1.0
