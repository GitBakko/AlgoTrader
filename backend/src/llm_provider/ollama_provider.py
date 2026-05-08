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

import base64

import httpx
from loguru import logger

from src.llm_provider.base import LLMProvider, LLMProviderError


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
