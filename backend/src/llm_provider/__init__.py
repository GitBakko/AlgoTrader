"""LLM provider abstraction.

Single entry point for text generation, vision analysis, and embeddings.
Backends: Ollama (local, free) and Anthropic (Claude API, fallback).

Usage:
    from src.llm_provider import get_llm_provider

    provider = get_llm_provider()
    text = await provider.generate("Hello", max_tokens=100)
    json_str = await provider.analyze_image(prompt, png_bytes, json_mode=True)
    vecs = await provider.embed(["hello", "world"])
"""

from src.llm_provider.base import LLMProvider, LLMProviderError
from src.llm_provider.factory import get_llm_provider, reset_llm_provider
from src.llm_provider.ollama_provider import OllamaProvider

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "OllamaProvider",
    "get_llm_provider",
    "reset_llm_provider",
]
