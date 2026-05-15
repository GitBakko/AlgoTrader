"""QW4 (2026-05-15): calendar gate MODE wiring + Prometheus counter."""

import pytest

from src.monitoring.metrics import (
    MetricsCollector,
    mantis_calendar_gate_blocked_total,
)
from src.utils.config import Settings


@pytest.mark.unit
def test_calendar_gate_mode_default_is_log_only():
    """Safe rollout — default mode ships observability without blocking."""
    s = Settings()
    assert s.calendar_gate_mode == "log_only"


@pytest.mark.unit
def test_calendar_gate_mode_accepts_valid_values(monkeypatch):
    for mode in ("off", "log_only", "block"):
        monkeypatch.setenv("CALENDAR_GATE_MODE", mode)
        s = Settings()
        assert s.calendar_gate_mode == mode


@pytest.mark.unit
def test_calendar_gate_mode_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("CALENDAR_GATE_MODE", "rubbish")
    with pytest.raises(Exception):
        Settings()


@pytest.mark.unit
def test_record_calendar_gate_blocked_counter():
    epic = "XAUUSD"
    before_log = mantis_calendar_gate_blocked_total.labels(
        epic=epic, mode="log_only"
    )._value.get()
    before_blk = mantis_calendar_gate_blocked_total.labels(
        epic=epic, mode="block"
    )._value.get()
    MetricsCollector.record_calendar_gate_blocked(epic=epic, mode="log_only")
    MetricsCollector.record_calendar_gate_blocked(epic=epic, mode="block")
    MetricsCollector.record_calendar_gate_blocked(epic=epic, mode="log_only")
    after_log = mantis_calendar_gate_blocked_total.labels(
        epic=epic, mode="log_only"
    )._value.get()
    after_blk = mantis_calendar_gate_blocked_total.labels(
        epic=epic, mode="block"
    )._value.get()
    assert after_log == before_log + 2
    assert after_blk == before_blk + 1
