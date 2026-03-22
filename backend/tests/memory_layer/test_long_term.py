# MANTIS-EVOLUTION: Long Term Memory Tests
"""Tests for MantisLongTermMemory (TDD — written before implementation)."""
from __future__ import annotations

import pytest

from src.memory_layer.schemas import (
    BlacklistCondition,
    MarketPattern,
    MemoryConfig,
    MemoryItem,
    TradeOutcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path) -> MemoryConfig:
    return MemoryConfig(db_path=str(tmp_path / "test_ltm.db"))


def _make_pattern(regime: str = "trending", confidence: float = 0.7) -> MarketPattern:
    return MarketPattern(
        description=f"Test pattern in {regime}",
        regime=regime,
        occurrence_count=5,
        avg_outcome=0.02,
        confidence=confidence,
        feature_signature=[0.1, 0.2, 0.3],
    )


def _make_trade_item(regime: str = "trending", pnl_pct: float = 1.0) -> MemoryItem:
    return MemoryItem(
        epic="XAUUSD",
        category="trade",
        data={"regime": regime, "pnl_pct": pnl_pct},
    )


# ---------------------------------------------------------------------------
# Import (will fail until module exists)
# ---------------------------------------------------------------------------


from src.memory_layer.long_term import MantisLongTermMemory


# ---------------------------------------------------------------------------
# 1. test_init_creates_db
# ---------------------------------------------------------------------------


def test_init_creates_db(tmp_path):
    """DB file is created on disk after MantisLongTermMemory is instantiated."""
    config = _make_config(tmp_path)
    ltm = MantisLongTermMemory(config=config)
    db_file = tmp_path / "test_ltm.db"
    assert db_file.exists(), "SQLite DB file should be created on init"


# ---------------------------------------------------------------------------
# 2. test_add_pattern
# ---------------------------------------------------------------------------


def test_add_pattern(tmp_path):
    """add_pattern increments pattern_count."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    assert ltm.pattern_count == 0
    ltm.add_pattern(_make_pattern())
    assert ltm.pattern_count == 1


# ---------------------------------------------------------------------------
# 3. test_get_pattern_by_id
# ---------------------------------------------------------------------------


def test_get_pattern_by_id(tmp_path):
    """get_pattern retrieves the correct pattern by its ID."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    pattern = _make_pattern(regime="ranging")
    pid = ltm.add_pattern(pattern)

    retrieved = ltm.get_pattern(pid)
    assert retrieved is not None
    assert retrieved.pattern_id == pid
    assert retrieved.regime == "ranging"
    assert retrieved.description == "Test pattern in ranging"


# ---------------------------------------------------------------------------
# 4. test_get_pattern_not_found
# ---------------------------------------------------------------------------


def test_get_pattern_not_found(tmp_path):
    """get_pattern returns None for unknown IDs."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    result = ltm.get_pattern("does-not-exist")
    assert result is None


# ---------------------------------------------------------------------------
# 5. test_add_pattern_generates_id
# ---------------------------------------------------------------------------


def test_add_pattern_generates_id(tmp_path):
    """add_pattern auto-generates a non-empty pattern_id if none is provided."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    pattern = MarketPattern(description="no-id pattern", regime="volatile")
    pid = ltm.add_pattern(pattern)
    assert isinstance(pid, str)
    assert len(pid) > 0


# ---------------------------------------------------------------------------
# 6. test_update_existing_pattern
# ---------------------------------------------------------------------------


def test_update_existing_pattern(tmp_path):
    """Adding a pattern with the same pattern_id increments occurrence_count."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    pattern = _make_pattern()
    pid = ltm.add_pattern(pattern)

    # Add same pattern_id again (simulating an update call)
    pattern2 = MarketPattern(
        pattern_id=pid,
        description="updated",
        regime="trending",
        occurrence_count=1,
        avg_outcome=0.03,
        confidence=0.8,
    )
    ltm.add_pattern(pattern2)

    # pattern_count should still be 1 (no new row)
    assert ltm.pattern_count == 1

    # occurrence_count should have incremented
    retrieved = ltm.get_pattern(pid)
    assert retrieved is not None
    assert retrieved.occurrence_count == pattern.occurrence_count + 1


# ---------------------------------------------------------------------------
# 7. test_query_by_regime
# ---------------------------------------------------------------------------


def test_query_by_regime(tmp_path):
    """query_by_regime returns only patterns matching the given regime."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    ltm.add_pattern(_make_pattern(regime="trending"))
    ltm.add_pattern(_make_pattern(regime="trending"))
    ltm.add_pattern(_make_pattern(regime="ranging"))

    trending = ltm.query_by_regime("trending")
    assert len(trending) == 2
    assert all(p.regime == "trending" for p in trending)

    ranging = ltm.query_by_regime("ranging")
    assert len(ranging) == 1
    assert ranging[0].regime == "ranging"


# ---------------------------------------------------------------------------
# 8. test_query_all_patterns
# ---------------------------------------------------------------------------


def test_query_all_patterns(tmp_path):
    """query_all_patterns returns all patterns ordered by confidence desc."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    ltm.add_pattern(_make_pattern(confidence=0.3))
    ltm.add_pattern(_make_pattern(confidence=0.9))
    ltm.add_pattern(_make_pattern(confidence=0.6))

    patterns = ltm.query_all_patterns()
    assert len(patterns) == 3
    confidences = [p.confidence for p in patterns]
    assert confidences == sorted(confidences, reverse=True)


# ---------------------------------------------------------------------------
# 9. test_add_blacklist
# ---------------------------------------------------------------------------


def test_add_blacklist(tmp_path):
    """add_blacklist increments blacklist_count."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    assert ltm.blacklist_count == 0

    condition = BlacklistCondition(
        description="Losing in volatile regime",
        avg_loss=0.05,
        occurrence_count=4,
    )
    ltm.add_blacklist(condition)
    assert ltm.blacklist_count == 1


# ---------------------------------------------------------------------------
# 10. test_get_blacklist_active_only
# ---------------------------------------------------------------------------


def test_get_blacklist_active_only(tmp_path):
    """get_blacklist(active_only=True) excludes inactive conditions."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))

    active_cond = BlacklistCondition(description="active", avg_loss=0.03, active=True)
    inactive_cond = BlacklistCondition(description="inactive", avg_loss=0.02, active=False)

    ltm.add_blacklist(active_cond)
    ltm.add_blacklist(inactive_cond)

    active_list = ltm.get_blacklist(active_only=True)
    assert len(active_list) == 1
    assert active_list[0].active is True

    all_list = ltm.get_blacklist(active_only=False)
    assert len(all_list) == 2


# ---------------------------------------------------------------------------
# 11. test_consolidate_groups_by_regime
# ---------------------------------------------------------------------------


def test_consolidate_groups_by_regime(tmp_path):
    """consolidate groups STM trade items by regime and creates one pattern per regime."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))

    items = [
        _make_trade_item("trending", pnl_pct=1.0),
        _make_trade_item("trending", pnl_pct=2.0),
        _make_trade_item("ranging", pnl_pct=-0.5),
    ]

    created = ltm.consolidate(items)
    assert created == 2  # one per regime
    assert ltm.pattern_count == 2

    trending_patterns = ltm.query_by_regime("trending")
    assert len(trending_patterns) == 1
    assert trending_patterns[0].avg_outcome == pytest.approx(1.5)  # mean of 1.0 + 2.0

    ranging_patterns = ltm.query_by_regime("ranging")
    assert len(ranging_patterns) == 1
    assert ranging_patterns[0].avg_outcome == pytest.approx(-0.5)


# ---------------------------------------------------------------------------
# 12. test_consolidate_creates_blacklist_for_losers
# ---------------------------------------------------------------------------


def test_consolidate_creates_blacklist_for_losers(tmp_path):
    """consolidate creates a blacklist entry when avg_outcome < -0.01 with ≥3 trades."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))

    # 3 losing trades in "volatile" regime
    items = [
        _make_trade_item("volatile", pnl_pct=-0.05),
        _make_trade_item("volatile", pnl_pct=-0.03),
        _make_trade_item("volatile", pnl_pct=-0.04),
    ]

    ltm.consolidate(items)
    assert ltm.blacklist_count == 1

    bl = ltm.get_blacklist(active_only=True)
    assert bl[0].avg_loss > 0
    assert "volatile" in bl[0].description


# ---------------------------------------------------------------------------
# 13. test_consolidate_empty_items
# ---------------------------------------------------------------------------


def test_consolidate_empty_items(tmp_path):
    """consolidate with empty list returns 0 and creates no patterns."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    result = ltm.consolidate([])
    assert result == 0
    assert ltm.pattern_count == 0


# ---------------------------------------------------------------------------
# 14. test_pattern_count_property
# ---------------------------------------------------------------------------


def test_pattern_count_property(tmp_path):
    """pattern_count accurately reflects the number of rows in the DB."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    assert ltm.pattern_count == 0

    for i in range(5):
        ltm.add_pattern(MarketPattern(description=f"pattern-{i}", regime="test"))

    assert ltm.pattern_count == 5


# ---------------------------------------------------------------------------
# 15. test_feature_signature_roundtrip
# ---------------------------------------------------------------------------


def test_feature_signature_roundtrip(tmp_path):
    """feature_signature list[float] survives JSON serialisation to/from SQLite."""
    ltm = MantisLongTermMemory(config=_make_config(tmp_path))
    sig = [0.1, 0.25, 0.5, 0.75, 1.0, -0.3]
    pattern = MarketPattern(
        description="sig test",
        regime="trending",
        feature_signature=sig,
    )
    pid = ltm.add_pattern(pattern)

    retrieved = ltm.get_pattern(pid)
    assert retrieved is not None
    assert retrieved.feature_signature == pytest.approx(sig)
