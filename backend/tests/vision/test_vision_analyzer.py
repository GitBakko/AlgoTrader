# MANTIS-EVOLUTION: Vision Analyzer Tests
"""
Tests for MantisVisionAnalyzer.

All tests mock the anthropic API (package is not installed).
"""
from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch out the anthropic import before importing the module under test
import sys
import types

# Create a minimal stub for the anthropic module so the import succeeds
_anthropic_stub = types.ModuleType("anthropic")
_anthropic_stub.AsyncAnthropic = MagicMock  # type: ignore[attr-defined]
sys.modules.setdefault("anthropic", _anthropic_stub)

from src.vision.vision_analyzer import MantisVisionAnalyzer, VISION_SYSTEM_PROMPT  # noqa: E402
from src.vision.schemas import VisionReport  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
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


def _make_analyzer_with_mock_client(response_text: str) -> tuple[MantisVisionAnalyzer, AsyncMock]:
    """Build an analyzer with a pre-configured mock client."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_text)]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    analyzer = MantisVisionAnalyzer()
    analyzer._client = mock_client
    return analyzer, mock_client


# ---------------------------------------------------------------------------
# Test 1: valid JSON response is parsed into VisionReport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chart_parses_response():
    """A valid JSON response from the API is parsed into a VisionReport."""
    analyzer, _ = _make_analyzer_with_mock_client(json.dumps(VALID_RESPONSE_PAYLOAD))

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert isinstance(report, VisionReport)
    assert report.trend_direction == "BULLISH"
    assert report.visual_confidence == 0.8
    assert report.momentum == "BUILDING"
    assert "DOUBLE_BOTTOM" in report.key_patterns


# ---------------------------------------------------------------------------
# Test 2: response wrapped in markdown fences is still parsed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chart_with_markdown_fences():
    """Responses wrapped in ```json ... ``` fences are stripped and parsed."""
    fenced = "```json\n" + json.dumps(VALID_RESPONSE_PAYLOAD) + "\n```"
    analyzer, _ = _make_analyzer_with_mock_client(fenced)

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.trend_direction == "BULLISH"
    assert report.visual_confidence == 0.8


# ---------------------------------------------------------------------------
# Test 3: empty bytes → default report with low confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chart_empty_bytes():
    """Empty chart bytes bypass the API and return a default low-confidence report."""
    analyzer = MantisVisionAnalyzer()

    report = await analyzer.analyze_chart(b"")

    assert isinstance(report, VisionReport)
    assert report.visual_confidence == 0.1
    assert report.trend_direction == "NEUTRAL"


# ---------------------------------------------------------------------------
# Test 4: API failure → default report returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chart_api_failure():
    """When the API raises an exception the default fallback report is returned."""
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=RuntimeError("network error"))

    analyzer = MantisVisionAnalyzer()
    analyzer._client = mock_client

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.visual_confidence == 0.1
    assert report.actionable_insight == "Vision analysis unavailable"


# ---------------------------------------------------------------------------
# Test 5: invalid JSON in response → default report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chart_invalid_json():
    """When the API returns non-JSON text the default report is returned."""
    analyzer, _ = _make_analyzer_with_mock_client("This is not JSON at all.")

    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.visual_confidence == 0.1
    assert report.trend_direction == "NEUTRAL"


# ---------------------------------------------------------------------------
# Test 6: chart_hash is set in returned report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chart_hash_set():
    """The chart_hash field in the returned report matches sha256[:16] of the input."""
    analyzer, _ = _make_analyzer_with_mock_client(json.dumps(VALID_RESPONSE_PAYLOAD))

    expected_hash = hashlib.sha256(CHART_BYTES).hexdigest()[:16]
    report = await analyzer.analyze_chart(CHART_BYTES)

    assert report.chart_hash == expected_hash


# ---------------------------------------------------------------------------
# Test 7: default report has visual_confidence == 0.1
# ---------------------------------------------------------------------------


def test_default_report_low_confidence():
    """_default_report returns a report with visual_confidence == 0.1."""
    report = MantisVisionAnalyzer._default_report("abc123")

    assert report.visual_confidence == 0.1


# ---------------------------------------------------------------------------
# Test 8: default report trend is NEUTRAL
# ---------------------------------------------------------------------------


def test_default_report_neutral():
    """_default_report returns a report with trend_direction == NEUTRAL."""
    report = MantisVisionAnalyzer._default_report("abc123")

    assert report.trend_direction == "NEUTRAL"


# ---------------------------------------------------------------------------
# Test 9: image is sent as correct base64 in the API call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_sent_as_base64():
    """The chart bytes are base64-encoded and sent in the image source block."""
    analyzer, mock_client = _make_analyzer_with_mock_client(json.dumps(VALID_RESPONSE_PAYLOAD))

    await analyzer.analyze_chart(CHART_BYTES)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    user_messages = call_kwargs["messages"]
    assert len(user_messages) == 1
    content_blocks = user_messages[0]["content"]

    image_block = next(b for b in content_blocks if b["type"] == "image")
    expected_b64 = base64.b64encode(CHART_BYTES).decode("utf-8")
    assert image_block["source"]["data"] == expected_b64
    assert image_block["source"]["media_type"] == "image/png"


# ---------------------------------------------------------------------------
# Test 10: VISION_SYSTEM_PROMPT is used in the API call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_prompt_used():
    """The VISION_SYSTEM_PROMPT constant is passed as the system parameter."""
    analyzer, mock_client = _make_analyzer_with_mock_client(json.dumps(VALID_RESPONSE_PAYLOAD))

    await analyzer.analyze_chart(CHART_BYTES)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == VISION_SYSTEM_PROMPT
