# MANTIS-EVOLUTION: Tests for MantisVectorStore
"""Tests for the numpy-based vector store."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from src.rag.vector_store import MantisVectorStore
from src.rag.schemas import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unit_vec(*components: float) -> np.ndarray:
    """Return a unit vector from given components."""
    v = np.array(components, dtype=np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Test 1: add single vector → size == 1
# ---------------------------------------------------------------------------

def test_add_single_vector():
    store = MantisVectorStore(dimension=3)
    idx = store.add("hello", [1.0, 0.0, 0.0])
    assert idx == 0
    assert store.size() == 1


# ---------------------------------------------------------------------------
# Test 2: add wrong dimension → ValueError
# ---------------------------------------------------------------------------

def test_add_wrong_dimension():
    store = MantisVectorStore(dimension=3)
    with pytest.raises(ValueError, match="dimension"):
        store.add("bad", [1.0, 0.0])  # dim=2, not 3


# ---------------------------------------------------------------------------
# Test 3: search basic — returns sorted by similarity descending
# ---------------------------------------------------------------------------

def test_search_basic():
    store = MantisVectorStore(dimension=3)
    # [1,0,0] is most similar to query [1,0,0]
    store.add("most similar", [1.0, 0.0, 0.0])
    store.add("least similar", [0.0, 0.0, 1.0])
    store.add("medium similar", [0.8, 0.6, 0.0])

    results = store.search([1.0, 0.0, 0.0], top_k=3)
    assert len(results) == 3
    # First result should be the most similar
    assert results[0].text == "most similar"
    # Similarities must be in descending order
    sims = [r.similarity for r in results]
    assert sims == sorted(sims, reverse=True)


# ---------------------------------------------------------------------------
# Test 4: search on empty store → empty list
# ---------------------------------------------------------------------------

def test_search_empty_store():
    store = MantisVectorStore(dimension=3)
    results = store.search([1.0, 0.0, 0.0])
    assert results == []


# ---------------------------------------------------------------------------
# Test 5: top_k=2 → only 2 results
# ---------------------------------------------------------------------------

def test_search_top_k():
    store = MantisVectorStore(dimension=3)
    for i in range(5):
        store.add(f"chunk {i}", np.random.rand(3).tolist())

    results = store.search([1.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Test 6: min_similarity filter
# ---------------------------------------------------------------------------

def test_search_min_similarity():
    store = MantisVectorStore(dimension=3)
    store.add("high sim", [1.0, 0.0, 0.0])          # sim ~1.0 to [1,0,0]
    store.add("low sim", [0.0, 0.0, 1.0])            # sim ~0.0 to [1,0,0]
    store.add("medium sim", [0.6, 0.8, 0.0])         # sim ~0.6

    results = store.search([1.0, 0.0, 0.0], top_k=5, min_similarity=0.5)
    # Only "high sim" (~1.0) and "medium sim" (~0.6) should pass
    texts = {r.text for r in results}
    assert "low sim" not in texts
    assert "high sim" in texts


# ---------------------------------------------------------------------------
# Test 7: metadata preserved in results
# ---------------------------------------------------------------------------

def test_search_returns_metadata():
    store = MantisVectorStore(dimension=3)
    meta = {"source": "reuters", "timestamp": "2026-01-01"}
    store.add("news headline", [1.0, 0.0, 0.0], metadata=meta)

    results = store.search([1.0, 0.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0].metadata == meta


# ---------------------------------------------------------------------------
# Test 8: text preserved in results
# ---------------------------------------------------------------------------

def test_search_returns_text():
    store = MantisVectorStore(dimension=3)
    store.add("specific text content", [1.0, 0.0, 0.0])

    results = store.search([1.0, 0.0, 0.0], top_k=1)
    assert results[0].text == "specific text content"


# ---------------------------------------------------------------------------
# Test 9: clear() → size == 0
# ---------------------------------------------------------------------------

def test_clear():
    store = MantisVectorStore(dimension=3)
    store.add("a", [1.0, 0.0, 0.0])
    store.add("b", [0.0, 1.0, 0.0])
    assert store.size() == 2

    store.clear()
    assert store.size() == 0
    # Also verify search returns empty after clear
    assert store.search([1.0, 0.0, 0.0]) == []


# ---------------------------------------------------------------------------
# Test 10: save and load (round-trip)
# ---------------------------------------------------------------------------

def test_save_and_load(tmp_path):
    store = MantisVectorStore(dimension=3, store_path=str(tmp_path))
    store.add("first", [1.0, 0.0, 0.0], metadata={"tag": "alpha"})
    store.add("second", [0.0, 1.0, 0.0], metadata={"tag": "beta"})
    store.save()

    # Load into a fresh store
    store2 = MantisVectorStore(dimension=3, store_path=str(tmp_path))
    store2.load()

    assert store2.size() == 2
    results = store2.search([1.0, 0.0, 0.0], top_k=1)
    assert results[0].text == "first"
    assert results[0].metadata == {"tag": "alpha"}


# ---------------------------------------------------------------------------
# Test 11: save with no path → ValueError
# ---------------------------------------------------------------------------

def test_save_no_path():
    store = MantisVectorStore(dimension=3)
    store.add("x", [1.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="store_path"):
        store.save()


# ---------------------------------------------------------------------------
# Test 12: load with no path → ValueError
# ---------------------------------------------------------------------------

def test_load_no_path():
    store = MantisVectorStore(dimension=3)
    with pytest.raises(ValueError, match="store_path"):
        store.load()


# ---------------------------------------------------------------------------
# Test 13: load from nonexistent directory → warning, no crash
# ---------------------------------------------------------------------------

def test_load_missing_dir(tmp_path):
    missing = str(tmp_path / "does_not_exist")
    store = MantisVectorStore(dimension=3, store_path=missing)
    # Should not raise — just log a warning
    store.load()
    assert store.size() == 0


# ---------------------------------------------------------------------------
# Test 14: cosine similarity correctness
# ---------------------------------------------------------------------------

def test_cosine_similarity_correct():
    store = MantisVectorStore(dimension=3)
    # Identical vector → similarity = 1.0
    store.add("identical", [1.0, 0.0, 0.0])
    # Orthogonal → similarity = 0.0
    store.add("orthogonal", [0.0, 1.0, 0.0])
    # Opposite → similarity = -1.0
    store.add("opposite", [-1.0, 0.0, 0.0])

    # min_similarity=-1.0 so even opposite vectors (sim=-1) are included
    results = store.search([1.0, 0.0, 0.0], top_k=3, min_similarity=-1.0)
    by_text = {r.text: r.similarity for r in results}

    assert abs(by_text["identical"] - 1.0) < 1e-5
    assert abs(by_text["orthogonal"] - 0.0) < 1e-5
    assert abs(by_text["opposite"] - (-1.0)) < 1e-5


# ---------------------------------------------------------------------------
# Test 15: vectors are normalized on add
# ---------------------------------------------------------------------------

def test_normalization():
    store = MantisVectorStore(dimension=3)
    # Add an unnormalized vector
    store.add("scaled", [10.0, 0.0, 0.0])
    store.add("unit", [1.0, 0.0, 0.0])

    # Both should be equally similar to [1,0,0] query (both normalize to [1,0,0])
    results = store.search([1.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2
    assert abs(results[0].similarity - 1.0) < 1e-5
    assert abs(results[1].similarity - 1.0) < 1e-5
