# MANTIS-EVOLUTION: Agent Orchestrator Tests
"""
Tests for MantisAgentOrchestrator — the central multi-agent pipeline coordinator.

ALL tests use mocks — no real LLM/Claude API calls. Each agent's analyze() or
propose() method is patched with AsyncMock or MagicMock returning predefined reports.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.schemas import (
    DebateArgument,
    DebateSummary,
    FinalDecision,
    MarketContext,
    RiskReport,
    SentimentReport,
    TechnicalReport,
    TradeProposal,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable mock data
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
        open_positions=2,
        equity=10000.0,
    )


@pytest.fixture
def bullish_technical() -> TechnicalReport:
    return TechnicalReport(
        symbol="XAUUSD",
        trend_direction="BULLISH",
        strength_score=0.8,
        key_support_levels=[2040.0, 2035.0],
        key_resistance_levels=[2060.0, 2075.0],
        active_patterns=["STRONG_TREND", "MACD_BULLISH"],
        timeframe_consensus={"15min": "BULLISH"},
        rationale="Mock bullish technical report",
    )


@pytest.fixture
def bullish_sentiment() -> SentimentReport:
    return SentimentReport(
        composite_score=0.6,
        fear_greed_index=0.7,
        social_sentiment=0.65,
        news_sentiment=0.5,
        confidence=0.75,
        dominant_narrative="Predominantly bullish sentiment across sources",
    )


@pytest.fixture
def low_risk() -> RiskReport:
    return RiskReport(
        risk_score=0.2,
        volatility_regime="LOW",
        max_position_size_pct=1.5,
        recommended_stop_loss_pct=1.1,
        liquidity_score=0.8,
        blocking=False,
        rationale="Low risk environment",
    )


@pytest.fixture
def blocking_risk() -> RiskReport:
    return RiskReport(
        risk_score=0.9,
        volatility_regime="EXTREME",
        max_position_size_pct=0.0,
        recommended_stop_loss_pct=3.0,
        liquidity_score=0.3,
        blocking=True,
        rationale="Extreme volatility — all trades blocked",
    )


@pytest.fixture
def bullish_debate() -> DebateSummary:
    return DebateSummary(
        bull_arguments=[
            DebateArgument(
                side="BULL",
                argument="Technical trend is BULLISH with 80% strength",
                confidence=0.8,
                evidence=["Active patterns: STRONG_TREND, MACD_BULLISH"],
            ),
        ],
        bear_arguments=[],
        consensus="BULLISH",
        consensus_confidence=0.8,
        key_disagreements=[],
    )


@pytest.fixture
def bearish_debate() -> DebateSummary:
    return DebateSummary(
        bull_arguments=[],
        bear_arguments=[
            DebateArgument(
                side="BEAR",
                argument="Technical trend is BEARISH",
                confidence=0.7,
                evidence=[],
            ),
        ],
        consensus="BEARISH",
        consensus_confidence=0.7,
        key_disagreements=[],
    )


def _make_orchestrator(**kwargs):
    """Instantiate orchestrator with optional overrides."""
    from src.agents.orchestrator import MantisAgentOrchestrator

    return MantisAgentOrchestrator(**kwargs)


# ---------------------------------------------------------------------------
# Test 1: Full pipeline BUY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_buy(
    market_context, bullish_technical, bullish_sentiment, low_risk, bullish_debate
):
    """Mock all agents to produce bullish data -> FinalDecision.approved=True, action=BUY."""
    orch = _make_orchestrator()

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=bullish_technical
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=low_risk
        ),
        patch.object(
            orch.debate, "debate", new_callable=AsyncMock, return_value=bullish_debate
        ),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)
    assert decision.action == "BUY"
    assert decision.approved is True
    assert decision.confidence > 0.0


# ---------------------------------------------------------------------------
# Test 2: HOLD when risk blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_hold_when_risk_blocks(
    market_context, bullish_technical, bullish_sentiment, blocking_risk
):
    """Mock risk to return blocking=True -> HOLD, approved=False."""
    orch = _make_orchestrator()

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=bullish_technical
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=blocking_risk
        ),
    ):
        decision = await orch.run(market_context)

    assert decision.action == "HOLD"
    assert decision.approved is False


# ---------------------------------------------------------------------------
# Test 3: Debate opposition rejects BUY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debate_opposition_rejects(
    market_context, bullish_technical, bullish_sentiment, low_risk, bearish_debate
):
    """Mock debate to BEARISH consensus on BUY proposal -> approved=False."""
    orch = _make_orchestrator()

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=bullish_technical
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=low_risk
        ),
        patch.object(
            orch.debate, "debate", new_callable=AsyncMock, return_value=bearish_debate
        ),
    ):
        decision = await orch.run(market_context)

    assert decision.approved is False
    assert decision.override_reason is not None
    assert "BEARISH" in decision.override_reason


# ---------------------------------------------------------------------------
# Test 4: Agent failure continues pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_failure_continues(
    market_context, bullish_sentiment, low_risk, bullish_debate
):
    """Mock technical to raise Exception -> pipeline continues with sentiment+risk."""
    orch = _make_orchestrator()

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=low_risk
        ),
        patch.object(
            orch.debate, "debate", new_callable=AsyncMock, return_value=bullish_debate
        ),
    ):
        decision = await orch.run(market_context)

    # Pipeline should still produce a decision (not crash)
    assert isinstance(decision, FinalDecision)
    # Technical failed, so audit trail should reflect that
    technical_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "technical"]
    assert len(technical_entries) >= 1
    assert technical_entries[0]["status"] == "error"


# ---------------------------------------------------------------------------
# Test 5: All agents fail -> HOLD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_agents_fail_returns_hold(market_context):
    """All agents return None -> HOLD."""
    orch = _make_orchestrator()

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=None
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=None
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=None
        ),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)
    assert decision.action == "HOLD"


# ---------------------------------------------------------------------------
# Test 6: Audit trail always populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_trail_always_populated(
    market_context, bullish_technical, bullish_sentiment, low_risk
):
    """Every run produces non-empty audit trail."""
    orch = _make_orchestrator()

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=bullish_technical
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=low_risk
        ),
    ):
        decision = await orch.run(market_context)

    assert decision.agent_audit_trail is not None
    assert len(decision.agent_audit_trail) > 0


# ---------------------------------------------------------------------------
# Test 7: Audit trail has all agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_trail_has_all_agents(
    market_context, bullish_technical, bullish_sentiment, low_risk, bullish_debate
):
    """Audit trail contains entries for technical, sentiment, risk, trader."""
    orch = _make_orchestrator()

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=bullish_technical
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=low_risk
        ),
        patch.object(
            orch.debate, "debate", new_callable=AsyncMock, return_value=bullish_debate
        ),
    ):
        decision = await orch.run(market_context)

    agent_names = {e.get("agent") for e in decision.agent_audit_trail}
    assert "technical" in agent_names
    assert "sentiment" in agent_names
    assert "risk" in agent_names
    assert "trader" in agent_names


# ---------------------------------------------------------------------------
# Test 8: Debate disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debate_disabled(
    market_context, bullish_technical, bullish_sentiment, low_risk
):
    """debate_enabled=False -> no debate step, still produces decision."""
    orch = _make_orchestrator(debate_enabled=False)

    mock_debate = AsyncMock()
    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=bullish_technical
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=low_risk
        ),
        patch.object(orch.debate, "debate", mock_debate),
    ):
        decision = await orch.run(market_context)

    # Debate should NOT have been called
    mock_debate.assert_not_called()
    # Decision should still be produced
    assert isinstance(decision, FinalDecision)
    # No debate entry in audit trail
    debate_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "debate"]
    assert len(debate_entries) == 0


# ---------------------------------------------------------------------------
# Test 9: Debate failure continues pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debate_failure_continues(
    market_context, bullish_technical, bullish_sentiment, low_risk
):
    """Debate raises -> pipeline continues, decision still made."""
    orch = _make_orchestrator(debate_enabled=True)

    with (
        patch.object(
            orch.technical, "analyze", new_callable=AsyncMock, return_value=bullish_technical
        ),
        patch.object(
            orch.sentiment, "analyze", new_callable=AsyncMock, return_value=bullish_sentiment
        ),
        patch.object(
            orch.risk, "analyze", new_callable=AsyncMock, return_value=low_risk
        ),
        patch.object(
            orch.debate, "debate", new_callable=AsyncMock, side_effect=RuntimeError("Debate crash")
        ),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)
    # Audit trail should contain debate error entry
    debate_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "debate"]
    assert len(debate_entries) == 1
    assert "error" in debate_entries[0]


# ---------------------------------------------------------------------------
# Test 10: Custom weights passed to trader
# ---------------------------------------------------------------------------


def test_custom_weights_passed_to_trader():
    """Verify TraderAgent gets correct weights from orchestrator init."""
    orch = _make_orchestrator(
        technical_weight=0.5,
        sentiment_weight=0.3,
        risk_weight=0.2,
    )

    assert orch.trader.technical_weight == 0.5
    assert orch.trader.sentiment_weight == 0.3
    assert orch.trader.risk_weight == 0.2


# ---------------------------------------------------------------------------
# Test 11: Risk threshold configurable
# ---------------------------------------------------------------------------


def test_risk_threshold_configurable():
    """Custom risk_block_threshold passed to RiskManagerAgent."""
    orch = _make_orchestrator(risk_block_threshold=0.6)
    assert orch.risk.RISK_BLOCK_THRESHOLD == 0.6

    orch2 = _make_orchestrator(risk_block_threshold=0.95)
    assert orch2.risk.RISK_BLOCK_THRESHOLD == 0.95
