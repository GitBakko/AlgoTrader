# MANTIS-EVOLUTION: Vision Agent
"""
VisionAgent — orchestrates chart generation, vision analysis, and RAG context
building into a single VisionSignal for the multi-agent pipeline.

This agent is OPTIONAL and feature-flag gated (VISION_ENABLED).
When disabled or on failure, returns a low-confidence default signal.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger

from src.agents.schemas import MarketContext
from src.vision.schemas import ChartConfig, VisionReport, VisionSignal
from src.vision.chart_generator import MantisChartGenerator
from src.vision.vision_analyzer import MantisVisionAnalyzer
from src.rag.context_builder import MantisRAGContextBuilder
from src.rag.news_ingester import MantisNewsIngester


class VisionAgent:
    """
    Combines chart generation, Claude Vision analysis, and RAG context
    into a single VisionSignal.

    Parameters
    ----------
    vision_model : str
        Claude model for vision analysis.
    chart_config : ChartConfig | None
        Chart rendering configuration.
    rag_max_tokens : int
        Max tokens for RAG context string.
    news_lookback_hours : int
        Hours of news to include in RAG context.
    """

    def __init__(
        self,
        vision_model: str = "claude-sonnet-4-20250514",
        chart_config: ChartConfig | None = None,
        rag_max_tokens: int = 2000,
        news_lookback_hours: int = 4,
    ) -> None:
        self.chart_generator = MantisChartGenerator(config=chart_config)
        self.vision_analyzer = MantisVisionAnalyzer(model=vision_model)
        self.context_builder = MantisRAGContextBuilder(max_tokens=rag_max_tokens)
        self.news_ingester = MantisNewsIngester(lookback_hours=news_lookback_hours)

    async def analyze(self, context: MarketContext) -> VisionSignal:
        """
        Run the full vision + RAG pipeline:
        1. Generate chart from features
        2. Analyze chart with Claude Vision
        3. Build RAG context from news/SIL/memory
        4. Return combined VisionSignal

        Never raises — returns default signal on failure.
        """
        try:
            # Step 1: Generate chart
            chart_bytes = self._generate_chart(context)

            # Step 2: Vision analysis
            rag_text = self._build_rag_context(context)
            vision_report = await self.vision_analyzer.analyze_chart(
                chart_bytes,
                additional_context=f"Asset: {context.epic}, Regime: {context.regime or 'unknown'}\n{rag_text[:500]}",
            )

            # Step 3: Build full RAG context
            return VisionSignal(
                vision_report=vision_report,
                rag_context_summary=rag_text,
                chart_confidence=vision_report.visual_confidence,
            )

        except Exception as e:
            logger.warning(f"[{context.epic}] VisionAgent failed: {e!r}")
            return self._default_signal()

    def _generate_chart(self, context: MarketContext) -> bytes:
        """Generate chart PNG from market context features."""
        features = context.features or {}

        # Extract OHLC arrays if available
        opens = features.get("opens", [])
        highs = features.get("highs", [])
        lows = features.get("lows", [])
        closes = features.get("closes", [])
        volumes = features.get("volumes")

        if not closes:
            # Fallback: generate minimal chart from current price
            n = 50
            np.random.seed(hash(context.epic) % 2**31)
            noise = np.random.randn(n) * context.atr * 0.01
            closes = list(context.current_price + np.cumsum(noise))
            opens = [c - np.random.rand() * context.atr * 0.005 for c in closes]
            highs = [
                max(o, c) + abs(np.random.randn()) * context.atr * 0.003
                for o, c in zip(opens, closes)
            ]
            lows = [
                min(o, c) - abs(np.random.randn()) * context.atr * 0.003
                for o, c in zip(opens, closes)
            ]

        indicators = {}
        for key in ("ema_9", "ema_21", "bb_upper", "bb_lower", "rsi_14"):
            if key in features and isinstance(features[key], (list, np.ndarray)):
                indicators[key] = features[key]

        dates = list(range(len(closes)))

        return self.chart_generator.generate(
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            indicators=indicators,
            title=f"{context.epic} — {context.timeframe}",
        )

    def _build_rag_context(self, context: MarketContext) -> str:
        """Build RAG context string from available data."""
        # Process news from SIL data if available
        news_items = []
        sil = context.sil_data or {}
        raw_news = sil.get("news", [])
        if raw_news:
            news_items = self.news_ingester.ingest(raw_news, symbol=context.epic)

        rag = self.context_builder.build(
            news=news_items,
            sil_data=sil.get("macro"),
        )

        # Combine sections
        parts = []
        if rag.news_section:
            parts.append(rag.news_section)
        if rag.macro_section:
            parts.append(rag.macro_section)
        if rag.memory_section:
            parts.append(rag.memory_section)

        return "\n\n".join(parts)

    @staticmethod
    def _default_signal() -> VisionSignal:
        """Low-confidence fallback signal."""
        return VisionSignal(
            vision_report=VisionReport(
                trend_direction="NEUTRAL",
                visual_confidence=0.1,
                actionable_insight="Vision analysis unavailable",
            ),
            rag_context_summary="",
            chart_confidence=0.1,
        )
