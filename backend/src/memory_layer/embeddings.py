# MANTIS-EVOLUTION: Embedding system for memory retrieval (Phase 14a, 2026-05-08)
"""Lightweight embeddings for semantic search in memory layers.

Phase 14a swapped the local sentence-transformers MiniLM (384-dim) for
the LLMProvider's bge-m3 (1024-dim, multilingual, 8192 context) running
on the GX10 Ollama instance. Falls back to sentence-transformers when
the provider is unreachable, then to a deterministic hash embedding as
last resort, so memory layer code never blocks on network issues.

Embedding dimension is dynamic: callers must read `embedding_dim`
property after construction (rather than assuming 384) since the active
backend dictates the size.
"""

from __future__ import annotations

import asyncio
import hashlib

import numpy as np
from loguru import logger

from src.agents.schemas import MarketContext
from src.llm_provider import LLMProviderError, get_llm_provider
from src.llm_provider.base import LLMProvider

try:
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class MantisEmbedder:
    """Generates embeddings for semantic retrieval.

    Strategy (in order of preference):
    1. LLMProvider.embed() — Ollama bge-m3 by default (1024-dim).
    2. sentence-transformers MiniLM (384-dim) — local fallback if
       provider unreachable AND the package is installed.
    3. Deterministic SHA-256 hash embedding — last resort, not
       semantically meaningful but avoids hard failure.

    The active path is decided per-call by `embed_text` so a transient
    Ollama outage doesn't permanently downgrade subsequent calls.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        provider: LLMProvider | None = None,
    ) -> None:
        self._model_name = model_name
        self._st_model = None  # lazy init
        self._provider = provider  # Lazy via get_llm_provider() if None
        # Embedding dim: prefer the LLM provider's, fall back to MiniLM
        # 384 only when the provider is unavailable. Set conservatively
        # at construction; refined when a real call lands.
        self._embedding_dim = self._resolve_provider_dim(default=384)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    def embed_text(self, text: str) -> list[float]:
        """Embed a text string, walking the fallback chain."""
        # Tier 1: LLM provider (Ollama bge-m3)
        try:
            provider = self._provider or get_llm_provider()
            vec = asyncio.run(provider.embed([text]))[0]
            self._embedding_dim = len(vec)
            return list(vec)
        except RuntimeError:
            # Already inside a running event loop — caller should use
            # `embed_text_async` instead. Fall through to Tier 2.
            logger.debug("MantisEmbedder.embed_text called inside event loop; using sync fallback")
        except LLMProviderError as exc:
            logger.debug(f"LLM provider embed failed: {exc!r}; trying sentence-transformers")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Unexpected provider error: {exc!r}; trying sentence-transformers")

        # Tier 2: sentence-transformers
        if HAS_SENTENCE_TRANSFORMERS:
            model = self._get_st_model()
            if model is not None:
                try:
                    vec = model.encode(text, convert_to_numpy=True)
                    return vec.tolist()
                except Exception as exc:
                    logger.warning(f"Sentence transformer failed: {exc!r}")

        # Tier 3: hash fallback
        return self._hash_embed(text)

    async def embed_text_async(self, text: str) -> list[float]:
        """Async version — preferred when called from an async context."""
        try:
            provider = self._provider or get_llm_provider()
            vec = (await provider.embed([text]))[0]
            self._embedding_dim = len(vec)
            return list(vec)
        except LLMProviderError as exc:
            logger.debug(f"LLM provider embed failed: {exc!r}; falling back")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Unexpected provider error: {exc!r}; falling back")

        if HAS_SENTENCE_TRANSFORMERS:
            model = self._get_st_model()
            if model is not None:
                try:
                    vec = model.encode(text, convert_to_numpy=True)
                    return vec.tolist()
                except Exception as exc:
                    logger.warning(f"Sentence transformer failed: {exc!r}")

        return self._hash_embed(text)

    def embed_market_context(self, context: MarketContext) -> list[float]:
        """Embed a MarketContext as a feature vector.

        Numeric-only path (no LLM). Combines key features + regime + epic
        into a fixed-size vector, padded/truncated to `embedding_dim` so
        it stays compatible with text embeddings stored in the same
        vector store.
        """
        feature_keys = [
            "ema_9",
            "ema_21",
            "rsi_14",
            "adx_14",
            "macd_histogram",
            "bb_upper",
            "bb_lower",
            "atr",
            "volume",
            "vwap",
        ]

        values: list[float] = []
        for key in feature_keys:
            val = context.features.get(key, 0.0)
            values.append(float(val) if val is not None else 0.0)

        values.append(context.current_price / 10000.0)
        values.append(
            context.atr / context.current_price if context.current_price > 0 else 0.0
        )

        regime_map = {
            "trending_up": [1, 0, 0],
            "trending_down": [0, 1, 0],
            "ranging": [0, 0, 1],
        }
        values.extend(regime_map.get(context.regime or "", [0, 0, 0]))

        vec = np.zeros(self._embedding_dim, dtype=np.float32)
        n = min(len(values), self._embedding_dim)
        vec[:n] = values[:n]

        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec = vec / norm
        return vec.tolist()

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Cosine similarity between two embedding vectors."""
        if not a or not b:
            return 0.0
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        norm_a = np.linalg.norm(va)
        norm_b = np.linalg.norm(vb)
        if norm_a < 1e-8 or norm_b < 1e-8:
            return 0.0
        return float(np.dot(va, vb) / (norm_a * norm_b))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_provider_dim(self, default: int) -> int:
        """Best-effort lookup of the provider's embedding dim at init.

        Avoids a network round-trip; reads the configured value from
        the provider object. If the provider can't be constructed
        (e.g. tests with no Settings), returns the supplied default.
        """
        try:
            provider = self._provider or get_llm_provider()
            return provider.embedding_dim
        except Exception:  # noqa: BLE001
            return default

    def _get_st_model(self):
        if self._st_model is None and HAS_SENTENCE_TRANSFORMERS:
            try:
                self._st_model = SentenceTransformer(self._model_name)
                self._embedding_dim = self._st_model.get_sentence_embedding_dimension()
                logger.info(
                    f"Loaded sentence-transformers fallback: {self._model_name} (dim={self._embedding_dim})"
                )
            except Exception as exc:
                logger.warning(f"Failed to load {self._model_name}: {exc!r}")
        return self._st_model

    def _hash_embed(self, text: str) -> list[float]:
        """Deterministic hash-based embedding fallback.

        Produces a fixed-size vector from text using SHA256 chunks.
        Not semantically meaningful but consistent across calls.
        """
        result = np.zeros(self._embedding_dim, dtype=np.float32)
        chunks_needed = (self._embedding_dim * 4 + 31) // 32

        hash_bytes = b""
        for i in range(chunks_needed):
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            hash_bytes += h

        for i in range(self._embedding_dim):
            byte_val = hash_bytes[i * 4] ^ hash_bytes[i * 4 + 1]
            result[i] = (byte_val / 127.5) - 1.0

        norm = np.linalg.norm(result)
        if norm > 1e-8:
            result = result / norm
        return result.tolist()
