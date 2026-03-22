# MANTIS-EVOLUTION: Agent schema contracts + base agent + concrete agents
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
from src.agents.base_agent import MantisBaseAgent
from src.agents.technical_analyst import TechnicalAnalystAgent
from src.agents.sentiment_analyst import SentimentAnalystAgent
from src.agents.risk_manager_agent import RiskManagerAgent
from src.agents.trader_agent import TraderAgent

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
]
