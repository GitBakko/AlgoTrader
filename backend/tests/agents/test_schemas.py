"""
Tests for multi-agent schema contracts.

Covers all Pydantic v2 models used as contracts between agents
in the MANTIS AI multi-agent trading system.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.agents.schemas import (
    AgentRole,
    MarketContext,
    TechnicalReport,
    SentimentReport,
    RiskReport,
    TradeProposal,
    DebateArgument,
    DebateSummary,
    FinalDecision,
)


# ---------------------------------------------------------------------------
# AgentRole
# ---------------------------------------------------------------------------

class TestAgentRole:
    def test_all_roles_exist(self):
        expected = {
            "TECHNICAL",
            "SENTIMENT",
            "RISK",
            "TRADER",
            "FUND_MANAGER",
            "VISION",
            "RL_ADAPTIVE",
            "DRL_ENSEMBLE",
        }
        actual = {role.value for role in AgentRole}
        assert actual == expected

    def test_roles_are_strings(self):
        for role in AgentRole:
            assert isinstance(role.value, str)

    def test_role_lookup_by_value(self):
        assert AgentRole("TECHNICAL") == AgentRole.TECHNICAL
        assert AgentRole("RISK") == AgentRole.RISK
        assert AgentRole("DRL_ENSEMBLE") == AgentRole.DRL_ENSEMBLE


# ---------------------------------------------------------------------------
# MarketContext
# ---------------------------------------------------------------------------

class TestMarketContext:
    def test_minimal_creation(self):
        ctx = MarketContext(epic="GOLD", current_price=2350.0, atr=12.5)
        assert ctx.epic == "GOLD"
        assert ctx.current_price == 2350.0
        assert ctx.atr == 12.5
        assert ctx.timeframe == "15min"
        assert ctx.features == {}
        assert ctx.regime is None
        assert ctx.sil_data is None
        assert ctx.open_positions == 0
        assert ctx.equity == 0.0
        assert isinstance(ctx.timestamp, datetime)

    def test_full_creation(self):
        ts = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
        ctx = MarketContext(
            epic="BTCUSD",
            timeframe="1h",
            current_price=85000.0,
            atr=500.0,
            features={"rsi": 55.0, "macd": 0.3},
            regime="TRENDING",
            sil_data={"fear_greed": 60.0},
            open_positions=3,
            equity=12000.0,
            timestamp=ts,
        )
        assert ctx.epic == "BTCUSD"
        assert ctx.timeframe == "1h"
        assert ctx.features["rsi"] == 55.0
        assert ctx.regime == "TRENDING"
        assert ctx.sil_data["fear_greed"] == 60.0
        assert ctx.open_positions == 3
        assert ctx.equity == 12000.0
        assert ctx.timestamp == ts

    def test_timestamp_defaults_to_utc_now(self):
        before = datetime.now(timezone.utc)
        ctx = MarketContext(epic="EURUSD", current_price=1.085, atr=0.0005)
        after = datetime.now(timezone.utc)
        assert before <= ctx.timestamp <= after


# ---------------------------------------------------------------------------
# TechnicalReport
# ---------------------------------------------------------------------------

class TestTechnicalReport:
    def _valid_data(self) -> dict:
        return {
            "symbol": "GOLD",
            "trend_direction": "BULLISH",
            "strength_score": 0.75,
            "key_support_levels": [2300.0, 2280.0],
            "key_resistance_levels": [2400.0, 2450.0],
            "active_patterns": ["golden_cross", "higher_high"],
            "timeframe_consensus": {"15min": "BULLISH", "1h": "BULLISH"},
            "rationale": "Strong uptrend with EMA alignment.",
        }

    def test_valid_creation(self):
        report = TechnicalReport(**self._valid_data())
        assert report.symbol == "GOLD"
        assert report.trend_direction == "BULLISH"
        assert report.strength_score == 0.75
        assert len(report.key_support_levels) == 2
        assert len(report.active_patterns) == 2
        assert isinstance(report.timestamp, datetime)

    def test_all_trend_directions(self):
        for direction in ("BULLISH", "BEARISH", "NEUTRAL"):
            data = self._valid_data()
            data["trend_direction"] = direction
            report = TechnicalReport(**data)
            assert report.trend_direction == direction

    def test_strength_score_boundary_valid(self):
        data = self._valid_data()
        data["strength_score"] = 0.0
        r = TechnicalReport(**data)
        assert r.strength_score == 0.0

        data["strength_score"] = 1.0
        r = TechnicalReport(**data)
        assert r.strength_score == 1.0

    def test_strength_score_above_one_rejected(self):
        data = self._valid_data()
        data["strength_score"] = 1.1
        with pytest.raises(ValidationError) as exc_info:
            TechnicalReport(**data)
        errors = exc_info.value.errors()
        assert any("strength_score" in str(e) for e in errors)

    def test_strength_score_below_zero_rejected(self):
        data = self._valid_data()
        data["strength_score"] = -0.1
        with pytest.raises(ValidationError) as exc_info:
            TechnicalReport(**data)
        errors = exc_info.value.errors()
        assert any("strength_score" in str(e) for e in errors)

    def test_invalid_trend_direction_rejected(self):
        data = self._valid_data()
        data["trend_direction"] = "UP"
        with pytest.raises(ValidationError):
            TechnicalReport(**data)

    def test_empty_lists_allowed(self):
        data = self._valid_data()
        data["key_support_levels"] = []
        data["key_resistance_levels"] = []
        data["active_patterns"] = []
        report = TechnicalReport(**data)
        assert report.key_support_levels == []


# ---------------------------------------------------------------------------
# SentimentReport
# ---------------------------------------------------------------------------

class TestSentimentReport:
    def _valid_data(self) -> dict:
        return {
            "composite_score": 0.35,
            "fear_greed_index": 62.0,
            "social_sentiment": 0.4,
            "news_sentiment": 0.3,
            "confidence": 0.8,
            "dominant_narrative": "Risk-on, institutional buying BTC",
        }

    def test_valid_creation(self):
        report = SentimentReport(**self._valid_data())
        assert report.composite_score == 0.35
        assert report.fear_greed_index == 62.0
        assert report.dominant_narrative == "Risk-on, institutional buying BTC"
        assert isinstance(report.timestamp, datetime)

    def test_composite_score_boundaries(self):
        data = self._valid_data()
        data["composite_score"] = -1.0
        r = SentimentReport(**data)
        assert r.composite_score == -1.0

        data["composite_score"] = 1.0
        r = SentimentReport(**data)
        assert r.composite_score == 1.0

    def test_composite_score_above_one_rejected(self):
        data = self._valid_data()
        data["composite_score"] = 1.01
        with pytest.raises(ValidationError) as exc_info:
            SentimentReport(**data)
        errors = exc_info.value.errors()
        assert any("composite_score" in str(e) for e in errors)

    def test_composite_score_below_minus_one_rejected(self):
        data = self._valid_data()
        data["composite_score"] = -1.01
        with pytest.raises(ValidationError) as exc_info:
            SentimentReport(**data)
        errors = exc_info.value.errors()
        assert any("composite_score" in str(e) for e in errors)

    def test_confidence_boundaries(self):
        data = self._valid_data()
        data["confidence"] = 0.0
        r = SentimentReport(**data)
        assert r.confidence == 0.0

        data["confidence"] = 1.0
        r = SentimentReport(**data)
        assert r.confidence == 1.0

    def test_confidence_above_one_rejected(self):
        data = self._valid_data()
        data["confidence"] = 1.5
        with pytest.raises(ValidationError):
            SentimentReport(**data)


# ---------------------------------------------------------------------------
# RiskReport
# ---------------------------------------------------------------------------

class TestRiskReport:
    def _valid_data(self) -> dict:
        return {
            "risk_score": 0.45,
            "volatility_regime": "MEDIUM",
            "max_position_size_pct": 2.0,
            "recommended_stop_loss_pct": 1.5,
            "liquidity_score": 0.9,
            "blocking": False,
            "rationale": "Normal market conditions.",
        }

    def test_valid_creation(self):
        report = RiskReport(**self._valid_data())
        assert report.risk_score == 0.45
        assert report.volatility_regime == "MEDIUM"
        assert report.blocking is False
        assert isinstance(report.timestamp, datetime)

    def test_all_volatility_regimes(self):
        for regime in ("LOW", "MEDIUM", "HIGH", "EXTREME"):
            data = self._valid_data()
            data["volatility_regime"] = regime
            r = RiskReport(**data)
            assert r.volatility_regime == regime

    def test_invalid_volatility_regime_rejected(self):
        data = self._valid_data()
        data["volatility_regime"] = "UNKNOWN"
        with pytest.raises(ValidationError):
            RiskReport(**data)

    def test_blocking_true_when_risk_high(self):
        """Pattern: consumers should set blocking=True when risk_score > 0.8."""
        data = self._valid_data()
        data["risk_score"] = 0.85
        data["blocking"] = True
        data["rationale"] = "Risk too high — blocking trade."
        report = RiskReport(**data)
        assert report.blocking is True
        assert report.risk_score > 0.8

    def test_blocking_false_by_default(self):
        data = self._valid_data()
        del data["blocking"]
        report = RiskReport(**data)
        assert report.blocking is False

    def test_max_position_size_pct_nonnegative(self):
        data = self._valid_data()
        data["max_position_size_pct"] = 0.0
        r = RiskReport(**data)
        assert r.max_position_size_pct == 0.0

    def test_max_position_size_pct_negative_rejected(self):
        data = self._valid_data()
        data["max_position_size_pct"] = -1.0
        with pytest.raises(ValidationError) as exc_info:
            RiskReport(**data)
        errors = exc_info.value.errors()
        assert any("max_position_size_pct" in str(e) for e in errors)

    def test_recommended_stop_loss_nonnegative(self):
        data = self._valid_data()
        data["recommended_stop_loss_pct"] = 0.0
        r = RiskReport(**data)
        assert r.recommended_stop_loss_pct == 0.0

    def test_recommended_stop_loss_negative_rejected(self):
        data = self._valid_data()
        data["recommended_stop_loss_pct"] = -0.5
        with pytest.raises(ValidationError) as exc_info:
            RiskReport(**data)
        errors = exc_info.value.errors()
        assert any("recommended_stop_loss_pct" in str(e) for e in errors)


# ---------------------------------------------------------------------------
# TradeProposal
# ---------------------------------------------------------------------------

class TestTradeProposal:
    def _valid_data(self) -> dict:
        return {
            "action": "BUY",
            "confidence": 0.72,
            "size_pct": 1.5,
            "entry_price": 2350.0,
            "take_profit_levels": [2380.0, 2420.0],
            "stop_loss": 2315.0,
            "rationale": "Confluence BUY with HTF aligned.",
            "source_reports": {"technical": "bullish", "risk": "low"},
        }

    def test_valid_creation(self):
        proposal = TradeProposal(**self._valid_data())
        assert proposal.action == "BUY"
        assert proposal.confidence == 0.72
        assert len(proposal.take_profit_levels) == 2
        assert isinstance(proposal.timestamp, datetime)

    def test_all_actions(self):
        for action in ("BUY", "SELL", "HOLD"):
            data = self._valid_data()
            data["action"] = action
            p = TradeProposal(**data)
            assert p.action == action

    def test_invalid_action_rejected(self):
        data = self._valid_data()
        data["action"] = "SHORT"
        with pytest.raises(ValidationError):
            TradeProposal(**data)

    def test_confidence_boundaries(self):
        data = self._valid_data()
        data["confidence"] = 0.0
        p = TradeProposal(**data)
        assert p.confidence == 0.0

        data["confidence"] = 1.0
        p = TradeProposal(**data)
        assert p.confidence == 1.0

    def test_size_pct_nonnegative(self):
        data = self._valid_data()
        data["size_pct"] = 0.0
        p = TradeProposal(**data)
        assert p.size_pct == 0.0

    def test_size_pct_negative_rejected(self):
        data = self._valid_data()
        data["size_pct"] = -1.0
        with pytest.raises(ValidationError) as exc_info:
            TradeProposal(**data)
        errors = exc_info.value.errors()
        assert any("size_pct" in str(e) for e in errors)


# ---------------------------------------------------------------------------
# DebateArgument
# ---------------------------------------------------------------------------

class TestDebateArgument:
    def test_bull_side(self):
        arg = DebateArgument(
            side="BULL",
            argument="Strong uptrend with EMA golden cross.",
            confidence=0.8,
            evidence=["ema_cross", "volume_spike"],
        )
        assert arg.side == "BULL"
        assert arg.confidence == 0.8
        assert len(arg.evidence) == 2

    def test_bear_side(self):
        arg = DebateArgument(
            side="BEAR",
            argument="RSI overbought, resistance at 2400.",
            confidence=0.6,
            evidence=["rsi_overbought"],
        )
        assert arg.side == "BEAR"

    def test_invalid_side_rejected(self):
        with pytest.raises(ValidationError):
            DebateArgument(
                side="NEUTRAL",
                argument="Unclear.",
                confidence=0.5,
                evidence=[],
            )

    def test_empty_evidence_allowed(self):
        arg = DebateArgument(side="BULL", argument="Gut feeling.", confidence=0.3, evidence=[])
        assert arg.evidence == []


# ---------------------------------------------------------------------------
# DebateSummary
# ---------------------------------------------------------------------------

class TestDebateSummary:
    def _make_arg(self, side: str) -> DebateArgument:
        return DebateArgument(
            side=side,
            argument=f"{side} argument.",
            confidence=0.7,
            evidence=["indicator_a"],
        )

    def test_valid_creation(self):
        summary = DebateSummary(
            bull_arguments=[self._make_arg("BULL"), self._make_arg("BULL")],
            bear_arguments=[self._make_arg("BEAR")],
            consensus="BULLISH",
            consensus_confidence=0.68,
            key_disagreements=["RSI divergence", "macro headwind"],
        )
        assert summary.consensus == "BULLISH"
        assert summary.consensus_confidence == 0.68
        assert len(summary.bull_arguments) == 2
        assert len(summary.bear_arguments) == 1
        assert len(summary.key_disagreements) == 2

    def test_all_consensus_values(self):
        for consensus in ("BULLISH", "BEARISH", "NEUTRAL"):
            s = DebateSummary(
                bull_arguments=[],
                bear_arguments=[],
                consensus=consensus,
                consensus_confidence=0.5,
                key_disagreements=[],
            )
            assert s.consensus == consensus

    def test_invalid_consensus_rejected(self):
        with pytest.raises(ValidationError):
            DebateSummary(
                bull_arguments=[],
                bear_arguments=[],
                consensus="MIXED",
                consensus_confidence=0.5,
                key_disagreements=[],
            )

    def test_empty_lists_allowed(self):
        s = DebateSummary(
            bull_arguments=[],
            bear_arguments=[],
            consensus="NEUTRAL",
            consensus_confidence=0.5,
            key_disagreements=[],
        )
        assert s.bull_arguments == []
        assert s.key_disagreements == []


# ---------------------------------------------------------------------------
# FinalDecision (extends TradeProposal)
# ---------------------------------------------------------------------------

class TestFinalDecision:
    def _valid_data(self) -> dict:
        return {
            "action": "BUY",
            "confidence": 0.78,
            "size_pct": 2.0,
            "entry_price": 2355.0,
            "take_profit_levels": [2390.0, 2430.0],
            "stop_loss": 2320.0,
            "rationale": "Multi-agent consensus BUY.",
            "source_reports": {"technical": "bullish", "sentiment": "positive"},
            "agent_audit_trail": [
                {"agent": "TechnicalAgent", "verdict": "BUY", "confidence": 0.8},
                {"agent": "RiskAgent", "verdict": "APPROVED"},
            ],
        }

    def test_approved_decision(self):
        data = self._valid_data()
        data["approved"] = True
        decision = FinalDecision(**data)
        assert decision.approved is True
        assert decision.override_reason is None
        assert decision.debate_summary is None
        assert len(decision.agent_audit_trail) == 2
        assert isinstance(decision.timestamp, datetime)

    def test_rejected_decision(self):
        data = self._valid_data()
        data["action"] = "HOLD"
        data["approved"] = False
        data["override_reason"] = "RiskAgent blocked: volatility EXTREME"
        decision = FinalDecision(**data)
        assert decision.approved is False
        assert decision.override_reason == "RiskAgent blocked: volatility EXTREME"

    def test_not_approved_by_default(self):
        decision = FinalDecision(**self._valid_data())
        assert decision.approved is False

    def test_with_debate_summary(self):
        data = self._valid_data()
        data["approved"] = True
        data["debate_summary"] = "Bulls won 3-1. Strong technical confluence."
        decision = FinalDecision(**data)
        assert decision.debate_summary == "Bulls won 3-1. Strong technical confluence."

    def test_is_subclass_of_trade_proposal(self):
        decision = FinalDecision(**self._valid_data())
        assert isinstance(decision, TradeProposal)

    def test_empty_audit_trail_allowed(self):
        data = self._valid_data()
        data["agent_audit_trail"] = []
        decision = FinalDecision(**data)
        assert decision.agent_audit_trail == []

    def test_audit_trail_preserves_arbitrary_dicts(self):
        data = self._valid_data()
        data["agent_audit_trail"] = [
            {"agent": "VisionAgent", "charts_analyzed": 3, "pattern": "H&S"},
        ]
        decision = FinalDecision(**data)
        assert decision.agent_audit_trail[0]["charts_analyzed"] == 3
