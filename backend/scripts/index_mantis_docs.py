"""Index MANTIS markdown docs into the RAG corpus.

Walks `docs/`, `docs/handoff/`, `docs/evolutive/`, plus root-level
markdown (`CLAUDE.md`, `STYLE_BIBLE.md`), chunks each file by header
section with a soft 1500-char limit, embeds via the configured
LLMProvider (Ollama bge-m3 by default → 1024-dim), and persists into
`data/rag_corpus/` via ``MantisVectorStore``.

Run from the backend root:

    .venv/Scripts/python.exe scripts/index_mantis_docs.py
    .venv/Scripts/python.exe scripts/index_mantis_docs.py --root D:/Develop/AI/_ClaudeCode/AlgoTrader

Re-runs are idempotent — the previous corpus is cleared before indexing.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the leaf modules directly to avoid the rag/__init__ → memory_layer
# → agents → vision_agent → rag.context_builder cycle that triggers when
# the rag package is loaded as a whole.
import importlib.util  # noqa: E402

_factory_spec = importlib.util.spec_from_file_location(
    "src.llm_provider.factory",
    Path(__file__).parent.parent / "src" / "llm_provider" / "factory.py",
)
_factory_mod = importlib.util.module_from_spec(_factory_spec)
_factory_spec.loader.exec_module(_factory_mod)
get_llm_provider = _factory_mod.get_llm_provider

_vs_spec = importlib.util.spec_from_file_location(
    "src.rag.vector_store",
    Path(__file__).parent.parent / "src" / "rag" / "vector_store.py",
)
_vs_mod = importlib.util.module_from_spec(_vs_spec)
_vs_spec.loader.exec_module(_vs_mod)
MantisVectorStore = _vs_mod.MantisVectorStore

DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "rag_corpus"

# Doc dirs walked relative to repo root.
DOC_DIRS = (
    "docs",
    "docs/handoff",
    "docs/evolutive",
    "docs/reports",
)
# Standalone markdown files at repo root.
ROOT_DOCS = (
    "CLAUDE.md",
    "STYLE_BIBLE.md",
    "README.md",
)
# Skip very-noisy files / generated artifacts.
SKIP_PATTERNS = (
    "node_modules/",
    ".pyc",
    ".git/",
    "__pycache__/",
)

CHUNK_CHAR_LIMIT = 1500  # ~375 tokens, fits comfortably in bge-m3 8192 ctx
CHUNK_OVERLAP_CHARS = 200


def collect_files(repo_root: Path) -> list[Path]:
    """Return absolute paths of every markdown file to index."""
    files: list[Path] = []
    for rel in DOC_DIRS:
        d = repo_root / rel
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.md")):
            if any(pat in str(f).replace("\\", "/") for pat in SKIP_PATTERNS):
                continue
            files.append(f)
    for rel in ROOT_DOCS:
        f = repo_root / rel
        if f.exists():
            files.append(f)
    return files


def chunk_by_section(text: str, source: str) -> list[tuple[str, str]]:
    """Split markdown into ``(header, body)`` chunks.

    Splits on ``^#`` / ``^##`` / ``^###`` headers. If a section is
    longer than ``CHUNK_CHAR_LIMIT``, falls back to char-based
    sliding-window splitting with overlap.
    """
    lines = text.splitlines(keepends=True)
    sections: list[tuple[str, list[str]]] = []
    current_header = source
    current_buf: list[str] = []

    header_re = re.compile(r"^#{1,3}\s+(.+)$")
    for line in lines:
        m = header_re.match(line.strip())
        if m:
            if current_buf:
                sections.append((current_header, current_buf))
            current_header = m.group(1).strip()
            current_buf = [line]
        else:
            current_buf.append(line)
    if current_buf:
        sections.append((current_header, current_buf))

    chunks: list[tuple[str, str]] = []
    for header, buf in sections:
        body = "".join(buf).strip()
        if not body:
            continue
        if len(body) <= CHUNK_CHAR_LIMIT:
            chunks.append((header, body))
            continue
        start = 0
        while start < len(body):
            end = min(start + CHUNK_CHAR_LIMIT, len(body))
            chunk = body[start:end]
            chunks.append((header, chunk))
            if end == len(body):
                break
            start = end - CHUNK_OVERLAP_CHARS
    return chunks


async def build_corpus(repo_root: Path, corpus_dir: Path) -> None:
    files = collect_files(repo_root)
    logger.info(f"Discovered {len(files)} markdown files under {repo_root}")

    provider = get_llm_provider()
    embedding_dim = provider.embedding_dim
    logger.info(f"Embedder dim={embedding_dim} via {type(provider).__name__}")

    store = MantisVectorStore(dimension=embedding_dim, store_path=str(corpus_dir))
    store.clear()

    total_chunks = 0
    skipped_files = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning(f"Skip {f}: {exc!r}")
            skipped_files += 1
            continue
        if not text.strip():
            continue

        rel = f.relative_to(repo_root).as_posix()
        chunks = chunk_by_section(text, rel)
        if not chunks:
            continue

        # Batch embed all chunks for this file in a single Ollama call.
        chunk_texts = [body for _, body in chunks]
        try:
            vectors = await provider.embed(chunk_texts)
        except Exception as exc:
            logger.warning(f"Embedding failed for {rel}: {exc!r}")
            skipped_files += 1
            continue

        for (header, body), vec in zip(chunks, vectors):
            store.add(
                text=body,
                vector=vec,
                metadata={
                    "source": rel,
                    "header": header,
                    "doc_type": "docs",
                    "chunk_index": total_chunks,
                },
            )
            total_chunks += 1

        logger.info(f"  [{rel}] {len(chunks)} chunks indexed (running total: {total_chunks})")

    corpus_dir.mkdir(parents=True, exist_ok=True)
    store.save()
    logger.info(
        f"Corpus built: {total_chunks} chunks from {len(files) - skipped_files} files "
        f"(skipped {skipped_files}) → {corpus_dir}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_REPO_ROOT, help="Repo root to walk"
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=CORPUS_DIR_DEFAULT,
        help="Output directory for vector store",
    )
    args = parser.parse_args()

    asyncio.run(build_corpus(args.root, args.corpus_dir))


if __name__ == "__main__":
    main()
