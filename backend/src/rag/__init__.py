# MANTIS-EVOLUTION: RAG package
"""Retrieval-Augmented Generation utilities for MANTIS AI agents.

Module imports are lazy to avoid the circular chain
``rag → memory_layer → agents → vision_agent → rag.context_builder``
that triggered when the package was eagerly loading every submodule on
first import. Callers should import the specific submodule they need
(e.g. ``from src.rag.vector_store import MantisVectorStore``).
"""

__all__ = [
    "NewsItem",
    "RAGContext",
    "SearchResult",
    "MantisNewsIngester",
    "MantisRAGContextBuilder",
    "MantisVectorStore",
]


def __getattr__(name: str):
    if name in ("NewsItem", "RAGContext", "SearchResult"):
        from src.rag.schemas import NewsItem, RAGContext, SearchResult
        return {"NewsItem": NewsItem, "RAGContext": RAGContext, "SearchResult": SearchResult}[name]
    if name == "MantisNewsIngester":
        from src.rag.news_ingester import MantisNewsIngester
        return MantisNewsIngester
    if name == "MantisRAGContextBuilder":
        from src.rag.context_builder import MantisRAGContextBuilder
        return MantisRAGContextBuilder
    if name == "MantisVectorStore":
        from src.rag.vector_store import MantisVectorStore
        return MantisVectorStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
