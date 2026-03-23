# MANTIS-EVOLUTION: Embedding system for memory retrieval
"""Lightweight embeddings for semantic search in memory layers."""
from __future__ import annotations

import hashlib
import numpy as np
from loguru import logger

from src.agents.schemas import MarketContext

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class MantisEmbedder:
    """
    Generates embeddings for semantic retrieval.

    Strategy (in order of preference):
    1. sentence-transformers MiniLM (22MB, high quality)
    2. TF-IDF fallback on structured text
    3. Simple numeric hash for feature vectors
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None  # lazy init
        self._embedding_dim = 384  # MiniLM default; fallback uses same dim

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    def embed_text(self, text: str) -> list[float]:
        """
        Embed a text string. Uses sentence-transformers if available,
        otherwise falls back to deterministic hash-based embedding.
        """
        if HAS_SENTENCE_TRANSFORMERS:
            model = self._get_model()
            if model is not None:
                try:
                    vec = model.encode(text, convert_to_numpy=True)
                    return vec.tolist()
                except Exception as e:
                    logger.warning(f"Sentence transformer failed: {e!r}")

        # Fallback: deterministic hash-based embedding
        return self._hash_embed(text)

    def embed_market_context(self, context: MarketContext) -> list[float]:
        """
        Embed a MarketContext as a feature vector.
        Combines numeric features + regime + epic into a fixed-size vector.
        """
        # Extract key features as a numeric vector
        feature_keys = [
            "ema_9", "ema_21", "rsi_14", "adx_14", "macd_histogram",
            "bb_upper", "bb_lower", "atr", "volume", "vwap",
        ]

        values: list[float] = []
        for key in feature_keys:
            val = context.features.get(key, 0.0)
            values.append(float(val) if val is not None else 0.0)

        # Add normalized context info
        values.append(context.current_price / 10000.0)  # normalize price
        values.append(context.atr / context.current_price if context.current_price > 0 else 0.0)

        # Regime one-hot (3 values)
        regime_map = {
            "trending_up": [1, 0, 0],
            "trending_down": [0, 1, 0],
            "ranging": [0, 0, 1],
        }
        values.extend(regime_map.get(context.regime or "", [0, 0, 0]))

        # Pad or truncate to embedding_dim
        vec = np.zeros(self._embedding_dim, dtype=np.float32)
        n = min(len(values), self._embedding_dim)
        vec[:n] = values[:n]

        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec = vec / norm

        return vec.tolist()

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        if not a or not b:
            return 0.0
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        norm_a = np.linalg.norm(va)
        norm_b = np.linalg.norm(vb)
        if norm_a < 1e-8 or norm_b < 1e-8:
            return 0.0
        return float(np.dot(va, vb) / (norm_a * norm_b))

    def _get_model(self):
        """Lazy-load sentence transformer model."""
        if self._model is None and HAS_SENTENCE_TRANSFORMERS:
            try:
                self._model = SentenceTransformer(self._model_name)
                self._embedding_dim = self._model.get_sentence_embedding_dimension()
                logger.info(
                    f"Loaded embedding model: {self._model_name} (dim={self._embedding_dim})"
                )
            except Exception as e:
                logger.warning(f"Failed to load {self._model_name}: {e!r}")
        return self._model

    def _hash_embed(self, text: str) -> list[float]:
        """
        Deterministic hash-based embedding fallback.
        Produces a fixed-size vector from text using SHA256.
        Not semantically meaningful, but deterministic and consistent.
        """
        # Generate enough hash bytes to fill embedding_dim
        result = np.zeros(self._embedding_dim, dtype=np.float32)
        chunks_needed = (self._embedding_dim * 4 + 31) // 32  # 32 bytes per SHA256

        hash_bytes = b""
        for i in range(chunks_needed):
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            hash_bytes += h

        # Convert bytes to floats in [-1, 1]
        for i in range(self._embedding_dim):
            byte_val = hash_bytes[i * 4] ^ hash_bytes[i * 4 + 1]
            result[i] = (byte_val / 127.5) - 1.0

        # L2 normalize
        norm = np.linalg.norm(result)
        if norm > 1e-8:
            result = result / norm

        return result.tolist()
