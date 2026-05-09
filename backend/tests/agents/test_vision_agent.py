# MANTIS-EVOLUTION: Vision Agent Tests
"""Tests for VisionAgent and orchestrator integration."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.schemas import MarketContext
from src.vision.schemas import VisionReport, VisionSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def market_context() -> MarketContext:
    return MarketContext(
        epic="XAUUSD",
        timeframe="15min",
        current_price=2050.0,
        atr=15.0,
        features={"ema_9": 2048.0, "rsi_14": 55.0},
        regime="TRENDING",
        open_positions=2,
        equity=10000.0,
    )


@pytest.fixture
def bullish_vision_report() -> VisionReport:
    return VisionReport(
        trend_direction="BULLISH",
        key_patterns=["STRONG_TREND"],
        support_levels=[2040.0],
        resistance_levels=[2060.0],
        volume_analysis="INCREASING",
        momentum="BUILDING",
        visual_confidence=0.8,
        actionable_insight="Strong bullish momentum detected",
        chart_hash="abc123",
    )


# ---------------------------------------------------------------------------
# VisionAgent unit tests
# ---------------------------------------------------------------------------


class TestVisionAgent:
    """Tests for VisionAgent in isolation."""

    @pytest.mark.asyncio
    async def test_analyze_returns_vision_signal(self, market_context, bullish_vision_report):
        """VisionAgent.analyze returns a VisionSignal."""
        from src.agents.vision_agent import VisionAgent

        agent = VisionAgent()
        # Mock the vision analyzer to return our report
        agent.vision_analyzer.analyze_chart = AsyncMock(return_value=bullish_vision_report)

        result = await agent.analyze(market_context)
        assert isinstance(result, VisionSignal)
        assert result.vision_report is not None
        assert result.vision_report.trend_direction == "BULLISH"
        assert result.chart_confidence == 0.8

    @pytest.mark.asyncio
    async def test_analyze_generates_chart(self, market_context, bullish_vision_report):
        """VisionAgent generates a chart and passes it to analyzer."""
        from src.agents.vision_agent import VisionAgent

        agent = VisionAgent()
        agent.vision_analyzer.analyze_chart = AsyncMock(return_value=bullish_vision_report)

        await agent.analyze(market_context)

        # Verify analyze_chart was called with bytes (the chart PNG)
        agent.vision_analyzer.analyze_chart.assert_called_once()
        call_args = agent.vision_analyzer.analyze_chart.call_args
        chart_bytes = call_args[0][0]
        assert isinstance(chart_bytes, bytes)
        assert len(chart_bytes) > 0

    @pytest.mark.asyncio
    async def test_analyze_includes_rag_context(self, market_context, bullish_vision_report):
        """VisionAgent builds RAG context from SIL data."""
        from src.agents.vision_agent import VisionAgent

        market_context.sil_data = {
            "news": [{"title": "Gold surges on Fed decision", "text": "Gold rallied today."}],
            "macro": {"VIX": 15.5, "DXY": 103.2},
        }

        agent = VisionAgent()
        agent.vision_analyzer.analyze_chart = AsyncMock(return_value=bullish_vision_report)

        result = await agent.analyze(market_context)
        assert result.rag_context_summary != ""

    @pytest.mark.asyncio
    async def test_analyze_failure_returns_default(self, market_context):
        """On failure, returns low-confidence default signal."""
        from src.agents.vision_agent import VisionAgent

        agent = VisionAgent()
        agent.vision_analyzer.analyze_chart = AsyncMock(side_effect=RuntimeError("API down"))

        result = await agent.analyze(market_context)
        assert isinstance(result, VisionSignal)
        assert result.chart_confidence == 0.1
        assert result.vision_report.trend_direction == "NEUTRAL"

    @pytest.mark.asyncio
    async def test_default_signal_structure(self):
        """Default signal has expected shape."""
        from src.agents.vision_agent import VisionAgent

        signal = VisionAgent._default_signal()
        assert signal.chart_confidence == 0.1
        assert signal.vision_report.visual_confidence == 0.1
        assert signal.vision_report.trend_direction == "NEUTRAL"
        assert signal.rag_context_summary == ""

    @pytest.mark.asyncio
    async def test_chart_from_synthetic_data(self, market_context, bullish_vision_report):
        """When no OHLC in features, generates synthetic chart data."""
        from src.agents.vision_agent import VisionAgent

        # No opens/highs/lows/closes in features -> synthetic
        agent = VisionAgent()
        agent.vision_analyzer.analyze_chart = AsyncMock(return_value=bullish_vision_report)

        result = await agent.analyze(market_context)
        assert isinstance(result, VisionSignal)
        # Chart was generated (analyzer was called)
        agent.vision_analyzer.analyze_chart.assert_called_once()


# ---------------------------------------------------------------------------
# Orchestrator integration tests
# ---------------------------------------------------------------------------


class TestOrchestratorVisionIntegration:
    """Tests for VisionAgent wired into the orchestrator."""

    @pytest.mark.asyncio
    async def test_vision_disabled_by_default(self, market_context):
        """vision_enabled=False (default) -> no vision step."""
        from src.agents.orchestrator import MantisAgentOrchestrator

        orch = MantisAgentOrchestrator()
        assert orch.vision_enabled is False
        assert orch.vision_agent is None

    @pytest.mark.asyncio
    async def test_vision_enabled_creates_agent(self):
        """vision_enabled=True -> VisionAgent is created."""
        from src.agents.orchestrator import MantisAgentOrchestrator

        orch = MantisAgentOrchestrator(vision_enabled=True)
        assert orch.vision_enabled is True
        assert orch.vision_agent is not None

    @pytest.mark.asyncio
    async def test_vision_step_in_pipeline(self, market_context, bullish_vision_report):
        """When vision enabled, vision step appears in audit trail."""
        from src.agents.orchestrator import MantisAgentOrchestrator
        from src.agents.schemas import (
            TechnicalReport, SentimentReport, RiskReport,
        )

        orch = MantisAgentOrchestrator(vision_enabled=True, debate_enabled=False)

        tech = TechnicalReport(
            symbol="XAUUSD", trend_direction="BULLISH", strength_score=0.8,
            key_support_levels=[2040.0], key_resistance_levels=[2060.0],
            active_patterns=["STRONG_TREND"], timeframe_consensus={"15min": "BULLISH"},
            rationale="Test",
        )
        sent = SentimentReport(
            composite_score=0.6, fear_greed_index=0.7, social_sentiment=0.65,
            news_sentiment=0.5, confidence=0.75, dominant_narrative="Bullish",
        )
        risk = RiskReport(
            risk_score=0.2, volatility_regime="LOW", max_position_size_pct=1.5,
            recommended_stop_loss_pct=1.1, liquidity_score=0.8, blocking=False,
            rationale="Low risk",
        )
        vision_signal = VisionSignal(
            vision_report=bullish_vision_report,
            rag_context_summary="Test RAG context",
            chart_confidence=0.8,
        )

        with (
            patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech),
            patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent),
            patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk),
            patch.object(orch.vision_agent, "analyze", new_callable=AsyncMock, return_value=vision_signal),
        ):
            decision = await orch.run(market_context)

        # Vision step should be in audit trail
        vision_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "vision"]
        assert len(vision_entries) == 1
        assert vision_entries[0]["status"] == "success"
        assert "BULLISH" in vision_entries[0]["summary"]

    @pytest.mark.asyncio
    async def test_vision_failure_continues_pipeline(self, market_context):
        """Vision failure doesn't crash the pipeline."""
        from src.agents.orchestrator import MantisAgentOrchestrator
        from src.agents.schemas import FinalDecision

        orch = MantisAgentOrchestrator(vision_enabled=True, debate_enabled=False)

        with (
            patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=None),
            patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=None),
            patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=None),
            patch.object(orch.vision_agent, "analyze", new_callable=AsyncMock, side_effect=RuntimeError("Vision crashed")),
        ):
            decision = await orch.run(market_context)

        assert isinstance(decision, FinalDecision)
        vision_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "vision"]
        assert len(vision_entries) == 1
        assert vision_entries[0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_vision_injects_context_data(self, market_context, bullish_vision_report):
        """Vision agent injects vision_data and rag_context into the
        orchestrator's pipeline copy (NOT the caller's MarketContext —
        post-C3 fix the orchestrator works on context.model_copy() so
        vision/DRL state never leaks back across tick boundaries)."""
        from src.agents.orchestrator import MantisAgentOrchestrator

        orch = MantisAgentOrchestrator(vision_enabled=True, debate_enabled=False)

        vision_signal = VisionSignal(
            vision_report=bullish_vision_report,
            rag_context_summary="Gold is rallying due to Fed",
            chart_confidence=0.8,
        )

        # Spy on the trader's propose() to inspect the enriched context the
        # orchestrator actually passed downstream. We assert on that copy.
        captured: dict = {}
        original_propose = orch.trader.propose

        def _capturing_propose(technical, sentiment, risk, ctx):
            captured["context"] = ctx
            return original_propose(technical, sentiment, risk, ctx)

        with (
            patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=None),
            patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=None),
            patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=None),
            patch.object(orch.vision_agent, "analyze", new_callable=AsyncMock, return_value=vision_signal),
            patch.object(orch.trader, "propose", side_effect=_capturing_propose),
        ):
            decision = await orch.run(market_context)

        # Caller's context MUST remain pristine (hub-schema immutability).
        assert market_context.vision_data is None
        assert market_context.rag_context is None
        # Orchestrator's pipeline copy received the vision enrichment.
        assert decision is not None
        enriched = captured["context"]
        assert enriched.vision_data is not None
        assert enriched.vision_data["trend"] == "BULLISH"
        assert enriched.vision_data["confidence"] == 0.8
        assert enriched.rag_context == "Gold is rallying due to Fed"
