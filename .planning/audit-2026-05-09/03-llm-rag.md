# LLM/RAG Audit — 2026-05-09

**Scope reviewed:**
- `llm_provider/` (base, ollama_provider, factory, __init__)
- `rag/` (context_builder, vector_store, news_ingester, __init__)
- `memory_layer/__init__.py`
- `agents/__init__.py`, `vision_agent.py`, `base_agent.py`, technical/sentiment/risk_manager_agent
- `scripts/index_mantis_docs.py`

---

## CRITICAL

None. Trading-loop crash invariant holds. All LLM/RAG calls wrapped with safe defaults.

---

## HIGH

### H-1 — Reranker first-load race: concurrent coroutines double-download HF model

`ollama_provider.py:54-67, 235-241`

**What**: `_get_reranker()` and `_ensure_loaded()` no lock. 15 epics calling `retrieve_docs(rerank=True)` in parallel can both pass None-check, both construct `_LocalCrossEncoder`, both download 568 MB.

**Fix**: Add `asyncio.Lock` around `_get_reranker()`.

---

### H-2 — `_run_in_thread` uses `asyncio.get_event_loop()` instead of `get_running_loop()`

`ollama_provider.py:91`

**What**: Inside coroutine, correct API is `get_running_loop()`. Python 3.14 will raise `RuntimeError`. DeprecationWarning in 3.12.

**Fix**: `loop = asyncio.get_running_loop()`.

---

### H-3 — Index script batches all chunks per file in one embed call; large files silently skipped on timeout

`index_mantis_docs.py:169-175`

**What**: `STYLE_BIBLE.md` 30+ chunks of 1500 char × bge-m3 → may exceed 60s timeout. Caught at WARNING, skipped silently. CLAUDE.md skip = corpus missing critical knowledge.

**Fix**: Batch ≤20 chunks per call:
```python
EMBED_BATCH_SIZE = 20
for i in range(0, len(chunk_texts), EMBED_BATCH_SIZE):
    batch_vecs = await provider.embed(chunk_texts[i:i+EMBED_BATCH_SIZE])
```

---

### H-4 — `MantisVectorStore` default dim 384 inconsistent with bge-m3 1024

`vector_store.py:22`, `context_builder.py:402`

**What**: `_load_corpus()` constructs without `dimension=`, starts at 384, corrected to 1024 after `.npy` load. `MantisEmbedder` fallback to MiniLM (384-dim) → `store.add()` raises `ValueError("Expected 1024, got 384")`. Memory layer silently degrades.

**Fix**: Pass `dimension=provider.embedding_dim` in `_load_corpus()`.

---

## MEDIUM

### M-1 — Markdown headers inside fenced code blocks split chunks incorrectly

`index_mantis_docs.py:108`

**What**: `header_re` applied to all lines including inside ```` ``` ```` fences. CLAUDE.md/STYLE_BIBLE.md have `# MANTIS-EVOLUTION:` Python comments inside code blocks → misidentified as `###` headers → mid-block splits.

---

### M-2 — `_load_corpus` re-hits disk on every call when corpus absent

`context_builder.py:389`

**What**: When dir missing/empty, returns None without setting `self._vector_store`. Re-stat per epic per tick.

**Fix**: Sentinel `False` to mark "tried-and-empty".

---

### M-3 — `/agents/status` reports stale `claude-sonnet-4-20250514` after Phase 14b

`api/routers/agents.py:44`

**What**: `agents_llm_model` defaults to anthropic name. Always exists in settings. Frontend shows wrong model.

**Fix**: Report actual provider via `get_llm_provider()`.

---

### M-4 — `_call_llm` fence-stripping truncates JSON with embedded triple-backticks

`base_agent.py:109`

**What**: `rsplit("```", 1)[0]` finds last triple-backtick. If qwen3 emits rationale with code snippet → truncated → JSONDecodeError → silent heuristic fallback.

---

## LOW

- `context_builder.py:319` — docstring says default 20, signature 10
- `index_mantis_docs.py:85` — `rglob` follows symlinks, NTFS junction loop risk

---

## Coverage Gaps

1. `OllamaProvider.rerank()` — zero tests
2. `_LocalCrossEncoder` real transformers path — untested
3. `_load_corpus` repeated-call behavior — no call-count assertion
4. Markdown chunking with code-block headers — untested
5. `MantisEmbedder` dim-mismatch fallback — untested

---

## Summary

Trading-loop invariant holds. Anthropic lib mostly removed (M-3 stale string only).

**Top fixes:**

| # | File | Fix |
|---|------|-----|
| H-1 | `ollama_provider.py:235` | asyncio.Lock around `_get_reranker()` |
| H-3 | `index_mantis_docs.py:169` | Batch embed ≤20 chunks |
| H-2 | `ollama_provider.py:91` | `get_running_loop()` |
| M-3 | `agents.py:44` | Real provider model in status |
| M-2 | `context_builder.py:389` | Cache None result |
