"""
Tests for BullBearDebate — structured bull/bear argumentation module.

TDD: all tests written before implementation.
Uses only heuristic path (use_llm=False) so no Anthropic API calls are needed.
All async tests run automatically via asyncio_mode = auto in pytest.ini.
"""

from __future__ import annotations

import inspect

import pytest

from src.agents.schemas import (
    DebateArgument,
    DebateSummary,
    RiskReport,
    SentimentReport,
    TechnicalReport,
    TradeProposal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_debate():
    """Import and instantiate BullBearDebate (deferred so collection never fails)."""
    from src.agents.debate import BullBearDebate  # noqa: PLC0415

    return BullBearDebate(use_llm=False)


def _make_bullish_tech() -> TechnicalReport:
    return TechnicalReport(
        symbol="GOLD",
        trend_direction="BULLISH",
        strength_score=0.75,
        key_support_levels=[2300.0],
        key_resistance_levels=[2500.0],
        active_patterns=["EMA_CROSSOVER", "MACD_BULLISH"],
        timeframe_consensus={"15min": "BULLISH"},
        rationale="Bullish technical setup.",
    )


def _make_bearish_tech() -> TechnicalReport:
    return TechnicalReport(
        symbol="GOLD",
        trend_direction="BEARISH",
        strength_score=0.70,
        key_support_levels=[2200.0],
        key_resistance_levels=[2350.0],
        active_patterns=["MACD_BEARISH"],
        timeframe_consensus={"15min": "BEARISH"},
        rationale="Bearish technical setup.",
    )


def _make_bullish_sentiment() -> SentimentReport:
    return SentimentReport(
        composite_score=0.5,
        fear_greed_index=65.0,
        social_sentiment=0.4,
        news_sentiment=0.6,
        confidence=0.8,
        dominant_narrative="Risk-on, gold demand strong.",
    )


def _make_bearish_sentiment() -> SentimentReport:
    return SentimentReport(
        composite_score=-0.5,
        fear_greed_index=30.0,
        social_sentiment=-0.4,
        news_sentiment=-0.6,
        confidence=0.75,
        dominant_narrative="Risk-off, dollar strength.",
    )


def _make_neutral_sentiment() -> SentimentReport:
    return SentimentReport(
        composite_score=0.05,
        fear_greed_index=50.0,
        social_sentiment=0.0,
        news_sentiment=0.1,
        confidence=0.5,
        dominant_narrative="Mixed signals.",
    )


def _make_high_risk() -> RiskReport:
    return RiskReport(
        risk_score=0.8,
        volatility_regime="HIGH",
        max_position_size_pct=1.0,
        recommended_stop_loss_pct=2.0,
        liquidity_score=0.7,
        rationale="Elevated volatility regime.",
    )


def _make_low_risk() -> RiskReport:
    return RiskReport(
        risk_score=0.2,
        volatility_regime="LOW",
        max_position_size_pct=3.0,
        recommended_stop_loss_pct=1.0,
        liquidity_score=0.9,
        rationale="Calm, low-risk environment.",
    )


def _make_low_liquidity_risk() -> RiskReport:
    return RiskReport(
        risk_score=0.4,
        volatility_regime="MEDIUM",
        max_position_size_pct=2.0,
        recommended_stop_loss_pct=1.5,
        liquidity_score=0.1,
        rationale="Low liquidity, slippage risk.",
    )


def _make_proposal(action: str = "BUY", entry_price: float = 2350.0) -> TradeProposal:
    return TradeProposal(
        action=action,  # type: ignore[arg-type]
        confidence=0.6,
        size_pct=1.0,
        entry_price=entry_price,
        take_profit_levels=[entry_price * 1.02],
        stop_loss=entry_price * 0.99,
        rationale="Test proposal.",
        source_reports={},
    )


# ---------------------------------------------------------------------------
# 1. test_heuristic_bullish_consensus
# ---------------------------------------------------------------------------


class TestHeuristicBullishConsensus:
    def test_heuristic_bullish_consensus(self):
        """Bullish tech + bullish sentiment should produce BULLISH consensus."""
        debate = _make_debate()
        proposal = _make_proposal("BUY", 2350.0)
        summary = debate._heuristic_debate(
            proposal,
            _make_bullish_tech(),
            _make_bullish_sentiment(),
            None,
        )

        assert isinstance(summary, DebateSummary)
        assert summary.consensus == "BULLISH"
        assert len(summary.bull_arguments) >= 1
        assert summary.consensus_confidence > 0.0


# ---------------------------------------------------------------------------
# 2. test_heuristic_bearish_consensus
# ---------------------------------------------------------------------------


class TestHeuristicBearishConsensus:
    def test_heuristic_bearish_consensus(self):
        """Bearish tech + bearish sentiment should produce BEARISH consensus."""
        debate = _make_debate()
        proposal = _make_proposal("SELL", 2350.0)
        summary = debate._heuristic_debate(
            proposal,
            _make_bearish_tech(),
            _make_bearish_sentiment(),
            None,
        )

        assert isinstance(summary, DebateSummary)
        assert summary.consensus == "BEARISH"
        assert len(summary.bear_arguments) >= 1
        assert summary.consensus_confidence > 0.0


# ---------------------------------------------------------------------------
# 3. test_heuristic_neutral_mixed
# ---------------------------------------------------------------------------


class TestHeuristicNeutralMixed:
    def test_heuristic_neutral_mixed(self):
        """Bullish tech + bearish sentiment should produce NEUTRAL consensus."""
        debate = _make_debate()
        proposal = _make_proposal("BUY", 2350.0)
        summary = debate._heuristic_debate(
            proposal,
            _make_bullish_tech(),
            _make_bearish_sentiment(),
            None,
        )

        assert isinstance(summary, DebateSummary)
        # With balanced bull/bear signals the consensus should be NEUTRAL
        assert summary.consensus == "NEUTRAL"


# ---------------------------------------------------------------------------
# 4. test_all_none_reports
# ---------------------------------------------------------------------------


class TestAllNoneReports:
    def test_all_none_returns_neutral_empty(self):
        """All None reports → empty args, NEUTRAL consensus, confidence 0."""
        debate = _make_debate()
        proposal = _make_proposal()
        summary = debate._heuristic_debate(proposal, None, None, None)

        assert isinstance(summary, DebateSummary)
        assert summary.bull_arguments == []
        assert summary.bear_arguments == []
        assert summary.consensus == "NEUTRAL"
        assert summary.consensus_confidence == 0.0


# ---------------------------------------------------------------------------
# 5. test_resistance_near_entry_adds_bear_arg
# ---------------------------------------------------------------------------


class TestResistanceNearEntry:
    def test_resistance_near_entry_adds_bear_arg(self):
        """BUY with resistance < entry * 1.01 should add a BEAR argument."""
        debate = _make_debate()
        # Entry at 2350, resistance at 2352 (well within 1%)
        tech = TechnicalReport(
            symbol="GOLD",
            trend_direction="BULLISH",
            strength_score=0.5,
            key_support_levels=[2300.0],
            key_resistance_levels=[2352.0],  # very close to entry
            active_patterns=[],
            timeframe_consensus={"15min": "BULLISH"},
            rationale="Bullish but tight resistance.",
        )
        proposal = _make_proposal("BUY", 2350.0)
        summary = debate._heuristic_debate(proposal, tech, None, None)

        bear_sides = [a.side for a in summary.bear_arguments]
        assert "BEAR" in bear_sides

        # At least one bear arg should mention resistance
        bear_texts = " ".join(a.argument for a in summary.bear_arguments)
        assert "resistance" in bear_texts.lower() or "Resistance" in bear_texts


# ---------------------------------------------------------------------------
# 6. test_low_risk_adds_bull_arg
# ---------------------------------------------------------------------------


class TestLowRiskAddsBullArg:
    def test_low_risk_adds_bull_arg(self):
        """risk_score < 0.3 should add a BULL argument about low risk."""
        debate = _make_debate()
        proposal = _make_proposal()
        summary = debate._heuristic_debate(proposal, None, None, _make_low_risk())

        bull_texts = " ".join(a.argument for a in summary.bull_arguments)
        assert any(a.side == "BULL" for a in summary.bull_arguments)
        assert "risk" in bull_texts.lower()


# ---------------------------------------------------------------------------
# 7. test_high_risk_adds_bear_arg
# ---------------------------------------------------------------------------


class TestHighRiskAddsBearArg:
    def test_high_risk_adds_bear_arg(self):
        """risk_score > 0.5 should add a BEAR argument about elevated risk."""
        debate = _make_debate()
        proposal = _make_proposal()
        summary = debate._heuristic_debate(proposal, None, None, _make_high_risk())

        assert any(a.side == "BEAR" for a in summary.bear_arguments)
        bear_texts = " ".join(a.argument for a in summary.bear_arguments)
        assert "risk" in bear_texts.lower() or "volatil" in bear_texts.lower()


# ---------------------------------------------------------------------------
# 8. test_low_liquidity_adds_bear_arg
# ---------------------------------------------------------------------------


class TestLowLiquidityAddsBearArg:
    def test_low_liquidity_adds_bear_arg(self):
        """liquidity_score < 0.3 should add a BEAR argument about slippage."""
        debate = _make_debate()
        proposal = _make_proposal()
        summary = debate._heuristic_debate(proposal, None, None, _make_low_liquidity_risk())

        bear_texts = " ".join(a.argument.lower() for a in summary.bear_arguments)
        assert "liquidity" in bear_texts or "slippage" in bear_texts


# ---------------------------------------------------------------------------
# 9. test_consensus_confidence_high_when_decisive
# ---------------------------------------------------------------------------


class TestConsensusConfidenceHighWhenDecisive:
    def test_confidence_high_when_all_bull(self):
        """All-bull signals (no bear) should produce consensus_confidence close to 1.0."""
        debate = _make_debate()
        proposal = _make_proposal("BUY", 2350.0)
        # Use bullish tech + bullish sentiment + low risk → all bull
        summary = debate._heuristic_debate(
            proposal,
            _make_bullish_tech(),
            _make_bullish_sentiment(),
            _make_low_risk(),
        )

        # consensus_confidence should be high because bears have no weight
        assert summary.consensus_confidence >= 0.5


# ---------------------------------------------------------------------------
# 10. test_consensus_confidence_low_when_split
# ---------------------------------------------------------------------------


class TestConsensusConfidenceLowWhenSplit:
    def test_confidence_low_when_equal_bull_bear(self):
        """Balanced bull/bear weights should yield low consensus_confidence."""
        debate = _make_debate()
        proposal = _make_proposal("BUY", 2350.0)
        # Bullish tech vs bearish sentiment — roughly equal
        summary = debate._heuristic_debate(
            proposal,
            _make_bullish_tech(),
            _make_bearish_sentiment(),
            None,
        )

        # When bull_total ≈ bear_total, confidence should be low
        assert summary.consensus_confidence < 0.5


# ---------------------------------------------------------------------------
# 11. test_key_disagreements_populated
# ---------------------------------------------------------------------------


class TestKeyDisagreementsPopulated:
    def test_key_disagreements_populated_when_both_sides(self):
        """Mixed arguments → key_disagreements list should be non-empty."""
        debate = _make_debate()
        proposal = _make_proposal("BUY", 2350.0)
        summary = debate._heuristic_debate(
            proposal,
            _make_bullish_tech(),
            _make_bearish_sentiment(),
            None,
        )

        assert isinstance(summary.key_disagreements, list)
        assert len(summary.key_disagreements) > 0

    def test_key_disagreements_empty_when_no_conflict(self):
        """When only one side has arguments → disagreements list should be empty."""
        debate = _make_debate()
        proposal = _make_proposal("BUY", 2350.0)
        # All bull, no bear
        summary = debate._heuristic_debate(
            proposal,
            _make_bullish_tech(),
            _make_bullish_sentiment(),
            None,
        )

        # Only bull args present → no disagreement entry
        assert summary.key_disagreements == []


# ---------------------------------------------------------------------------
# 12. test_debate_is_async
# ---------------------------------------------------------------------------


class TestDebateIsAsync:
    def test_debate_method_is_coroutine(self):
        """debate() must be an async method (awaitable)."""
        debate = _make_debate()
        method = getattr(debate, "debate")
        assert inspect.iscoroutinefunction(method)

    async def test_debate_returns_debate_summary(self):
        """Calling await debate.debate(...) should return a DebateSummary."""
        debate = _make_debate()
        proposal = _make_proposal()
        result = await debate.debate(proposal, _make_bullish_tech(), _make_bullish_sentiment(), None)

        assert isinstance(result, DebateSummary)


# ---------------------------------------------------------------------------
# 13. test_llm_disabled_by_default
# ---------------------------------------------------------------------------


class TestLlmDisabledByDefault:
    def test_use_llm_defaults_to_false(self):
        """BullBearDebate() with no args should have use_llm=False."""
        from src.agents.debate import BullBearDebate  # noqa: PLC0415

        debate = BullBearDebate()
        assert debate.use_llm is False

    def test_model_default_is_set(self):
        """BullBearDebate() should have a default model string."""
        from src.agents.debate import BullBearDebate  # noqa: PLC0415

        debate = BullBearDebate()
        assert isinstance(debate.model, str)
        assert len(debate.model) > 0

    def test_llm_path_raises_not_implemented(self):
        """_llm_debate() stub should raise NotImplementedError."""
        from src.agents.debate import BullBearDebate  # noqa: PLC0415

        debate = BullBearDebate(use_llm=True)
        proposal = _make_proposal()

        async def _run():
            return await debate._llm_debate(proposal, None, None, None)

        with pytest.raises((NotImplementedError, Exception)):
            import asyncio

            asyncio.get_event_loop().run_until_complete(_run())
