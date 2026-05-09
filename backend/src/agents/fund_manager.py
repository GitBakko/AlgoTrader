# MANTIS-EVOLUTION: Fund Manager Agent
"""
FundManagerAgent — final decision-maker in the MANTIS AI multi-agent system.

Receives a TradeProposal + DebateSummary + RiskReport and produces a FinalDecision.
Pure heuristic logic — no LLM required (optionally upgradeable in the future).

Decision priority:
  1. Risk veto (blocking=True) → always HOLD, approved=False
  2. Debate consensus opposes proposal direction → approved=False
  3. Debate confidence below threshold → approved=False (too uncertain)
  4. HOLD proposals → always approved=True (no trade = no risk)
  5. Approved trade → blend proposal confidence with debate confidence
"""

from __future__ import annotations

from src.agents.schemas import (
    DebateSummary,
    FinalDecision,
    RiskReport,
    TradeProposal,
)


class FundManagerAgent:
    """
    Final decision-maker. Receives proposal + debate + risk → FinalDecision.
    Pure logic — no LLM needed.
    """

    def __init__(self, min_debate_confidence: float = 0.3) -> None:
        self.min_debate_confidence = min_debate_confidence

    def decide(
        self,
        proposal: TradeProposal,
        debate: DebateSummary | None,
        risk: RiskReport | None,
    ) -> FinalDecision:
        """Make final trade decision."""
        audit_trail: list[dict] = []

        # Record proposal entry from trader. FundManager owns this row —
        # the orchestrator-level "trader" entry was removed (H6 fix:
        # previously every FinalDecision shipped two "trader" rows
        # because both layers appended one and merged trails at the end).
        audit_trail.append(
            {
                "agent": "trader",
                "action": proposal.action,
                "confidence": proposal.confidence,
            }
        )

        # ------------------------------------------------------------------
        # 1. Risk veto check — blocks everything, including active proposals
        # ------------------------------------------------------------------
        if risk and risk.blocking:
            audit_trail.append(
                {
                    "agent": "risk_manager",
                    "decision": "BLOCKED",
                    "risk_score": risk.risk_score,
                }
            )
            return FinalDecision(
                action="HOLD",
                confidence=0.0,
                size_pct=0.0,
                entry_price=proposal.entry_price,
                take_profit_levels=[],
                stop_loss=0.0,
                rationale=f"Risk veto: {risk.rationale}",
                source_reports=proposal.source_reports,
                approved=False,
                override_reason=f"Risk score {risk.risk_score:.2f} exceeds threshold",
                agent_audit_trail=audit_trail,
            )

        # ------------------------------------------------------------------
        # 2. Debate consensus check
        # ------------------------------------------------------------------
        if debate:
            audit_trail.append(
                {
                    "agent": "debate",
                    "consensus": debate.consensus,
                    "confidence": debate.consensus_confidence,
                }
            )

            # BUY proposal vs BEARISH consensus → reject
            if proposal.action == "BUY" and debate.consensus == "BEARISH":
                return FinalDecision(
                    **proposal.model_dump(),
                    approved=False,
                    override_reason="Debate consensus BEARISH opposes BUY proposal",
                    debate_summary=f"Consensus: {debate.consensus} ({debate.consensus_confidence:.0%})",
                    agent_audit_trail=audit_trail,
                )

            # SELL proposal vs BULLISH consensus → reject
            if proposal.action == "SELL" and debate.consensus == "BULLISH":
                return FinalDecision(
                    **proposal.model_dump(),
                    approved=False,
                    override_reason="Debate consensus BULLISH opposes SELL proposal",
                    debate_summary=f"Consensus: {debate.consensus} ({debate.consensus_confidence:.0%})",
                    agent_audit_trail=audit_trail,
                )

            # Debate confidence too low for an active trade → reject
            if (
                debate.consensus_confidence < self.min_debate_confidence
                and proposal.action != "HOLD"
            ):
                return FinalDecision(
                    **proposal.model_dump(),
                    approved=False,
                    override_reason=(
                        f"Debate confidence {debate.consensus_confidence:.2f} below "
                        f"threshold {self.min_debate_confidence}"
                    ),
                    debate_summary=f"Consensus: {debate.consensus} ({debate.consensus_confidence:.0%})",
                    agent_audit_trail=audit_trail,
                )

        # ------------------------------------------------------------------
        # 3. HOLD proposals are always safe — approve immediately
        # ------------------------------------------------------------------
        if proposal.action == "HOLD":
            return FinalDecision(
                **proposal.model_dump(),
                approved=True,
                debate_summary=(f"Consensus: {debate.consensus}" if debate else None),
                agent_audit_trail=audit_trail,
            )

        # ------------------------------------------------------------------
        # 4. Approved — blend confidences and build the final decision
        # ------------------------------------------------------------------
        final_confidence = proposal.confidence
        if debate:
            final_confidence = (proposal.confidence + debate.consensus_confidence) / 2
        final_confidence = max(0.0, min(1.0, final_confidence))

        audit_trail.append(
            {
                "agent": "fund_manager",
                "decision": "APPROVED",
                "final_confidence": final_confidence,
            }
        )

        return FinalDecision(
            action=proposal.action,
            confidence=round(final_confidence, 4),
            size_pct=proposal.size_pct,
            entry_price=proposal.entry_price,
            take_profit_levels=proposal.take_profit_levels,
            stop_loss=proposal.stop_loss,
            rationale=proposal.rationale,
            source_reports=proposal.source_reports,
            approved=True,
            debate_summary=(
                f"Consensus: {debate.consensus} ({debate.consensus_confidence:.0%})"
                if debate
                else None
            ),
            agent_audit_trail=audit_trail,
        )
