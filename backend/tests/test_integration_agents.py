# MANTIS-EVOLUTION: Integration Tests — Full Pipeline
"""
End-to-end integration tests for the multi-agent + vision + DRL pipeline.
All external calls (LLM, broker) are mocked.

These tests verify the full pipeline produces a FinalDecision without errors
when all modules are wired together (vision + DRL + debate + agents).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.orchestrator import MantisAgentOrchestrator
from src.agents.schemas import (
    DebateArgument,
    DebateSummary,
    FinalDecision,
    MarketContext,
    RiskReport,
    SentimentReport,
    TechnicalReport,
)
from src.drl.schemas import DRLEnsembleSignal
from src.vision.schemas import VisionReport, VisionSignal


# ---------------------------------------------------------------------------
# Fixtures — shared mock data
# ---------------------------------------------------------------------------


@pytest.fixture
def market_context() -> MarketContext:
    return MarketContext(
        epic="XAUUSD",
        timeframe="15min",
        current_price=2050.0,
        atr=15.0,
        features={"ema_9": 2048.0, "ema_21": 2045.0, "rsi_14": 55.0, "adx_14": 30.0},
        regime="TRENDING",
        open_positions=1,
        equity=10000.0,
    )


@pytest.fixture
def tech_report() -> TechnicalReport:
    return TechnicalReport(
        symbol="XAUUSD",
        trend_direction="BULLISH",
        strength_score=0.75,
        key_support_levels=[2040.0, 2030.0],
        key_resistance_levels=[2060.0, 2080.0],
        active_patterns=["STRONG_TREND", "MACD_BULLISH"],
        timeframe_consensus={"15min": "BULLISH"},
        rationale="Strong bullish technical setup",
    )


@pytest.fixture
def sent_report() -> SentimentReport:
    return SentimentReport(
        composite_score=0.55,
        fear_greed_index=0.65,
        social_sentiment=0.6,
        news_sentiment=0.5,
        confidence=0.7,
        dominant_narrative="Risk-on sentiment across markets",
    )


@pytest.fixture
def risk_report() -> RiskReport:
    return RiskReport(
        risk_score=0.25,
        volatility_regime="LOW",
        max_position_size_pct=1.5,
        recommended_stop_loss_pct=1.0,
        liquidity_score=0.85,
        blocking=False,
        rationale="Low volatility — favorable conditions",
    )


@pytest.fixture
def vision_signal() -> VisionSignal:
    return VisionSignal(
        vision_report=VisionReport(
            trend_direction="BULLISH",
            key_patterns=["ascending_channel", "golden_cross"],
            support_levels=[2040.0],
            resistance_levels=[2065.0],
            volume_analysis="Volume confirming uptrend",
            momentum="BUILDING",
            visual_confidence=0.72,
            actionable_insight="Chart confirms bullish breakout setup",
        ),
        rag_context_summary="Historical context: XAUUSD bullish in similar regimes",
        chart_confidence=0.72,
    )


@pytest.fixture
def drl_signal() -> DRLEnsembleSignal:
    return DRLEnsembleSignal(
        action=1,  # BUY
        confidence=0.68,
        contributing_agents=["PPO", "SAC"],
        regime_match=True,
        voting_mode="REGIME_ROUTING",
        agent_votes={"PPO": 1, "SAC": 1, "A2C": 0},
    )


@pytest.fixture
def debate_summary() -> DebateSummary:
    return DebateSummary(
        bull_arguments=[
            DebateArgument(
                side="BULL",
                argument="Technical + vision + DRL all agree: BUY",
                confidence=0.78,
                evidence=["STRONG_TREND", "DRL BUY vote", "Chart bullish"],
            ),
        ],
        bear_arguments=[],
        consensus="BULLISH",
        consensus_confidence=0.78,
        key_disagreements=[],
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_orchestrator(**kwargs) -> MantisAgentOrchestrator:
    return MantisAgentOrchestrator(**kwargs)


# ---------------------------------------------------------------------------
# Test 1: Full pipeline — all features enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_all_enabled(
    market_context,
    tech_report,
    sent_report,
    risk_report,
    vision_signal,
    drl_signal,
    debate_summary,
):
    """
    Orchestrator with vision_enabled=True, drl_enabled=True, debate_enabled=True.
    Verify FinalDecision produced with audit trail containing entries for:
    technical, sentiment, risk, vision, drl, trader, debate.
    """
    orch = _make_orchestrator(vision_enabled=True, drl_enabled=True, debate_enabled=True)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech_report),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent_report),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk_report),
        patch.object(orch.vision_agent, "analyze", new_callable=AsyncMock, return_value=vision_signal),
        patch.object(orch.drl_agent, "analyze", new_callable=AsyncMock, return_value=drl_signal),
        patch.object(orch.debate, "debate", new_callable=AsyncMock, return_value=debate_summary),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)

    agent_names = {e.get("agent") for e in decision.agent_audit_trail}
    assert "technical" in agent_names
    assert "sentiment" in agent_names
    assert "risk" in agent_names
    assert "vision" in agent_names
    assert "drl" in agent_names
    assert "trader" in agent_names
    assert "debate" in agent_names


# ---------------------------------------------------------------------------
# Test 2: Full pipeline — vision only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_vision_only(
    market_context,
    tech_report,
    sent_report,
    risk_report,
    vision_signal,
):
    """
    vision_enabled=True, drl_enabled=False.
    Verify vision appears in audit trail but drl does not.
    """
    orch = _make_orchestrator(vision_enabled=True, drl_enabled=False, debate_enabled=False)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech_report),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent_report),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk_report),
        patch.object(orch.vision_agent, "analyze", new_callable=AsyncMock, return_value=vision_signal),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)

    agent_names = {e.get("agent") for e in decision.agent_audit_trail}
    assert "vision" in agent_names
    assert "drl" not in agent_names


# ---------------------------------------------------------------------------
# Test 3: Full pipeline — DRL only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_drl_only(
    market_context,
    tech_report,
    sent_report,
    risk_report,
    drl_signal,
):
    """
    drl_enabled=True, vision_enabled=False.
    Verify DRL appears in audit trail but vision does not.
    """
    orch = _make_orchestrator(vision_enabled=False, drl_enabled=True, debate_enabled=False)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech_report),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent_report),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk_report),
        patch.object(orch.drl_agent, "analyze", new_callable=AsyncMock, return_value=drl_signal),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)

    agent_names = {e.get("agent") for e in decision.agent_audit_trail}
    assert "drl" in agent_names
    assert "vision" not in agent_names


# ---------------------------------------------------------------------------
# Test 4: Full pipeline — nothing enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_nothing_enabled(
    market_context,
    tech_report,
    sent_report,
    risk_report,
):
    """
    vision_enabled=False, drl_enabled=False, debate_enabled=False.
    Verify basic pipeline still works: technical + sentiment + risk + trader.
    """
    orch = _make_orchestrator(vision_enabled=False, drl_enabled=False, debate_enabled=False)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech_report),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent_report),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk_report),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)

    agent_names = {e.get("agent") for e in decision.agent_audit_trail}
    assert "technical" in agent_names
    assert "sentiment" in agent_names
    assert "risk" in agent_names
    assert "trader" in agent_names
    assert "vision" not in agent_names
    assert "drl" not in agent_names
    assert "debate" not in agent_names


# ---------------------------------------------------------------------------
# Test 5: Market context enriched with vision + DRL data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_market_context_enriched(
    market_context,
    tech_report,
    sent_report,
    risk_report,
    vision_signal,
    drl_signal,
    debate_summary,
):
    """
    After running with vision + DRL enabled, verify:
    - context.vision_data is populated with trend, confidence, patterns, insight
    - context.drl_signal is populated with action, confidence, voting_mode, contributing_agents
    """
    orch = _make_orchestrator(vision_enabled=True, drl_enabled=True, debate_enabled=False)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech_report),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent_report),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk_report),
        patch.object(orch.vision_agent, "analyze", new_callable=AsyncMock, return_value=vision_signal),
        patch.object(orch.drl_agent, "analyze", new_callable=AsyncMock, return_value=drl_signal),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)

    # Vision data injected into context
    assert market_context.vision_data is not None
    assert "trend" in market_context.vision_data
    assert "confidence" in market_context.vision_data
    assert "patterns" in market_context.vision_data
    assert "insight" in market_context.vision_data
    assert market_context.vision_data["trend"] == "BULLISH"
    assert market_context.vision_data["confidence"] == pytest.approx(0.72)

    # DRL signal injected into context
    assert market_context.drl_signal is not None
    assert "action" in market_context.drl_signal
    assert "confidence" in market_context.drl_signal
    assert "voting_mode" in market_context.drl_signal
    assert "contributing_agents" in market_context.drl_signal
    assert market_context.drl_signal["action"] == 1  # BUY
    assert market_context.drl_signal["voting_mode"] == "REGIME_ROUTING"


# ---------------------------------------------------------------------------
# Test 6: Pipeline resilience — vision, DRL, and debate all throw
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_resilience(
    market_context,
    tech_report,
    sent_report,
    risk_report,
):
    """
    Vision throws, DRL throws, debate throws.
    Verify FinalDecision is still produced (HOLD or any action) — pipeline never crashes.
    Each failure is captured in the audit trail with status='error'.
    """
    orch = _make_orchestrator(vision_enabled=True, drl_enabled=True, debate_enabled=True)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech_report),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent_report),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk_report),
        patch.object(
            orch.vision_agent,
            "analyze",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Vision model unavailable"),
        ),
        patch.object(
            orch.drl_agent,
            "analyze",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DRL ensemble empty"),
        ),
        patch.object(
            orch.debate,
            "debate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Debate service down"),
        ),
    ):
        decision = await orch.run(market_context)

    # Pipeline must not crash — always returns a FinalDecision
    assert isinstance(decision, FinalDecision)

    # Vision error captured in audit trail
    vision_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "vision"]
    assert len(vision_entries) == 1
    assert vision_entries[0]["status"] == "error"
    assert "Vision model unavailable" in vision_entries[0]["error"]

    # DRL error captured in audit trail
    drl_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "drl"]
    assert len(drl_entries) == 1
    assert drl_entries[0]["status"] == "error"
    assert "DRL ensemble empty" in drl_entries[0]["error"]

    # Debate error captured in audit trail
    debate_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "debate"]
    assert len(debate_entries) == 1
    assert "error" in debate_entries[0]
    assert "Debate service down" in debate_entries[0]["error"]


# ---------------------------------------------------------------------------
# Test 7: Audit trail complete — all agents represented
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_trail_complete(
    market_context,
    tech_report,
    sent_report,
    risk_report,
    vision_signal,
    drl_signal,
    debate_summary,
):
    """
    With all features enabled and no failures, verify that the audit trail
    contains exactly one successful entry for each agent:
    technical, sentiment, risk, vision, drl, trader, debate.
    """
    orch = _make_orchestrator(vision_enabled=True, drl_enabled=True, debate_enabled=True)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=tech_report),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sent_report),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk_report),
        patch.object(orch.vision_agent, "analyze", new_callable=AsyncMock, return_value=vision_signal),
        patch.object(orch.drl_agent, "analyze", new_callable=AsyncMock, return_value=drl_signal),
        patch.object(orch.debate, "debate", new_callable=AsyncMock, return_value=debate_summary),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)
    trail = decision.agent_audit_trail
    assert len(trail) >= 7, f"Expected ≥7 audit entries, got {len(trail)}: {trail}"

    # Each required agent appears at least once.
    # Note: 'trader' and 'debate' may appear twice — once in the orchestrator trail
    # and once in the fund_manager's internal audit trail (both are merged).
    required_agents = ["technical", "sentiment", "risk", "vision", "drl", "trader", "debate"]
    agent_names = [e.get("agent") for e in trail]
    for agent in required_agents:
        count = agent_names.count(agent)
        assert count >= 1, f"Expected ≥1 entry for '{agent}', got {count}"

    # Single-occurrence agents (added only by orchestrator's _safe_analyze)
    for agent_name in ("technical", "sentiment", "risk", "vision", "drl"):
        count = agent_names.count(agent_name)
        assert count == 1, f"Expected exactly 1 entry for '{agent_name}', got {count}"

    # LLM-backed agents report success
    for agent_name in ("technical", "sentiment", "risk", "vision", "drl"):
        entry = next(e for e in trail if e.get("agent") == agent_name)
        assert entry.get("status") == "success", (
            f"Expected status='success' for '{agent_name}', got: {entry}"
        )
