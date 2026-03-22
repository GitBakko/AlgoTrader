# MANTIS-EVOLUTION: Memory Layer
"""
3-layer memory system for MANTIS AI:
  - Short-Term Memory (STM): in-memory ring buffer of recent signals/trades
  - Long-Term Memory (LTM): SQLite-backed pattern store with similarity search
  - Episodic Memory: SQLite-backed high-impact event store with embeddings

This package provides schema contracts, storage backends, and the unified
MemoryManager that orchestrates all three layers.
"""

from src.memory_layer.long_term import MantisLongTermMemory
from src.memory_layer.short_term import MantisShortTermMemory

__all__ = ["MantisShortTermMemory", "MantisLongTermMemory"]
