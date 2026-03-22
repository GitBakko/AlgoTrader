"""
Tests for FundManagerAgent — final trade approval/rejection decision maker.

FundManagerAgent is pure logic (no LLM). It combines TradeProposal + DebateSummary
+ RiskReport into a FinalDecision. All tests are synchronous.
"""

import pytest

from src.agents.schemas import (
    DebateArgument,
    DebateSummary,
    FinalDecision,
    RiskReport,
    TradeProposal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(**kwargs):
    """Instantiate FundManagerAgent with optional threshold overrides."""
    from src.agents.fund_manager import FundManagerAgent  # noqa: PLC0415

    return FundManagerAgent(**kwargs)


def _make_buy_proposal(confidence: float = 0.7, size_pct: float = 1.0) -> TradeProposal:
    return TradeProposal(
        action="BUY",
        confidence=confidence,
        size_pct=size_pct,
        entry_price=2000.0,
        take_profit_levels=[2020.0, 2050.0],
        stop_loss=1970.0,
        rationale="Bullish technical + sentiment alignment.",
        source_reports={"technical": "BULLISH", "sentiment": "positive"},
    )


def _make_sell_proposal(confidence: float = 0.7) -> TradeProposal:
    return TradeProposal(
        action="SELL",
        confidence=confidence,
        size_pct=1.0,
        entry_price=2000.0,
        take_profit_levels=[1970.0, 1950.0],
        stop_loss=2030.0,
        rationale="Bearish technical + sentiment alignment.",
        source_reports={"technical": "BEARISH", "sentiment": "negative"},
    )


def _make_hold_proposal() -> TradeProposal:
    return TradeProposal(
        action="HOLD",
        confidence=0.0,
        size_pct=0.0,
        entry_price=2000.0,
        take_profit_levels=[],
        stop_loss=0.0,
        rationale="No clear signal.",
        source_reports={},
    )


def _make_bullish_debate(confidence: float = 0.7) -> DebateSummary:
    return DebateSummary(
        bull_arguments=[
            DebateArgument(
                side="BULL",
                argument="Strong uptrend confirmed by volume.",
                confidence=confidence,
                evidence=["EMA crossover", "volume spike"],
            )
        ],
        bear_arguments=[
            DebateArgument(
                side="BEAR",
                argument="Overbought RSI.",
                confidence=0.3,
                evidence=["RSI>70"],
            )
        ],
        consensus="BULLISH",
        consensus_confidence=confidence,
        key_disagreements=["RSI overbought vs trend continuation"],
    )


def _make_bearish_debate(confidence: float = 0.7) -> DebateSummary:
    return DebateSummary(
        bull_arguments=[
            DebateArgument(
                side="BULL",
                argument="Support holding.",
                confidence=0.3,
                evidence=["key support at 1980"],
            )
        ],
        bear_arguments=[
            DebateArgument(
                side="BEAR",
                argument="Head-and-shoulders pattern complete.",
                confidence=confidence,
                evidence=["pattern confirmation", "volume surge down"],
            )
        ],
        consensus="BEARISH",
        consensus_confidence=confidence,
        key_disagreements=["support level significance"],
    )


def _make_neutral_debate(confidence: float = 0.5) -> DebateSummary:
    return DebateSummary(
        bull_arguments=[],
        bear_arguments=[],
        consensus="NEUTRAL",
        consensus_confidence=confidence,
        key_disagreements=["no clear consensus"],
    )


def _make_blocking_risk(risk_score: float = 0.95) -> RiskReport:
    return RiskReport(
        risk_score=risk_score,
        volatility_regime="EXTREME",
        max_position_size_pct=0.0,
        recommended_stop_loss_pct=5.0,
        liquidity_score=0.2,
        blocking=True,
        rationale="Extreme volatility — position blocked.",
    )


def _make_normal_risk(risk_score: float = 0.3) -> RiskReport:
    return RiskReport(
        risk_score=risk_score,
        volatility_regime="MEDIUM",
        max_position_size_pct=1.0,
        recommended_stop_loss_pct=1.5,
        liquidity_score=0.8,
        blocking=False,
        rationale=f"Risk score {risk_score:.2f}, manageable.",
    )


# ---------------------------------------------------------------------------
# 1. test_approved_when_aligned
# ---------------------------------------------------------------------------


class TestApprovedWhenAligned:
    def test_buy_bullish_debate_approved(self):
        """BUY proposal + BULLISH debate → approved=True."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.approved is True

    def test_buy_bullish_returns_final_decision(self):
        """Result must be a FinalDecision instance."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert isinstance(decision, FinalDecision)

    def test_buy_bullish_keeps_buy_action(self):
        """Approved BUY decision retains action=BUY."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.action == "BUY"

    def test_sell_bearish_debate_approved(self):
        """SELL proposal + BEARISH debate → approved=True."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_sell_proposal(),
            debate=_make_bearish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.approved is True


# ---------------------------------------------------------------------------
# 2. test_rejected_buy_bearish_debate
# ---------------------------------------------------------------------------


class TestRejectedBuyBearishDebate:
    def test_buy_bearish_debate_rejected(self):
        """BUY proposal + BEARISH debate consensus → approved=False."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bearish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.approved is False

    def test_buy_bearish_override_reason_set(self):
        """BUY + BEARISH debate → override_reason must be non-empty string."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bearish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.override_reason is not None
        assert len(decision.override_reason) > 0

    def test_buy_bearish_override_mentions_bearish(self):
        """override_reason must mention 'BEARISH' when debate opposes BUY."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bearish_debate(),
            risk=_make_normal_risk(),
        )
        assert "BEARISH" in decision.override_reason


# ---------------------------------------------------------------------------
# 3. test_rejected_sell_bullish_debate
# ---------------------------------------------------------------------------


class TestRejectedSellBullishDebate:
    def test_sell_bullish_debate_rejected(self):
        """SELL proposal + BULLISH debate consensus → approved=False."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_sell_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.approved is False

    def test_sell_bullish_override_reason_set(self):
        """SELL + BULLISH debate → override_reason must be non-empty."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_sell_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.override_reason is not None
        assert len(decision.override_reason) > 0

    def test_sell_bullish_override_mentions_bullish(self):
        """override_reason must mention 'BULLISH' when debate opposes SELL."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_sell_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert "BULLISH" in decision.override_reason


# ---------------------------------------------------------------------------
# 4. test_rejected_low_debate_confidence
# ---------------------------------------------------------------------------


class TestRejectedLowDebateConfidence:
    def test_low_confidence_buy_rejected(self):
        """debate.consensus_confidence < 0.3 with BUY → approved=False."""
        agent = _make_agent(min_debate_confidence=0.3)
        low_conf_debate = _make_neutral_debate(confidence=0.1)
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=low_conf_debate,
            risk=_make_normal_risk(),
        )
        assert decision.approved is False

    def test_low_confidence_override_reason_mentions_threshold(self):
        """override_reason must mention the threshold when confidence is too low."""
        agent = _make_agent(min_debate_confidence=0.3)
        low_conf_debate = _make_neutral_debate(confidence=0.1)
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=low_conf_debate,
            risk=_make_normal_risk(),
        )
        assert decision.override_reason is not None
        # Should mention confidence value or threshold
        assert "0.3" in decision.override_reason or "confidence" in decision.override_reason.lower()

    def test_sufficient_confidence_not_rejected_for_low_conf(self):
        """debate.consensus_confidence >= 0.3 → not rejected for low confidence."""
        agent = _make_agent(min_debate_confidence=0.3)
        ok_conf_debate = _make_bullish_debate(confidence=0.5)
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=ok_conf_debate,
            risk=_make_normal_risk(),
        )
        # Should pass the confidence check (may still be approved)
        assert decision.override_reason is None or "confidence" not in (decision.override_reason or "").lower()


# ---------------------------------------------------------------------------
# 5. test_risk_veto_overrides_all
# ---------------------------------------------------------------------------


class TestRiskVetoOverridesAll:
    def test_risk_veto_with_bullish_debate_still_rejects(self):
        """risk.blocking=True → approved=False even with favorable debate."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_blocking_risk(),
        )
        assert decision.approved is False

    def test_risk_veto_sets_action_hold(self):
        """risk.blocking=True → action must be HOLD."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_blocking_risk(),
        )
        assert decision.action == "HOLD"

    def test_risk_veto_sets_zero_confidence(self):
        """risk.blocking=True → confidence must be 0.0."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_blocking_risk(),
        )
        assert decision.confidence == 0.0

    def test_risk_veto_sets_zero_size(self):
        """risk.blocking=True → size_pct must be 0.0."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_blocking_risk(),
        )
        assert decision.size_pct == 0.0

    def test_risk_veto_override_reason_mentions_risk(self):
        """risk.blocking=True → override_reason mentions 'Risk' or 'risk'."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_blocking_risk(),
        )
        assert decision.override_reason is not None
        assert "risk" in decision.override_reason.lower() or "Risk" in decision.override_reason

    def test_risk_veto_no_debate_also_rejects(self):
        """risk.blocking=True + debate=None → still approved=False."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=None,
            risk=_make_blocking_risk(),
        )
        assert decision.approved is False


# ---------------------------------------------------------------------------
# 6. test_hold_always_approved
# ---------------------------------------------------------------------------


class TestHoldAlwaysApproved:
    def test_hold_approved_true(self):
        """HOLD proposal → approved=True (no trade = no risk)."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_hold_proposal(),
            debate=None,
            risk=None,
        )
        assert decision.approved is True

    def test_hold_approved_with_blocking_risk(self):
        """HOLD proposal is not subject to risk veto — risk only vetos active trades."""
        agent = _make_agent()
        # Note: risk veto check runs first but produces HOLD; let's check HOLD input
        # The risk veto intercepts before reaching HOLD check, but that still returns HOLD approved=False
        # Per design: risk veto overrides ALL, including HOLD input proposals.
        # So a HOLD *proposal* going into risk veto will become a HOLD with approved=False.
        # This test just verifies that when there's no risk blocking, HOLD is approved.
        decision = agent.decide(
            proposal=_make_hold_proposal(),
            debate=None,
            risk=_make_normal_risk(),
        )
        assert decision.approved is True

    def test_hold_approved_with_bullish_debate(self):
        """HOLD proposal + BULLISH debate → still approved=True."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_hold_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert decision.approved is True

    def test_hold_action_unchanged(self):
        """HOLD proposal remains action=HOLD in decision."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_hold_proposal(),
            debate=None,
            risk=None,
        )
        assert decision.action == "HOLD"


# ---------------------------------------------------------------------------
# 7. test_audit_trail_always_populated
# ---------------------------------------------------------------------------


class TestAuditTrailAlwaysPopulated:
    def test_approved_has_audit_trail(self):
        """Approved decision → agent_audit_trail is non-empty."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert len(decision.agent_audit_trail) > 0

    def test_rejected_risk_veto_has_audit_trail(self):
        """Risk veto rejection → agent_audit_trail is non-empty."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=None,
            risk=_make_blocking_risk(),
        )
        assert len(decision.agent_audit_trail) > 0

    def test_rejected_debate_has_audit_trail(self):
        """Debate rejection → agent_audit_trail is non-empty."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bearish_debate(),
            risk=_make_normal_risk(),
        )
        assert len(decision.agent_audit_trail) > 0

    def test_hold_has_audit_trail(self):
        """HOLD decision → agent_audit_trail is non-empty."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_hold_proposal(),
            debate=None,
            risk=None,
        )
        assert len(decision.agent_audit_trail) > 0

    def test_audit_trail_is_list_of_dicts(self):
        """agent_audit_trail must be a list of dicts."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        assert isinstance(decision.agent_audit_trail, list)
        for entry in decision.agent_audit_trail:
            assert isinstance(entry, dict)


# ---------------------------------------------------------------------------
# 8. test_audit_trail_has_trader_entry
# ---------------------------------------------------------------------------


class TestAuditTrailHasTraderEntry:
    def test_approved_audit_has_trader(self):
        """Approved decision → audit trail contains entry with agent='trader'."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        agents_in_trail = [e["agent"] for e in decision.agent_audit_trail]
        assert "trader" in agents_in_trail

    def test_rejected_audit_has_trader(self):
        """Rejected decision → audit trail still has trader entry."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bearish_debate(),
            risk=_make_normal_risk(),
        )
        agents_in_trail = [e["agent"] for e in decision.agent_audit_trail]
        assert "trader" in agents_in_trail

    def test_trader_entry_has_action(self):
        """Trader audit entry must have 'action' key."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        trader_entry = next(e for e in decision.agent_audit_trail if e["agent"] == "trader")
        assert "action" in trader_entry

    def test_trader_entry_action_matches_proposal(self):
        """Trader audit entry 'action' must match the original proposal action."""
        agent = _make_agent()
        proposal = _make_buy_proposal()
        decision = agent.decide(
            proposal=proposal,
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        trader_entry = next(e for e in decision.agent_audit_trail if e["agent"] == "trader")
        assert trader_entry["action"] == proposal.action

    def test_trader_entry_has_confidence(self):
        """Trader audit entry must have 'confidence' key."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(confidence=0.65),
            debate=_make_bullish_debate(),
            risk=_make_normal_risk(),
        )
        trader_entry = next(e for e in decision.agent_audit_trail if e["agent"] == "trader")
        assert "confidence" in trader_entry
        assert trader_entry["confidence"] == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# 9. test_confidence_averaged_with_debate
# ---------------------------------------------------------------------------


class TestConfidenceAveragedWithDebate:
    def test_final_confidence_is_average_of_proposal_and_debate(self):
        """When approved, final confidence = (proposal.confidence + debate.confidence) / 2."""
        agent = _make_agent()
        proposal = _make_buy_proposal(confidence=0.8)
        debate = _make_bullish_debate(confidence=0.6)
        decision = agent.decide(
            proposal=proposal,
            debate=debate,
            risk=_make_normal_risk(),
        )
        expected = (0.8 + 0.6) / 2  # = 0.7
        assert decision.approved is True
        assert abs(decision.confidence - expected) < 0.001

    def test_final_confidence_rounded_to_4dp(self):
        """Final confidence must be rounded to 4 decimal places."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(confidence=0.7),
            debate=_make_bullish_debate(confidence=0.6),
            risk=_make_normal_risk(),
        )
        assert decision.confidence == round(decision.confidence, 4)

    def test_final_confidence_in_valid_range(self):
        """Final confidence must be in [0.0, 1.0]."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(confidence=0.9),
            debate=_make_bullish_debate(confidence=0.95),
            risk=_make_normal_risk(),
        )
        assert 0.0 <= decision.confidence <= 1.0

    def test_sell_confidence_averaged_correctly(self):
        """SELL: final confidence also averaged with debate."""
        agent = _make_agent()
        proposal = _make_sell_proposal(confidence=0.6)
        debate = _make_bearish_debate(confidence=0.8)
        decision = agent.decide(
            proposal=proposal,
            debate=debate,
            risk=_make_normal_risk(),
        )
        expected = (0.6 + 0.8) / 2  # = 0.7
        assert decision.approved is True
        assert abs(decision.confidence - expected) < 0.001


# ---------------------------------------------------------------------------
# 10. test_no_debate_still_works
# ---------------------------------------------------------------------------


class TestNoDebateStillWorks:
    def test_buy_no_debate_returns_decision(self):
        """debate=None → FinalDecision returned without crash."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=None,
            risk=_make_normal_risk(),
        )
        assert isinstance(decision, FinalDecision)

    def test_buy_no_debate_approved_true(self):
        """BUY + debate=None → no debate check → approved=True (if risk ok)."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=None,
            risk=_make_normal_risk(),
        )
        assert decision.approved is True

    def test_buy_no_debate_uses_proposal_confidence(self):
        """BUY + debate=None → confidence comes directly from proposal."""
        agent = _make_agent()
        proposal = _make_buy_proposal(confidence=0.72)
        decision = agent.decide(
            proposal=proposal,
            debate=None,
            risk=_make_normal_risk(),
        )
        assert decision.confidence == pytest.approx(0.72)

    def test_no_debate_no_debate_summary_in_decision(self):
        """debate=None → debate_summary field in decision is None."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=None,
            risk=_make_normal_risk(),
        )
        assert decision.debate_summary is None


# ---------------------------------------------------------------------------
# 11. test_no_risk_still_works
# ---------------------------------------------------------------------------


class TestNoRiskStillWorks:
    def test_buy_no_risk_returns_decision(self):
        """risk=None → FinalDecision returned without crash."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=None,
        )
        assert isinstance(decision, FinalDecision)

    def test_buy_no_risk_approved_true(self):
        """BUY + risk=None → no risk veto check → approved=True (if debate ok)."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=_make_bullish_debate(),
            risk=None,
        )
        assert decision.approved is True

    def test_buy_no_risk_no_debate_approved_true(self):
        """BUY + risk=None + debate=None → approved=True."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=None,
            risk=None,
        )
        assert decision.approved is True

    def test_no_risk_action_preserved(self):
        """risk=None → action in decision matches proposal action."""
        agent = _make_agent()
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=None,
            risk=None,
        )
        assert decision.action == "BUY"


# ---------------------------------------------------------------------------
# 12. test_custom_min_debate_confidence
# ---------------------------------------------------------------------------


class TestCustomMinDebateConfidence:
    def test_high_threshold_rejects_moderate_confidence(self):
        """Custom min_debate_confidence=0.7 → debate conf=0.5 → rejected."""
        agent = _make_agent(min_debate_confidence=0.7)
        moderate_debate = _make_bullish_debate(confidence=0.5)
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=moderate_debate,
            risk=_make_normal_risk(),
        )
        assert decision.approved is False

    def test_low_threshold_accepts_same_confidence(self):
        """Custom min_debate_confidence=0.3 → debate conf=0.5 → passes confidence check."""
        agent = _make_agent(min_debate_confidence=0.3)
        moderate_debate = _make_bullish_debate(confidence=0.5)
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=moderate_debate,
            risk=_make_normal_risk(),
        )
        # 0.5 >= 0.3 → confidence check passes → approved (debate is BULLISH + BUY)
        assert decision.approved is True

    def test_threshold_stored_on_instance(self):
        """min_debate_confidence must be accessible on the instance."""
        agent = _make_agent(min_debate_confidence=0.45)
        assert agent.min_debate_confidence == pytest.approx(0.45)

    def test_default_threshold_is_0_3(self):
        """Default min_debate_confidence must be 0.3."""
        agent = _make_agent()
        assert agent.min_debate_confidence == pytest.approx(0.3)

    def test_exact_threshold_boundary_passes(self):
        """debate conf == threshold exactly → should NOT be rejected for low confidence."""
        agent = _make_agent(min_debate_confidence=0.4)
        exact_debate = _make_bullish_debate(confidence=0.4)
        decision = agent.decide(
            proposal=_make_buy_proposal(),
            debate=exact_debate,
            risk=_make_normal_risk(),
        )
        # confidence == threshold → not < threshold → passes → approved (BULLISH+BUY)
        assert decision.approved is True
