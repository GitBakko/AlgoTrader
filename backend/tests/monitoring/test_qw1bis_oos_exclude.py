"""QW1-bis (2026-05-18): honor OOS scorecard EXCLUDE decisions."""

import json

import pytest

from src.monitoring.metrics import (
    MetricsCollector,
    mantis_oos_excluded_skipped_total,
)
from src.strategy.strategy_manager import StrategyManager


@pytest.mark.unit
def test_record_oos_excluded_skipped_counter():
    """Counter increments per epic label and is callable through MetricsCollector."""
    epic = "USDCAD"
    before = mantis_oos_excluded_skipped_total.labels(epic=epic)._value.get()
    MetricsCollector.record_oos_excluded_skipped(epic=epic)
    MetricsCollector.record_oos_excluded_skipped(epic=epic)
    after = mantis_oos_excluded_skipped_total.labels(epic=epic)._value.get()
    assert after == before + 2


@pytest.mark.unit
def test_from_optimal_thresholds_populates_excluded_epics(tmp_path):
    """The classmethod must load decision=EXCLUDE entries into excluded_epics."""
    payload = {
        "default_confidence": 0.40,
        "per_asset": {
            "USDCAD": {"min_confidence": 0.55, "decision": "EXCLUDE"},
            "USDCHF": {"min_confidence": 0.55, "decision": "EXCLUDE"},
            "XAUUSD": {"min_confidence": 0.55, "decision": "KEEP"},
            "NVDA": {"min_confidence": 0.45, "decision": "REVIEW"},
        },
    }
    p = tmp_path / "optimal_thresholds.json"
    p.write_text(json.dumps(payload))
    mgr = StrategyManager.from_optimal_thresholds(path=p)
    assert "USDCAD" in mgr.excluded_epics
    assert "USDCHF" in mgr.excluded_epics
    assert "XAUUSD" not in mgr.excluded_epics
    assert "NVDA" not in mgr.excluded_epics  # REVIEW is not EXCLUDE
    # Excluded epics also must not have a StrategyConfig
    assert "USDCAD" not in mgr._configs
    assert "USDCHF" not in mgr._configs
    # KEEP/REVIEW retain configs
    assert "XAUUSD" in mgr._configs
    assert "NVDA" in mgr._configs


@pytest.mark.unit
def test_excluded_epics_default_empty_when_no_file():
    """No path / missing JSON → empty excluded_epics, manager still usable."""
    mgr = StrategyManager()
    assert mgr.excluded_epics == set()
