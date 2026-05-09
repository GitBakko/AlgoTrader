# MANTIS-EVOLUTION: RAG Context Builder tests
"""TDD tests for MantisRAGContextBuilder — run before implementation."""
from __future__ import annotations

import pytest

from src.rag.schemas import NewsItem, RAGContext
from src.memory_layer.schemas import (
    MemoryContext,
    MarketPattern,
    BlacklistCondition,
    Warning,
)
from src.rag.context_builder import MantisRAGContextBuilder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_news_item(
    title: str = "Gold hits record high",
    source: str = "reuters",
    sentiment: float = 0.5,
    lead_paragraph: str = "Gold surged above $3000 as safe-haven demand grew.",
) -> NewsItem:
    return NewsItem(
        title=title,
        source=source,
        sentiment=sentiment,
        lead_paragraph=lead_paragraph,
    )


def make_sil_data(
    fg: float | None = 0.3,
    real_yield: float | None = 1.5,
    cot: float | None = 0.4,
    social: float | None = 0.6,
    alpha: float | None = 0.25,
    composite: float | None = 0.35,
) -> dict:
    data = {}
    if fg is not None:
        data["sil_fear_greed_value"] = fg
    if real_yield is not None:
        data["sil_real_yield_10y"] = real_yield
    if cot is not None:
        data["sil_cot_net_position_norm"] = cot
    if social is not None:
        data["sil_social_bullish_ratio"] = social
    if alpha is not None:
        data["sil_alpha_sentiment_score"] = alpha
    if composite is not None:
        data["sil_composite_score"] = composite
    return data


def make_memory_context(
    win_rate: float = 0.55,
    stm_count: int = 10,
    ltm_count: int = 3,
    with_patterns: bool = False,
    with_warnings: bool = False,
    with_blacklist: bool = False,
) -> MemoryContext:
    patterns = []
    if with_patterns:
        patterns = [
            MarketPattern(
                pattern_id="p1",
                description="Bullish engulfing after support",
                confidence=0.7,
                avg_outcome=0.0035,
            )
        ]
    warnings = []
    if with_warnings:
        warnings = [
            Warning(
                episode_id="ep1",
                similarity=0.85,
                description="London open volatility spike",
                lesson="Reduce size during news events",
                recommended_action="reduce_size",
            )
        ]
    blacklist = []
    if with_blacklist:
        blacklist = [
            BlacklistCondition(
                condition_id="bl1",
                description="Low ADX chop zone",
                avg_loss=-0.02,
            )
        ]
    return MemoryContext(
        recent_win_rate=win_rate,
        stm_item_count=stm_count,
        ltm_pattern_count=ltm_count,
        similar_patterns=patterns,
        episodic_warnings=warnings,
        blacklist_conditions=blacklist,
    )


# ---------------------------------------------------------------------------
# Test 1: build with all sources
# ---------------------------------------------------------------------------


def test_build_with_all_sources():
    """All three sections populated when all sources provided."""
    builder = MantisRAGContextBuilder()
    news = [make_news_item()]
    sil = make_sil_data()
    mem = make_memory_context()

    ctx = builder.build(news=news, sil_data=sil, memory_context=mem)

    assert isinstance(ctx, RAGContext)
    assert ctx.news_section != ""
    assert ctx.macro_section != ""
    assert ctx.memory_section != ""
    assert ctx.total_tokens_estimate > 0
    assert ctx.sources_count > 0


# ---------------------------------------------------------------------------
# Test 2: build with news only
# ---------------------------------------------------------------------------


def test_build_news_only():
    """Only news section populated when only news provided."""
    builder = MantisRAGContextBuilder()
    news = [make_news_item("BTC rallies", sentiment=0.6)]

    ctx = builder.build(news=news)

    assert ctx.news_section != ""
    assert ctx.macro_section == ""
    assert ctx.memory_section == ""
    assert ctx.sources_count == 1


# ---------------------------------------------------------------------------
# Test 3: build with empty sources
# ---------------------------------------------------------------------------


def test_build_empty_sources():
    """Empty RAGContext returned when no data provided."""
    builder = MantisRAGContextBuilder()

    ctx = builder.build()

    assert ctx.news_section == ""
    assert ctx.macro_section == ""
    assert ctx.memory_section == ""
    assert ctx.total_tokens_estimate == 0
    assert ctx.sources_count == 0


# ---------------------------------------------------------------------------
# Test 4: news section format
# ---------------------------------------------------------------------------


def test_news_section_format():
    """News section has header and bullet-point entries."""
    builder = MantisRAGContextBuilder()
    news = [
        make_news_item("Gold rally continues", source="bloomberg", sentiment=0.5),
        make_news_item("Oil prices drop", source="reuters", sentiment=-0.3),
    ]

    ctx = builder.build(news=news)

    assert "## Recent News" in ctx.news_section
    assert "Gold rally continues" in ctx.news_section
    assert "Oil prices drop" in ctx.news_section
    assert "bloomberg" in ctx.news_section
    assert "reuters" in ctx.news_section
    # Bullet point format
    assert ctx.news_section.count("- ") >= 2


# ---------------------------------------------------------------------------
# Test 5: news section sentiment tags
# ---------------------------------------------------------------------------


def test_news_section_sentiment_tags():
    """Positive sentiment → [+], negative → [-], neutral → [~]."""
    builder = MantisRAGContextBuilder()
    news = [
        make_news_item("Positive headline", sentiment=0.5),   # positive
        make_news_item("Negative headline", sentiment=-0.5),  # negative
        make_news_item("Neutral headline", sentiment=0.0),    # neutral
    ]

    ctx = builder.build(news=news)

    assert "[+]" in ctx.news_section
    assert "[-]" in ctx.news_section
    assert "[~]" in ctx.news_section


# ---------------------------------------------------------------------------
# Test 6: macro section fear & greed labels
# ---------------------------------------------------------------------------


def test_macro_section_fear_greed():
    """Fear & Greed values map to correct labels."""
    builder = MantisRAGContextBuilder()

    # Extreme Fear: fg < 0.25
    ctx = builder.build(sil_data={"sil_fear_greed_value": 0.10})
    assert "Extreme Fear" in ctx.macro_section

    # Fear: 0.25 <= fg < 0.45
    ctx = builder.build(sil_data={"sil_fear_greed_value": 0.35})
    assert "Fear" in ctx.macro_section

    # Neutral: 0.45 <= fg < 0.55
    ctx = builder.build(sil_data={"sil_fear_greed_value": 0.50})
    assert "Neutral" in ctx.macro_section

    # Greed: 0.55 <= fg < 0.75
    ctx = builder.build(sil_data={"sil_fear_greed_value": 0.65})
    assert "Greed" in ctx.macro_section

    # Extreme Greed: fg >= 0.75
    ctx = builder.build(sil_data={"sil_fear_greed_value": 0.90})
    assert "Extreme Greed" in ctx.macro_section


# ---------------------------------------------------------------------------
# Test 7: macro section COT bias labels
# ---------------------------------------------------------------------------


def test_macro_section_cot():
    """COT net positions map to institutional bias labels."""
    builder = MantisRAGContextBuilder()

    # institutional long: cot > 0.2
    ctx = builder.build(sil_data={"sil_cot_net_position_norm": 0.5})
    assert "institutional long" in ctx.macro_section

    # institutional short: cot < -0.2
    ctx = builder.build(sil_data={"sil_cot_net_position_norm": -0.5})
    assert "institutional short" in ctx.macro_section

    # neutral: -0.2 <= cot <= 0.2
    ctx = builder.build(sil_data={"sil_cot_net_position_norm": 0.0})
    assert "neutral" in ctx.macro_section


# ---------------------------------------------------------------------------
# Test 8: memory section win rate
# ---------------------------------------------------------------------------


def test_memory_section_win_rate():
    """Win rate is included in memory section."""
    builder = MantisRAGContextBuilder()
    mem = make_memory_context(win_rate=0.62)

    ctx = builder.build(memory_context=mem)

    assert "62%" in ctx.memory_section
    assert "Memory Context" in ctx.memory_section


# ---------------------------------------------------------------------------
# Test 9: memory section episodic warnings
# ---------------------------------------------------------------------------


def test_memory_section_warnings():
    """Episodic warnings are formatted with description and lesson."""
    builder = MantisRAGContextBuilder()
    mem = make_memory_context(with_warnings=True)

    ctx = builder.build(memory_context=mem)

    assert "WARNINGS" in ctx.memory_section
    assert "London open volatility spike" in ctx.memory_section
    assert "Reduce size during news events" in ctx.memory_section
    assert "reduce_size" in ctx.memory_section


# ---------------------------------------------------------------------------
# Test 10: respects max tokens
# ---------------------------------------------------------------------------


def test_respects_max_tokens():
    """total_tokens_estimate stays within MAX_CONTEXT_TOKENS."""
    builder = MantisRAGContextBuilder(max_tokens=200)
    # Generate lots of news
    news = [
        make_news_item(
            f"Headline number {i} about markets and trading and crypto",
            lead_paragraph="A" * 200,
        )
        for i in range(5)
    ]
    sil = make_sil_data()
    mem = make_memory_context(with_patterns=True, with_warnings=True, with_blacklist=True)

    ctx = builder.build(news=news, sil_data=sil, memory_context=mem)

    assert ctx.total_tokens_estimate <= 200


# ---------------------------------------------------------------------------
# Test 11: custom max tokens
# ---------------------------------------------------------------------------


def test_custom_max_tokens():
    """Custom max_tokens overrides the class default."""
    builder = MantisRAGContextBuilder(max_tokens=50)
    assert builder.MAX_CONTEXT_TOKENS == 50

    news = [make_news_item("A" * 500, lead_paragraph="B" * 500)]
    ctx = builder.build(news=news)

    assert ctx.total_tokens_estimate <= 50


# ---------------------------------------------------------------------------
# Test 12: truncation happens on large input
# ---------------------------------------------------------------------------


def test_truncation_happens():
    """With tiny max_tokens and large input, truncation is applied."""
    builder = MantisRAGContextBuilder(max_tokens=10)  # ~40 chars
    news = [make_news_item("X" * 300, lead_paragraph="Y" * 300)]

    ctx = builder.build(news=news)

    # The section must be shorter than the original input
    assert len(ctx.news_section) < 300
    assert ctx.total_tokens_estimate <= 10


# ---------------------------------------------------------------------------
# Test 13: sources count accuracy
# ---------------------------------------------------------------------------


def test_sources_count():
    """sources_count reflects number of individual items consumed."""
    builder = MantisRAGContextBuilder()

    # 3 news items + sil (1) + memory (1) = 5
    news = [make_news_item() for _ in range(3)]
    ctx = builder.build(news=news, sil_data=make_sil_data(), memory_context=make_memory_context())
    assert ctx.sources_count == 5  # 3 news + 1 sil + 1 memory

    # news only: 2 items
    ctx2 = builder.build(news=[make_news_item(), make_news_item()])
    assert ctx2.sources_count == 2

    # sil only: 1
    ctx3 = builder.build(sil_data=make_sil_data())
    assert ctx3.sources_count == 1

    # nothing: 0
    ctx4 = builder.build()
    assert ctx4.sources_count == 0


# ---------------------------------------------------------------------------
# Phase 14b: build_with_summary (LLM-driven exec summary)
# ---------------------------------------------------------------------------


from src.llm_provider.base import LLMProvider, LLMProviderError  # noqa: E402


class _FakeProvider(LLMProvider):
    def __init__(self, response):
        self._response = response
        self.calls = 0
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    async def generate(self, prompt, *, system=None, max_tokens=1500,
                       temperature=0.0, json_mode=False, keep_alive=None):
        self.calls += 1
        self.last_prompt = prompt
        self.last_system = system
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def analyze_image(self, prompt, image_bytes, *, system=None, max_tokens=1500,
                            temperature=0.0, json_mode=False, keep_alive=None):
        return ""

    async def embed(self, texts):
        return [[0.0] * self.embedding_dim for _ in texts]

    async def health_check(self):
        return True

    @property
    def embedding_dim(self) -> int:
        return 1024


@pytest.mark.asyncio
async def test_build_with_summary_populates_executive_summary():
    fake = _FakeProvider("Gold momentum building on safe-haven flows; macro tail-risk elevated.")
    builder = MantisRAGContextBuilder(provider=fake)

    ctx = await builder.build_with_summary(
        news=[make_news_item()],
        sil_data=make_sil_data(),
        symbol="XAUUSD",
    )

    assert ctx.executive_summary.startswith("Gold momentum")
    assert fake.calls == 1
    assert fake.last_system is not None
    assert "MANTIS" in fake.last_system
    assert "XAUUSD" in (fake.last_prompt or "")


@pytest.mark.asyncio
async def test_build_with_summary_skips_when_no_sections():
    fake = _FakeProvider("should not be called")
    builder = MantisRAGContextBuilder(provider=fake)

    ctx = await builder.build_with_summary(symbol="BTCUSD")

    assert ctx.executive_summary == ""
    assert fake.calls == 0


@pytest.mark.asyncio
async def test_build_with_summary_falls_back_on_provider_error():
    fake = _FakeProvider(LLMProviderError("network down"))
    builder = MantisRAGContextBuilder(provider=fake)

    ctx = await builder.build_with_summary(
        news=[make_news_item()],
        symbol="XAUUSD",
    )

    assert ctx.executive_summary == ""
    # Template-only sections still populated
    assert ctx.news_section != ""


@pytest.mark.asyncio
async def test_build_with_summary_falls_back_on_unexpected_error():
    fake = _FakeProvider(RuntimeError("unexpected"))
    builder = MantisRAGContextBuilder(provider=fake)

    ctx = await builder.build_with_summary(
        news=[make_news_item()],
        symbol="XAUUSD",
    )

    assert ctx.executive_summary == ""
    assert ctx.news_section != ""


# ---------------------------------------------------------------------------
# Phase 14c/d: docs corpus retrieval + reranker
# ---------------------------------------------------------------------------


import numpy as np  # noqa: E402

from src.rag.vector_store import MantisVectorStore  # noqa: E402


class _RetrievalFakeProvider(_FakeProvider):
    """FakeProvider with embed/rerank wired for retrieve_docs tests."""

    def __init__(self, embed_response=None, rerank_response=None):
        super().__init__("ok")
        self._embed = embed_response
        self._rerank = rerank_response
        self.rerank_calls = 0

    async def embed(self, texts):
        if self._embed is not None:
            return self._embed
        return [[0.0] * self.embedding_dim for _ in texts]

    async def rerank(self, query, passages):
        self.rerank_calls += 1
        if isinstance(self._rerank, Exception):
            raise self._rerank
        if self._rerank is not None:
            return self._rerank
        return [0.5 for _ in passages]


def _make_corpus(tmp_path):
    store = MantisVectorStore(dimension=4, store_path=str(tmp_path))
    store.add("alpha doc text", np.array([1.0, 0.0, 0.0, 0.0]),
              metadata={"source": "a.md", "header": "alpha"})
    store.add("beta doc text", np.array([0.9, 0.4, 0.0, 0.0]),
              metadata={"source": "b.md", "header": "beta"})
    store.add("gamma doc text", np.array([0.5, 0.8, 0.0, 0.0]),
              metadata={"source": "c.md", "header": "gamma"})
    store.add("delta doc text", np.array([0.1, 0.99, 0.0, 0.0]),
              metadata={"source": "d.md", "header": "delta"})
    store.save()


@pytest.mark.asyncio
async def test_retrieve_docs_returns_top_k_cosine_only(tmp_path):
    _make_corpus(tmp_path)
    fake = _RetrievalFakeProvider(embed_response=[[1.0, 0.0, 0.0, 0.0]])
    builder = MantisRAGContextBuilder(provider=fake, corpus_dir=str(tmp_path))

    results = await builder.retrieve_docs("alpha?", top_k=2, rerank=False)

    assert len(results) == 2
    assert results[0]["source"] == "a.md"  # most similar
    assert "rerank_score" not in results[0]
    assert fake.rerank_calls == 0


@pytest.mark.asyncio
async def test_retrieve_docs_applies_rerank(tmp_path):
    _make_corpus(tmp_path)
    # All 4 corpus docs above the default min_similarity floor when the
    # query embedding is [1, 0, 0, 0]: cosine(a)=1.0, b≈0.91, c≈0.53,
    # d≈0.10. Lower min_similarity to 0.0 so the candidate pool keeps
    # all four — gives the reranker meaningful work to do.
    fake = _RetrievalFakeProvider(
        embed_response=[[1.0, 0.0, 0.0, 0.0]],
        rerank_response=[0.1, 0.2, 0.9, 0.3],  # gamma should win
    )
    builder = MantisRAGContextBuilder(provider=fake, corpus_dir=str(tmp_path))

    results = await builder.retrieve_docs(
        "alpha?", top_k=2, rerank=True, candidate_pool=4, min_similarity=0.0
    )

    assert fake.rerank_calls == 1
    assert results[0]["source"] == "c.md"  # promoted by reranker
    assert results[0]["rerank_score"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_retrieve_docs_rerank_failure_falls_back_to_cosine(tmp_path):
    _make_corpus(tmp_path)
    fake = _RetrievalFakeProvider(
        embed_response=[[1.0, 0.0, 0.0, 0.0]],
        rerank_response=RuntimeError("reranker offline"),
    )
    builder = MantisRAGContextBuilder(provider=fake, corpus_dir=str(tmp_path))

    results = await builder.retrieve_docs("alpha?", top_k=2, rerank=True)

    assert fake.rerank_calls == 1
    assert results[0]["source"] == "a.md"  # cosine ordering preserved
    assert "rerank_score" not in results[0]


@pytest.mark.asyncio
async def test_retrieve_docs_handles_missing_corpus(tmp_path):
    fake = _RetrievalFakeProvider()
    builder = MantisRAGContextBuilder(
        provider=fake, corpus_dir=str(tmp_path / "does-not-exist")
    )

    assert await builder.retrieve_docs("anything") == []
    assert fake.rerank_calls == 0


@pytest.mark.asyncio
async def test_build_with_summary_includes_docs_when_query_passed(tmp_path):
    _make_corpus(tmp_path)
    fake = _RetrievalFakeProvider(
        embed_response=[[1.0, 0.0, 0.0, 0.0]],
        rerank_response=[0.9, 0.5, 0.4, 0.3],
    )
    fake._response = "Concise summary."
    builder = MantisRAGContextBuilder(provider=fake, corpus_dir=str(tmp_path))

    ctx = await builder.build_with_summary(
        news=[make_news_item()],
        symbol="XAUUSD",
        retrieval_query="alpha?",
    )

    assert ctx.executive_summary == "Concise summary."
    # The synthesized prompt fed to generate() should reference the docs
    # block — assert via the FakeProvider's last_prompt capture.
    assert "Relevant MANTIS Knowledge" in (fake.last_prompt or "")
