# MANTIS-EVOLUTION: Vision Analyzer (Claude Vision API)
"""Analyzes trading charts using Claude's vision capabilities."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from loguru import logger

from src.vision.schemas import VisionReport

try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


VISION_SYSTEM_PROMPT = """You are an expert technical analyst specialized in crypto and forex trading.
Analyze the chart provided and produce a structured JSON report with these fields:
- trend_direction: "BULLISH" | "BEARISH" | "NEUTRAL" | "RANGING"
- key_patterns: list of chart patterns detected (e.g., "DOUBLE_BOTTOM", "HEAD_AND_SHOULDERS")
- support_levels: list of float price levels acting as support
- resistance_levels: list of float price levels acting as resistance
- volume_analysis: brief string ("INCREASING", "DECREASING", or description)
- momentum: "BUILDING" | "FADING" | "NEUTRAL"
- visual_confidence: float 0-1 (your confidence in the reading)
- actionable_insight: one-sentence trading insight

Respond ONLY with valid JSON. No additional text."""


class MantisVisionAnalyzer:
    """
    Analyzes chart PNG images using Claude Vision API.
    Falls back to a low-confidence default report on failure.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514", max_tokens: int = 1500):
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    async def analyze_chart(self, chart_bytes: bytes, additional_context: str = "") -> VisionReport:
        """
        Send chart to Claude Vision and parse VisionReport.
        Returns low-confidence default on any failure.
        """
        if not chart_bytes:
            return self._default_report("")

        chart_hash = hashlib.sha256(chart_bytes).hexdigest()[:16]

        try:
            client = self._get_client()
            b64_image = base64.b64encode(chart_bytes).decode("utf-8")

            user_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64_image,
                    },
                },
                {
                    "type": "text",
                    "text": additional_context or "Analyze this trading chart.",
                },
            ]

            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=VISION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )

            text = response.content[0].text
            # Strip markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]

            data = json.loads(text)
            report = VisionReport.model_validate(data)
            report.chart_hash = chart_hash
            return report

        except Exception as e:
            logger.warning(f"Vision analysis failed: {e!r}")
            return self._default_report(chart_hash)

    def _get_client(self):
        """Lazy-init anthropic async client."""
        if self._client is None:
            if not HAS_ANTHROPIC:
                raise RuntimeError("anthropic package required for vision analysis")
            self._client = anthropic.AsyncAnthropic()
        return self._client

    @staticmethod
    def _default_report(chart_hash: str) -> VisionReport:
        """Low-confidence fallback report."""
        return VisionReport(
            trend_direction="NEUTRAL",
            visual_confidence=0.1,
            actionable_insight="Vision analysis unavailable",
            chart_hash=chart_hash,
        )
