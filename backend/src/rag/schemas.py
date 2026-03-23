# MANTIS-EVOLUTION: RAG schema contracts
from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """A single news article/item."""
    title: str = ""
    source: str = ""
    url: str = ""
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lead_paragraph: str = ""  # extracted key content
    full_text: str = ""
    relevance_score: float = 0.0  # 0.0-1.0
    sentiment: float = 0.0  # -1.0 to 1.0


class RAGContext(BaseModel):
    """Combined RAG context ready for agent consumption."""
    news_section: str = ""
    macro_section: str = ""
    memory_section: str = ""
    total_tokens_estimate: int = 0
    sources_count: int = 0


class SearchResult(BaseModel):
    """A result from the vector store."""
    text: str = ""
    metadata: dict = Field(default_factory=dict)
    similarity: float = 0.0
