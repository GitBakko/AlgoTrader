"""LLMProvider factory.

`get_llm_provider()` returns a process-singleton instance configured
from settings. The first call constructs it; subsequent calls reuse.

Backend selection follows the `LLM_BACKEND` env (default ``"ollama"``).
Each backend reads its own config block from `Settings`.
"""

from __future__ import annotations

from loguru import logger

from src.llm_provider.base import LLMProvider
from src.llm_provider.ollama_provider import OllamaProvider

_provider_singleton: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Return the configured LLMProvider singleton, building if needed."""
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    # Local import to avoid circular dependency at module load time —
    # `Settings` imports parts of the codebase that may not be ready
    # when this module is first imported during app startup.
    from src.utils.config import get_settings

    settings = get_settings()
    backend = (getattr(settings, "llm_backend", "ollama") or "ollama").strip().lower()

    if backend == "ollama":
        _provider_singleton = OllamaProvider(
            base_url=settings.ollama_base_url,
            generation_model=settings.ollama_generation_model,
            vision_model=settings.ollama_vision_model,
            embedding_model=settings.ollama_embedding_model,
            embedding_dim=settings.ollama_embedding_dim,
            keep_alive_generation=settings.ollama_keep_alive_generation,
            keep_alive_vision=settings.ollama_keep_alive_vision,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        logger.info(
            f"LLMProvider initialized: backend=ollama "
            f"url={settings.ollama_base_url} "
            f"gen={settings.ollama_generation_model} "
            f"vision={settings.ollama_vision_model} "
            f"embed={settings.ollama_embedding_model}"
        )
    else:
        raise ValueError(
            f"Unknown LLM_BACKEND={backend!r}. Supported: 'ollama'."
        )

    return _provider_singleton


def reset_llm_provider() -> None:
    """Clear the singleton.

    Tests use this between cases to inject mocks without leaking state.
    Production code never calls this.
    """
    global _provider_singleton
    _provider_singleton = None
