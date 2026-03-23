# MANTIS-EVOLUTION: Unified Memory Store
"""Coordinates Short-Term, Long-Term, and Episodic memory layers."""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from src.agents.schemas import MarketContext
from src.memory_layer.schemas import (
    Episode,
    MemoryConfig,
    MemoryContext,
    MemoryItem,
    TradeOutcome,
    Warning,
)
from src.memory_layer.short_term import MantisShortTermMemory
from src.memory_layer.long_term import MantisLongTermMemory
from src.memory_layer.episodic import MantisEpisodicMemory
from src.memory_layer.embeddings import MantisEmbedder


class MantisMemoryStore:
    """
    Unified coordinator for all 3 memory layers.

    This is the object that agents use to access memory.
    Provides:
    - get_trading_context(): combines all layers into MemoryContext
    - record_signal(): writes to STM
    - record_outcome(): writes to STM + potentially promotes to LTM/Episodic
    - run_daily_consolidation(): STM → LTM pattern extraction
    """

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig()
        self.short_term = MantisShortTermMemory(self.config)
        self.long_term = MantisLongTermMemory(self.config)
        self.episodic = MantisEpisodicMemory(self.config)
        self.embedder = MantisEmbedder()
        self._last_consolidation: datetime | None = None

    def get_trading_context(self, market_context: MarketContext) -> MemoryContext:
        """
        Main method: returns a MemoryContext enriched from all 3 layers.
        Used by agents before making decisions.
        """
        # STM: recent signals and trades
        recent_signals = self.short_term.get_recent_signals(n=10)
        recent_trades = self.short_term.get_recent_trades(n=10)
        recent_win_rate = self.short_term.get_win_rate_recent(window_hours=24)

        # LTM: similar patterns for current regime
        regime = market_context.regime or ""
        similar_patterns = self.long_term.query_by_regime(regime, limit=5)
        blacklist = self.long_term.get_blacklist(active_only=True)

        # Episodic: warnings from similar negative episodes
        context_embedding = self.embedder.embed_market_context(market_context)
        episodic_warnings = self.episodic.get_warnings(context_embedding, similarity_threshold=0.7)

        return MemoryContext(
            recent_signals=recent_signals,
            recent_trades=recent_trades,
            recent_win_rate=recent_win_rate,
            similar_patterns=similar_patterns,
            blacklist_conditions=blacklist,
            episodic_warnings=episodic_warnings,
            stm_item_count=self.short_term.signal_count + self.short_term.trade_count,
            ltm_pattern_count=self.long_term.pattern_count,
            episodic_count=self.episodic.episode_count,
        )

    def record_signal(
        self,
        epic: str,
        direction: str,
        confidence: float,
        metadata: dict | None = None,
    ) -> str:
        """Record a new signal in STM."""
        return self.short_term.add_signal(epic, direction, confidence, metadata)

    def record_outcome(self, outcome: TradeOutcome) -> None:
        """
        Record a trade outcome.
        - Always writes to STM
        - If exceptional (top/bottom P&L), creates an Episode
        """
        self.short_term.add_trade_outcome(outcome)

        # Check if this is an exceptional trade (episode-worthy)
        significance = self._assess_significance(outcome)
        if significance >= self.config.episodic_significance_threshold:
            lesson = self._generate_lesson(outcome)
            self.episodic.record_episode(
                description=f"{outcome.epic}: {outcome.pnl_pct:+.4f} P&L ({outcome.exit_reason})",
                significance=significance,
                epic=outcome.epic,
                outcome=outcome,
                lesson=lesson,
            )

    def run_daily_consolidation(self) -> int:
        """
        Consolidate STM → LTM.
        Should be called periodically (e.g., daily cron).
        Returns number of patterns created/updated.
        """
        stm_items = list(self.short_term._trades)  # all trade items
        count = self.long_term.consolidate(stm_items)
        self._last_consolidation = datetime.now(timezone.utc)
        logger.info(f"Memory consolidation complete: {count} patterns updated")
        return count

    def save_state(self) -> bool:
        """Save STM snapshot to disk."""
        return self.short_term.save_snapshot()

    def load_state(self) -> bool:
        """Load STM snapshot from disk."""
        return self.short_term.load_snapshot()

    def _assess_significance(self, outcome: TradeOutcome) -> float:
        """
        Assess how significant/memorable a trade outcome is.
        Returns 0.0–1.0. Higher = more memorable.
        """
        significance = 0.0

        # Large P&L (positive or negative) = significant
        abs_pnl = abs(outcome.pnl_pct)
        if abs_pnl > 0.03:  # > 3% move
            significance = min(abs_pnl / 0.05, 1.0)  # 5% → max significance
        elif abs_pnl > 0.01:  # > 1%
            significance = 0.5

        # Large drawdown during trade = significant
        if outcome.max_drawdown_during > 0.02:
            significance = max(significance, 0.7)

        # Very short or very long trades = notable
        if outcome.duration_candles <= 2:  # flash trade
            significance = max(significance, 0.6)
        elif outcome.duration_candles > 50:  # held too long
            significance = max(significance, 0.5)

        return min(significance, 1.0)

    def _generate_lesson(self, outcome: TradeOutcome) -> str:
        """Generate a lesson string from a trade outcome."""
        if outcome.pnl_pct > 0:
            return (
                f"Profitable {outcome.exit_reason} exit on {outcome.epic}: "
                f"held {outcome.duration_candles} candles"
            )
        return (
            f"Loss on {outcome.epic} ({outcome.exit_reason}): "
            f"drawdown {outcome.max_drawdown_during:.4f}, held {outcome.duration_candles} candles"
        )
