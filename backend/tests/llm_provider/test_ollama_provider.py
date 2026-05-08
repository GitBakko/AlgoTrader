"""Unit tests for OllamaProvider.

All HTTP traffic is intercepted via httpx.MockTransport so the suite is
hermetic — no live GX10 dependency.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from src.llm_provider.base import LLMProviderError
from src.llm_provider.ollama_provider import OllamaProvider


def _mock_transport(handler):
    """Wrap a callable that returns httpx.Response into a transport."""
    return httpx.MockTransport(handler)


class _FakeOllama:
    """Records each request and returns scripted responses."""

    def __init__(self):
        self.requests: list[tuple[str, dict]] = []
        self.next_response: dict | None = None
        self.next_status: int = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        self.requests.append((path, body))
        if path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        if self.next_status != 200:
            return httpx.Response(self.next_status, text="server boom")
        return httpx.Response(200, json=self.next_response or {})


@pytest.fixture
def fake_ollama(monkeypatch):
    """Patch httpx.AsyncClient to route through MockTransport."""
    fake = _FakeOllama()
    transport = _mock_transport(fake.handler)
    real_init = httpx.AsyncClient.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)
    return fake


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_response_field(fake_ollama):
    fake_ollama.next_response = {"response": "hello world", "done": True}
    p = OllamaProvider()

    out = await p.generate("Hi", max_tokens=10)

    assert out == "hello world"
    path, body = fake_ollama.requests[-1]
    assert path == "/api/generate"
    assert body["model"] == "qwen3.6:35b"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["options"]["num_predict"] == 10
    assert body["keep_alive"] == -1  # default pin-forever


@pytest.mark.asyncio
async def test_generate_passes_system_and_json_mode(fake_ollama):
    fake_ollama.next_response = {"response": "{}"}
    p = OllamaProvider()

    await p.generate("Hi", system="You are a JSON robot", json_mode=True)

    body = fake_ollama.requests[-1][1]
    assert body["system"] == "You are a JSON robot"
    assert body["format"] == "json"


@pytest.mark.asyncio
async def test_generate_keep_alive_override(fake_ollama):
    fake_ollama.next_response = {"response": "ok"}
    p = OllamaProvider(keep_alive_generation=-1)

    await p.generate("Hi", keep_alive="30s")

    body = fake_ollama.requests[-1][1]
    assert body["keep_alive"] == "30s"


@pytest.mark.asyncio
async def test_generate_disable_thinking_off(fake_ollama):
    fake_ollama.next_response = {"response": "ok"}
    p = OllamaProvider(disable_thinking=False)

    await p.generate("Hi")

    body = fake_ollama.requests[-1][1]
    assert "think" not in body  # not injected when disable_thinking=False


@pytest.mark.asyncio
async def test_generate_http_error_raises_llm_provider_error(fake_ollama):
    fake_ollama.next_status = 500
    p = OllamaProvider()

    with pytest.raises(LLMProviderError, match="500"):
        await p.generate("Hi")


# ---------------------------------------------------------------------------
# analyze_image()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_image_base64_encodes_bytes(fake_ollama):
    fake_ollama.next_response = {"response": "{}"}
    p = OllamaProvider()
    img = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    await p.analyze_image("describe", img)

    body = fake_ollama.requests[-1][1]
    assert body["model"] == "qwen2.5vl:7b"
    expected_b64 = base64.b64encode(img).decode("ascii")
    assert body["images"] == [expected_b64]
    # Vision must NOT carry think param (qwen2.5vl rejects it).
    assert "think" not in body


@pytest.mark.asyncio
async def test_analyze_image_uses_vision_keep_alive_default(fake_ollama):
    fake_ollama.next_response = {"response": "{}"}
    p = OllamaProvider()
    img = b"x" * 32

    await p.analyze_image("p", img)

    body = fake_ollama.requests[-1][1]
    assert body["keep_alive"] == "1h"  # vision default


@pytest.mark.asyncio
async def test_analyze_image_empty_bytes_raises(fake_ollama):
    p = OllamaProvider()
    with pytest.raises(LLMProviderError, match="empty image_bytes"):
        await p.analyze_image("p", b"")


# ---------------------------------------------------------------------------
# embed()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_returns_vectors(fake_ollama):
    fake_ollama.next_response = {"embeddings": [[0.1, 0.2, 0.3]]}
    p = OllamaProvider()

    vecs = await p.embed(["hello"])

    assert vecs == [[0.1, 0.2, 0.3]]
    body = fake_ollama.requests[-1][1]
    assert body["model"] == "bge-m3:latest"
    assert body["input"] == ["hello"]


@pytest.mark.asyncio
async def test_embed_empty_input_short_circuits(fake_ollama):
    p = OllamaProvider()

    out = await p.embed([])

    assert out == []
    # No HTTP call made
    assert all(req[0] != "/api/embed" for req in fake_ollama.requests)


@pytest.mark.asyncio
async def test_embed_dimension_mismatch_raises(fake_ollama):
    fake_ollama.next_response = {"embeddings": [[0.1]]}  # only 1 vector for 2 inputs
    p = OllamaProvider()

    with pytest.raises(LLMProviderError, match="returned"):
        await p.embed(["a", "b"])


# ---------------------------------------------------------------------------
# health_check()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_reachable(fake_ollama):
    p = OllamaProvider()

    assert await p.health_check() is True


@pytest.mark.asyncio
async def test_health_check_unreachable_returns_false(monkeypatch):
    """A network error must NOT raise — health_check returns False."""

    def _boom(*args, **kwargs):
        raise httpx.ConnectError("no route")

    transport = httpx.MockTransport(_boom)
    real_init = httpx.AsyncClient.__init__

    def _patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)
    p = OllamaProvider()

    assert await p.health_check() is False


# ---------------------------------------------------------------------------
# embedding_dim
# ---------------------------------------------------------------------------


def test_embedding_dim_default():
    p = OllamaProvider()
    assert p.embedding_dim == 1024  # bge-m3 default


def test_embedding_dim_custom():
    p = OllamaProvider(embedding_dim=384)
    assert p.embedding_dim == 384
