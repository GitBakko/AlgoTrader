# MANTIS-EVOLUTION: Memory layer schema contracts
"""
Pydantic v2 models defining shared contracts for the MANTIS AI 3-layer memory system.

These schemas are the single source of truth for:
  - What gets stored in Short-Term Memory (MemoryItem)
  - What gets stored in Long-Term Memory (MarketPattern, BlacklistCondition)
  - What gets stored in Episodic Memory (Episode, TradeOutcome)
  - What gets passed to agents as context (MemoryContext)
  - How the memory system is configured (MemoryConfig)

No numpy arrays in Pydantic models — list[float] for embeddings to ensure
clean JSON serialization and SQLite storage compatibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Core storage atoms
# ---------------------------------------------------------------------------


class MemoryItem(BaseModel):
    """Base item stored in any memory layer."""

    id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    epic: str = ""
    category: str = ""  # "signal", "trade", "pattern", "episode"
    data: dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0  # decay-adjusted weight

    class Config:
        arbitrary_types_allowed = True


class TradeOutcome(BaseModel):
    """Outcome of a completed trade, embedded inside Episode."""

    trade_id: str
    epic: str = ""
    entry_price: float
    exit_price: float
    pnl_pct: float
    duration_candles: int = 0
    max_drawdown_during: float = 0.0
    exit_reason: Literal["TP", "SL", "MANUAL", "TIMEOUT", "TIME"] = "MANUAL"


# ---------------------------------------------------------------------------
# Long-Term Memory schemas
# ---------------------------------------------------------------------------


class MarketPattern(BaseModel):
    """A recurring market pattern identified by the memory system."""

    pattern_id: str = ""
    description: str = ""
    regime: str = ""
    occurrence_count: int = 1
    avg_outcome: float = 0.0  # avg P&L when this pattern appears
    confidence: float = 0.0
    feature_signature: list[float] = Field(default_factory=list)  # embedding vector
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BlacklistCondition(BaseModel):
    """A condition pattern that historically produces losses."""

    condition_id: str = ""
    description: str = ""
    feature_signature: list[float] = Field(default_factory=list)
    avg_loss: float = 0.0
    occurrence_count: int = 0
    active: bool = True


# ---------------------------------------------------------------------------
# Episodic Memory schemas
# ---------------------------------------------------------------------------


class Episode(BaseModel):
    """A high-impact memorable event stored in episodic memory."""

    episode_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    epic: str = ""
    description: str = ""
    context_embedding: list[float] = Field(default_factory=list)
    outcome: Optional[TradeOutcome] = None
    significance: float = 0.0  # 0.0-1.0
    lesson: str = ""  # what was learned


# ---------------------------------------------------------------------------
# Agent-facing output schemas
# ---------------------------------------------------------------------------


class Warning(BaseModel):
    """Warning generated from episodic memory similarity search."""

    episode_id: str
    similarity: float = 0.0
    description: str = ""
    lesson: str = ""
    recommended_action: str = "reduce_size"  # reduce_size, skip, normal


class MemoryContext(BaseModel):
    """
    Combined context from all 3 memory layers.

    Passed to agents (TechnicalAnalyst, RiskManager, etc.) so they can
    incorporate memory into their reasoning without coupling to storage details.
    """

    recent_signals: list[MemoryItem] = Field(default_factory=list)
    recent_trades: list[MemoryItem] = Field(default_factory=list)
    recent_win_rate: float = 0.5
    similar_patterns: list[MarketPattern] = Field(default_factory=list)
    blacklist_conditions: list[BlacklistCondition] = Field(default_factory=list)
    episodic_warnings: list[Warning] = Field(default_factory=list)
    stm_item_count: int = 0
    ltm_pattern_count: int = 0
    episodic_count: int = 0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class MemoryConfig(BaseModel):
    """Configuration for the memory system."""

    stm_max_signals: int = 50
    stm_max_trades: int = 20
    decay_lambda: float = 0.1
    consolidation_interval_hours: int = 24
    episodic_significance_threshold: float = 0.8
    db_path: str = "data/memory/mantis_memory.db"
    embedding_model: str = "all-MiniLM-L6-v2"
