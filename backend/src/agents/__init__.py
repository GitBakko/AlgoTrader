# MANTIS-EVOLUTION: Agents package — lazy imports
"""Schema contracts, base agent, concrete agents, and the orchestrator.

Imports are lazy to avoid the
``agents → orchestrator → vision_agent → rag.context_builder → memory_layer``
cycle. Sub-modules that only need ``MarketContext`` (or any other
schema) should import directly from ``src.agents.schemas`` rather than
the package root.
"""

__all__ = [
    "AgentRole",
    "MarketContext",
    "TechnicalReport",
    "SentimentReport",
    "RiskReport",
    "TradeProposal",
    "DebateArgument",
    "DebateSummary",
    "FinalDecision",
    "MantisBaseAgent",
    "TechnicalAnalystAgent",
    "SentimentAnalystAgent",
    "RiskManagerAgent",
    "TraderAgent",
    "BullBearDebate",
    "FundManagerAgent",
    "MantisAgentOrchestrator",
    "VisionAgent",
    "MantisDRLEnsembleAgent",
]


_SCHEMA_NAMES = {
    "AgentRole",
    "MarketContext",
    "TechnicalReport",
    "SentimentReport",
    "RiskReport",
    "TradeProposal",
    "DebateArgument",
    "DebateSummary",
    "FinalDecision",
}


def __getattr__(name: str):
    if name in _SCHEMA_NAMES:
        from src.agents import schemas
        return getattr(schemas, name)
    if name == "MantisBaseAgent":
        from src.agents.base_agent import MantisBaseAgent
        return MantisBaseAgent
    if name == "TechnicalAnalystAgent":
        from src.agents.technical_analyst import TechnicalAnalystAgent
        return TechnicalAnalystAgent
    if name == "SentimentAnalystAgent":
        from src.agents.sentiment_analyst import SentimentAnalystAgent
        return SentimentAnalystAgent
    if name == "RiskManagerAgent":
        from src.agents.risk_manager_agent import RiskManagerAgent
        return RiskManagerAgent
    if name == "TraderAgent":
        from src.agents.trader_agent import TraderAgent
        return TraderAgent
    if name == "BullBearDebate":
        from src.agents.debate import BullBearDebate
        return BullBearDebate
    if name == "FundManagerAgent":
        from src.agents.fund_manager import FundManagerAgent
        return FundManagerAgent
    if name == "MantisAgentOrchestrator":
        from src.agents.orchestrator import MantisAgentOrchestrator
        return MantisAgentOrchestrator
    if name == "VisionAgent":
        from src.agents.vision_agent import VisionAgent
        return VisionAgent
    if name == "MantisDRLEnsembleAgent":
        from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent
        return MantisDRLEnsembleAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
