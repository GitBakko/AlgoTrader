# MANTIS-EVOLUTION: Vision Analyzer Tests (Phase 14a, provider-based)
"""Tests for MantisVisionAnalyzer.

Phase 14a (2026-05-08): the analyzer was refactored to call
LLMProvider.analyze_image() instead of the anthropic client directly.
Tests now inject a FakeProvider via the constructor — no live HTTP and
no global singleton mutation. Coverage of the failure modes is
preserved.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from src.llm_provider.base import LLMProvider, LLMProviderError
from src.vision.schemas import VisionReport
from src.vision.vision_analyzer import MantisVisionAnalyzer

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

VALID_RESPONSE_PAYLOAD = {
    "trend_direction": "BULLISH",
    "key_patterns": ["DOUBLE_BOTTOM"],
    "support_levels": [1800.0, 1780.0],
    "resistance_levels": [1850.0],
    "volume_analysis": "INCREASING",
    "momentum": "BUILDING",
    "visual_confidence": 0.8,
    "actionable_insight": "Price approaching key resistance; consider long on breakout.",
}

CHART_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG header + padding


class FakeProvider(LLMProvider):
    """In-memory LLMProvider double for tests.

    Stores the last call arguments so tests can assert on them, and
    returns a configurable response (string or exception).
    """

    def __init__(self, response: str | Exception):
        self._response = response
        self.last_image_bytes: bytes | None = None
        self.last_prompt: str | None = None
        self.last_system: str | None = None
        self.last_json_mode: bool | None = None

    async def generate(self, prompt, *, system=None, max_tokens=1500, temperature=0.0,
                       json_mode=False, keep_alive=None):  # noqa: D401
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def analyze_image(self, prompt, image_bytes, *, system=None, max_tokens=1500,
                            temperature=0.0, json_mode=False, keep_alive=None):
        self.last_image_bytes = image_bytes
        self.last_prompt = prompt
        self.last_system = system
        self.last_json_mode = json_mode
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def embed(self, texts):
        return [[0.0] * self.embedding_dim for _ in texts]

    async def health_check(self):
        return True

    @property
    def embedding_dim(self) -> int:
        return 1024


def _analyzer_with(response: str | Exception) -> tuple[MantisVisionAnalyzer, FakeProvider]:
    fake = FakeProvider(response)
    return MantisVisionAnalyzer(provider=fake), fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chart_parses_response():
    """Valid JSON response is parsed into a VisionReport."""
    analyzer, _ = _analyzer_with(json.dumps(VALID_RESPONSE_PAYLOAD))

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert isinstance(report, VisionReport)
    assert report.trend_direction == "BULLISH"
    assert report.visual_confidence == 0.8
    assert report.momentum == "BUILDING"
    assert "DOUBLE_BOTTOM" in report.key_patterns


@pytest.mark.asyncio
async def test_analyze_chart_with_markdown_fences():
    """Responses wrapped in ```json ... ``` fences are stripped and parsed."""
    fenced = "```json\n" + json.dumps(VALID_RESPONSE_PAYLOAD) + "\n```"
    analyzer, _ = _analyzer_with(fenced)

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.trend_direction == "BULLISH"
    assert report.visual_confidence == 0.8


@pytest.mark.asyncio
async def test_analyze_chart_empty_bytes():
    """Empty chart bytes bypass the provider and return a default low-confidence report."""
    analyzer, fake = _analyzer_with(json.dumps(VALID_RESPONSE_PAYLOAD))

    report = await analyzer.analyze_chart(b"")

    assert isinstance(report, VisionReport)
    assert report.visual_confidence == 0.1
    assert report.trend_direction == "NEUTRAL"
    # Provider was never called
    assert fake.last_image_bytes is None


@pytest.mark.asyncio
async def test_analyze_chart_provider_error():
    """Provider error → default fallback report (no exception leaks)."""
    analyzer, _ = _analyzer_with(LLMProviderError("network down"))

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.visual_confidence == 0.1
    assert report.actionable_insight == "Vision analysis unavailable"


@pytest.mark.asyncio
async def test_analyze_chart_unexpected_exception():
    """Non-LLMProviderError exceptions are also caught and fall back."""
    analyzer, _ = _analyzer_with(RuntimeError("ollama crashed"))

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.visual_confidence == 0.1


@pytest.mark.asyncio
async def test_analyze_chart_invalid_json():
    """Non-JSON response from provider → default report."""
    analyzer, _ = _analyzer_with("This is not JSON at all.")

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.visual_confidence == 0.1
    assert report.trend_direction == "NEUTRAL"


@pytest.mark.asyncio
async def test_analyze_chart_empty_response():
    """Empty string from provider → default report."""
    analyzer, _ = _analyzer_with("")

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.visual_confidence == 0.1


@pytest.mark.asyncio
async def test_analyze_chart_hash_set():
    """chart_hash field matches sha256[:16] of the input bytes."""
    analyzer, _ = _analyzer_with(json.dumps(VALID_RESPONSE_PAYLOAD))

    expected_hash = hashlib.sha256(CHART_BYTES).hexdigest()[:16]
    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.chart_hash == expected_hash


def test_default_report_low_confidence():
    """_default_report returns visual_confidence == 0.1."""
    report = MantisVisionAnalyzer._default_report("abc123")
    assert report.visual_confidence == 0.1


def test_default_report_neutral():
    """_default_report returns trend_direction == NEUTRAL."""
    report = MantisVisionAnalyzer._default_report("abc123")
    assert report.trend_direction == "NEUTRAL"


@pytest.mark.asyncio
async def test_provider_receives_raw_bytes():
    """The provider must receive the raw chart bytes (not pre-encoded)."""
    analyzer, fake = _analyzer_with(json.dumps(VALID_RESPONSE_PAYLOAD))

    await analyzer.analyze_chart(CHART_BYTES)

    assert fake.last_image_bytes == CHART_BYTES
    # The system prompt is the production constant — anchors visual
    # output schema. Check by looking at the FakeProvider capture.
    assert fake.last_system is not None
    assert "trend_direction" in fake.last_system
    # JSON mode hint must propagate so Ollama enforces format=json
    assert fake.last_json_mode is True


@pytest.mark.asyncio
async def test_default_context_prompt_when_none_provided():
    """Empty additional_context falls back to the default user prompt."""
    analyzer, fake = _analyzer_with(json.dumps(VALID_RESPONSE_PAYLOAD))

    await analyzer.analyze_chart(CHART_BYTES, additional_context="")

    assert fake.last_prompt == "Analyze this trading chart."


@pytest.mark.asyncio
async def test_custom_context_passed_through():
    """Caller-supplied context overrides the default user prompt."""
    analyzer, fake = _analyzer_with(json.dumps(VALID_RESPONSE_PAYLOAD))

    custom = "Focus on volume divergence around the 2025-06 lows."
    await analyzer.analyze_chart(CHART_BYTES, additional_context=custom)

    assert fake.last_prompt == custom
