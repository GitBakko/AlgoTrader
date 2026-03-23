# MANTIS-EVOLUTION: Episodic Memory Tests
"""Tests for MantisEpisodicMemory (TDD — written before implementation)."""
from __future__ import annotations

import pytest

from src.memory_layer.schemas import (
    Episode,
    MemoryConfig,
    TradeOutcome,
    Warning,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path) -> MemoryConfig:
    return MemoryConfig(db_path=str(tmp_path / "test_episodic.db"))


def _make_outcome(pnl_pct: float = -0.05) -> TradeOutcome:
    return TradeOutcome(
        trade_id="T001",
        epic="XAUUSD",
        entry_price=2000.0,
        exit_price=1990.0,
        pnl_pct=pnl_pct,
        exit_reason="SL",
    )


# Known embeddings for similarity tests
EMBEDDING_A = [1.0, 0.0, 0.0, 0.0]
EMBEDDING_B = [0.9, 0.1, 0.0, 0.0]   # very similar to A
EMBEDDING_C = [0.0, 0.0, 1.0, 0.0]   # orthogonal to A


# ---------------------------------------------------------------------------
# Import (will fail until module exists)
# ---------------------------------------------------------------------------


from src.memory_layer.episodic import MantisEpisodicMemory


# ---------------------------------------------------------------------------
# 1. test_init_creates_db
# ---------------------------------------------------------------------------


def test_init_creates_db(tmp_path):
    """DB file is created on disk after MantisEpisodicMemory is instantiated."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)
    assert (tmp_path / "test_episodic.db").exists()


# ---------------------------------------------------------------------------
# 2. test_record_episode_above_threshold
# ---------------------------------------------------------------------------


def test_record_episode_above_threshold(tmp_path):
    """Significance >= threshold (0.8) → episode is recorded, returns ID."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    episode_id = mem.record_episode(
        description="Flash crash on BTCUSD: -12% in 5 minutes",
        significance=0.9,
        epic="BTCUSD",
        lesson="Avoid trading during macro news events",
    )

    assert episode_id is not None
    assert isinstance(episode_id, str)
    assert len(episode_id) > 0


# ---------------------------------------------------------------------------
# 3. test_record_episode_below_threshold
# ---------------------------------------------------------------------------


def test_record_episode_below_threshold(tmp_path):
    """Significance < threshold (0.8) → NOT recorded, returns None."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    result = mem.record_episode(
        description="Minor signal generated for EURUSD",
        significance=0.5,
        epic="EURUSD",
    )

    assert result is None
    assert mem.episode_count == 0


# ---------------------------------------------------------------------------
# 4. test_get_episode_by_id
# ---------------------------------------------------------------------------


def test_get_episode_by_id(tmp_path):
    """Retrieve a specific episode by its ID."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    episode_id = mem.record_episode(
        description="Extreme Fear&Greed: index at 8",
        significance=0.85,
        epic="BTCUSD",
        lesson="Market capitulation zone",
    )
    assert episode_id is not None

    ep = mem.get_episode(episode_id)
    assert ep is not None
    assert ep.episode_id == episode_id
    assert ep.epic == "BTCUSD"
    assert ep.description == "Extreme Fear&Greed: index at 8"
    assert ep.lesson == "Market capitulation zone"
    assert ep.significance == 0.85


# ---------------------------------------------------------------------------
# 5. test_get_episode_not_found
# ---------------------------------------------------------------------------


def test_get_episode_not_found(tmp_path):
    """Non-existent episode_id → returns None."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    result = mem.get_episode("nonexistent-id")
    assert result is None


# ---------------------------------------------------------------------------
# 6. test_get_all_episodes_ordered
# ---------------------------------------------------------------------------


def test_get_all_episodes_ordered(tmp_path):
    """get_all_episodes returns episodes ordered by significance descending."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    mem.record_episode(description="Episode low sig", significance=0.82, epic="XAUUSD")
    mem.record_episode(description="Episode high sig", significance=0.99, epic="BTCUSD")
    mem.record_episode(description="Episode mid sig", significance=0.90, epic="US500")

    episodes = mem.get_all_episodes()
    assert len(episodes) == 3
    assert episodes[0].significance >= episodes[1].significance
    assert episodes[1].significance >= episodes[2].significance
    assert episodes[0].significance == 0.99


# ---------------------------------------------------------------------------
# 7. test_get_by_epic
# ---------------------------------------------------------------------------


def test_get_by_epic(tmp_path):
    """get_by_epic filters episodes to the specific epic."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    mem.record_episode(description="XAUUSD crash", significance=0.90, epic="XAUUSD")
    mem.record_episode(description="BTCUSD pump", significance=0.88, epic="BTCUSD")
    mem.record_episode(description="Another XAUUSD event", significance=0.85, epic="XAUUSD")

    xauusd_eps = mem.get_by_epic("XAUUSD")
    assert len(xauusd_eps) == 2
    assert all(ep.epic == "XAUUSD" for ep in xauusd_eps)

    btc_eps = mem.get_by_epic("BTCUSD")
    assert len(btc_eps) == 1
    assert btc_eps[0].epic == "BTCUSD"


# ---------------------------------------------------------------------------
# 8. test_record_with_outcome
# ---------------------------------------------------------------------------


def test_record_with_outcome(tmp_path):
    """TradeOutcome is persisted and can be retrieved correctly."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    outcome = _make_outcome(pnl_pct=-0.08)
    episode_id = mem.record_episode(
        description="High-confidence signal resulted in -8% loss",
        significance=0.92,
        epic="XAUUSD",
        outcome=outcome,
        lesson="ML confidence does not guarantee positive outcome in high volatility",
    )
    assert episode_id is not None

    ep = mem.get_episode(episode_id)
    assert ep is not None
    assert ep.outcome is not None
    assert ep.outcome.trade_id == "T001"
    assert ep.outcome.pnl_pct == -0.08
    assert ep.outcome.exit_reason == "SL"
    assert ep.outcome.entry_price == 2000.0


# ---------------------------------------------------------------------------
# 9. test_recall_similar_finds_matching
# ---------------------------------------------------------------------------


def test_recall_similar_finds_matching(tmp_path):
    """Episodes with similar embeddings are ranked highest in recall_similar."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    # Record three episodes with different embeddings
    mem.record_episode(
        description="Episode A — similar context",
        significance=0.85,
        epic="XAUUSD",
        context_embedding=EMBEDDING_A,
    )
    mem.record_episode(
        description="Episode B — very similar context",
        significance=0.85,
        epic="BTCUSD",
        context_embedding=EMBEDDING_B,
    )
    mem.record_episode(
        description="Episode C — orthogonal context",
        significance=0.85,
        epic="US500",
        context_embedding=EMBEDDING_C,
    )

    # Query similar to A — B should rank above C
    results = mem.recall_similar(EMBEDDING_A, top_k=3)
    assert len(results) == 3
    descriptions = [ep.description for ep in results]
    # A is identical to query (similarity=1.0), then B (very high), then C (0.0)
    assert "Episode A" in descriptions[0]
    assert "Episode C" not in descriptions[0]
    # C (orthogonal) should be last
    assert "Episode C" in descriptions[-1]


# ---------------------------------------------------------------------------
# 10. test_recall_similar_empty_embedding
# ---------------------------------------------------------------------------


def test_recall_similar_empty_embedding(tmp_path):
    """Empty query embedding → returns empty list without error."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    mem.record_episode(
        description="Some episode",
        significance=0.85,
        epic="XAUUSD",
        context_embedding=EMBEDDING_A,
    )

    results = mem.recall_similar([], top_k=3)
    assert results == []


# ---------------------------------------------------------------------------
# 11. test_get_warnings_negative_episodes
# ---------------------------------------------------------------------------


def test_get_warnings_negative_episodes(tmp_path):
    """get_warnings returns Warning objects for similar negative-outcome episodes."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    negative_outcome = _make_outcome(pnl_pct=-0.07)
    mem.record_episode(
        description="Painful loss on XAUUSD during FOMC",
        significance=0.90,
        epic="XAUUSD",
        outcome=negative_outcome,
        context_embedding=EMBEDDING_A,
        lesson="Avoid FOMC week entries",
    )

    # Query with very similar embedding
    warnings = mem.get_warnings(EMBEDDING_A, similarity_threshold=0.7)
    assert len(warnings) >= 1
    w = warnings[0]
    assert isinstance(w, Warning)
    assert w.similarity >= 0.7
    assert w.lesson == "Avoid FOMC week entries"
    assert w.recommended_action in ("skip", "reduce_size")


# ---------------------------------------------------------------------------
# 12. test_get_warnings_skips_positive
# ---------------------------------------------------------------------------


def test_get_warnings_skips_positive(tmp_path):
    """Episodes with positive P&L outcomes do NOT generate warnings."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    positive_outcome = _make_outcome(pnl_pct=0.12)
    mem.record_episode(
        description="Excellent trade on BTCUSD",
        significance=0.88,
        epic="BTCUSD",
        outcome=positive_outcome,
        context_embedding=EMBEDDING_A,
        lesson="Momentum plays work in trending BTC",
    )

    warnings = mem.get_warnings(EMBEDDING_A, similarity_threshold=0.7)
    assert len(warnings) == 0


# ---------------------------------------------------------------------------
# 13. test_get_warnings_high_similarity_skip
# ---------------------------------------------------------------------------


def test_get_warnings_high_similarity_skip(tmp_path):
    """Very similar episode (sim > 0.9) → recommended_action == 'skip'."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    negative_outcome = _make_outcome(pnl_pct=-0.10)
    # Use identical embedding to guarantee similarity = 1.0 > 0.9
    mem.record_episode(
        description="Catastrophic loss — identical context",
        significance=0.95,
        epic="XAUUSD",
        outcome=negative_outcome,
        context_embedding=EMBEDDING_A,
        lesson="This exact context leads to large losses",
    )

    warnings = mem.get_warnings(EMBEDDING_A, similarity_threshold=0.7)
    assert len(warnings) >= 1
    # The highest similarity warning should be "skip"
    skip_warnings = [w for w in warnings if w.recommended_action == "skip"]
    assert len(skip_warnings) >= 1


# ---------------------------------------------------------------------------
# 14. test_episode_count_property
# ---------------------------------------------------------------------------


def test_episode_count_property(tmp_path):
    """episode_count property reflects accurate number of stored episodes."""
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    assert mem.episode_count == 0

    mem.record_episode(description="Ep 1", significance=0.85, epic="XAUUSD")
    assert mem.episode_count == 1

    mem.record_episode(description="Ep 2", significance=0.90, epic="BTCUSD")
    assert mem.episode_count == 2

    # Below threshold — should NOT increment count
    mem.record_episode(description="Below threshold", significance=0.3, epic="EURUSD")
    assert mem.episode_count == 2


# ---------------------------------------------------------------------------
# 15. test_episode_never_decays
# ---------------------------------------------------------------------------


def test_episode_never_decays(tmp_path):
    """
    Episodes remain accessible indefinitely — no decay mechanism exists.
    Records episodes, re-opens the DB, and verifies all are still present.
    """
    config = _make_config(tmp_path)
    mem = MantisEpisodicMemory(config=config)

    ids = []
    for i in range(5):
        eid = mem.record_episode(
            description=f"Historical episode {i}",
            significance=0.85 + i * 0.01,
            epic="XAUUSD",
            lesson=f"Lesson {i}",
        )
        assert eid is not None
        ids.append(eid)

    # Re-instantiate from same DB (simulates app restart / long time passing)
    mem2 = MantisEpisodicMemory(config=config)
    assert mem2.episode_count == 5

    # Every individual episode is still retrievable
    for eid in ids:
        ep = mem2.get_episode(eid)
        assert ep is not None, f"Episode {eid} should not have decayed"
        assert "Historical episode" in ep.description
