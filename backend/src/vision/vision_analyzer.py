# MANTIS-EVOLUTION: Vision Analyzer (provider-agnostic)
"""Analyze trading charts via the LLMProvider abstraction.

Phase 14a (2026-05-08): the legacy direct-Anthropic path was replaced
with `LLMProvider.analyze_image`. The default backend is Ollama on the
GX10 (qwen2.5vl:7b), so vision analysis runs locally with zero token
cost. Switching to a different backend (e.g. anthropic) is a single
env flip — see `src/llm_provider/factory.py`.

Failure mode contract: this module NEVER raises into the caller. Any
provider error or malformed response yields a low-confidence default
report so the strategy loop keeps running.
"""

from __future__ import annotations

import hashlib
import json

from loguru import logger

from src.llm_provider import LLMProviderError, get_llm_provider
from src.llm_provider.base import LLMProvider
from src.vision.schemas import VisionReport

VISION_SYSTEM_PROMPT = """You are an expert technical analyst specialized in crypto, forex, and stock trading.
Analyze the chart provided and produce a structured JSON report with these fields:
- trend_direction: "BULLISH" | "BEARISH" | "NEUTRAL" | "RANGING"
- key_patterns: list of chart patterns detected (e.g., "DOUBLE_BOTTOM", "HEAD_AND_SHOULDERS")
- support_levels: list of float price levels acting as support
- resistance_levels: list of float price levels acting as resistance
- volume_analysis: brief string ("INCREASING", "DECREASING", or description)
- momentum: "BUILDING" | "FADING" | "NEUTRAL"
- visual_confidence: float 0-1 (your confidence in the reading)
- actionable_insight: one-sentence trading insight

Respond ONLY with valid JSON. No additional text. No markdown fences."""


class MantisVisionAnalyzer:
    """Analyzes chart PNG images via the configured LLMProvider.

    The default provider is Ollama (qwen2.5vl:7b on GX10) — local, free,
    sub-2-second warm latency. Pluggable: pass a different provider in
    the constructor for tests or to override the global singleton.
    """

    def __init__(
        self,
        max_tokens: int = 1500,
        provider: LLMProvider | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self._provider = provider  # Lazy-resolve via get_llm_provider() if None

    async def analyze_chart(
        self, chart_bytes: bytes, additional_context: str = ""
    ) -> VisionReport:
        """Send chart to the configured vision provider and parse a VisionReport.

        Returns a low-confidence default report on any failure
        (provider error, malformed JSON, schema mismatch).
        """
        if not chart_bytes:
            return self._default_report("")

        chart_hash = hashlib.sha256(chart_bytes).hexdigest()[:16]

        try:
            provider = self._provider or get_llm_provider()
            user_prompt = additional_context or "Analyze this trading chart."
            text = await provider.analyze_image(
                user_prompt,
                chart_bytes,
                system=VISION_SYSTEM_PROMPT,
                max_tokens=self.max_tokens,
                temperature=0.0,
                json_mode=True,
            )

            # Strip markdown fences if the model added them despite the
            # system-prompt instructions (qwen2.5vl occasionally wraps
            # output in ```json ... ```).
            text = _strip_fences(text).strip()
            if not text:
                logger.warning("Vision analyzer returned empty response")
                return self._default_report(chart_hash)

            data = json.loads(text)
            report = VisionReport.model_validate(data)
            report.chart_hash = chart_hash
            return report

        except LLMProviderError as exc:
            logger.warning(f"Vision provider error: {exc!r}")
            return self._default_report(chart_hash)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(f"Vision analyzer parse error: {exc!r}")
            return self._default_report(chart_hash)
        except Exception as exc:  # noqa: BLE001 — defensive, must not crash trading loop
            logger.warning(f"Vision analysis failed: {exc!r}")
            return self._default_report(chart_hash)

    @staticmethod
    def _default_report(chart_hash: str) -> VisionReport:
        """Low-confidence fallback report."""
        return VisionReport(
            trend_direction="NEUTRAL",
            visual_confidence=0.1,
            actionable_insight="Vision analysis unavailable",
            chart_hash=chart_hash,
        )


def _strip_fences(text: str) -> str:
    """Remove a single set of markdown code fences if present.

    Handles ```json ... ```, ``` ... ```, and unfenced text alike.
    """
    s = text.strip()
    if not s.startswith("```"):
        return s
    # Drop the opening fence (and optional language tag) and the
    # trailing fence.
    body = s.split("\n", 1)[1] if "\n" in s else s[3:]
    body = body.rsplit("```", 1)[0]
    return body
