# MANTIS-EVOLUTION: Embeddings Tests
"""Tests for MantisEmbedder (TDD — written before implementation)."""
from __future__ import annotations

import math

import pytest

from src.agents.schemas import MarketContext
from src.memory_layer.embeddings import MantisEmbedder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    epic: str = "XAUUSD",
    price: float = 2000.0,
    atr: float = 10.0,
    regime: str | None = "trending_up",
) -> MarketContext:
    return MarketContext(
        epic=epic,
        current_price=price,
        atr=atr,
        regime=regime,
        features={
            "ema_9": 1998.0,
            "ema_21": 1990.0,
            "rsi_14": 58.0,
            "adx_14": 25.0,
            "macd_histogram": 0.5,
            "bb_upper": 2020.0,
            "bb_lower": 1980.0,
            "atr": 10.0,
            "volume": 1234.0,
            "vwap": 1999.0,
        },
    )


# ---------------------------------------------------------------------------
# Embedding dimension
# ---------------------------------------------------------------------------


def test_embedding_dim_default():
    """Phase 14a: default embedding dimension follows the active LLMProvider.

    With Ollama + bge-m3 (default since 2026-05-08) → 1024-dim. The
    embedder probes the provider at construction so production code
    sees the real number. If the provider is unreachable in CI, the
    embedder falls back to MiniLM 384, so accept either as valid.
    """
    embedder = MantisEmbedder()
    assert embedder.embedding_dim in (1024, 384)


# ---------------------------------------------------------------------------
# Text embedding tests
# ---------------------------------------------------------------------------


def test_embed_text_returns_list():
    """embed_text returns a list[float] of correct length."""
    embedder = MantisEmbedder()
    result = embedder.embed_text("BUY XAUUSD at 2000 — RSI oversold")
    assert isinstance(result, list)
    assert len(result) == embedder.embedding_dim
    assert all(isinstance(v, float) for v in result)


def test_embed_text_deterministic():
    """Same text produces the same embedding on repeated calls."""
    embedder = MantisEmbedder()
    text = "SELL BTCUSD — bearish divergence at resistance"
    result1 = embedder.embed_text(text)
    result2 = embedder.embed_text(text)
    assert result1 == result2


def test_embed_text_different_for_different_input():
    """Different texts produce different embeddings."""
    embedder = MantisEmbedder()
    emb1 = embedder.embed_text("BUY signal on XAUUSD")
    emb2 = embedder.embed_text("SELL signal on BTCUSD")
    assert emb1 != emb2


# ---------------------------------------------------------------------------
# Market context embedding tests
# ---------------------------------------------------------------------------


def test_embed_market_context_returns_list():
    """embed_market_context returns a list[float] of correct length."""
    embedder = MantisEmbedder()
    ctx = _make_context()
    result = embedder.embed_market_context(ctx)
    assert isinstance(result, list)
    assert len(result) == embedder.embedding_dim
    assert all(isinstance(v, float) for v in result)


def test_embed_market_context_normalized():
    """Market context embedding has L2 norm ≈ 1.0."""
    embedder = MantisEmbedder()
    ctx = _make_context()
    vec = embedder.embed_market_context(ctx)
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-5


def test_embed_market_context_regime_encoding():
    """Different regimes produce different embeddings."""
    embedder = MantisEmbedder()
    ctx_up = _make_context(regime="trending_up")
    ctx_down = _make_context(regime="trending_down")
    ctx_range = _make_context(regime="ranging")

    emb_up = embedder.embed_market_context(ctx_up)
    emb_down = embedder.embed_market_context(ctx_down)
    emb_range = embedder.embed_market_context(ctx_range)

    assert emb_up != emb_down
    assert emb_up != emb_range
    assert emb_down != emb_range


# ---------------------------------------------------------------------------
# Cosine similarity tests
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical():
    """Cosine similarity of a vector with itself is 1.0."""
    embedder = MantisEmbedder()
    vec = embedder.embed_text("MANTIS AI trading signal")
    sim = embedder.cosine_similarity(vec, vec)
    assert abs(sim - 1.0) < 1e-5


def test_cosine_similarity_orthogonal():
    """Orthogonal vectors have cosine similarity 0.0."""
    embedder = MantisEmbedder()
    dim = embedder.embedding_dim
    a = [0.0] * dim
    b = [0.0] * dim
    a[0] = 1.0
    b[1] = 1.0
    sim = embedder.cosine_similarity(a, b)
    assert abs(sim) < 1e-5


def test_cosine_similarity_opposite():
    """Opposite vectors have cosine similarity -1.0."""
    embedder = MantisEmbedder()
    dim = embedder.embedding_dim
    a = [1.0] + [0.0] * (dim - 1)
    b = [-1.0] + [0.0] * (dim - 1)
    sim = embedder.cosine_similarity(a, b)
    assert abs(sim - (-1.0)) < 1e-5


def test_cosine_similarity_empty():
    """Empty input vectors return 0.0 (no crash)."""
    embedder = MantisEmbedder()
    assert embedder.cosine_similarity([], []) == 0.0
    assert embedder.cosine_similarity([1.0], []) == 0.0
    assert embedder.cosine_similarity([], [1.0]) == 0.0


# ---------------------------------------------------------------------------
# Hash fallback tests
# ---------------------------------------------------------------------------


def test_hash_embed_fallback():
    """_hash_embed always returns a valid normalised vector."""
    embedder = MantisEmbedder()
    result = embedder._hash_embed("fallback test string")
    assert isinstance(result, list)
    assert len(result) == embedder.embedding_dim
    norm = math.sqrt(sum(v * v for v in result))
    assert abs(norm - 1.0) < 1e-5


def test_hash_embed_deterministic():
    """_hash_embed is deterministic across calls."""
    embedder = MantisEmbedder()
    text = "deterministic check"
    assert embedder._hash_embed(text) == embedder._hash_embed(text)


def test_hash_embed_different_inputs():
    """_hash_embed produces different vectors for different inputs."""
    embedder = MantisEmbedder()
    v1 = embedder._hash_embed("hello world")
    v2 = embedder._hash_embed("goodbye world")
    assert v1 != v2
