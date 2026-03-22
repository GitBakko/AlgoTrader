"""
Signal Intelligence Layer (SIL) — Data schemas.
Pydantic models for all SIL external data sources.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class FearGreedData(BaseModel):
    """Composite Fear & Greed index data."""

    value: float = Field(
        default=50.0, ge=0, le=100,
        description="0=extreme fear, 100=extreme greed",
    )
    normalized: float = Field(default=0.5, ge=0.0, le=1.0)
    classification: str = Field(default="neutral")
    is_extreme_fear: bool = False
    is_extreme_greed: bool = False
    gold_bias: float = Field(
        default=0.0, ge=-1.0, le=1.0,
        description="+1=bullish gold (fear), -1=bearish gold (greed)",
    )
    timestamp: datetime | None = None


class FREDData(BaseModel):
    """FRED economic indicators (12 series)."""

    # New SIL series (from Prompt Contract)
    fed_funds_rate: float | None = None         # DFF
    yield_spread_10y2y: float | None = None     # T10Y2Y
    high_yield_spread: float | None = None      # BAMLH0A0HYM2
    consumer_sentiment: float | None = None     # UMCSENT
    unemployment_rate: float | None = None      # UNRATE
    nonfarm_payrolls: float | None = None       # PAYEMS
    # Existing macro overlap
    real_yield_10y: float | None = None         # DFII10
    breakeven_inflation: float | None = None    # T10YIE
    nominal_yield_10y: float | None = None      # DGS10
    broad_dollar: float | None = None           # DTWEXBGS
    vix_close: float | None = None              # VIXCLS
    wti_crude: float | None = None              # DCOILWTICO
    timestamp: datetime | None = None


class AlphaVantageData(BaseModel):
    """Alpha Vantage news sentiment."""

    average_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    bullish_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: datetime | None = None


class COTData(BaseModel):
    """CFTC Commitment of Traders data."""

    noncomm_long: int = 0
    noncomm_short: int = 0
    net_position: int = 0
    net_position_normalized: float = 0.0    # normalized on 52w history
    is_institutional_bullish: bool = False
    z_score_4w: float = 0.0
    report_date: datetime | None = None


class SocialSentimentData(BaseModel):
    """Reddit + X social sentiment."""

    reddit_bullish_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    reddit_post_count: int = 0
    reddit_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    x_bullish_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    x_post_count: int = 0
    x_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    combined_bullish_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: datetime | None = None


class CalendarEvent(BaseModel):
    """Single economic calendar event."""

    event: str = ""
    country: str = ""
    currency: str = ""
    impact: str = "low"     # low, medium, high
    event_time: datetime | None = None
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None


class SILData(BaseModel):
    """Aggregated SIL data passed to the feature pipeline."""

    fear_greed: FearGreedData = Field(default_factory=FearGreedData)
    fred: FREDData = Field(default_factory=FREDData)
    alpha_vantage: AlphaVantageData = Field(default_factory=AlphaVantageData)
    cot: COTData = Field(default_factory=COTData)
    social: SocialSentimentData = Field(default_factory=SocialSentimentData)
    calendar_events: list[CalendarEvent] = Field(default_factory=list)
    fetch_errors: list[str] = Field(default_factory=list)
