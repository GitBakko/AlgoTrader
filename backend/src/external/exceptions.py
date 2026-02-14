"""
Exceptions for external API integrations.
"""


class ExternalAPIError(Exception):
    """Base exception for external API errors."""

    pass


class FinnhubError(ExternalAPIError):
    """Finnhub API specific error."""

    pass


class MarketauxError(ExternalAPIError):
    """Marketaux API specific error."""

    pass


class RateLimitExceeded(ExternalAPIError):
    """API rate limit exceeded."""

    pass


class SentimentAnalysisError(ExternalAPIError):
    """Sentiment analysis processing error."""

    pass
