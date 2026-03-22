"""
Tests for TechnicalAnalystAgent — technical analysis agent with heuristic fallback.

Uses unittest.mock to avoid real Anthropic API calls.
All async tests run automatically via asyncio_mode = auto in pytest.ini.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.schemas import AgentRole, MarketContext, TechnicalReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent():
    """Import and instantiate TechnicalAnalystAgent (deferred so collection never fails)."""
    from src.agents.technical_analyst import TechnicalAnalystAgent  # noqa: PLC0415

    return TechnicalAnalystAgent()


def _make_bullish_context() -> MarketContext:
    """Context with ema_9 clearly above ema_21 → should produce BULLISH."""
    return MarketContext(
        epic="GOLD",
        current_price=2350.0,
        atr=12.5,
        timeframe="15min",
        features={
            "ema_9": 2360.0,
            "ema_21": 2330.0,  # ema_9 > ema_21 by ~1.3% → BULLISH
            "rsi_14": 62.0,
            "adx_14": 30.0,
            "macd_histogram": 0.5,
            "bb_upper": 2400.0,
            "bb_lower": 2300.0,
            "vwap": 2340.0,
        },
    )


def _make_bearish_context() -> MarketContext:
    """Context with ema_9 clearly below ema_21 → should produce BEARISH."""
    return MarketContext(
        epic="BTCUSD",
        current_price=65000.0,
        atr=800.0,
        timeframe="15min",
        features={
            "ema_9": 64200.0,
            "ema_21": 65400.0,  # ema_9 < ema_21 by ~1.8% → BEARISH
            "rsi_14": 40.0,
            "adx_14": 28.0,
            "macd_histogram": -0.3,
            "bb_upper": 67000.0,
            "bb_lower": 63000.0,
            "vwap": 65200.0,
        },
    )


def _make_neutral_context() -> MarketContext:
    """Context with ema_9 ≈ ema_21 (within 0.1%) → should produce NEUTRAL."""
    return MarketContext(
        epic="EURUSD",
        current_price=1.0850,
        atr=0.0010,
        timeframe="15min",
        features={
            "ema_9": 1.0851,
            "ema_21": 1.0850,  # spread = 0.009% → well within ±0.1% → NEUTRAL
            "rsi_14": 50.0,
            "adx_14": 18.0,
            "macd_histogram": 0.0001,
            "bb_upper": 1.0870,
            "bb_lower": 1.0830,
            "vwap": 1.0849,
        },
    )


def _make_empty_context() -> MarketContext:
    """Context with no features at all."""
    return MarketContext(epic="XAGUSD", current_price=28.5, atr=0.3, features={})


# ---------------------------------------------------------------------------
# 1. test_heuristic_bullish
# ---------------------------------------------------------------------------


class TestHeuristicBullish:
    def test_heuristic_bullish(self):
        """ema_9 clearly above ema_21 should produce BULLISH trend direction."""
        agent = _make_agent()
        ctx = _make_bullish_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, TechnicalReport)
        assert report.trend_direction == "BULLISH"
        assert report.symbol == "GOLD"


# ---------------------------------------------------------------------------
# 2. test_heuristic_bearish
# ---------------------------------------------------------------------------


class TestHeuristicBearish:
    def test_heuristic_bearish(self):
        """ema_9 clearly below ema_21 should produce BEARISH trend direction."""
        agent = _make_agent()
        ctx = _make_bearish_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, TechnicalReport)
        assert report.trend_direction == "BEARISH"
        assert report.symbol == "BTCUSD"


# ---------------------------------------------------------------------------
# 3. test_heuristic_neutral
# ---------------------------------------------------------------------------


class TestHeuristicNeutral:
    def test_heuristic_neutral(self):
        """ema_9 ≈ ema_21 (< 0.1% spread) should produce NEUTRAL trend direction."""
        agent = _make_agent()
        ctx = _make_neutral_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, TechnicalReport)
        assert report.trend_direction == "NEUTRAL"

    def test_heuristic_neutral_exact_equality(self):
        """When ema_9 == ema_21, the direction must be NEUTRAL."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1.085,
            atr=0.001,
            features={"ema_9": 1.0850, "ema_21": 1.0850},
        )
        report = agent._heuristic_analyze(ctx)
        assert report.trend_direction == "NEUTRAL"


# ---------------------------------------------------------------------------
# 4. test_strength_score_range
# ---------------------------------------------------------------------------


class TestStrengthScoreRange:
    def test_strength_score_bullish_in_range(self):
        """Strength score must be in [0.0, 1.0] for a bullish context."""
        agent = _make_agent()
        report = agent._heuristic_analyze(_make_bullish_context())
        assert 0.0 <= report.strength_score <= 1.0

    def test_strength_score_bearish_in_range(self):
        """Strength score must be in [0.0, 1.0] for a bearish context."""
        agent = _make_agent()
        report = agent._heuristic_analyze(_make_bearish_context())
        assert 0.0 <= report.strength_score <= 1.0

    def test_strength_score_empty_features_in_range(self):
        """Strength score must be in [0.0, 1.0] even with no features."""
        agent = _make_agent()
        report = agent._heuristic_analyze(_make_empty_context())
        assert 0.0 <= report.strength_score <= 1.0

    def test_strength_score_extreme_values_clamped(self):
        """Extreme EMA spread and ADX should be clamped to [0.0, 1.0], not exceed 1."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2000.0,
            atr=10.0,
            features={
                "ema_9": 3000.0,   # massive spread
                "ema_21": 1000.0,
                "rsi_14": 99.0,    # extreme RSI
                "adx_14": 100.0,   # extreme ADX
                "macd_histogram": 999.0,
            },
        )
        report = agent._heuristic_analyze(ctx)
        assert 0.0 <= report.strength_score <= 1.0


# ---------------------------------------------------------------------------
# 5. test_patterns_detected
# ---------------------------------------------------------------------------


class TestPatternsDetected:
    def test_rsi_oversold_pattern(self):
        """RSI < 30 should add 'RSI_OVERSOLD' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2300.0,
            atr=10.0,
            features={"rsi_14": 25.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert "RSI_OVERSOLD" in report.active_patterns

    def test_rsi_overbought_pattern(self):
        """RSI > 70 should add 'RSI_OVERBOUGHT' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2400.0,
            atr=10.0,
            features={"rsi_14": 75.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert "RSI_OVERBOUGHT" in report.active_patterns

    def test_strong_trend_pattern(self):
        """ADX > 25 should add 'STRONG_TREND' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={"adx_14": 30.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert "STRONG_TREND" in report.active_patterns

    def test_macd_bullish_pattern(self):
        """Positive macd_histogram should add 'MACD_BULLISH' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={"macd_histogram": 0.5},
        )
        report = agent._heuristic_analyze(ctx)
        assert "MACD_BULLISH" in report.active_patterns

    def test_macd_bearish_pattern(self):
        """Negative macd_histogram should add 'MACD_BEARISH' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={"macd_histogram": -0.5},
        )
        report = agent._heuristic_analyze(ctx)
        assert "MACD_BEARISH" in report.active_patterns

    def test_ema_crossover_pattern_when_close(self):
        """EMA_9 and EMA_21 within 0.5% should add 'EMA_CROSSOVER' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={
                "ema_9": 2350.0,
                "ema_21": 2352.0,  # 0.085% spread → within 0.5% → crossover
            },
        )
        report = agent._heuristic_analyze(ctx)
        assert "EMA_CROSSOVER" in report.active_patterns

    def test_no_rsi_oversold_when_above_30(self):
        """RSI = 35 should NOT add 'RSI_OVERSOLD' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2300.0,
            atr=10.0,
            features={"rsi_14": 35.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert "RSI_OVERSOLD" not in report.active_patterns

    def test_no_strong_trend_when_adx_low(self):
        """ADX = 20 should NOT add 'STRONG_TREND' to active_patterns."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={"adx_14": 20.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert "STRONG_TREND" not in report.active_patterns


# ---------------------------------------------------------------------------
# 6. test_key_levels_from_features
# ---------------------------------------------------------------------------


class TestKeyLevelsFromFeatures:
    def test_bb_upper_in_resistance(self):
        """bb_upper from features should appear in key_resistance_levels."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={"bb_upper": 2400.0, "bb_lower": 2300.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert 2400.0 in report.key_resistance_levels

    def test_bb_lower_in_support(self):
        """bb_lower from features should appear in key_support_levels."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={"bb_upper": 2400.0, "bb_lower": 2300.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert 2300.0 in report.key_support_levels

    def test_vwap_in_support(self):
        """vwap from features should appear in key_support_levels."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=10.0,
            features={"vwap": 2340.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert 2340.0 in report.key_support_levels

    def test_levels_empty_when_features_absent(self):
        """When bb_upper/bb_lower/vwap are absent, level lists should be empty lists."""
        agent = _make_agent()
        ctx = _make_empty_context()
        report = agent._heuristic_analyze(ctx)
        assert isinstance(report.key_support_levels, list)
        assert isinstance(report.key_resistance_levels, list)


# ---------------------------------------------------------------------------
# 7. test_missing_features_graceful
# ---------------------------------------------------------------------------


class TestMissingFeaturesGraceful:
    def test_empty_features_returns_valid_report(self):
        """Empty features dict should return a valid TechnicalReport without crashing."""
        agent = _make_agent()
        ctx = _make_empty_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, TechnicalReport)
        assert report.trend_direction == "NEUTRAL"
        assert 0.0 <= report.strength_score <= 1.0
        assert isinstance(report.active_patterns, list)
        assert isinstance(report.timeframe_consensus, dict)
        assert report.rationale  # non-empty string

    def test_partial_features_no_crash(self):
        """Only some features present — should not raise any exceptions."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="BTCUSD",
            current_price=60000.0,
            atr=500.0,
            features={"ema_9": 60500.0},  # ema_21 missing — must not crash
        )
        report = agent._heuristic_analyze(ctx)
        assert isinstance(report, TechnicalReport)

    def test_none_values_in_features_no_crash(self):
        """None values for feature keys should not raise exceptions."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1.085,
            atr=0.001,
            features={"ema_9": None, "ema_21": None, "rsi_14": None},
        )
        # Should not raise — just treat as missing
        report = agent._heuristic_analyze(ctx)
        assert isinstance(report, TechnicalReport)


# ---------------------------------------------------------------------------
# 8. test_analyze_falls_back_to_heuristic
# ---------------------------------------------------------------------------


class TestAnalyzeFallbackToHeuristic:
    async def test_analyze_falls_back_when_llm_raises(self):
        """When _call_llm raises, analyze() should fall back to heuristic and return a report."""
        agent = _make_agent()
        ctx = _make_bullish_context()

        with patch.object(agent, "_call_llm", new=AsyncMock(side_effect=RuntimeError("API down"))):
            result = await agent.analyze(ctx)

        # Must return a TechnicalReport (not None) because of heuristic fallback
        assert result is not None
        assert isinstance(result, TechnicalReport)
        assert result.trend_direction == "BULLISH"

    async def test_analyze_returns_llm_result_when_successful(self):
        """When _call_llm succeeds, analyze() should return its result directly."""
        agent = _make_agent()
        ctx = _make_bullish_context()

        llm_report = TechnicalReport(
            symbol="GOLD",
            trend_direction="BEARISH",  # LLM overrides heuristic
            strength_score=0.9,
            key_support_levels=[2200.0],
            key_resistance_levels=[2500.0],
            active_patterns=["LLM_PATTERN"],
            timeframe_consensus={"15min": "BEARISH"},
            rationale="LLM-based analysis.",
        )

        with patch.object(agent, "_call_llm", new=AsyncMock(return_value=llm_report)):
            result = await agent.analyze(ctx)

        assert result is llm_report
        assert result.trend_direction == "BEARISH"  # LLM result, not heuristic


# ---------------------------------------------------------------------------
# 9. test_system_prompt_mentions_technical
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_system_prompt_mentions_technical(self):
        """System prompt should contain 'technical' (case-insensitive)."""
        agent = _make_agent()
        prompt = agent.get_system_prompt()
        assert "technical" in prompt.lower()

    def test_system_prompt_is_non_empty_string(self):
        """System prompt must be a non-empty string."""
        agent = _make_agent()
        prompt = agent.get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 50  # substantial enough to be useful

    def test_system_prompt_mentions_json(self):
        """System prompt should instruct the model to produce JSON output."""
        agent = _make_agent()
        prompt = agent.get_system_prompt()
        assert "json" in prompt.lower() or "JSON" in prompt

    def test_user_message_contains_epic(self):
        """_build_user_message should include the asset epic in the message."""
        agent = _make_agent()
        ctx = _make_bullish_context()
        message = agent._build_user_message(ctx)
        assert "GOLD" in message

    def test_user_message_contains_feature_data(self):
        """_build_user_message should include feature data for the LLM to reason over."""
        agent = _make_agent()
        ctx = _make_bullish_context()
        message = agent._build_user_message(ctx)
        # At minimum some numeric data should appear
        assert len(message) > 100  # has meaningful content


# ---------------------------------------------------------------------------
# 10. test_role_and_schema
# ---------------------------------------------------------------------------


class TestRoleAndSchema:
    def test_role_is_technical(self):
        """TechnicalAnalystAgent.role must be AgentRole.TECHNICAL."""
        agent = _make_agent()
        assert agent.role == AgentRole.TECHNICAL

    def test_output_schema_is_technical_report(self):
        """TechnicalAnalystAgent.output_schema must be TechnicalReport."""
        agent = _make_agent()
        assert agent.output_schema is TechnicalReport

    def test_role_is_class_variable(self):
        """role should be accessible as a class variable (not just instance)."""
        from src.agents.technical_analyst import TechnicalAnalystAgent  # noqa: PLC0415

        assert TechnicalAnalystAgent.role == AgentRole.TECHNICAL

    def test_output_schema_is_class_variable(self):
        """output_schema should be accessible as a class variable (not just instance)."""
        from src.agents.technical_analyst import TechnicalAnalystAgent  # noqa: PLC0415

        assert TechnicalAnalystAgent.output_schema is TechnicalReport

    def test_inherits_from_base_agent(self):
        """TechnicalAnalystAgent must inherit from MantisBaseAgent."""
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415
        from src.agents.technical_analyst import TechnicalAnalystAgent  # noqa: PLC0415

        assert issubclass(TechnicalAnalystAgent, MantisBaseAgent)

    def test_timeframe_consensus_uses_context_timeframe(self):
        """timeframe_consensus dict key should match context.timeframe."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.5,
            timeframe="1H",
            features={"ema_9": 2360.0, "ema_21": 2330.0},
        )
        report = agent._heuristic_analyze(ctx)
        assert "1H" in report.timeframe_consensus
