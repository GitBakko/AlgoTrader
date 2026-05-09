"""Ollama backend for the LLMProvider abstraction.

Targets a remote Ollama server (default: ``http://192.168.3.191:11434``,
the GX10 NVIDIA AI box on the LAN). Speaks the standard Ollama HTTP
API — `/api/generate`, `/api/embed`, `/api/tags`, `/api/ps`.

Design notes:
- Async via httpx. No background tasks; one request = one HTTP call.
- The generation model is pinned in VRAM by default
  (`keep_alive=-1`) so qwen3.6:35b stays loaded across sessions.
  The vision model uses a bounded keep_alive (default ``"1h"``) so
  multi-tenant servers don't get monopolized.
- ``think=False`` is set on every generation call. Qwen3+ models
  default to a Chain-of-Thought "thinking" trace that bloats latency
  10–20×; for production trading we want the answer, not the
  reasoning. The audit trail captures upstream context anyway.
- Errors raise `LLMProviderError`. The vision_analyzer / news_ingester
  layers catch these and fall back to safe defaults — the trading
  loop never crashes on a transient Ollama hiccup.
"""

from __future__ import annotations

import asyncio
import base64

import httpx
from loguru import logger

from src.llm_provider.base import LLMProvider, LLMProviderError


class _LocalCrossEncoder:
    """Lazy-loaded bge-reranker-v2-m3 wrapper.

    Loads the cross-encoder once on first ``__call__`` and reuses it
    across calls. Pure CPU (uses the existing ``torch+cpu`` install in
    the backend venv); first call pays the ~568 MB HF download +
    ~2-4 s model load. Subsequent calls run in ~50-200 ms per query
    against ≤20 passages.

    Thread-safety: the model itself is read-only after load. We hold
    a single ``torch.no_grad()`` context per call. Multiple concurrent
    callers serialize on the GIL but the bottleneck is the matmul,
    not Python — so concurrency-via-asyncio is fine.
    """

    def __init__(self, model_id: str, max_length: int = 512):
        self.model_id = model_id
        self.max_length = max_length
        self._tokenizer = None
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        # Local imports — keep heavy deps out of module-load time.
        from transformers import (  # noqa: PLC0415
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        logger.info(f"[rerank] loading {self.model_id} on CPU (first call)...")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_id)
        self._model.eval()
        logger.info(f"[rerank] {self.model_id} loaded.")

    def __call__(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        self._ensure_loaded()
        import torch  # noqa: PLC0415

        pairs = [(query, p) for p in passages]
        with torch.no_grad():
            inputs = self._tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            logits = self._model(**inputs).logits.view(-1).float()
            scores = torch.sigmoid(logits).tolist()
        return [float(s) for s in scores]


async def _run_in_thread(scorer: _LocalCrossEncoder, query: str, passages: list[str]) -> list[float]:
    """Off-load the (CPU-bound) reranker call to a default executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, scorer, query, passages)


class OllamaProvider(LLMProvider):
    """Ollama-backed LLMProvider implementation."""

    def __init__(
        self,
        base_url: str = "http://192.168.3.191:11434",
        generation_model: str = "qwen3.6:35b",
        vision_model: str = "qwen2.5vl:7b",
        embedding_model: str = "bge-m3:latest",
        embedding_dim: int = 1024,
        keep_alive_generation: str | int = -1,
        keep_alive_vision: str | int = "1h",
        timeout_seconds: float = 60.0,
        disable_thinking: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.generation_model = generation_model
        self.vision_model = vision_model
        self.embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self.keep_alive_generation = keep_alive_generation
        self.keep_alive_vision = keep_alive_vision
        self.timeout = timeout_seconds
        self.disable_thinking = disable_thinking

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
        json_mode: bool = False,
        keep_alive: str | int | None = None,
    ) -> str:
        payload: dict = {
            "model": self.generation_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": (
                keep_alive if keep_alive is not None else self.keep_alive_generation
            ),
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if self.disable_thinking:
            payload["think"] = False
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        body = await self._post("/api/generate", payload)
        return body.get("response", "")

    async def analyze_image(
        self,
        prompt: str,
        image_bytes: bytes,
        *,
        system: str | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
        json_mode: bool = False,
        keep_alive: str | int | None = None,
    ) -> str:
        if not image_bytes:
            raise LLMProviderError("analyze_image: empty image_bytes")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        payload: dict = {
            "model": self.vision_model,
            "prompt": prompt,
            "images": [b64],
            "stream": False,
            "keep_alive": (
                keep_alive if keep_alive is not None else self.keep_alive_vision
            ),
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        # NB: do NOT pass `think=False` to vision models. qwen2.5vl
        # ignores the param and some Ollama versions error on unknown
        # opts being mixed with `images`. Vision models don't have
        # thinking mode anyway.
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        body = await self._post("/api/generate", payload)
        return body.get("response", "")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload = {"model": self.embedding_model, "input": texts}
        body = await self._post("/api/embed", payload)
        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise LLMProviderError(
                f"Ollama embed returned {len(embeddings) if isinstance(embeddings, list) else '?'} "
                f"vectors for {len(texts)} inputs"
            )
        return embeddings

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        """Score query↔passage relevance via local bge-reranker-v2-m3.

        Ollama's ``/api/embed`` for ``qllama/bge-reranker-v2-m3`` returns
        bi-encoder vectors, not the cross-encoder relevance scores the
        model was trained for. We bypass Ollama for reranking and load
        ``BAAI/bge-reranker-v2-m3`` locally via ``transformers`` —
        cached in HF home on first call (~568 MB), then reused. Runs on
        CPU; the reranker is small enough that batched 20-pair scoring
        completes in ~1-2s on modern desktops, fast enough for the
        non-blocking RAG enrichment path.

        Returns one scalar per passage (sigmoid-applied logit, range
        [0, 1] after sigmoid). Returns an empty list when ``passages``
        is empty.
        """
        if not passages:
            return []
        scorer = self._get_reranker()
        return await _run_in_thread(scorer, query, passages)

    def _get_reranker(self):
        if getattr(self, "_reranker", None) is None:
            self._reranker = _LocalCrossEncoder(
                model_id="BAAI/bge-reranker-v2-m3",
                max_length=512,
            )
        return self._reranker

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception as exc:
            logger.debug(f"Ollama health_check failed: {exc!r}")
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload)
                if r.status_code != 200:
                    raise LLMProviderError(
                        f"Ollama {path} returned {r.status_code}: {r.text[:300]}"
                    )
                return r.json()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama HTTP error on {path}: {exc!r}") from exc
