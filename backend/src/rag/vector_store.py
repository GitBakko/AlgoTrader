# MANTIS-EVOLUTION: Vector Store for RAG pipeline
"""Simple numpy-based vector store for RAG similarity search."""

from __future__ import annotations

import json
import os
from typing import Any

import numpy as np
from loguru import logger

from src.rag.schemas import SearchResult


class MantisVectorStore:
    """
    Lightweight vector store using numpy cosine similarity.
    No FAISS dependency — pure numpy for portability.
    Supports persist/load for disk caching.
    """

    def __init__(self, dimension: int = 384, store_path: str | None = None):
        self.dimension = dimension
        self.store_path = store_path
        self._vectors: list[np.ndarray] = []
        self._texts: list[str] = []
        self._metadata: list[dict] = []

    def add(
        self,
        text: str,
        vector: np.ndarray | list[float],
        metadata: dict | None = None,
    ) -> int:
        """
        Add a text chunk with its embedding vector.
        Returns the index of the added item.
        """
        vec = np.asarray(vector, dtype=np.float32)
        if vec.shape != (self.dimension,):
            raise ValueError(f"Expected vector of dimension {self.dimension}, got {vec.shape}")

        # Normalize for cosine similarity
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        idx = len(self._vectors)
        self._vectors.append(vec)
        self._texts.append(text)
        self._metadata.append(metadata or {})
        return idx

    def search(
        self,
        query_vector: np.ndarray | list[float],
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[SearchResult]:
        """
        Search for most similar vectors using cosine similarity.
        Returns top_k results sorted by similarity descending.
        """
        if not self._vectors:
            return []

        query = np.asarray(query_vector, dtype=np.float32)
        norm = np.linalg.norm(query)
        if norm > 0:
            query = query / norm

        # Stack all vectors and compute cosine similarities
        matrix = np.stack(self._vectors)
        similarities = matrix @ query  # cosine sim (vectors already normalized)

        # Get top-k indices sorted by descending similarity
        if top_k >= len(similarities):
            top_indices = np.argsort(-similarities)
        else:
            # Partial sort for efficiency, then sort the slice
            top_indices = np.argpartition(-similarities, top_k)[:top_k]
            top_indices = top_indices[np.argsort(-similarities[top_indices])]

        results: list[SearchResult] = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim < min_similarity:
                continue
            results.append(
                SearchResult(
                    text=self._texts[idx],
                    metadata=self._metadata[idx],
                    similarity=sim,
                )
            )

        return results

    def size(self) -> int:
        """Number of vectors in the store."""
        return len(self._vectors)

    def clear(self) -> None:
        """Remove all vectors."""
        self._vectors.clear()
        self._texts.clear()
        self._metadata.clear()

    def save(self, path: str | None = None) -> None:
        """Persist store to disk."""
        save_path = path or self.store_path
        if not save_path:
            raise ValueError("No store_path specified")

        os.makedirs(save_path, exist_ok=True)

        if self._vectors:
            np.save(os.path.join(save_path, "vectors.npy"), np.stack(self._vectors))

        with open(os.path.join(save_path, "texts.json"), "w") as f:
            json.dump(self._texts, f)

        with open(os.path.join(save_path, "metadata.json"), "w") as f:
            json.dump(self._metadata, f)

        logger.info(f"Vector store saved: {len(self._vectors)} vectors to {save_path}")

    def load(self, path: str | None = None) -> None:
        """Load store from disk."""
        load_path = path or self.store_path
        if not load_path:
            raise ValueError("No store_path specified")

        texts_file = os.path.join(load_path, "texts.json")
        metadata_file = os.path.join(load_path, "metadata.json")
        vectors_file = os.path.join(load_path, "vectors.npy")

        if not os.path.exists(texts_file):
            logger.warning(f"No vector store found at {load_path}")
            return

        with open(texts_file) as f:
            self._texts = json.load(f)

        with open(metadata_file) as f:
            self._metadata = json.load(f)

        if os.path.exists(vectors_file):
            matrix = np.load(vectors_file)
            self._vectors = [matrix[i] for i in range(len(matrix))]
            if len(matrix) > 0:
                self.dimension = matrix.shape[1]

        logger.info(f"Vector store loaded: {len(self._vectors)} vectors from {load_path}")
