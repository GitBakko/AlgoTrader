# MANTIS AI — RAG Architecture Research Report
**Date**: 2026-05-09  
**Author**: Claude Code (research task)  
**Status**: RECOMMENDED — ready for implementation planning

---

## 1. Current State Diagnosis

Before evaluating alternatives, it's worth being precise about what the existing scaffold does and where it falls short.

### What exists today

| Layer | Implementation | Gap |
|---|---|---|
| `MantisVectorStore` | Pure numpy cosine similarity, in-memory, file-persisted | No BM25, no metadata filtering, O(n) linear scan |
| `MantisNewsIngester` | Keyword + recency + credibility scoring → top-5 by relevance score | Rule-based, not embedding-semantic; misses paraphrases |
| `MantisRAGContextBuilder` | String concat of news/macro/memory sections | No retrieval — just formats what's already been pre-filtered |
| `MantisEmbedder` | bge-m3 (1024-dim) via Ollama, with MiniLM fallback | Embed path exists, but not wired to the news or trade history stores |
| `MantisEpisodicMemory` | SQLite + per-call cosine scan over all episodes | O(n) scan, no approximate nearest-neighbour index |
| `MantisLongTermMemory` | SQLite patterns grouped by regime only | Feature signatures stored as JSON blobs, not embedding-indexed |

### Root bottleneck
The biggest gap is not the embedding model — bge-m3 is excellent for this domain. The gap is **retrieval architecture**:
1. News relevance is determined by keyword density, not semantic similarity to the current signal query.
2. Past trades are never retrieved by similarity to the current market context; LTM just returns all patterns in a regime bucket.
3. There is no BM25 layer, so exact ticker-name / metric matches (e.g. "BTCUSD +3.8% surge") are handled only by naive keyword regex.
4. There is no reranker — whatever the vector store returns goes straight to the prompt.

---

## 2. Survey of Candidate RAG Approaches

### 2.1 Classic Chunk + Embed (baseline)
Chunk documents → embed each chunk → cosine search → inject top-k.

**Verdict for MANTIS**: Current implementation is already here, minus the news / trade wiring. The bottleneck is the absence of a lexical layer and reranker, not the chunk strategy. Improving this without a BM25 layer yields only marginal gains.

---

### 2.2 HyDE — Hypothetical Document Embeddings
Generate a "fake ideal document" that answers the query via LLM, embed that document instead of the query, then retrieve by similarity to the fake document.

**Verdict for MANTIS**: ❌ **Do not use for this domain.** The 2026 financial QA benchmark (arXiv 2604.01733) showed HyDE Recall@5 = 0.544 vs 0.695 for plain hybrid RRF — a regression. Financial queries involve exact entities (BTCUSD, ATR=1.8), and LLM-generated pseudo-documents hallucinate numerical values, producing drift in embedding space that moves retrieval away from actual matching passages. High added latency (one LLM call per query) makes this worse. One exception: Multi-HyDE on long-form financial corpora (SEC filings) showed improvement; irrelevant here since MANTIS's docs are concise decision records, not long-form text.

---

### 2.3 GraphRAG / Knowledge Graph Hybrid
Build an entity-relationship graph from documents, use graph traversal to retrieve structurally connected facts, summarize communities via LLM.

**Verdict for MANTIS**: ❌ **Overkill and wrong fit.** GraphRAG is 10× more expensive to index than RAPTOR, and the benchmark (arXiv 2502.11371) shows 13.4% lower accuracy on time-sensitive queries — exactly the trading use case. MANTIS's corpus is relatively small (~50 markdown files + episodic memory) and not entity-dense enough to justify a graph. Use case 4 (cross-asset correlation) might benefit, but this is already handled structurally by the `DynamicCorrelationGuard` — the RAG layer doesn't need to re-derive it.

---

### 2.4 ColBERT-style Late Interaction
Each token in query and document gets its own embedding; MaxSim (max similarity of each query token against all doc tokens) is the score. Requires a columnar token index.

**Verdict for MANTIS**: ⚠️ **Potentially valuable but infrastructure-heavy.** ColBERT achieves +8.8% NDCG@10 over standard bi-encoder on 10-K financial documents. However, it requires `RAGatouille` or `pylate` + custom index, cannot run through Ollama's `/api/embed` endpoint (needs token-level vectors), and demands ~3× more storage per document. Memory-mapped serving reduces RAM usage >90% but still requires a dedicated serving process. **Defer** — reranker achieves 80% of ColBERT's benefit with <10% of the infrastructure complexity.

---

### 2.5 RAG-Fusion (Multi-Query)
Generate N variant phrasings of the query → retrieve for each → fuse ranked lists via Reciprocal Rank Fusion (RRF).

**Verdict for MANTIS**: ❌ **Marginal gain, real latency cost.** The same financial QA benchmark showed multi-query recall@5 = 0.640, essentially identical to plain BM25 (0.644), and far behind hybrid+reranker (0.816). Financial queries are already precise; generating alternative phrasings doesn't surface new documents. The N additional LLM calls for query generation (each ~300ms on Ollama) would blow the 2s latency budget.

---

### 2.6 Self-RAG / CRAG (Corrective RAG)
Retrieve, then have an LLM grade the retrieved chunks for relevance, re-retrieve if graded poor.

**Verdict for MANTIS**: ⚠️ **Useful as a quality gate, not as the primary architecture.** CRAG showed moderate improvement in the benchmark but adds 1-2 LLM calls in the critical path. The right place for this pattern in MANTIS is as a **post-retrieval filter** on the executive summary generation — the existing `_summarize()` method in `MantisRAGContextBuilder` is already a lite version of this. Not recommended as a core retrieval driver given the latency budget.

---

### 2.7 RAPTOR — Recursive Abstractive Summarization Tree
Cluster chunks → generate LLM summaries of each cluster → embed summaries → build a tree of increasing abstraction levels. Retrieve at multiple tree levels.

**Verdict for MANTIS**: ⚠️ **Good for the docs corpus, wrong for real-time news.** RAPTOR achieved 64.3% accuracy on MSMARCO (best of methods tested). It shines on large corpora that benefit from multi-granularity retrieval — exactly like MANTIS's 50+ handoff/decision markdown files. However, RAPTOR requires offline index rebuilds; it cannot be updated incrementally for streaming news. Good fit for the `docs/` corpus specifically, but adds indexing complexity. Recommend as an **optional enhancement** for the static knowledge base only, not as the primary retrieval path.

---

### 2.8 Hybrid BM25 + Vector Search (with RRF)
Run both a keyword (BM25/inverted-index) and semantic (vector) search in parallel, fuse results using Reciprocal Rank Fusion.

**Verdict for MANTIS**: ✅ **Strong fit. The lexical + semantic combination directly addresses the financial vocabulary mismatch problem.** Benchmark: Hybrid RRF achieved R@5 = 0.695 vs 0.587 for dense-only and 0.644 for BM25-only. Ticker names, metric labels ("ATR", "RSI_14"), and exact P&L figures are handled by BM25; semantic similarity clusters similar market regimes. PostgreSQL already in-stack via `pg_search` (ParadeDB, BM25 in pure Postgres via Tantivy/Rust) + `pgvector` (HNSW index, 1024-dim compatible). **Zero new infrastructure required.**

---

### 2.9 Cross-Encoder Reranker on top of Vector Search
First stage: approximate vector search returns top-20-50 candidates. Second stage: cross-encoder model scores each (query, candidate) pair and re-orders. Top-3-5 go into the prompt.

**Verdict for MANTIS**: ✅ **Highest single-step gain available.** Reranking lifted MRR@3 by +17.2pp over unreranked hybrid (0.605 vs 0.433). Anthropic's Contextual Retrieval study showed reranking reduces failure rate by 67% (vs 35% for embeddings alone). `bge-reranker-v2-m3` is available on Ollama today (`qllama/bge-reranker-v2-m3`), runs at ~278M params (fast on GX10), and is from the same BAAI family as bge-m3, so query/document distributions are well-matched. **Combine with hybrid BM25+vector as one unified pipeline.**

---

### 2.10 Contextual Retrieval (Anthropic's approach — index-time chunk enrichment)
At index time, prepend an LLM-generated context sentence to each chunk before embedding and BM25 indexing. The sentence situates the chunk within the broader document.

**Verdict for MANTIS**: ✅ **Excellent fit for the static docs corpus, moderate fit for news.** Anthropic measured: Contextual Embeddings alone −35% failure rate; adding Contextual BM25 → −49%; adding reranker → −67%. This technique is applied once at indexing time and costs nothing at retrieval time. For MANTIS's handoff docs (decision records, incident postmortems, trading invariants), this adds the "why" that naked chunk text often lacks. For streaming news, it's too slow to do per-article (one LLM call each) unless batched asynchronously.

---

### 2.11 Multi-Vector Retrieval (per-chunk + per-section embeddings)
Maintain two embedding granularities — full-section / full-document summaries AND fine-grained paragraphs. Retrieve at coarse level first, then drill into paragraphs.

**Verdict for MANTIS**: ✅ **Low-effort, high-reward for trade history.** For the trade history corpus, a trade record has both a "summary" (epic, direction, outcome, regime) and "details" (indicator values, risk metrics). Embedding both and searching the summary vector first, then checking detail vectors, surfaces "we had a similar BUY on BTCUSD in trending_up regime with RSI=68, it lost 0.8%" without false-positives from semantically similar summaries with opposite outcomes. This is a coding pattern, not a new library.

---

## 3. Recommended Architecture: Contextual Hybrid + Reranker

### 3.1 Why This Combination

The recommended approach stacks four well-validated techniques into a single pipeline:

```
[Query] 
   ↓
[Stage 1 — Dual Retrieval, parallel]
   ├─ BM25 on pg_search (lexical: ticker names, metric IDs, exact figures)
   └─ pgvector HNSW (semantic: regime similarity, narrative context)
   ↓
[Stage 2 — RRF Fusion]
   top-20 candidates ranked by Reciprocal Rank Fusion
   ↓
[Stage 3 — Cross-Encoder Rerank]
   bge-reranker-v2-m3 scores all 20 (query, chunk) pairs
   top-5 selected
   ↓
[Stage 4 — LLM Executive Summary]
   existing MantisRAGContextBuilder._summarize() runs on top-5
   (already implemented)
```

Index-time enrichment (Contextual Retrieval) is applied offline to the static docs corpus using qwen3.6:35b, amortizing the LLM cost over many queries.

### 3.2 What makes this "surprisingly optimal" vs naive cosine-on-bge-m3

| Dimension | Naive bge-m3 cosine | Recommended pipeline |
|---|---|---|
| Financial entity matching | Weak — "BTCUSD" and "Bitcoin" may score 0.72; adjacent docs score 0.71 | BM25 nails exact-string matches; reranker corrects cross-encoder ambiguity |
| Retrieval accuracy (financial QA benchmark) | R@5 ≈ 0.587, MRR@3 ≈ 0.351 | R@5 ≈ 0.816, MRR@3 ≈ 0.605 (+72% relative MRR) |
| News noise reduction | Top-5 by embedding similarity may include thematically similar but time-stale articles | Temporal metadata pre-filter eliminates stale items before retrieval; reranker re-scores by signal relevance |
| Trade pattern recall | Cosine of feature-signature embedding (12 floats, padded to 1024) is meaninglessly high-dimensional | Multi-vector approach: regime bucket filter → semantic similarity within bucket → reranker |
| Context quality for LLM | Raw chunk text may lack document context | Contextual prefix explains where each chunk comes from |
| NDCG@10 improvement estimate | baseline | +31-40% NDCG@10 (hybrid adds ~18pp over dense-only; reranker adds further 13-17pp — consistent with published benchmarks) |

### 3.3 Quantified expected improvement

Based on the arXiv 2604.01733v1 benchmark on financial documents:
- Dense-only → Hybrid: +2.8pp NDCG@10 (0.466 → 0.551), +18% relative  
- Hybrid → Hybrid+Rerank: +13.2pp NDCG@10 (0.551 → 0.683), +24% relative  
- Combined vs current state (dense-only, no reranker): **+46.6% relative NDCG@10**

Contextual indexing adds a further −49% retrieval failure rate (Anthropic study) on top of the above, but at index time only.

---

## 4. Components Needed

### 4.1 Infrastructure (all local, zero new services)

| Component | Solution | Notes |
|---|---|---|
| Vector search | `pgvector` extension on existing PostgreSQL | Already available via asyncpg stack; add HNSW index |
| Lexical search | `pg_search` (ParadeDB) or `pg_textsearch` (Timescale) | Single Postgres extension, no Elastic, no Redis change |
| Embedding | bge-m3 via existing Ollama (`/api/embed`) | Already in `OllamaProvider.embed()` |
| Reranker | `bge-reranker-v2-m3` via Ollama (`qllama/bge-reranker-v2-m3`) | Same Ollama instance; 278M params, fast on GX10 |
| Contextual indexing | `qwen3.6:35b` offline batch | Runs once per doc ingestion, amortized cost |
| Result fusion | Pure Python RRF | 10 lines of code, no library needed |

**ParadeDB `pg_search`** is the recommended BM25 solution — production-grade, built on Tantivy/Rust, ACID-compliant, no synchronization headaches, installs as a PostgreSQL extension. Alternative: `pg_textsearch` by Timescale (also BM25, OSS-licensed). Either avoids Elasticsearch.

### 4.2 New tables / schema changes

```sql
-- Unified RAG document store
CREATE TABLE rag_documents (
    id          BIGSERIAL PRIMARY KEY,
    doc_type    TEXT NOT NULL,          -- 'news','trade','episode','docs','pattern'
    epic        TEXT,                   -- NULL = global
    regime      TEXT,
    content     TEXT NOT NULL,          -- contextual-enriched text for embedding + BM25
    raw_content TEXT NOT NULL,          -- original text before enrichment
    embedding   vector(1024),           -- bge-m3 vector
    source_id   TEXT,                   -- link back to position/episode/news URL
    published_at TIMESTAMPTZ,           -- for temporal pre-filter
    metadata    JSONB DEFAULT '{}'
);

-- pgvector HNSW index
CREATE INDEX rag_docs_embedding_idx 
    ON rag_documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- BM25 index (pg_search)
CREATE INDEX rag_docs_bm25_idx 
    ON rag_documents USING bm25 (content)
    WITH (text_fields='{"content": {}}');

-- Composite metadata filtering
CREATE INDEX rag_docs_filter_idx 
    ON rag_documents (doc_type, epic, published_at DESC);
```

### 4.3 Retrieval pipeline sketch

```python
# src/rag/retrieval.py  (new file — ~200 lines)

class MantisHybridRetriever:
    """
    Stage 1: Dual BM25 + vector retrieval with pre-filters.
    Stage 2: RRF fusion.
    Stage 3: Cross-encoder reranking via bge-reranker-v2-m3.
    """
    
    async def retrieve(
        self,
        query: str,
        *,
        epic: str | None = None,
        doc_types: list[str] | None = None,
        published_after: datetime | None = None,
        top_k_candidates: int = 20,
        top_k_final: int = 5,
    ) -> list[RankedChunk]:
        
        # 1. Embed query (bge-m3, existing OllamaProvider.embed())
        query_vec = (await self._provider.embed([query]))[0]
        
        # 2. BM25 search (pg_search) — lexical lane
        bm25_hits = await self._db.fetch("""
            SELECT id, content, metadata,
                   paradedb.score(id) AS bm25_score
            FROM rag_documents
            WHERE content @@@ paradedb.parse($1)
              AND ($2::text IS NULL OR epic = $2)
              AND ($3::text[] IS NULL OR doc_type = ANY($3))
              AND ($4::timestamptz IS NULL OR published_at >= $4)
            ORDER BY bm25_score DESC
            LIMIT $5
        """, query, epic, doc_types, published_after, top_k_candidates)
        
        # 3. Vector search (pgvector HNSW) — semantic lane
        vec_hits = await self._db.fetch("""
            SELECT id, content, metadata,
                   1 - (embedding <=> $1::vector) AS vec_score
            FROM rag_documents
            WHERE ($2::text IS NULL OR epic = $2)
              AND ($3::text[] IS NULL OR doc_type = ANY($3))
              AND ($4::timestamptz IS NULL OR published_at >= $4)
            ORDER BY embedding <=> $1::vector
            LIMIT $5
        """, query_vec, epic, doc_types, published_after, top_k_candidates)
        
        # 4. RRF fusion
        candidates = self._rrf_fuse(bm25_hits, vec_hits, k=60)[:top_k_candidates]
        
        # 5. Cross-encoder rerank via bge-reranker-v2-m3
        if len(candidates) > top_k_final:
            candidates = await self._rerank(query, candidates, top_k=top_k_final)
        
        return candidates
    
    async def _rerank(self, query: str, candidates: list, top_k: int) -> list:
        # bge-reranker-v2-m3 via Ollama embed API (reranker endpoint)
        # Returns scores; sort descending; return top_k
        pairs = [[query, c.content] for c in candidates]
        scores = await self._provider.rerank(pairs)  # new method on OllamaProvider
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        return [c for _, c in ranked[:top_k]]
    
    @staticmethod
    def _rrf_fuse(bm25_hits, vec_hits, k: int = 60) -> list:
        """Reciprocal Rank Fusion: score = Σ 1/(k + rank_i)"""
        scores: dict[int, float] = {}
        for rank, row in enumerate(bm25_hits, 1):
            scores[row["id"]] = scores.get(row["id"], 0) + 1 / (k + rank)
        for rank, row in enumerate(vec_hits, 1):
            scores[row["id"]] = scores.get(row["id"], 0) + 1 / (k + rank)
        # return all rows merged, sorted by fused score
        ...
```

### 4.4 Indexing pipelines

**A. Static docs corpus** (one-time + on doc change)
```
docs/**/*.md  →  chunk(800 tokens, 100 overlap)
              →  qwen3.6:35b generates context sentence per chunk
              →  content = context + chunk_text
              →  bge-m3 embeds contextual content
              →  INSERT INTO rag_documents (doc_type='docs', ...)
```
Estimated: ~50 files × ~5 chunks × 1 LLM call = 250 calls. At ~500ms each = ~2 min one-time run.

**B. News feed** (continuous, existing SIL pipeline)
```
MantisNewsIngester.ingest() → top-10 by relevance score
    → bge-m3 embed(title + lead_paragraph)   [no contextual enrichment — too slow per-article]
    → INSERT INTO rag_documents (doc_type='news', published_at=..., epic=...)
    → DELETE FROM rag_documents WHERE doc_type='news' AND published_at < NOW() - INTERVAL '48h'
```

**C. Trade history** (on position close)
```
position closed → generate summary text:
    f"[{direction}] {epic} in {regime} regime: entry={entry}, SL={sl}, TP={tp},
      exit={exit}, outcome={pnl_pct:+.2f}%, RSI={rsi}, ATR={atr}, confidence={conf:.2f}"
    → bge-m3 embed
    → INSERT INTO rag_documents (doc_type='trade', epic=epic, regime=regime, source_id=deal_id)
```

**D. Episodic memory** (on episode record — already in `MantisEpisodicMemory.record_episode()`)
```
episode recorded → INSERT INTO rag_documents (doc_type='episode', ...)
    (replace current SQLite cosine scan with pgvector HNSW lookup)
```

### 4.5 Integration points in MANTIS code

| File | Change required |
|---|---|
| `src/rag/vector_store.py` | Deprecate numpy store; delegate to `rag_documents` table; keep interface for tests |
| `src/rag/context_builder.py` | Replace static news list parameter with `MantisHybridRetriever.retrieve()` call; add `epic` and temporal filter params |
| `src/rag/retrieval.py` | **New file** — `MantisHybridRetriever` class (Stage 1-4 pipeline above) |
| `src/rag/indexer.py` | **New file** — `MantisDocIndexer` (contextual enrichment + batch upsert) |
| `src/llm_provider/base.py` | Add `rerank(pairs: list[list[str]]) -> list[float]` abstract method |
| `src/llm_provider/ollama_provider.py` | Implement `rerank()` calling `qllama/bge-reranker-v2-m3` via `/api/embed` endpoint |
| `src/memory_layer/episodic.py` | In `recall_similar()`: replace numpy linear scan with pgvector HNSW call |
| `src/memory_layer/long_term.py` | Add `query_by_embedding()` method using pgvector; keep regime bucket filter as pre-filter |
| `src/trading/paper_loop.py` | On position close: call `MantisDocIndexer.index_trade(position, outcome)` |
| DB migration | New `rag_documents` table + pgvector + pg_search indexes |

### 4.6 Use-case-specific retrieval queries

**Use case 1 — Trade signal enrichment**:
```python
await retriever.retrieve(
    query=f"{direction} {epic} {regime} RSI={rsi:.0f} ATR_pct={atr_pct:.3f}",
    epic=epic,
    doc_types=["trade", "episode"],
    published_after=None,  # all history
    top_k_final=3,
)
```
Surfaces: "we placed BUY BTCUSD trending_up RSI=72 3 months ago → +1.2% in 4h"

**Use case 2 — News-driven context**:
```python
await retriever.retrieve(
    query=f"Market-moving news for {epic} in next 4h",
    epic=epic,
    doc_types=["news"],
    published_after=datetime.now(UTC) - timedelta(hours=4),  # recency hard filter
    top_k_final=5,
)
```
Recency pre-filter eliminates temporal noise before semantic scoring.

**Use case 3 — Decision audit**:
```python
await retriever.retrieve(
    query=f"REJECTED {direction} {epic}: {rejection_reason}",
    doc_types=["trade", "episode", "docs"],
    top_k_final=5,
)
```
Retrieves closest past rejections + relevant doc passages + outcomes.

**Use case 4 — Cross-asset correlation**:
```python
await retriever.retrieve(
    query=f"{lead_asset} price movement preceded {lagged_asset} correlation",
    doc_types=["episode", "docs"],
    top_k_final=5,
)
```
Episode store captures "BTC drop preceded ETH drop by 20min" when recorded by the episodic system.

---

## 5. Estimated Implementation Effort

| Task | Effort |
|---|---|
| DB migration: `rag_documents` table + pgvector + pg_search extensions | 2h |
| `OllamaProvider.rerank()` method + unit tests | 1h |
| `MantisHybridRetriever` (retrieval.py) — RRF + rerank pipeline | 4h |
| `MantisDocIndexer` (indexer.py) — contextual enrichment + batch upsert | 3h |
| Wire trade-close → indexer in paper_loop.py | 1h |
| Wire news ingestion → indexer (replace numpy store) | 2h |
| Update `MantisEpisodicMemory.recall_similar()` → pgvector | 1h |
| Update `MantisRAGContextBuilder.build()` to call retriever | 2h |
| One-time docs corpus indexing script | 1h |
| Tests + baseline rebaseline | 3h |
| **Total** | **~20h** |

---

## 6. Estimated Retrieval Latency Budget

Signal flow latency budget: **2s total** for RAG retrieval + summary.

| Step | Latency |
|---|---|
| bge-m3 embed (1 query, batch=1) | ~50ms (LAN Ollama, GX10 already loaded) |
| pgvector HNSW search (top-20, 1024-dim, HNSW) | <5ms (in-process PostgreSQL) |
| pg_search BM25 search (top-20) | <5ms (in-process PostgreSQL) |
| RRF fusion (Python, 40 candidates) | <1ms |
| bge-reranker-v2-m3 (20 pairs, 278M params) | ~200-400ms (GX10, batched) |
| MantisRAGContextBuilder executive summary (qwen3.6:35b, 300 tokens) | ~800-1200ms (already in-flight) |
| **Total** | **~1.1-1.7s** |

Comfortably within 2s budget. The reranker is the dominant new cost; the LLM summary was already present. If latency is tight, reduce candidate pool from 20 to 10 (saves ~100ms on reranker) or skip reranking for trade/episode types (only apply to news + docs).

---

## 7. Known Failure Modes and Mitigations

### 7.1 Temporal look-ahead bias
**Risk**: news indexed at T=14:00 could be retrieved for a signal generated at T=13:45 if `published_at` is set on ingest-time, not article publish-time.  
**Mitigation**: Always use the article's original `published_at` field, not `NOW()` at ingestion. Apply `published_after` filter in retrieval using signal generation time, not real-time. This is a hard invariant — violating it introduces future leakage into the signal.

### 7.2 Embedding dimension mismatch on migration
**Risk**: Existing episodic memory SQLite store has embeddings at 1024-dim (bge-m3) mixed with legacy 384-dim (MiniLM fallback). pgvector requires a fixed dimension per table.  
**Mitigation**: Create `rag_documents` with `vector(1024)` from day 1. Re-embed legacy 384-dim records using bge-m3 during migration. The `MantisEmbedder` already normalizes to `embedding_dim` dynamically — migration script should call `embed_text_async()` to produce 1024-dim vectors.

### 7.3 Cross-encoder confirmation bias in trade history
**Risk**: If past trade records are sparse (e.g. only 3 BTCUSD trades in the store), the reranker will return all 3 regardless of relevance, creating false precision.  
**Mitigation**: Apply a minimum similarity threshold from Stage 1 (`vec_score > 0.65`) before passing candidates to the reranker. Return fewer results rather than low-quality ones. The `executive_summary` LLM step already has graceful degradation — it produces "no relevant context" output if the prompt is sparse.

### 7.4 Reranker latency spike under concurrent load
**Risk**: Multiple signal paths (21 assets, potential simultaneous 4h slots) calling reranker concurrently could saturate GX10 VRAM.  
**Mitigation**: Reranker is gated behind a `asyncio.Semaphore(max_concurrent=3)`. Other callers fall back to pure RRF ranking without reranking. The news-filtering path (Use Case 2) should always run with reranker; trade-pattern retrieval (Use Case 1) can degrade to RRF-only gracefully.

### 7.5 pg_search extension availability
**Risk**: Managed PostgreSQL services don't allow custom extensions. Local dev may have different extension availability.  
**Mitigation**: Graceful degradation: if pg_search is unavailable, fall back to PostgreSQL `ts_rank_cd` (native tsvector FTS). This loses BM25's probabilistic ranking but keeps lexical search alive. Detected at startup via `CREATE EXTENSION IF NOT EXISTS pg_search` check.

### 7.6 bge-reranker-v2-m3 not yet available on Ollama pull
**Risk**: The model is listed on Ollama (`qllama/bge-reranker-v2-m3`) but may have different API behavior from embedding models.  
**Mitigation**: The reranker returns relevance scores via the `/api/embed` endpoint (returns a single scalar per pair). Test and validate this endpoint behavior before wiring into production. Fallback: implement reranker as a direct Python call to `transformers.AutoModelForSequenceClassification` on the GX10 box if Ollama's reranker support is incomplete.

---

## RECOMMENDATION

**Single chosen approach: Contextual Hybrid BM25 + pgvector HNSW + bge-reranker-v2-m3**

This is not a radical architectural departure — it extends what is already partially built (bge-m3 embeddings, Ollama provider, PostgreSQL, memory store) into a well-validated retrieval pipeline. The "surprising" aspect is the reranker: a cross-encoder scoring all 20 candidates jointly (not independently) against the query is fundamentally a different computation than bi-encoder cosine similarity. The cross-encoder sees the query and document together, allowing full attention between their tokens — this is why it achieves +46% relative NDCG improvement over naive cosine search on financial text.

### 5-Step Implementation Plan

**Step 1 — Foundation (Day 1, ~3h)**  
Install `pg_search` (ParadeDB) on local PostgreSQL. Write and run the DB migration creating `rag_documents` table with `vector(1024)` column, HNSW index, BM25 index, and composite metadata filter index. Verify both index types work via test queries. Add `ollama pull qllama/bge-reranker-v2-m3` to GX10 setup docs.

**Step 2 — Reranker provider (Day 1, ~1h)**  
Add `rerank(pairs: list[list[str]]) -> list[float]` to `LLMProvider` base class and `OllamaProvider`. Write a unit test that mocks the HTTP call. Validate latency against GX10 with a batch of 20 pairs.

**Step 3 — Hybrid retriever (Day 2, ~5h)**  
Implement `src/rag/retrieval.py`: `MantisHybridRetriever` with async BM25 + vector dual-lane, RRF fusion, reranker stage, and metadata pre-filtering. Write tests with fixture data. Benchmark against 2s latency target.

**Step 4 — Indexers (Day 2-3, ~5h)**  
Implement `src/rag/indexer.py`: `MantisDocIndexer` with methods for each doc type (news, trade, episode, docs). Add contextual enrichment for docs corpus (offline batch, one-time run). Wire trade-close path in `paper_loop.py`. Replace numpy vector store calls in `MantisEpisodicMemory.recall_similar()` with pgvector.

**Step 5 — Context builder + integration tests (Day 3, ~3h)**  
Update `MantisRAGContextBuilder.build()` to call `MantisHybridRetriever` with per-use-case query construction. Run the one-time docs indexing script. Rebaseline tests. Smoke test against live trading loop with `RECONCILER_DEDICATED_ENABLED=false` to isolate any new latency.

---

## Sources

- [Financial RAG Benchmarking: BM25 to Corrective RAG](https://arxiv.org/html/2604.01733v1)
- [RAG for Financial Time Series (FinSrag)](https://arxiv.org/html/2502.05878v3)
- [Contextual Retrieval — Anthropic](https://www.anthropic.com/news/contextual-retrieval)
- [RAG vs GraphRAG Systematic Evaluation](https://arxiv.org/html/2502.11371v3)
- [GraphRAG-Bench: When to Use Graphs](https://arxiv.org/html/2506.05690v3)
- [Hybrid Search with pgvector — Superlinked VectorHub](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
- [pgvector HNSW vs IVFFlat Guide](https://dbadataverse.com/tech/postgresql/2025/12/pgvector-postgresql-vector-database-guide)
- [ParadeDB pg_search: BM25 in Postgres](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)
- [bge-reranker-v2-m3 on Ollama](https://ollama.com/qllama/bge-reranker-v2-m3)
- [BAAI bge-reranker-v2-m3 HuggingFace](https://huggingface.co/BAAI/bge-reranker-v2-m3)
- [Multi-HyDE for Financial RAG](https://arxiv.org/html/2509.16369)
- [Temporal-Aware MultiModal RAG in Finance](https://arxiv.org/pdf/2503.05185)
- [Self-Aware Vector Embeddings with Temporal Decay](https://arxiv.org/html/2604.20598v1)
- [Hybrid Search for RAG: BM25, SPLADE, Vector](https://blog.premai.io/hybrid-search-for-rag-bm25-splade-and-vector-search-combined/)
- [New Research: Cross-Encoder Reranking +40% RAG Accuracy](https://app.ailog.fr/en/blog/news/reranking-cross-encoders-study)
- [Episodic Memory Beyond Fact Retrieval (AAAI 2026)](https://ojs.aaai.org/index.php/AAAI/article/view/40557)
