"""
Tests for RiskManagerAgent — risk assessment agent with veto power.

Uses unittest.mock to avoid real Anthropic API calls.
All async tests run automatically via asyncio_mode = auto in pytest.ini.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.schemas import AgentRole, MarketContext, RiskReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent():
    """Import and instantiate RiskManagerAgent (deferred so collection never fails)."""
    from src.agents.risk_manager_agent import RiskManagerAgent  # noqa: PLC0415

    return RiskManagerAgent()


def _make_normal_context() -> MarketContext:
    """Low-risk context: normal ATR, RSI near 50, 1 open position, healthy ADX."""
    return MarketContext(
        epic="GOLD",
        current_price=2350.0,
        atr=11.75,  # ATR% ≈ 0.5% → LOW/MEDIUM boundary
        timeframe="15min",
        features={
            "rsi_14": 52.0,
            "adx_14": 30.0,
            "volume": 1200.0,
            "volume_sma": 1000.0,
        },
        open_positions=1,
        equity=10000.0,
    )


def _make_extreme_context() -> MarketContext:
    """High-risk context: extreme ATR, many positions, extreme RSI, low ADX."""
    return MarketContext(
        epic="BTCUSD",
        current_price=65000.0,
        atr=5200.0,  # ATR% = 8% → EXTREME vol
        timeframe="15min",
        features={
            "rsi_14": 92.0,  # very overbought → high rsi_risk
            "adx_14": 10.0,  # very low ADX → high adx_risk
            "volume": 500.0,
            "volume_sma": 1000.0,
        },
        open_positions=9,  # near-max exposure → high pos_risk
        equity=10000.0,
    )


def _make_empty_context() -> MarketContext:
    """Context with no features at all."""
    return MarketContext(
        epic="XAGUSD",
        current_price=28.5,
        atr=0.3,
        features={},
        open_positions=0,
        equity=0.0,
    )


# ---------------------------------------------------------------------------
# 1. test_heuristic_low_risk
# ---------------------------------------------------------------------------


class TestHeuristicLowRisk:
    def test_heuristic_low_risk(self):
        """Normal market conditions should produce risk_score < 0.5 and blocking=False."""
        agent = _make_agent()
        ctx = _make_normal_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, RiskReport)
        assert report.risk_score < 0.5
        assert report.blocking is False

    def test_heuristic_low_risk_max_size_positive(self):
        """Low risk should allow a positive max_position_size_pct."""
        agent = _make_agent()
        report = agent._heuristic_analyze(_make_normal_context())
        assert report.max_position_size_pct > 0.0


# ---------------------------------------------------------------------------
# 2. test_heuristic_high_risk_blocks
# ---------------------------------------------------------------------------


class TestHeuristicHighRiskBlocks:
    def test_heuristic_high_risk_blocks(self):
        """Extreme conditions should produce risk_score > 0.8 and blocking=True."""
        agent = _make_agent()
        ctx = _make_extreme_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, RiskReport)
        assert report.risk_score > 0.8
        assert report.blocking is True


# ---------------------------------------------------------------------------
# 3. test_blocking_threshold
# ---------------------------------------------------------------------------


class TestBlockingThreshold:
    def test_risk_score_at_08_not_blocking(self):
        """risk_score exactly at 0.8 should NOT be blocking (threshold is > 0.8)."""
        from src.agents.risk_manager_agent import RiskManagerAgent  # noqa: PLC0415

        agent = RiskManagerAgent()
        # We test the blocking logic directly: 0.8 is not > 0.8
        assert not (0.8 > agent.RISK_BLOCK_THRESHOLD)

    def test_risk_score_above_08_is_blocking(self):
        """risk_score of 0.81 should be blocking."""
        from src.agents.risk_manager_agent import RiskManagerAgent  # noqa: PLC0415

        agent = RiskManagerAgent()
        assert 0.81 > agent.RISK_BLOCK_THRESHOLD

    def test_threshold_value_is_08(self):
        """RISK_BLOCK_THRESHOLD must be 0.8."""
        from src.agents.risk_manager_agent import RiskManagerAgent  # noqa: PLC0415

        assert RiskManagerAgent.RISK_BLOCK_THRESHOLD == 0.8


# ---------------------------------------------------------------------------
# 4. test_volatility_regime_low
# ---------------------------------------------------------------------------


class TestVolatilityRegimeLow:
    def test_volatility_regime_low(self):
        """ATR/price < 0.5% should produce volatility_regime='LOW'."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1.0850,
            atr=0.004,  # ATR% = 0.37% → LOW
            features={"rsi_14": 50.0, "adx_14": 25.0},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "LOW"

    def test_volatility_regime_low_boundary(self):
        """ATR/price exactly at 0.499% should be LOW."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1000.0,
            atr=4.99,  # ATR% = 0.499% → LOW
            features={},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "LOW"


# ---------------------------------------------------------------------------
# 5. test_volatility_regime_medium
# ---------------------------------------------------------------------------


class TestVolatilityRegimeMedium:
    def test_volatility_regime_medium(self):
        """ATR/price between 0.5% and 1.5% should produce volatility_regime='MEDIUM'."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2000.0,
            atr=20.0,  # ATR% = 1.0% → MEDIUM
            features={"rsi_14": 50.0, "adx_14": 25.0},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "MEDIUM"

    def test_volatility_regime_medium_at_lower_boundary(self):
        """ATR/price = 0.5% should produce MEDIUM (threshold: atr_pct < 0.5 → LOW)."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=1000.0,
            atr=5.0,  # ATR% = 0.5% → MEDIUM (not < 0.5)
            features={},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "MEDIUM"


# ---------------------------------------------------------------------------
# 6. test_volatility_regime_high
# ---------------------------------------------------------------------------


class TestVolatilityRegimeHigh:
    def test_volatility_regime_high(self):
        """ATR/price between 1.5% and 3.0% should produce volatility_regime='HIGH'."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="BTCUSD",
            current_price=60000.0,
            atr=1200.0,  # ATR% = 2.0% → HIGH
            features={"rsi_14": 50.0, "adx_14": 25.0},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "HIGH"

    def test_volatility_regime_high_at_lower_boundary(self):
        """ATR/price = 1.5% should produce HIGH."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="BTCUSD",
            current_price=1000.0,
            atr=15.0,  # ATR% = 1.5% → HIGH (not < 1.5)
            features={},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "HIGH"


# ---------------------------------------------------------------------------
# 7. test_volatility_regime_extreme
# ---------------------------------------------------------------------------


class TestVolatilityRegimeExtreme:
    def test_volatility_regime_extreme(self):
        """ATR/price > 3.0% should produce volatility_regime='EXTREME'."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="BTCUSD",
            current_price=60000.0,
            atr=2400.0,  # ATR% = 4.0% → EXTREME
            features={"rsi_14": 50.0, "adx_14": 25.0},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "EXTREME"

    def test_volatility_regime_extreme_at_boundary(self):
        """ATR/price = 3.0% should produce EXTREME (not < 3.0)."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="BTCUSD",
            current_price=1000.0,
            atr=30.0,  # ATR% = 3.0% → EXTREME
            features={},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.volatility_regime == "EXTREME"


# ---------------------------------------------------------------------------
# 8. test_max_size_zero_when_blocking
# ---------------------------------------------------------------------------


class TestMaxSizeZeroWhenBlocking:
    def test_max_size_zero_when_blocking(self):
        """When blocking=True, max_position_size_pct must be 0.0."""
        agent = _make_agent()
        ctx = _make_extreme_context()
        report = agent._heuristic_analyze(ctx)

        assert report.blocking is True
        assert report.max_position_size_pct == 0.0

    def test_max_size_at_least_half_when_low_risk(self):
        """Low risk should yield max_position_size_pct >= 0.5."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1.0850,
            atr=0.004,  # very low ATR%
            features={"rsi_14": 50.0, "adx_14": 40.0},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.max_position_size_pct >= 0.5


# ---------------------------------------------------------------------------
# 9. test_max_size_inversely_proportional
# ---------------------------------------------------------------------------


class TestMaxSizeInverselyProportional:
    def test_max_size_inversely_proportional(self):
        """Lower risk context should yield higher max_position_size_pct."""
        agent = _make_agent()

        low_risk_ctx = MarketContext(
            epic="EURUSD",
            current_price=1.0850,
            atr=0.004,  # ~0.37% ATR → LOW vol
            features={"rsi_14": 50.0, "adx_14": 40.0},
            open_positions=0,
            equity=10000.0,
        )
        high_risk_ctx = MarketContext(
            epic="BTCUSD",
            current_price=60000.0,
            atr=900.0,  # 1.5% ATR → HIGH vol
            features={"rsi_14": 50.0, "adx_14": 25.0},
            open_positions=5,
            equity=10000.0,
        )

        low_report = agent._heuristic_analyze(low_risk_ctx)
        high_report = agent._heuristic_analyze(high_risk_ctx)

        assert low_report.max_position_size_pct > high_report.max_position_size_pct

    def test_max_size_bounded(self):
        """max_position_size_pct must be in [0.0, 2.0] range."""
        agent = _make_agent()
        ctx = _make_normal_context()
        report = agent._heuristic_analyze(ctx)
        assert 0.0 <= report.max_position_size_pct <= 2.0


# ---------------------------------------------------------------------------
# 10. test_liquidity_score
# ---------------------------------------------------------------------------


class TestLiquidityScore:
    def test_liquidity_score_above_average(self):
        """volume > volume_sma should produce liquidity_score > 0.5."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.0,
            features={
                "rsi_14": 50.0,
                "adx_14": 25.0,
                "volume": 2000.0,     # 2x average → liq_score = 1.0
                "volume_sma": 1000.0,
            },
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.liquidity_score > 0.5

    def test_liquidity_score_below_average(self):
        """volume < volume_sma should produce liquidity_score < 0.5."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.0,
            features={
                "rsi_14": 50.0,
                "adx_14": 25.0,
                "volume": 300.0,      # 0.3x average → liq_score = 0.15
                "volume_sma": 1000.0,
            },
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.liquidity_score < 0.5

    def test_liquidity_score_defaults_when_no_volume(self):
        """Missing volume_sma should default liquidity_score to 0.5."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.0,
            features={},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.liquidity_score == 0.5

    def test_liquidity_score_capped_at_1(self):
        """Extremely high volume should be capped at liquidity_score = 1.0."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="GOLD",
            current_price=2350.0,
            atr=12.0,
            features={
                "volume": 100000.0,   # 100x average
                "volume_sma": 1000.0,
            },
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert report.liquidity_score <= 1.0


# ---------------------------------------------------------------------------
# 11. test_missing_features
# ---------------------------------------------------------------------------


class TestMissingFeatures:
    def test_empty_features_no_crash(self):
        """Empty features dict should return a valid RiskReport without crashing."""
        agent = _make_agent()
        ctx = _make_empty_context()
        report = agent._heuristic_analyze(ctx)

        assert isinstance(report, RiskReport)
        assert 0.0 <= report.risk_score <= 1.0
        assert report.volatility_regime in ("LOW", "MEDIUM", "HIGH", "EXTREME")
        assert report.rationale  # non-empty string

    def test_none_feature_values_no_crash(self):
        """None values for feature keys should not raise exceptions."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="EURUSD",
            current_price=1.085,
            atr=0.001,
            features={"rsi_14": None, "adx_14": None, "volume": None, "volume_sma": None},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert isinstance(report, RiskReport)

    def test_zero_price_no_crash(self):
        """current_price = 0 should not produce ZeroDivisionError."""
        agent = _make_agent()
        ctx = MarketContext(
            epic="TEST",
            current_price=0.0,
            atr=1.0,
            features={},
            open_positions=0,
            equity=10000.0,
        )
        report = agent._heuristic_analyze(ctx)
        assert isinstance(report, RiskReport)

    def test_risk_score_always_in_range(self):
        """risk_score must always be in [0.0, 1.0] regardless of input."""
        agent = _make_agent()
        for ctx in [_make_normal_context(), _make_extreme_context(), _make_empty_context()]:
            report = agent._heuristic_analyze(ctx)
            assert 0.0 <= report.risk_score <= 1.0

    def test_sl_pct_non_negative(self):
        """recommended_stop_loss_pct must always be >= 0."""
        agent = _make_agent()
        report = agent._heuristic_analyze(_make_normal_context())
        assert report.recommended_stop_loss_pct >= 0.0


# ---------------------------------------------------------------------------
# 12. test_analyze_falls_back_to_heuristic
# ---------------------------------------------------------------------------


class TestAnalyzeFallbackToHeuristic:
    async def test_analyze_falls_back_when_llm_raises(self):
        """When _call_llm raises, analyze() should fall back to heuristic and return a report."""
        agent = _make_agent()
        ctx = _make_normal_context()

        with patch.object(agent, "_call_llm", new=AsyncMock(side_effect=RuntimeError("API down"))):
            result = await agent.analyze(ctx)

        assert result is not None
        assert isinstance(result, RiskReport)
        assert result.risk_score < 0.5
        assert result.blocking is False

    async def test_analyze_returns_llm_result_when_successful(self):
        """When _call_llm succeeds, analyze() should return its result directly."""
        agent = _make_agent()
        ctx = _make_normal_context()

        llm_report = RiskReport(
            risk_score=0.9,
            volatility_regime="EXTREME",
            max_position_size_pct=0.0,
            recommended_stop_loss_pct=3.5,
            liquidity_score=0.3,
            blocking=True,
            rationale="LLM-based risk assessment.",
        )

        with patch.object(agent, "_call_llm", new=AsyncMock(return_value=llm_report)):
            result = await agent.analyze(ctx)

        assert result is llm_report
        assert result.blocking is True  # LLM result, not heuristic

    async def test_analyze_never_raises(self):
        """analyze() must never raise — always returns RiskReport or None."""
        agent = _make_agent()
        ctx = _make_normal_context()

        with patch.object(
            agent, "_call_llm", new=AsyncMock(side_effect=Exception("catastrophic failure"))
        ):
            result = await agent.analyze(ctx)

        # Falls back to heuristic → always returns a RiskReport
        assert result is not None
        assert isinstance(result, RiskReport)


# ---------------------------------------------------------------------------
# 13. test_role_and_schema
# ---------------------------------------------------------------------------


class TestRoleAndSchema:
    def test_role_is_risk(self):
        """RiskManagerAgent.role must be AgentRole.RISK."""
        agent = _make_agent()
        assert agent.role == AgentRole.RISK

    def test_output_schema_is_risk_report(self):
        """RiskManagerAgent.output_schema must be RiskReport."""
        agent = _make_agent()
        assert agent.output_schema is RiskReport

    def test_role_is_class_variable(self):
        """role should be accessible as a class variable (not just instance)."""
        from src.agents.risk_manager_agent import RiskManagerAgent  # noqa: PLC0415

        assert RiskManagerAgent.role == AgentRole.RISK

    def test_output_schema_is_class_variable(self):
        """output_schema should be accessible as a class variable (not just instance)."""
        from src.agents.risk_manager_agent import RiskManagerAgent  # noqa: PLC0415

        assert RiskManagerAgent.output_schema is RiskReport

    def test_inherits_from_base_agent(self):
        """RiskManagerAgent must inherit from MantisBaseAgent."""
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415
        from src.agents.risk_manager_agent import RiskManagerAgent  # noqa: PLC0415

        assert issubclass(RiskManagerAgent, MantisBaseAgent)

    def test_rationale_is_non_empty_string(self):
        """rationale field should always be a non-empty string."""
        agent = _make_agent()
        report = agent._heuristic_analyze(_make_normal_context())
        assert isinstance(report.rationale, str)
        assert len(report.rationale) > 0

    def test_rationale_contains_risk_score(self):
        """rationale should mention the risk score."""
        agent = _make_agent()
        report = agent._heuristic_analyze(_make_normal_context())
        assert "Risk" in report.rationale or "risk" in report.rationale
