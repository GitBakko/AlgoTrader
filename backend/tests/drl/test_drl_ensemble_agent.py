# MANTIS-EVOLUTION: DRL Ensemble Agent Tests
"""
Tests for MantisDRLEnsembleAgent and its orchestrator integration.

ALL tests use mocks — no real DRL training or model loading.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
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
from src.drl.schemas import DRLEnsembleSignal


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
        features={
            "rsi_14": 62.0,
            "adx_14": 38.0,
            "ema_9": 2048.0,
            "ema_21": 2045.0,
        },
        regime="TRENDING_UP",
        open_positions=2,
        equity=10000.0,
    )


@pytest.fixture
def context_no_regime() -> MarketContext:
    return MarketContext(
        epic="BTCUSD",
        timeframe="15min",
        current_price=65000.0,
        atr=500.0,
        features={
            "rsi_14": 55.0,
            "adx_14": 28.0,
            "ema_9": 64900.0,
            "ema_21": 64500.0,
        },
        regime=None,
        open_positions=1,
        equity=10000.0,
    )


@pytest.fixture
def mock_ensemble() -> MagicMock:
    ensemble = MagicMock()
    ensemble.predict.return_value = DRLEnsembleSignal(
        action=1,  # BUY
        confidence=0.75,
        contributing_agents=["ppo_agent"],
        voting_mode="REGIME_ROUTING",
    )
    return ensemble


@pytest.fixture
def mock_ensemble_low_confidence() -> MagicMock:
    ensemble = MagicMock()
    ensemble.predict.return_value = DRLEnsembleSignal(
        action=1,  # BUY originally, but confidence too low
        confidence=0.3,
        contributing_agents=[],
        voting_mode="REGIME_ROUTING",
    )
    return ensemble


@pytest.fixture
def mock_ensemble_high_confidence() -> MagicMock:
    ensemble = MagicMock()
    ensemble.predict.return_value = DRLEnsembleSignal(
        action=2,  # SELL
        confidence=0.85,
        contributing_agents=["sac_agent", "a2c_agent"],
        voting_mode="WEIGHTED_VOTE",
    )
    return ensemble


# ---------------------------------------------------------------------------
# MantisDRLEnsembleAgent unit tests
# ---------------------------------------------------------------------------


def test_analyze_returns_signal(market_context, mock_ensemble):
    """analyze() wrapping a mock ensemble returns a DRLEnsembleSignal."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    agent = MantisDRLEnsembleAgent(ensemble=mock_ensemble, confidence_threshold=0.6)

    import asyncio
    signal = asyncio.get_event_loop().run_until_complete(agent.analyze(market_context))

    assert isinstance(signal, DRLEnsembleSignal)
    assert signal.action == 1  # BUY passes confidence threshold
    assert signal.confidence == 0.75
    mock_ensemble.predict.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_confidence_threshold(context_no_regime, mock_ensemble_low_confidence):
    """Confidence below threshold forces HOLD (action=0)."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    agent = MantisDRLEnsembleAgent(
        ensemble=mock_ensemble_low_confidence, confidence_threshold=0.6
    )
    signal = await agent.analyze(context_no_regime)

    assert signal.action == 0  # forced HOLD
    assert signal.confidence == 0.3  # confidence unchanged


@pytest.mark.asyncio
async def test_analyze_high_confidence(market_context, mock_ensemble_high_confidence):
    """High confidence signal passes through unchanged."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    agent = MantisDRLEnsembleAgent(
        ensemble=mock_ensemble_high_confidence, confidence_threshold=0.6
    )
    signal = await agent.analyze(market_context)

    assert signal.action == 2  # SELL passes through
    assert signal.confidence == 0.85


@pytest.mark.asyncio
async def test_analyze_failure_returns_hold(market_context):
    """Exception during ensemble.predict returns a safe HOLD signal."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    broken_ensemble = MagicMock()
    broken_ensemble.predict.side_effect = RuntimeError("DRL exploded")

    agent = MantisDRLEnsembleAgent(ensemble=broken_ensemble, confidence_threshold=0.6)
    signal = await agent.analyze(market_context)

    assert isinstance(signal, DRLEnsembleSignal)
    assert signal.action == 0   # HOLD
    assert signal.confidence == 0.0


def test_build_observation_shape(market_context):
    """_build_observation returns a float32 numpy array with 6 elements."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    agent = MantisDRLEnsembleAgent(ensemble=MagicMock(), confidence_threshold=0.6)
    obs = agent._build_observation(market_context)

    assert isinstance(obs, np.ndarray)
    assert obs.dtype == np.float32
    assert obs.shape == (6,)
    # All values should be finite
    assert np.all(np.isfinite(obs))


def test_detect_regime_from_context(market_context):
    """If context.regime is set, it is returned directly without ADX/RSI logic."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    agent = MantisDRLEnsembleAgent(ensemble=MagicMock(), confidence_threshold=0.6)
    regime = agent._detect_regime(market_context)

    assert regime == "TRENDING_UP"  # taken directly from context.regime


def test_detect_regime_adx_trending(context_no_regime):
    """High ADX + high RSI (no context.regime) → TRENDING_UP."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    # Provide features that indicate trending up
    context_no_regime.features["adx_14"] = 40.0
    context_no_regime.features["rsi_14"] = 65.0

    agent = MantisDRLEnsembleAgent(ensemble=MagicMock(), confidence_threshold=0.6)
    regime = agent._detect_regime(context_no_regime)

    assert regime == "TRENDING_UP"


def test_detect_regime_ranging(context_no_regime):
    """Medium ADX (20-35) → RANGING."""
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    context_no_regime.features["adx_14"] = 25.0
    context_no_regime.features["rsi_14"] = 50.0

    agent = MantisDRLEnsembleAgent(ensemble=MagicMock(), confidence_threshold=0.6)
    regime = agent._detect_regime(context_no_regime)

    assert regime == "RANGING"


# ---------------------------------------------------------------------------
# Orchestrator integration tests
# ---------------------------------------------------------------------------


def _make_bullish_fixtures():
    """Helper: return minimal bullish mock reports."""
    technical = TechnicalReport(
        symbol="XAUUSD",
        trend_direction="BULLISH",
        strength_score=0.8,
        key_support_levels=[2040.0],
        key_resistance_levels=[2060.0],
        active_patterns=["STRONG_TREND"],
        timeframe_consensus={"15min": "BULLISH"},
        rationale="Mock",
    )
    sentiment = SentimentReport(
        composite_score=0.5,
        fear_greed_index=0.6,
        social_sentiment=0.5,
        news_sentiment=0.5,
        confidence=0.7,
        dominant_narrative="Mock bullish",
    )
    risk = RiskReport(
        risk_score=0.2,
        volatility_regime="LOW",
        max_position_size_pct=1.5,
        recommended_stop_loss_pct=1.0,
        liquidity_score=0.8,
        blocking=False,
        rationale="Low risk",
    )
    return technical, sentiment, risk


@pytest.mark.asyncio
async def test_orchestrator_drl_disabled(market_context):
    """drl_enabled=False → no DRL step, drl_agent is None."""
    from src.agents.orchestrator import MantisAgentOrchestrator

    orch = MantisAgentOrchestrator(drl_enabled=False)

    assert orch.drl_agent is None

    technical, sentiment, risk = _make_bullish_fixtures()
    debate = DebateSummary(
        bull_arguments=[],
        bear_arguments=[],
        consensus="BULLISH",
        consensus_confidence=0.7,
        key_disagreements=[],
    )

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=technical),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sentiment),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk),
        patch.object(orch.debate, "debate", new_callable=AsyncMock, return_value=debate),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)
    # No "drl" entry in audit trail
    drl_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "drl"]
    assert len(drl_entries) == 0


@pytest.mark.asyncio
async def test_orchestrator_drl_enabled(market_context):
    """drl_enabled=True → DRL step runs and appears in audit trail."""
    from src.agents.orchestrator import MantisAgentOrchestrator
    from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent

    orch = MantisAgentOrchestrator(drl_enabled=True)

    assert orch.drl_agent is not None
    assert isinstance(orch.drl_agent, MantisDRLEnsembleAgent)

    technical, sentiment, risk = _make_bullish_fixtures()
    debate = DebateSummary(
        bull_arguments=[],
        bear_arguments=[],
        consensus="BULLISH",
        consensus_confidence=0.7,
        key_disagreements=[],
    )
    drl_signal = DRLEnsembleSignal(action=1, confidence=0.75)

    with (
        patch.object(orch.technical, "analyze", new_callable=AsyncMock, return_value=technical),
        patch.object(orch.sentiment, "analyze", new_callable=AsyncMock, return_value=sentiment),
        patch.object(orch.risk, "analyze", new_callable=AsyncMock, return_value=risk),
        patch.object(orch.debate, "debate", new_callable=AsyncMock, return_value=debate),
        patch.object(
            orch.drl_agent, "analyze", new_callable=AsyncMock, return_value=drl_signal
        ),
    ):
        decision = await orch.run(market_context)

    assert isinstance(decision, FinalDecision)
    # DRL entry must appear in audit trail
    drl_entries = [e for e in decision.agent_audit_trail if e.get("agent") == "drl"]
    assert len(drl_entries) == 1
    assert drl_entries[0]["status"] == "success"
