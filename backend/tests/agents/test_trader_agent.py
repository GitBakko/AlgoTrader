"""
Tests for TraderAgent — pure-logic proposal generator combining analyst reports.

TraderAgent has NO LLM, so no mocking of _call_llm is needed.
All tests are synchronous.
"""

import pytest

from src.agents.schemas import (
    MarketContext,
    RiskReport,
    SentimentReport,
    TechnicalReport,
    TradeProposal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(**kwargs):
    """Instantiate TraderAgent with optional weight overrides."""
    from src.agents.trader_agent import TraderAgent  # noqa: PLC0415

    return TraderAgent(**kwargs)


def _make_context(price: float = 2000.0) -> MarketContext:
    return MarketContext(
        epic="GOLD",
        current_price=price,
        atr=10.0,
        timeframe="15min",
        open_positions=1,
        equity=10000.0,
    )


def _make_bullish_technical(support: list[float] | None = None, resistance: list[float] | None = None) -> TechnicalReport:
    return TechnicalReport(
        symbol="GOLD",
        trend_direction="BULLISH",
        strength_score=0.8,
        key_support_levels=support if support is not None else [1950.0, 1970.0],
        key_resistance_levels=resistance if resistance is not None else [2020.0, 2050.0],
        active_patterns=["higher_high"],
        timeframe_consensus={"15min": "BULLISH"},
        rationale="Strong uptrend with volume confirmation.",
    )


def _make_bearish_technical(support: list[float] | None = None, resistance: list[float] | None = None) -> TechnicalReport:
    return TechnicalReport(
        symbol="GOLD",
        trend_direction="BEARISH",
        strength_score=0.7,
        key_support_levels=support if support is not None else [1950.0, 1970.0],
        key_resistance_levels=resistance if resistance is not None else [2020.0, 2050.0],
        active_patterns=["lower_low"],
        timeframe_consensus={"15min": "BEARISH"},
        rationale="Bearish momentum with volume distribution.",
    )


def _make_neutral_technical() -> TechnicalReport:
    return TechnicalReport(
        symbol="GOLD",
        trend_direction="NEUTRAL",
        strength_score=0.5,
        key_support_levels=[1980.0],
        key_resistance_levels=[2010.0],
        active_patterns=[],
        timeframe_consensus={"15min": "NEUTRAL"},
        rationale="No clear trend.",
    )


def _make_bullish_sentiment() -> SentimentReport:
    return SentimentReport(
        composite_score=0.6,
        fear_greed_index=65.0,
        social_sentiment=0.5,
        news_sentiment=0.7,
        confidence=0.75,
        dominant_narrative="Risk-on environment; gold demand rising.",
    )


def _make_bearish_sentiment() -> SentimentReport:
    return SentimentReport(
        composite_score=-0.6,
        fear_greed_index=30.0,
        social_sentiment=-0.5,
        news_sentiment=-0.7,
        confidence=0.75,
        dominant_narrative="Risk-off; gold selling pressure.",
    )


def _make_normal_risk(blocking: bool = False, risk_score: float = 0.3, size_pct: float = 1.0) -> RiskReport:
    return RiskReport(
        risk_score=risk_score,
        volatility_regime="MEDIUM",
        max_position_size_pct=size_pct,
        recommended_stop_loss_pct=1.5,
        liquidity_score=0.7,
        blocking=blocking,
        rationale=f"Risk score {risk_score:.2f}.",
    )


def _make_blocking_risk() -> RiskReport:
    return RiskReport(
        risk_score=0.95,
        volatility_regime="EXTREME",
        max_position_size_pct=0.0,
        recommended_stop_loss_pct=5.0,
        liquidity_score=0.2,
        blocking=True,
        rationale="Extreme volatility — position blocked.",
    )


# ---------------------------------------------------------------------------
# 1. test_risk_blocks_returns_hold
# ---------------------------------------------------------------------------


class TestRiskBlocksReturnsHold:
    def test_risk_blocks_returns_hold_action(self):
        """When RiskReport.blocking=True, action must be HOLD."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_blocking_risk(),
            context=_make_context(),
        )
        assert proposal.action == "HOLD"

    def test_risk_blocks_returns_zero_size(self):
        """When RiskReport.blocking=True, size_pct must be 0.0."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_blocking_risk(),
            context=_make_context(),
        )
        assert proposal.size_pct == 0.0

    def test_risk_blocks_zero_confidence(self):
        """When RiskReport.blocking=True, confidence must be 0.0."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_blocking_risk(),
            context=_make_context(),
        )
        assert proposal.confidence == 0.0

    def test_risk_blocks_rationale_mentions_veto(self):
        """Rationale must mention the risk veto when blocking."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_blocking_risk(),
            context=_make_context(),
        )
        assert "Risk veto" in proposal.rationale or "risk" in proposal.rationale.lower()


# ---------------------------------------------------------------------------
# 2. test_bullish_technical_bullish_sentiment_buy
# ---------------------------------------------------------------------------


class TestBullishTechnicalBullishSentimentBuy:
    def test_both_bullish_produces_buy(self):
        """Both bullish reports should yield action=BUY."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert proposal.action == "BUY"

    def test_both_bullish_positive_confidence(self):
        """Both bullish should yield confidence > 0."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert proposal.confidence > 0.0

    def test_both_bullish_returns_trade_proposal(self):
        """Result must be a TradeProposal instance."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert isinstance(proposal, TradeProposal)


# ---------------------------------------------------------------------------
# 3. test_bearish_technical_bearish_sentiment_sell
# ---------------------------------------------------------------------------


class TestBearishTechnicalBearishSentimentSell:
    def test_both_bearish_produces_sell(self):
        """Both bearish reports should yield action=SELL."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bearish_technical(),
            sentiment=_make_bearish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert proposal.action == "SELL"

    def test_both_bearish_positive_confidence(self):
        """Both bearish should yield confidence > 0."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bearish_technical(),
            sentiment=_make_bearish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert proposal.confidence > 0.0


# ---------------------------------------------------------------------------
# 4. test_mixed_signals_hold
# ---------------------------------------------------------------------------


class TestMixedSignalsHold:
    def test_mixed_signals_produce_hold(self):
        """Bullish tech + bearish sentiment of equal weight → direction near 0 → HOLD."""
        # strength_score=0.5 for tech (BULLISH), composite_score=-0.5 for sentiment
        # dir_score = (0.5*0.4 + (-0.5)*0.2) / (0.4+0.2) = (0.2 - 0.1) / 0.6 = 0.1/0.6 ≈ 0.167 > 0.15
        # To guarantee HOLD we need to keep it within [-0.15, 0.15]:
        # Use strength_score=0.4 → (0.4*0.4 + (-0.5)*0.2) / 0.6 = (0.16-0.10)/0.6 ≈ 0.10 → HOLD
        tech = TechnicalReport(
            symbol="GOLD",
            trend_direction="BULLISH",
            strength_score=0.4,
            key_support_levels=[1980.0],
            key_resistance_levels=[2010.0],
            active_patterns=[],
            timeframe_consensus={"15min": "BULLISH"},
            rationale="Mild bullish.",
        )
        sent = SentimentReport(
            composite_score=-0.5,
            fear_greed_index=40.0,
            social_sentiment=-0.4,
            news_sentiment=-0.6,
            confidence=0.6,
            dominant_narrative="Bearish macro backdrop.",
        )
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=sent,
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert proposal.action == "HOLD"

    def test_hold_has_zero_confidence(self):
        """HOLD action must always have confidence=0.0."""
        tech = TechnicalReport(
            symbol="GOLD",
            trend_direction="BULLISH",
            strength_score=0.4,
            key_support_levels=[1980.0],
            key_resistance_levels=[2010.0],
            active_patterns=[],
            timeframe_consensus={"15min": "BULLISH"},
            rationale="Mild bullish.",
        )
        sent = SentimentReport(
            composite_score=-0.5,
            fear_greed_index=40.0,
            social_sentiment=-0.4,
            news_sentiment=-0.6,
            confidence=0.6,
            dominant_narrative="Bearish macro backdrop.",
        )
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=sent,
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert proposal.confidence == 0.0


# ---------------------------------------------------------------------------
# 5. test_confidence_weighted
# ---------------------------------------------------------------------------


class TestConfidenceWeighted:
    def test_confidence_in_valid_range(self):
        """Confidence must be in [0.0, 1.0]."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(risk_score=0.2),
            context=_make_context(),
        )
        assert 0.0 <= proposal.confidence <= 1.0

    def test_confidence_reflects_weighted_average(self):
        """
        With default weights (tech=0.4, sent=0.2, risk=0.4):
        tech.strength_score=0.8 → weight 0.4
        sent.confidence=0.75 → weight 0.2
        risk_conf = 1 - 0.3 = 0.7 → weight 0.4
        total_weight = 1.0
        expected = (0.8*0.4 + 0.75*0.2 + 0.7*0.4) / 1.0 = (0.32 + 0.15 + 0.28) = 0.75
        """
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),   # strength=0.8
            sentiment=_make_bullish_sentiment(),    # confidence=0.75
            risk=_make_normal_risk(risk_score=0.3),  # risk_conf=0.7
            context=_make_context(),
        )
        assert proposal.action == "BUY"
        expected = (0.8 * 0.4 + 0.75 * 0.2 + 0.7 * 0.4) / 1.0
        assert abs(proposal.confidence - expected) < 0.01

    def test_confidence_rounded_to_4dp(self):
        """Confidence should be rounded to 4 decimal places."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        # Check it's not excessively precise
        assert proposal.confidence == round(proposal.confidence, 4)


# ---------------------------------------------------------------------------
# 6. test_size_from_risk
# ---------------------------------------------------------------------------


class TestSizeFromRisk:
    def test_size_pct_comes_from_risk_report(self):
        """size_pct must equal risk.max_position_size_pct."""
        agent = _make_agent()
        risk = _make_normal_risk(size_pct=0.75)
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=risk,
            context=_make_context(),
        )
        assert proposal.size_pct == 0.75

    def test_size_pct_defaults_to_1_when_no_risk(self):
        """When risk=None, size_pct should default to 1.0."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=None,
            context=_make_context(),
        )
        assert proposal.size_pct == 1.0

    def test_size_pct_rounded_to_2dp(self):
        """size_pct should be rounded to 2 decimal places."""
        agent = _make_agent()
        risk = _make_normal_risk(size_pct=0.33333)
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=risk,
            context=_make_context(),
        )
        assert proposal.size_pct == round(proposal.size_pct, 2)


# ---------------------------------------------------------------------------
# 7. test_stop_loss_from_support
# ---------------------------------------------------------------------------


class TestStopLossFromSupport:
    def test_buy_sl_at_min_support(self):
        """BUY → stop_loss = min(key_support_levels)."""
        tech = _make_bullish_technical(support=[1950.0, 1970.0, 1940.0])
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(price=2000.0),
        )
        assert proposal.action == "BUY"
        assert proposal.stop_loss == 1940.0  # min([1950, 1970, 1940])

    def test_buy_sl_default_when_no_support(self):
        """BUY → if no support levels, SL defaults to entry * 0.98."""
        tech = _make_bullish_technical(support=[])
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(price=2000.0),
        )
        assert proposal.action == "BUY"
        assert proposal.stop_loss == pytest.approx(2000.0 * 0.98)

    def test_sell_sl_at_max_resistance(self):
        """SELL → stop_loss = max(key_resistance_levels)."""
        tech = _make_bearish_technical(resistance=[2020.0, 2050.0, 2030.0])
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=_make_bearish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(price=2000.0),
        )
        assert proposal.action == "SELL"
        assert proposal.stop_loss == 2050.0  # max([2020, 2050, 2030])

    def test_sell_sl_default_when_no_resistance(self):
        """SELL → if no resistance levels, SL defaults to entry * 1.02."""
        tech = _make_bearish_technical(resistance=[])
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=_make_bearish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(price=2000.0),
        )
        assert proposal.action == "SELL"
        assert proposal.stop_loss == pytest.approx(2000.0 * 1.02)


# ---------------------------------------------------------------------------
# 8. test_take_profit_from_resistance
# ---------------------------------------------------------------------------


class TestTakeProfitFromResistance:
    def test_buy_tp_levels_above_entry(self):
        """BUY → take_profit_levels contains only resistance levels above entry_price."""
        tech = _make_bullish_technical(resistance=[1990.0, 2020.0, 2050.0])
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(price=2000.0),
        )
        assert proposal.action == "BUY"
        # Only 2020 and 2050 are above 2000
        assert 2020.0 in proposal.take_profit_levels
        assert 2050.0 in proposal.take_profit_levels
        assert 1990.0 not in proposal.take_profit_levels

    def test_sell_tp_levels_below_entry(self):
        """SELL → take_profit_levels contains only support levels below entry_price."""
        tech = _make_bearish_technical(support=[1950.0, 1970.0, 2010.0])
        agent = _make_agent()
        proposal = agent.propose(
            technical=tech,
            sentiment=_make_bearish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(price=2000.0),
        )
        assert proposal.action == "SELL"
        # Only 1950 and 1970 are below 2000
        assert 1950.0 in proposal.take_profit_levels
        assert 1970.0 in proposal.take_profit_levels
        assert 2010.0 not in proposal.take_profit_levels

    def test_hold_has_empty_tp_levels(self):
        """HOLD → take_profit_levels should be empty."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert proposal.action == "HOLD"
        assert proposal.take_profit_levels == []


# ---------------------------------------------------------------------------
# 9. test_none_reports_graceful
# ---------------------------------------------------------------------------


class TestNoneReportsGraceful:
    def test_all_none_returns_hold(self):
        """All reports None → action=HOLD."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert proposal.action == "HOLD"

    def test_all_none_zero_confidence(self):
        """All reports None → confidence=0.0."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert proposal.confidence == 0.0

    def test_all_none_returns_trade_proposal(self):
        """All reports None → must return TradeProposal (no crash)."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert isinstance(proposal, TradeProposal)

    def test_all_none_entry_price_from_context(self):
        """entry_price must come from context.current_price even when all reports are None."""
        agent = _make_agent()
        ctx = _make_context(price=3500.0)
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=None,
            context=ctx,
        )
        assert proposal.entry_price == 3500.0


# ---------------------------------------------------------------------------
# 10. test_partial_reports
# ---------------------------------------------------------------------------


class TestPartialReports:
    def test_only_technical_produces_proposal(self):
        """Only technical report (no sentiment, no risk) → valid proposal."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert isinstance(proposal, TradeProposal)
        # With only strong bullish tech, direction_score should be > 0.15 → BUY
        assert proposal.action == "BUY"

    def test_only_sentiment_produces_proposal(self):
        """Only sentiment report (no technical, no risk) → valid proposal."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=_make_bullish_sentiment(),
            risk=None,
            context=_make_context(),
        )
        assert isinstance(proposal, TradeProposal)

    def test_only_risk_produces_hold(self):
        """Only risk report (no technical, no sentiment) → direction=0 → HOLD."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert proposal.action == "HOLD"

    def test_technical_and_risk_no_sentiment(self):
        """Technical + risk but no sentiment → still produces valid proposal."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=None,
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert isinstance(proposal, TradeProposal)
        assert proposal.action in ("BUY", "SELL", "HOLD")


# ---------------------------------------------------------------------------
# 11. test_custom_weights
# ---------------------------------------------------------------------------


class TestCustomWeights:
    def test_risk_heavy_weight_different_result(self):
        """With risk_weight=0.9, high risk_score should pull confidence down significantly."""
        agent_default = _make_agent()
        agent_risk_heavy = _make_agent(technical_weight=0.05, sentiment_weight=0.05, risk_weight=0.9)

        high_risk = _make_normal_risk(risk_score=0.9, blocking=False, size_pct=0.1)

        proposal_default = agent_default.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=high_risk,
            context=_make_context(),
        )
        proposal_risk_heavy = agent_risk_heavy.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=high_risk,
            context=_make_context(),
        )
        # Risk-heavy weighting should produce lower confidence (risk_conf=0.1 pulls it down)
        assert proposal_risk_heavy.confidence < proposal_default.confidence

    def test_technical_heavy_weight_prefers_tech(self):
        """With tech_weight=0.9, strong bullish tech dominates bearish sentiment."""
        agent = _make_agent(technical_weight=0.9, sentiment_weight=0.1, risk_weight=0.0)
        proposal = agent.propose(
            technical=_make_bullish_technical(),   # BULLISH, strength=0.8
            sentiment=_make_bearish_sentiment(),   # composite=-0.6
            risk=None,
            context=_make_context(),
        )
        # dir_score = (0.8*0.9 + (-0.6)*0.1) / 1.0 = (0.72 - 0.06) = 0.66 → BUY
        assert proposal.action == "BUY"

    def test_weights_stored_on_instance(self):
        """Custom weights must be accessible on the instance."""
        agent = _make_agent(technical_weight=0.3, sentiment_weight=0.3, risk_weight=0.4)
        assert agent.technical_weight == 0.3
        assert agent.sentiment_weight == 0.3
        assert agent.risk_weight == 0.4


# ---------------------------------------------------------------------------
# 12. test_source_reports_populated
# ---------------------------------------------------------------------------


class TestSourceReportsPopulated:
    def test_source_reports_has_technical_key(self):
        """source_reports must contain 'technical' key when technical is provided."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert "technical" in proposal.source_reports

    def test_source_reports_has_sentiment_key(self):
        """source_reports must contain 'sentiment' key when sentiment is provided."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=_make_bullish_sentiment(),
            risk=None,
            context=_make_context(),
        )
        assert "sentiment" in proposal.source_reports

    def test_source_reports_has_risk_key(self):
        """source_reports must contain 'risk' key when risk is provided."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert "risk" in proposal.source_reports

    def test_source_reports_all_keys_with_all_reports(self):
        """source_reports must have technical, sentiment, and risk when all provided."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=_make_bullish_sentiment(),
            risk=_make_normal_risk(),
            context=_make_context(),
        )
        assert "technical" in proposal.source_reports
        assert "sentiment" in proposal.source_reports
        assert "risk" in proposal.source_reports

    def test_source_reports_empty_when_no_reports(self):
        """source_reports must be empty dict when all reports are None."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert proposal.source_reports == {}

    def test_source_reports_technical_contains_trend(self):
        """source_reports['technical'] should contain the trend direction."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=_make_bullish_technical(),
            sentiment=None,
            risk=None,
            context=_make_context(),
        )
        assert "BULLISH" in proposal.source_reports["technical"]

    def test_source_reports_risk_mentions_blocking(self):
        """source_reports['risk'] should mention blocking status."""
        agent = _make_agent()
        proposal = agent.propose(
            technical=None,
            sentiment=None,
            risk=_make_normal_risk(blocking=False),
            context=_make_context(),
        )
        assert "blocking" in proposal.source_reports["risk"]
