# MANTIS-EVOLUTION: Memory Layer
"""3-layer memory system for MANTIS AI.

Imports are lazy to avoid the
``memory_layer → embeddings → agents.schemas → agents.__init__ →
orchestrator → vision_agent → rag.context_builder → memory_layer.schemas``
cycle that triggered when callers (e.g. tests, scripts) imported only
``schemas`` from this package.
"""

__all__ = [
    "MantisEmbedder",
    "MantisShortTermMemory",
    "MantisLongTermMemory",
    "MantisEpisodicMemory",
    "MantisMemoryStore",
]


def __getattr__(name: str):
    if name == "MantisEmbedder":
        from src.memory_layer.embeddings import MantisEmbedder
        return MantisEmbedder
    if name == "MantisShortTermMemory":
        from src.memory_layer.short_term import MantisShortTermMemory
        return MantisShortTermMemory
    if name == "MantisLongTermMemory":
        from src.memory_layer.long_term import MantisLongTermMemory
        return MantisLongTermMemory
    if name == "MantisEpisodicMemory":
        from src.memory_layer.episodic import MantisEpisodicMemory
        return MantisEpisodicMemory
    if name == "MantisMemoryStore":
        from src.memory_layer.memory_store import MantisMemoryStore
        return MantisMemoryStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
