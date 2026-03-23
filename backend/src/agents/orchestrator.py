# MANTIS-EVOLUTION: Agent Orchestrator
"""
MantisAgentOrchestrator — the central coordinator for the MANTIS AI multi-agent
trading pipeline.

Flow:
1. TechnicalAnalyst.analyze(context) -> TechnicalReport
2. SentimentAnalyst.analyze(context) -> SentimentReport
3. RiskManager.analyze(context) -> RiskReport
4. TraderAgent.propose(technical, sentiment, risk, context) -> TradeProposal
5. BullBearDebate.debate(proposal, technical, sentiment, risk) -> DebateSummary
6. FundManager.decide(proposal, debate, risk) -> FinalDecision

Every step is wrapped in error handling — a single-agent failure never crashes
the pipeline. On total failure, the orchestrator returns a safe HOLD decision.

An audit trail is accumulated throughout the pipeline and attached to the
FinalDecision, providing full observability into every agent's contribution.
"""

from __future__ import annotations

from loguru import logger

from src.agents.debate import BullBearDebate
from src.agents.fund_manager import FundManagerAgent
from src.agents.risk_manager_agent import RiskManagerAgent
from src.agents.schemas import FinalDecision, MarketContext
from src.agents.sentiment_analyst import SentimentAnalystAgent
from src.agents.technical_analyst import TechnicalAnalystAgent
from src.agents.trader_agent import TraderAgent
from src.agents.vision_agent import VisionAgent
from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent
from src.drl.ensemble import MantisDRLEnsemble


class MantisAgentOrchestrator:
    """
    Coordinates the multi-agent pipeline.

    Parameters
    ----------
    llm_model:
        Anthropic model identifier passed to LLM-backed agents.
    temperature:
        Sampling temperature for Claude calls.
    max_tokens:
        Max tokens per Claude response.
    technical_weight:
        Weight for technical analysis in the TraderAgent scoring.
    sentiment_weight:
        Weight for sentiment analysis in the TraderAgent scoring.
    risk_weight:
        Weight for risk assessment in the TraderAgent scoring.
    debate_enabled:
        Whether to run the BullBearDebate step.
    vision_enabled:
        Whether to run the VisionAgent step.
    drl_enabled:
        Whether to run the DRL Ensemble step (step 3c).
    risk_block_threshold:
        Risk score above which the RiskManagerAgent sets blocking=True.
    """

    def __init__(
        self,
        llm_model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        technical_weight: float = 0.4,
        sentiment_weight: float = 0.2,
        risk_weight: float = 0.4,
        debate_enabled: bool = True,
        vision_enabled: bool = False,
        drl_enabled: bool = False,
        risk_block_threshold: float = 0.8,
    ) -> None:
        self.technical = TechnicalAnalystAgent(
            model=llm_model, temperature=temperature, max_tokens=max_tokens
        )
        self.sentiment = SentimentAnalystAgent(
            model=llm_model, temperature=temperature, max_tokens=max_tokens
        )
        self.risk = RiskManagerAgent(
            model=llm_model, temperature=temperature, max_tokens=max_tokens
        )
        self.risk.RISK_BLOCK_THRESHOLD = risk_block_threshold
        self.trader = TraderAgent(
            technical_weight=technical_weight,
            sentiment_weight=sentiment_weight,
            risk_weight=risk_weight,
        )
        self.debate = BullBearDebate(use_llm=False)  # heuristic debate by default
        self.fund_manager = FundManagerAgent()
        self.debate_enabled = debate_enabled
        self.vision_enabled = vision_enabled
        self.vision_agent = VisionAgent(vision_model=llm_model) if vision_enabled else None
        self.drl_enabled = drl_enabled
        # DRL ensemble agent: start with an empty ensemble (agents are loaded/trained separately)
        self.drl_agent = (
            MantisDRLEnsembleAgent(ensemble=MantisDRLEnsemble(agents={}))
            if drl_enabled
            else None
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, context: MarketContext) -> FinalDecision:
        """
        Execute the full agent pipeline. Never raises — returns HOLD on total failure.

        Steps:
        1. Technical analysis (safe)
        2. Sentiment analysis (safe)
        3. Risk assessment (safe)
        4. Trade proposal (deterministic)
        5. Bull/bear debate (optional, safe)
        6. Fund manager final decision
        """
        audit_trail: list[dict] = []

        # Step 1: Technical Analysis
        technical = await self._safe_analyze(
            self.technical, context, audit_trail, "technical"
        )

        # Step 2: Sentiment Analysis
        sentiment = await self._safe_analyze(
            self.sentiment, context, audit_trail, "sentiment"
        )

        # Step 3: Risk Assessment
        risk_report = await self._safe_analyze(
            self.risk, context, audit_trail, "risk"
        )

        # Step 3b: Vision + RAG (optional)
        if self.vision_enabled and self.vision_agent is not None:
            try:
                vision_signal = await self.vision_agent.analyze(context)
                # Inject vision data into context for downstream agents
                context.vision_data = {
                    "trend": vision_signal.vision_report.trend_direction if vision_signal.vision_report else "NEUTRAL",
                    "confidence": vision_signal.chart_confidence,
                    "patterns": vision_signal.vision_report.key_patterns if vision_signal.vision_report else [],
                    "insight": vision_signal.vision_report.actionable_insight if vision_signal.vision_report else "",
                }
                context.rag_context = vision_signal.rag_context_summary
                audit_trail.append({
                    "agent": "vision",
                    "status": "success",
                    "summary": f"{vision_signal.vision_report.trend_direction if vision_signal.vision_report else 'N/A'} (conf={vision_signal.chart_confidence:.2f})",
                })
            except Exception as e:
                logger.warning(f"Vision agent failed: {e!r}")
                audit_trail.append({"agent": "vision", "status": "error", "error": str(e)})

        # Step 3c: DRL Ensemble (optional)
        if self.drl_enabled and self.drl_agent is not None:
            try:
                drl_signal = await self.drl_agent.analyze(context)
                # Inject DRL signal data into context for downstream agents
                context.drl_signal = {
                    "action": drl_signal.action,
                    "confidence": drl_signal.confidence,
                    "voting_mode": drl_signal.voting_mode,
                    "contributing_agents": drl_signal.contributing_agents,
                }
                audit_trail.append({
                    "agent": "drl",
                    "status": "success",
                    "summary": (
                        f"action={drl_signal.action} "
                        f"(conf={drl_signal.confidence:.2f}, "
                        f"mode={drl_signal.voting_mode})"
                    ),
                })
            except Exception as e:
                logger.warning(f"DRL ensemble agent failed: {e!r}")
                audit_trail.append({"agent": "drl", "status": "error", "error": str(e)})

        # Step 4: Trade Proposal
        proposal = self.trader.propose(technical, sentiment, risk_report, context)
        audit_trail.append({
            "agent": "trader",
            "action": proposal.action,
            "confidence": proposal.confidence,
        })

        # Step 5: Debate (optional)
        debate_summary = None
        if self.debate_enabled:
            try:
                debate_summary = await self.debate.debate(
                    proposal, technical, sentiment, risk_report
                )
                audit_trail.append({
                    "agent": "debate",
                    "consensus": debate_summary.consensus,
                    "confidence": debate_summary.consensus_confidence,
                })
            except Exception as e:
                logger.warning(f"Debate failed: {e!r}")
                audit_trail.append({"agent": "debate", "error": str(e)})

        # Step 6: Final Decision
        decision = self.fund_manager.decide(proposal, debate_summary, risk_report)
        # Merge full audit trail: pipeline trail + fund_manager's own trail
        decision.agent_audit_trail = audit_trail + decision.agent_audit_trail

        return decision

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _safe_analyze(self, agent, context, audit_trail, name):
        """Run agent analysis safely — log failure, return None on error."""
        try:
            result = await agent.analyze(context)
            if result:
                audit_trail.append({
                    "agent": name,
                    "status": "success",
                    "summary": self._summarize(result, name),
                })
            else:
                audit_trail.append({"agent": name, "status": "no_result"})
            return result
        except Exception as e:
            logger.warning(f"[{name}] Agent failed: {e!r}")
            audit_trail.append({
                "agent": name,
                "status": "error",
                "error": str(e),
            })
            return None

    def _summarize(self, result, name: str) -> str:
        """Create a brief audit summary of an agent result."""
        if name == "technical" and hasattr(result, "trend_direction"):
            return f"{result.trend_direction} ({result.strength_score:.2f})"
        elif name == "sentiment" and hasattr(result, "composite_score"):
            return f"composite={result.composite_score:.2f}"
        elif name == "risk" and hasattr(result, "risk_score"):
            return f"risk={result.risk_score:.2f}, blocking={result.blocking}"
        return "ok"
