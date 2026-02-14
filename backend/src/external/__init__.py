"""
External API integrations module.
Provides clients for Finnhub (insider/analyst data) and Marketaux (news sentiment).
"""

from src.external.exceptions import ExternalAPIError, FinnhubError, MarketauxError, RateLimitExceeded
from src.external.finnhub_client import FinnhubClient
from src.external.marketaux_client import MarketauxClient
from src.external.models import (
    AnalystConsensus,
    Earnings,
    InsiderSentiment,
    NewsArticle,
    PriceTarget,
)

__all__ = [
    "FinnhubClient",
    "MarketauxClient",
    "InsiderSentiment",
    "AnalystConsensus",
    "PriceTarget",
    "Earnings",
    "NewsArticle",
    "ExternalAPIError",
    "FinnhubError",
    "MarketauxError",
    "RateLimitExceeded",
]
