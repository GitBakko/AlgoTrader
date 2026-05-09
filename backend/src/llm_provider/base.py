"""LLMProvider abstract base.

Defines the contract every concrete backend must satisfy for the three
operation classes Mantis uses: text generation, multimodal vision
analysis, and dense-vector embedding.

Operations are async. Each backend is free to fan out to a remote
HTTP endpoint, an in-process model, or a hybrid — callers don't care.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProviderError(RuntimeError):
    """Raised when a provider call fails irrecoverably.

    Callers in production paths (vision_analyzer, news_ingester) catch
    this and fall back to low-confidence defaults so the trading loop
    never crashes on LLM transient errors.
    """


class LLMProvider(ABC):
    """Provider-agnostic interface for text + vision + embedding.

    Concrete implementations live alongside this module
    (`ollama_provider.py`, future `anthropic_provider.py`). Selection is
    via `get_llm_provider()` which reads `LLM_BACKEND` env.
    """

    @abstractmethod
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
        """Generate text completion.

        Args:
            prompt: User prompt (no chat-template wrapping).
            system: Optional system prompt prepended.
            max_tokens: Cap on generated tokens.
            temperature: Sampling temperature; 0.0 = deterministic.
            json_mode: When True, hint the backend to enforce valid JSON
                output. Ollama maps to ``format="json"``, Anthropic
                handles via system prompt.
            keep_alive: Backend-specific lifetime hint (Ollama). Set to
                ``-1`` to pin the model in VRAM forever, ``"1h"`` for
                bounded keep, ``None`` to use the provider default.

        Returns:
            Generated text. Markdown fences are NOT stripped — the
            caller decides how to parse.

        Raises:
            LLMProviderError: irrecoverable backend failure.
        """

    @abstractmethod
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
        """Analyze a single image and return a text response.

        Args:
            image_bytes: Raw PNG/JPEG bytes. The provider handles
                base64 encoding internally.
            (other args identical to `generate`)
        """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate dense embeddings for a list of texts.

        Returns:
            One float vector per input text. Embedding dimension is
            backend/model-specific (bge-m3 = 1024 for the Ollama
            default).

        Raises:
            LLMProviderError: irrecoverable backend failure.
        """

    async def rerank(
        self,
        query: str,
        passages: list[str],
    ) -> list[float]:
        """Score query↔passage relevance via a cross-encoder reranker.

        Returns a list of scalar scores (one per passage), higher = more
        relevant. Default implementation raises NotImplementedError; concrete
        backends opt in by overriding (the OllamaProvider lazy-loads
        ``BAAI/bge-reranker-v2-m3`` locally via transformers when first called).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement rerank()"
        )

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the backend is reachable + responsive.

        Used by VisionAgent / orchestrator startup to decide whether to
        enable optional vision/RAG steps. Must NOT raise; on any error,
        return False.
        """

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Dimensionality of vectors returned by `embed()`.

        Required by callers (vector store schema, cosine similarity
        normalization). Must match the model the backend uses.
        """
