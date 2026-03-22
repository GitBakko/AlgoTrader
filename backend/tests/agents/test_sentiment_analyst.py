"""
Tests for SentimentAnalystAgent — SIL sentiment aggregation agent with heuristic fallback.

Uses unittest.mock to avoid real Anthropic API calls.
All async tests run automatically via asyncio_mode = auto in pytest.ini.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.schemas import AgentRole, MarketContext, SentimentReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent():
    """Import and instantiate SentimentAnalystAgent (deferred so collection never fails)."""
    from src.agents.sentiment_analyst import SentimentAnalystAgent  # noqa: PLC0415

    return SentimentAnalystAgent()


def _make_bullish_sil_context() -> MarketContext:
    """Context where all SIL sources point bullish."""
    return MarketContext(
        epic="GOLD",
        current_price=2350.0,
        atr=12.5,
        sil_data={
            "sil_fear_greed_value": 0.85,       # 0-1, high = greedy = bullish
            "sil_alpha_sentiment_score": 0.70,   # -1 to 1, positive = bullish
            "sil_social_bullish_ratio": 0.80,    # 0-1, high = bullish
            "sil_cot_net_position_norm": 0.65,   # -1 to 1, positive = bullish
        },
    )


def _make_bearish_sil_context() -> MarketContext:
    """Context where all SIL sources point bearish."""
    return MarketContext(
        epic="BTCUSD",
        current_price=65000.0,
        atr=800.0,
        sil_data={
            "sil_fear_greed_value": 0.15,        # low = fearful = bearish
            "sil_alpha_sentiment_score": -0.60,  # negative = bearish
            "sil_social_bullish_ratio": 0.20,    # low = bearish
            "sil_cot_net_position_norm": -0.55,  # negative = bearish
        },
    )


def _make_mixed_sil_context() -> MarketContext:
    """Context where SIL sources are split: some bullish, some bearish."""
    return MarketContext(
        epic="EURUSD",
        current_price=1.085,
        atr=0.001,
        sil_data={
            "sil_fear_greed_value": 0.75,        # bullish
            "sil_alpha_sentiment_score": 0.60,   # bullish
            "sil_social_bullish_ratio": 0.25,    # bearish
            "sil_cot_net_position_norm": -0.50,  # bearish
        },
    )


# ---------------------------------------------------------------------------
# 1. test_heuristic_all_bullish
# ---------------------------------------------------------------------------


class TestHeuristicAllBullish:
    def test_heuristic_all_bullish(self):
        """All SIL sources positive → positive composite score, high confidence."""
        agent = _make_agent()
        ctx = _make_bullish_sil_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, SentimentReport)
        assert report.composite_score > 0.2, (
            f"Expected composite > 0.2 for all-bullish inputs, got {report.composite_score}"
        )
        assert report.confidence > 0.5, (
            f"Expected confidence > 0.5 for consistent bullish sources, got {report.confidence}"
        )


# ---------------------------------------------------------------------------
# 2. test_heuristic_all_bearish
# ---------------------------------------------------------------------------


class TestHeuristicAllBearish:
    def test_heuristic_all_bearish(self):
        """All SIL sources negative → negative composite score, high confidence."""
        agent = _make_agent()
        ctx = _make_bearish_sil_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, SentimentReport)
        assert report.composite_score < -0.2, (
            f"Expected composite < -0.2 for all-bearish inputs, got {report.composite_score}"
        )
        assert report.confidence > 0.5, (
            f"Expected confidence > 0.5 for consistent bearish sources, got {report.confidence}"
        )


# ---------------------------------------------------------------------------
# 3. test_heuristic_mixed_signals
# ---------------------------------------------------------------------------


class TestHeuristicMixedSignals:
    def test_heuristic_mixed_signals(self):
        """2 bullish vs 2 bearish sources → low confidence (split signals)."""
        agent = _make_agent()
        ctx = _make_mixed_sil_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, SentimentReport)
        assert report.confidence < 0.5, (
            f"Expected confidence < 0.5 for mixed signals, got {report.confidence}"
        )


# ---------------------------------------------------------------------------
# 4. test_heuristic_missing_sil_data
# ---------------------------------------------------------------------------


class TestHeuristicMissingSilData:
    def test_heuristic_missing_sil_data(self):
        """sil_data is None → returns neutral report with low confidence."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="XAUUSD",
            current_price=2350.0,
            atr=12.5,
            sil_data=None,
        )
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, SentimentReport)
        # All sources default to 0.5 for fear/greed and social, 0.0 for others
        # → composite ≈ 0.0, confidence = low (all near zero after normalization)
        assert -0.3 <= report.composite_score <= 0.3, (
            f"Expected near-neutral composite for None sil_data, got {report.composite_score}"
        )
        assert report.confidence <= 0.5, (
            f"Expected low confidence for no data, got {report.confidence}"
        )


# ---------------------------------------------------------------------------
# 5. test_heuristic_empty_sil_dict
# ---------------------------------------------------------------------------


class TestHeuristicEmptySilDict:
    def test_heuristic_empty_sil_dict(self):
        """sil_data is {} → all defaults used → neutral-ish result."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="BTCUSD",
            current_price=65000.0,
            atr=800.0,
            sil_data={},
        )
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, SentimentReport)
        # Defaults: fear_greed=0.5 (→ 0.0), alpha=0.0, social=0.5 (→ 0.0), cot=0.0
        # All normalise to 0.0 → composite == 0.0
        assert report.composite_score == 0.0, (
            f"Expected 0.0 composite for empty sil_data, got {report.composite_score}"
        )


# ---------------------------------------------------------------------------
# 6. test_fear_greed_normalization
# ---------------------------------------------------------------------------


class TestFearGreedNormalization:
    def test_fear_greed_high_value(self):
        """Fear&Greed = 0.8 → normalized to (0.8-0.5)*2 = +0.6 in composite."""
        agent = _make_agent()
        # Isolate: only fear_greed present, others at neutral
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.5,
            sil_data={
                "sil_fear_greed_value": 0.8,
                "sil_alpha_sentiment_score": 0.0,
                "sil_social_bullish_ratio": 0.5,  # normalises to 0.0
                "sil_cot_net_position_norm": 0.0,
            },
        )
        report = agent._heuristic_analyze(ctx)

        # fg_normalized = (0.8 - 0.5) * 2 = 0.6, weight=0.30
        # alpha=0.0 * 0.25 = 0.0
        # social=(0.5-0.5)*2=0.0 * 0.20 = 0.0
        # cot=0.0 * 0.25 = 0.0
        # composite = 0.6 * 0.30 = 0.18
        expected = round(0.6 * 0.30, 4)
        assert abs(report.composite_score - expected) < 1e-4, (
            f"Expected composite ≈ {expected}, got {report.composite_score}"
        )

    def test_fear_greed_low_value(self):
        """Fear&Greed = 0.2 → normalized to (0.2-0.5)*2 = -0.6."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.5,
            sil_data={
                "sil_fear_greed_value": 0.2,
                "sil_alpha_sentiment_score": 0.0,
                "sil_social_bullish_ratio": 0.5,
                "sil_cot_net_position_norm": 0.0,
            },
        )
        report = agent._heuristic_analyze(ctx)

        expected = round(-0.6 * 0.30, 4)
        assert abs(report.composite_score - expected) < 1e-4, (
            f"Expected composite ≈ {expected}, got {report.composite_score}"
        )


# ---------------------------------------------------------------------------
# 7. test_composite_clamped
# ---------------------------------------------------------------------------


class TestCompositeClamped:
    def test_composite_clamped_positive(self):
        """Extreme positive values should be clamped to 1.0 max."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.5,
            sil_data={
                "sil_fear_greed_value": 1.0,          # max bullish
                "sil_alpha_sentiment_score": 1.0,     # max bullish
                "sil_social_bullish_ratio": 1.0,      # max bullish
                "sil_cot_net_position_norm": 1.0,     # max bullish
            },
        )
        report = agent._heuristic_analyze(ctx)
        assert report.composite_score <= 1.0
        assert report.composite_score >= 0.8  # should be near max

    def test_composite_clamped_negative(self):
        """Extreme negative values should be clamped to -1.0 min."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="BTCUSD",
            current_price=65000.0,
            atr=800.0,
            sil_data={
                "sil_fear_greed_value": 0.0,           # max bearish
                "sil_alpha_sentiment_score": -1.0,     # max bearish
                "sil_social_bullish_ratio": 0.0,       # max bearish
                "sil_cot_net_position_norm": -1.0,     # max bearish
            },
        )
        report = agent._heuristic_analyze(ctx)
        assert report.composite_score >= -1.0
        assert report.composite_score <= -0.8  # should be near min

    def test_composite_always_in_range(self):
        """composite_score must always be within [-1.0, 1.0]."""
        agent = _make_agent()
        for fg, alpha, social, cot in [
            (1.0, 1.0, 1.0, 1.0),
            (0.0, -1.0, 0.0, -1.0),
            (0.5, 0.0, 0.5, 0.0),
            (0.99, 0.99, 0.99, 0.99),
        ]:
            ctx = MarketContext(
                epic="GOLD",
                current_price=2350.0,
                atr=12.5,
                sil_data={
                    "sil_fear_greed_value": fg,
                    "sil_alpha_sentiment_score": alpha,
                    "sil_social_bullish_ratio": social,
                    "sil_cot_net_position_norm": cot,
                },
            )
            report = agent._heuristic_analyze(ctx)
            assert -1.0 <= report.composite_score <= 1.0


# ---------------------------------------------------------------------------
# 8. test_confidence_all_agree
# ---------------------------------------------------------------------------


class TestConfidenceAllAgree:
    def test_confidence_all_same_sign_bullish(self):
        """All 4 sources bullish → high confidence (> 0.7)."""
        agent = _make_agent()
        ctx = _make_bullish_sil_context()
        report = agent._heuristic_analyze(ctx)
        assert report.confidence > 0.7, (
            f"Expected confidence > 0.7 for all-bullish, got {report.confidence}"
        )

    def test_confidence_all_same_sign_bearish(self):
        """All 4 sources bearish → high confidence (> 0.7)."""
        agent = _make_agent()
        ctx = _make_bearish_sil_context()
        report = agent._heuristic_analyze(ctx)
        assert report.confidence > 0.7, (
            f"Expected confidence > 0.7 for all-bearish, got {report.confidence}"
        )


# ---------------------------------------------------------------------------
# 9. test_confidence_disagree
# ---------------------------------------------------------------------------


class TestConfidenceDisagree:
    def test_confidence_two_vs_two(self):
        """2 bullish + 2 bearish sources → low confidence (< 0.5)."""
        agent = _make_agent()
        ctx = _make_mixed_sil_context()
        report = agent._heuristic_analyze(ctx)
        assert report.confidence < 0.5, (
            f"Expected confidence < 0.5 for 2-vs-2 split, got {report.confidence}"
        )

    def test_confidence_three_vs_one(self):
        """3 bullish + 1 bearish → moderate confidence between 0.4 and 0.8."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1.085,
            atr=0.001,
            sil_data={
                "sil_fear_greed_value": 0.75,        # bullish
                "sil_alpha_sentiment_score": 0.50,   # bullish
                "sil_social_bullish_ratio": 0.70,    # bullish
                "sil_cot_net_position_norm": -0.40,  # bearish
            },
        )
        report = agent._heuristic_analyze(ctx)
        # 3 of 4 agree (0.75 agreement) → confidence = 0.75 * 0.8 + 0.2 = 0.8
        assert report.confidence >= 0.4, (
            f"Expected confidence >= 0.4 for 3-vs-1, got {report.confidence}"
        )


# ---------------------------------------------------------------------------
# 10. test_dominant_narrative_bullish
# ---------------------------------------------------------------------------


class TestDominantNarrativeBullish:
    def test_dominant_narrative_bullish_when_composite_high(self):
        """composite > 0.2 → 'bullish' should appear in dominant_narrative."""
        agent = _make_agent()
        ctx = _make_bullish_sil_context()
        report = agent._heuristic_analyze(ctx)

        assert report.composite_score > 0.2
        assert "bullish" in report.dominant_narrative.lower(), (
            f"Expected 'bullish' in narrative, got: '{report.dominant_narrative}'"
        )


# ---------------------------------------------------------------------------
# 11. test_dominant_narrative_bearish
# ---------------------------------------------------------------------------


class TestDominantNarrativeBearish:
    def test_dominant_narrative_bearish_when_composite_low(self):
        """composite < -0.2 → 'bearish' should appear in dominant_narrative."""
        agent = _make_agent()
        ctx = _make_bearish_sil_context()
        report = agent._heuristic_analyze(ctx)

        assert report.composite_score < -0.2
        assert "bearish" in report.dominant_narrative.lower(), (
            f"Expected 'bearish' in narrative, got: '{report.dominant_narrative}'"
        )

    def test_dominant_narrative_neutral_when_composite_near_zero(self):
        """composite in (-0.2, 0.2) → 'mixed' or 'neutral' in dominant_narrative."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1.085,
            atr=0.001,
            sil_data={},  # all defaults → composite = 0.0
        )
        report = agent._heuristic_analyze(ctx)

        assert -0.2 <= report.composite_score <= 0.2
        narrative_lower = report.dominant_narrative.lower()
        assert "mixed" in narrative_lower or "neutral" in narrative_lower, (
            f"Expected 'mixed' or 'neutral' in narrative, got: '{report.dominant_narrative}'"
        )


# ---------------------------------------------------------------------------
# 12. test_analyze_falls_back_to_heuristic
# ---------------------------------------------------------------------------


class TestAnalyzeFallsBackToHeuristic:
    async def test_analyze_falls_back_when_llm_raises(self):
        """When _call_llm raises, analyze() should fall back to heuristic and return a report."""
        agent = _make_agent()
        ctx = _make_bullish_sil_context()

        with patch.object(agent, "_call_llm", new=AsyncMock(side_effect=RuntimeError("API down"))):
            result = await agent.analyze(ctx)

        # Must return a SentimentReport (not None) because of heuristic fallback
        assert result is not None
        assert isinstance(result, SentimentReport)
        assert result.composite_score > 0.0  # all-bullish context

    async def test_analyze_returns_llm_result_when_successful(self):
        """When _call_llm succeeds, analyze() should return its result directly."""
        agent = _make_agent()
        ctx = _make_bullish_sil_context()

        llm_report = SentimentReport(
            composite_score=-0.5,  # LLM overrides heuristic
            fear_greed_index=0.3,
            social_sentiment=0.4,
            news_sentiment=-0.6,
            confidence=0.85,
            dominant_narrative="LLM analysis: mostly bearish",
        )

        with patch.object(agent, "_call_llm", new=AsyncMock(return_value=llm_report)):
            result = await agent.analyze(ctx)

        assert result is llm_report
        assert result.composite_score == -0.5  # LLM result, not heuristic

    async def test_analyze_falls_back_when_llm_import_error(self):
        """When anthropic package not installed, should fall back to heuristic."""
        agent = _make_agent()
        ctx = _make_bearish_sil_context()

        with patch.object(
            agent,
            "_call_llm",
            new=AsyncMock(side_effect=ImportError("No module named 'anthropic'")),
        ):
            result = await agent.analyze(ctx)

        assert result is not None
        assert isinstance(result, SentimentReport)
        assert result.composite_score < 0.0  # all-bearish context


# ---------------------------------------------------------------------------
# 13. test_role_and_schema
# ---------------------------------------------------------------------------


class TestRoleAndSchema:
    def test_role_is_sentiment(self):
        """SentimentAnalystAgent.role must be AgentRole.SENTIMENT."""
        agent = _make_agent()
        assert agent.role == AgentRole.SENTIMENT

    def test_output_schema_is_sentiment_report(self):
        """SentimentAnalystAgent.output_schema must be SentimentReport."""
        agent = _make_agent()
        assert agent.output_schema is SentimentReport

    def test_role_is_class_variable(self):
        """role should be accessible as a class variable (not just instance)."""
        from src.agents.sentiment_analyst import SentimentAnalystAgent  # noqa: PLC0415

        assert SentimentAnalystAgent.role == AgentRole.SENTIMENT

    def test_output_schema_is_class_variable(self):
        """output_schema should be accessible as a class variable (not just instance)."""
        from src.agents.sentiment_analyst import SentimentAnalystAgent  # noqa: PLC0415

        assert SentimentAnalystAgent.output_schema is SentimentReport

    def test_inherits_from_base_agent(self):
        """SentimentAnalystAgent must inherit from MantisBaseAgent."""
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415
        from src.agents.sentiment_analyst import SentimentAnalystAgent  # noqa: PLC0415

        assert issubclass(SentimentAnalystAgent, MantisBaseAgent)


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------


class TestSilDataPassthrough:
    def test_fear_greed_stored_as_raw(self):
        """fear_greed_index in report should be the raw 0-1 value, not normalised."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.5,
            sil_data={"sil_fear_greed_value": 0.72},
        )
        report = agent._heuristic_analyze(ctx)
        assert report.fear_greed_index == 0.72

    def test_social_sentiment_stored_as_raw(self):
        """social_sentiment in report should be the raw 0-1 value."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.5,
            sil_data={"sil_social_bullish_ratio": 0.65},
        )
        report = agent._heuristic_analyze(ctx)
        assert report.social_sentiment == 0.65

    def test_news_sentiment_stored_as_raw(self):
        """news_sentiment in report should be the raw -1 to 1 alpha value."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.5,
            sil_data={"sil_alpha_sentiment_score": -0.33},
        )
        report = agent._heuristic_analyze(ctx)
        assert report.news_sentiment == -0.33

    def test_report_fields_in_valid_ranges(self):
        """All numeric fields must be within their Pydantic schema bounds."""
        agent = _make_agent()
        ctx = _make_bullish_sil_context()
        report = agent._heuristic_analyze(ctx)

        assert -1.0 <= report.composite_score <= 1.0
        assert 0.0 <= report.confidence <= 1.0
        assert isinstance(report.dominant_narrative, str)
        assert len(report.dominant_narrative) > 0
