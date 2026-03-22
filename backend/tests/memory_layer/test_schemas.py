"""
Tests for MANTIS-EVOLUTION Memory Layer schema contracts.

Covers all Pydantic v2 models used as contracts for the 3-layer memory system
(Short-Term Memory, Long-Term Memory, Episodic Memory).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.memory_layer.schemas import (
    BlacklistCondition,
    Episode,
    MarketPattern,
    MemoryConfig,
    MemoryContext,
    MemoryItem,
    TradeOutcome,
    Warning,
)


# ---------------------------------------------------------------------------
# MemoryItem
# ---------------------------------------------------------------------------


class TestMemoryItem:
    def test_default_creation(self):
        item = MemoryItem()
        assert item.id == ""
        assert item.epic == ""
        assert item.category == ""
        assert item.data == {}
        assert item.weight == 1.0
        assert isinstance(item.timestamp, datetime)

    def test_timestamp_is_utc(self):
        item = MemoryItem()
        # Should have timezone info
        assert item.timestamp.tzinfo is not None

    def test_custom_fields(self):
        item = MemoryItem(
            id="item-001",
            epic="XAUUSD",
            category="signal",
            data={"confidence": 0.75, "direction": "BUY"},
            weight=0.8,
        )
        assert item.id == "item-001"
        assert item.epic == "XAUUSD"
        assert item.category == "signal"
        assert item.data["confidence"] == 0.75
        assert item.weight == 0.8

    def test_category_values(self):
        for cat in ("signal", "trade", "pattern", "episode"):
            item = MemoryItem(category=cat)
            assert item.category == cat

    def test_data_accepts_nested_dict(self):
        item = MemoryItem(
            data={"features": {"rsi": 65.0, "adx": 28.0}, "meta": {"src": "scalp"}}
        )
        assert item.data["features"]["rsi"] == 65.0

    def test_serialization_roundtrip(self):
        item = MemoryItem(id="x", epic="BTCUSD", category="trade", weight=0.5)
        restored = MemoryItem.model_validate(item.model_dump())
        assert restored.id == item.id
        assert restored.epic == item.epic
        assert restored.weight == item.weight


# ---------------------------------------------------------------------------
# TradeOutcome
# ---------------------------------------------------------------------------


class TestTradeOutcome:
    def test_minimal_creation(self):
        outcome = TradeOutcome(trade_id="t-001", entry_price=1900.0, exit_price=1920.0, pnl_pct=1.05)
        assert outcome.trade_id == "t-001"
        assert outcome.epic == ""
        assert outcome.duration_candles == 0
        assert outcome.max_drawdown_during == 0.0
        assert outcome.exit_reason == "MANUAL"

    def test_all_exit_reasons_accepted(self):
        for reason in ("TP", "SL", "MANUAL", "TIMEOUT", "TIME"):
            outcome = TradeOutcome(
                trade_id="t-002",
                entry_price=1900.0,
                exit_price=1910.0,
                pnl_pct=0.5,
                exit_reason=reason,
            )
            assert outcome.exit_reason == reason

    def test_invalid_exit_reason_raises(self):
        with pytest.raises(ValidationError):
            TradeOutcome(
                trade_id="t-003",
                entry_price=1900.0,
                exit_price=1880.0,
                pnl_pct=-1.05,
                exit_reason="EXPIRED",  # invalid
            )

    def test_full_creation(self):
        outcome = TradeOutcome(
            trade_id="t-004",
            epic="XAUUSD",
            entry_price=2000.0,
            exit_price=1980.0,
            pnl_pct=-1.0,
            duration_candles=12,
            max_drawdown_during=-1.5,
            exit_reason="SL",
        )
        assert outcome.duration_candles == 12
        assert outcome.max_drawdown_during == -1.5
        assert outcome.exit_reason == "SL"

    def test_serialization_roundtrip(self):
        outcome = TradeOutcome(
            trade_id="t-005", entry_price=1900.0, exit_price=1920.0, pnl_pct=1.05
        )
        restored = TradeOutcome.model_validate(outcome.model_dump())
        assert restored.trade_id == outcome.trade_id
        assert restored.pnl_pct == outcome.pnl_pct


# ---------------------------------------------------------------------------
# MarketPattern
# ---------------------------------------------------------------------------


class TestMarketPattern:
    def test_default_creation(self):
        pattern = MarketPattern()
        assert pattern.pattern_id == ""
        assert pattern.description == ""
        assert pattern.regime == ""
        assert pattern.occurrence_count == 1
        assert pattern.avg_outcome == 0.0
        assert pattern.confidence == 0.0
        assert pattern.feature_signature == []

    def test_timestamp_is_utc(self):
        pattern = MarketPattern()
        assert pattern.last_seen.tzinfo is not None

    def test_with_feature_signature(self):
        sig = [0.1, 0.5, -0.3, 0.8, 0.0]
        pattern = MarketPattern(
            pattern_id="p-001",
            description="Bull breakout with high volume",
            regime="trending",
            feature_signature=sig,
            confidence=0.72,
        )
        assert pattern.feature_signature == sig
        assert len(pattern.feature_signature) == 5
        assert pattern.confidence == 0.72

    def test_update_occurrence(self):
        pattern = MarketPattern(occurrence_count=5, avg_outcome=0.8)
        assert pattern.occurrence_count == 5
        assert pattern.avg_outcome == 0.8

    def test_serialization_roundtrip(self):
        sig = [0.1, 0.2, 0.3]
        pattern = MarketPattern(pattern_id="p-002", feature_signature=sig)
        restored = MarketPattern.model_validate(pattern.model_dump())
        assert restored.pattern_id == "p-002"
        assert restored.feature_signature == sig


# ---------------------------------------------------------------------------
# Episode
# ---------------------------------------------------------------------------


class TestEpisode:
    def test_default_creation(self):
        ep = Episode()
        assert ep.episode_id == ""
        assert ep.epic == ""
        assert ep.description == ""
        assert ep.context_embedding == []
        assert ep.outcome is None
        assert ep.significance == 0.0
        assert ep.lesson == ""

    def test_timestamp_is_utc(self):
        ep = Episode()
        assert ep.timestamp.tzinfo is not None

    def test_with_nested_trade_outcome(self):
        outcome = TradeOutcome(
            trade_id="t-100",
            epic="XAUUSD",
            entry_price=1900.0,
            exit_price=1850.0,
            pnl_pct=-2.6,
            exit_reason="SL",
        )
        ep = Episode(
            episode_id="ep-001",
            epic="XAUUSD",
            description="Flash crash during FOMC announcement",
            context_embedding=[0.1, 0.9, -0.3],
            outcome=outcome,
            significance=0.95,
            lesson="Avoid BUY positions 1h before FOMC",
        )
        assert ep.outcome is not None
        assert ep.outcome.trade_id == "t-100"
        assert ep.outcome.exit_reason == "SL"
        assert ep.significance == 0.95

    def test_significance_range(self):
        # Significance is a plain float, no validation constraints specified
        ep = Episode(significance=1.0)
        assert ep.significance == 1.0
        ep2 = Episode(significance=0.0)
        assert ep2.significance == 0.0

    def test_serialization_roundtrip_with_outcome(self):
        outcome = TradeOutcome(
            trade_id="t-200", entry_price=1900.0, exit_price=1920.0, pnl_pct=1.05
        )
        ep = Episode(episode_id="ep-002", outcome=outcome)
        data = ep.model_dump()
        restored = Episode.model_validate(data)
        assert restored.episode_id == "ep-002"
        assert restored.outcome is not None
        assert restored.outcome.trade_id == "t-200"

    def test_serialization_roundtrip_no_outcome(self):
        ep = Episode(episode_id="ep-003", significance=0.5)
        restored = Episode.model_validate(ep.model_dump())
        assert restored.outcome is None
        assert restored.significance == 0.5


# ---------------------------------------------------------------------------
# BlacklistCondition
# ---------------------------------------------------------------------------


class TestBlacklistCondition:
    def test_default_creation(self):
        cond = BlacklistCondition()
        assert cond.condition_id == ""
        assert cond.description == ""
        assert cond.feature_signature == []
        assert cond.avg_loss == 0.0
        assert cond.occurrence_count == 0
        assert cond.active is True

    def test_active_and_inactive(self):
        active = BlacklistCondition(active=True)
        inactive = BlacklistCondition(active=False)
        assert active.active is True
        assert inactive.active is False

    def test_full_creation(self):
        cond = BlacklistCondition(
            condition_id="bl-001",
            description="RSI overbought + MACD cross during Asian session",
            feature_signature=[0.9, 0.1, -0.7],
            avg_loss=-2.3,
            occurrence_count=7,
            active=True,
        )
        assert cond.avg_loss == -2.3
        assert cond.occurrence_count == 7
        assert len(cond.feature_signature) == 3

    def test_deactivation(self):
        cond = BlacklistCondition(condition_id="bl-002", active=True)
        # Simulate deactivation by creating new instance
        updated = cond.model_copy(update={"active": False})
        assert updated.active is False
        assert updated.condition_id == "bl-002"

    def test_serialization_roundtrip(self):
        cond = BlacklistCondition(condition_id="bl-003", avg_loss=-1.5, occurrence_count=3)
        restored = BlacklistCondition.model_validate(cond.model_dump())
        assert restored.condition_id == "bl-003"
        assert restored.avg_loss == -1.5


# ---------------------------------------------------------------------------
# Warning
# ---------------------------------------------------------------------------


class TestWarning:
    def test_minimal_creation(self):
        w = Warning(episode_id="ep-001")
        assert w.episode_id == "ep-001"
        assert w.similarity == 0.0
        assert w.description == ""
        assert w.lesson == ""
        assert w.recommended_action == "reduce_size"

    def test_all_recommended_actions(self):
        for action in ("reduce_size", "skip", "normal"):
            w = Warning(episode_id="ep-002", recommended_action=action)
            assert w.recommended_action == action

    def test_full_creation(self):
        w = Warning(
            episode_id="ep-003",
            similarity=0.87,
            description="Current market resembles FOMC flash crash",
            lesson="Avoid BUY near FOMC",
            recommended_action="skip",
        )
        assert w.similarity == 0.87
        assert w.recommended_action == "skip"

    def test_serialization_roundtrip(self):
        w = Warning(episode_id="ep-004", similarity=0.6, recommended_action="reduce_size")
        restored = Warning.model_validate(w.model_dump())
        assert restored.episode_id == "ep-004"
        assert restored.similarity == 0.6


# ---------------------------------------------------------------------------
# MemoryContext
# ---------------------------------------------------------------------------


class TestMemoryContext:
    def test_empty_context(self):
        ctx = MemoryContext()
        assert ctx.recent_signals == []
        assert ctx.recent_trades == []
        assert ctx.recent_win_rate == 0.5
        assert ctx.similar_patterns == []
        assert ctx.blacklist_conditions == []
        assert ctx.episodic_warnings == []
        assert ctx.stm_item_count == 0
        assert ctx.ltm_pattern_count == 0
        assert ctx.episodic_count == 0

    def test_fully_populated_context(self):
        signals = [MemoryItem(id=f"s-{i}", category="signal") for i in range(3)]
        trades = [MemoryItem(id=f"t-{i}", category="trade") for i in range(2)]
        patterns = [MarketPattern(pattern_id=f"p-{i}") for i in range(2)]
        conditions = [BlacklistCondition(condition_id=f"bl-{i}") for i in range(1)]
        warnings = [Warning(episode_id=f"ep-{i}") for i in range(2)]

        ctx = MemoryContext(
            recent_signals=signals,
            recent_trades=trades,
            recent_win_rate=0.63,
            similar_patterns=patterns,
            blacklist_conditions=conditions,
            episodic_warnings=warnings,
            stm_item_count=5,
            ltm_pattern_count=10,
            episodic_count=3,
        )

        assert len(ctx.recent_signals) == 3
        assert len(ctx.recent_trades) == 2
        assert ctx.recent_win_rate == 0.63
        assert len(ctx.similar_patterns) == 2
        assert len(ctx.blacklist_conditions) == 1
        assert len(ctx.episodic_warnings) == 2
        assert ctx.stm_item_count == 5
        assert ctx.ltm_pattern_count == 10
        assert ctx.episodic_count == 3

    def test_serialization_roundtrip(self):
        ctx = MemoryContext(
            recent_signals=[MemoryItem(id="s-0", category="signal")],
            recent_win_rate=0.55,
            stm_item_count=1,
        )
        restored = MemoryContext.model_validate(ctx.model_dump())
        assert len(restored.recent_signals) == 1
        assert restored.recent_win_rate == 0.55
        assert restored.stm_item_count == 1

    def test_default_win_rate_neutral(self):
        ctx = MemoryContext()
        # Default win rate should be neutral (0.5 = no prior knowledge)
        assert ctx.recent_win_rate == 0.5

    def test_context_with_all_warning_types(self):
        warnings = [
            Warning(episode_id="ep-1", recommended_action="reduce_size"),
            Warning(episode_id="ep-2", recommended_action="skip"),
            Warning(episode_id="ep-3", recommended_action="normal"),
        ]
        ctx = MemoryContext(episodic_warnings=warnings)
        actions = [w.recommended_action for w in ctx.episodic_warnings]
        assert "reduce_size" in actions
        assert "skip" in actions
        assert "normal" in actions


# ---------------------------------------------------------------------------
# MemoryConfig
# ---------------------------------------------------------------------------


class TestMemoryConfig:
    def test_defaults(self):
        cfg = MemoryConfig()
        assert cfg.stm_max_signals == 50
        assert cfg.stm_max_trades == 20
        assert cfg.decay_lambda == 0.1
        assert cfg.consolidation_interval_hours == 24
        assert cfg.episodic_significance_threshold == 0.8
        assert cfg.db_path == "data/memory/mantis_memory.db"
        assert cfg.embedding_model == "all-MiniLM-L6-v2"

    def test_custom_values(self):
        cfg = MemoryConfig(
            stm_max_signals=100,
            stm_max_trades=40,
            decay_lambda=0.05,
            consolidation_interval_hours=12,
            episodic_significance_threshold=0.9,
            db_path="/tmp/test_memory.db",
            embedding_model="paraphrase-MiniLM-L3-v2",
        )
        assert cfg.stm_max_signals == 100
        assert cfg.stm_max_trades == 40
        assert cfg.decay_lambda == 0.05
        assert cfg.consolidation_interval_hours == 12
        assert cfg.episodic_significance_threshold == 0.9
        assert cfg.db_path == "/tmp/test_memory.db"
        assert cfg.embedding_model == "paraphrase-MiniLM-L3-v2"

    def test_serialization_roundtrip(self):
        cfg = MemoryConfig(stm_max_signals=75, decay_lambda=0.2)
        restored = MemoryConfig.model_validate(cfg.model_dump())
        assert restored.stm_max_signals == 75
        assert restored.decay_lambda == 0.2

    def test_db_path_is_string(self):
        cfg = MemoryConfig()
        assert isinstance(cfg.db_path, str)

    def test_thresholds_are_floats(self):
        cfg = MemoryConfig()
        assert isinstance(cfg.decay_lambda, float)
        assert isinstance(cfg.episodic_significance_threshold, float)
