"""
Pydantic models for external API responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class InsiderSentiment(BaseModel):
    """Insider sentiment data from Finnhub."""

    epic: str
    mspr: float = Field(description="Monthly Share Purchase Ratio (-100 to +100)")
    change: float = Field(description="Net share change")
    period: str = Field(description="YYYY-MM format")


class AnalystConsensus(BaseModel):
    """Analyst consensus data from Finnhub."""

    epic: str
    buy: int
    hold: int
    sell: int
    consensus: str = Field(description="BUY | HOLD | SELL")
    target_price: float


class PriceTarget(BaseModel):
    """Analyst price target from Finnhub."""

    epic: str
    current_price: float
    target_price: float
    upside_pct: float = Field(description="Percentage upside")


class Earnings(BaseModel):
    """Earnings calendar entry from Finnhub."""

    epic: str
    date: datetime
    estimate: float | None
    actual: float | None


class NewsArticle(BaseModel):
    """News article with sentiment from Marketaux or Finnhub."""

    title: str
    description: str
    url: str
    published_at: datetime
    sentiment: float = Field(description="Sentiment score [-1.0, 1.0]")
    entities: list[str] = Field(description="Ticker symbols mentioned")
    source: str = Field(default="marketaux", description="News source: 'marketaux' or 'finnhub'")
    thumbnail: str | None = Field(default=None, description="Thumbnail image URL (optional)")
