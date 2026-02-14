"""
Finnhub API client for insider sentiment, analyst data, and earnings.
API Documentation: https://finnhub.io/docs/api
Rate limit: 60 requests/minute (free tier)
"""

from datetime import datetime

import httpx
from loguru import logger

from src.broker.rate_limiter import RateLimiter
from src.external.exceptions import FinnhubError, RateLimitExceeded
from src.external.models import (
    AnalystConsensus,
    Earnings,
    InsiderSentiment,
    NewsArticle,
    PriceTarget,
)
from src.utils.config import get_settings


class FinnhubClient:
    """
    Finnhub API client for stock fundamentals and sentiment data.

    Provides methods for:
    - Insider sentiment (MSPR - Monthly Share Purchase Ratio)
    - Analyst recommendations and consensus
    - Price targets
    - Earnings calendar
    """

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str | None = None, sentiment_analyzer=None):
        """
        Initialize Finnhub client.

        Args:
            api_key: Finnhub API key (uses settings if None)
            sentiment_analyzer: Optional SentimentAnalyzer for local sentiment
        """
        settings = get_settings()
        self.api_key = api_key or settings.finnhub_api_key
        self.sentiment_analyzer = sentiment_analyzer

        if not self.api_key:
            logger.warning("Finnhub API key not configured")

        # 60 req/min = 1 req/sec
        self.rate_limiter = RateLimiter(requests_per_second=1.0)
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client (lazy init pattern)."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def _request(self, endpoint: str, params: dict) -> dict:
        """
        Make rate-limited API request.

        Args:
            endpoint: API endpoint path (e.g., "stock/insider-sentiment")
            params: Query parameters

        Returns:
            JSON response

        Raises:
            RateLimitExceeded: If rate limiter timeout
            FinnhubError: If API request fails
        """
        acquired = await self.rate_limiter.acquire(timeout=10.0)
        if not acquired:
            raise RateLimitExceeded("Finnhub rate limit timeout")

        params["token"] = self.api_key
        client = await self._get_client()

        try:
            url = f"{self.BASE_URL}/{endpoint}"
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            error_msg = f"API error: {e.response.status_code}"
            logger.error(f"Finnhub {endpoint}: {error_msg}")
            raise FinnhubError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(f"Finnhub {endpoint}: {error_msg}")
            raise FinnhubError(error_msg)

    async def get_insider_sentiment(
        self, epic: str, start_date: datetime, end_date: datetime
    ) -> InsiderSentiment | None:
        """
        Get insider trading sentiment (MSPR).

        MSPR = Monthly Share Purchase Ratio
        Positive MSPR indicates more buying than selling by insiders.

        Args:
            epic: Stock ticker (e.g., "NVDA", "TSLA")
            start_date: Start date
            end_date: End date

        Returns:
            Insider sentiment data for most recent month, or None if unavailable
        """
        try:
            data = await self._request(
                "stock/insider-sentiment",
                {
                    "symbol": epic,
                    "from": start_date.date().isoformat(),
                    "to": end_date.date().isoformat(),
                },
            )

            if not data.get("data"):
                logger.debug(f"No insider sentiment data for {epic}")
                return None

            # Get most recent month
            latest = data["data"][-1]
            return InsiderSentiment(
                epic=epic,
                mspr=latest["mspr"],
                change=latest["change"],
                period=f"{latest['year']}-{latest['month']:02d}",
            )

        except FinnhubError as e:
            logger.warning(f"Finnhub insider sentiment failed for {epic}: {e}")
            return None

    async def get_analyst_recommendations(self, epic: str) -> AnalystConsensus | None:
        """
        Get analyst recommendations consensus.

        Args:
            epic: Stock ticker

        Returns:
            Analyst consensus (buy/hold/sell counts), or None if unavailable
        """
        try:
            data = await self._request("stock/recommendation", {"symbol": epic})

            if not data:
                logger.debug(f"No analyst recommendations for {epic}")
                return None

            # Get most recent recommendations
            latest = data[0]
            buy_count = latest["strongBuy"] + latest["buy"]
            sell_count = latest["sell"] + latest["strongSell"]

            # Determine consensus
            if buy_count > sell_count:
                consensus = "BUY"
            elif sell_count > buy_count:
                consensus = "SELL"
            else:
                consensus = "HOLD"

            return AnalystConsensus(
                epic=epic,
                buy=buy_count,
                hold=latest["hold"],
                sell=sell_count,
                consensus=consensus,
                target_price=0.0,  # Populated by get_price_target()
            )

        except FinnhubError as e:
            logger.warning(f"Finnhub analyst recs failed for {epic}: {e}")
            return None

    async def get_price_target(self, epic: str) -> PriceTarget | None:
        """
        Get analyst price target.

        Args:
            epic: Stock ticker

        Returns:
            Price target data, or None if unavailable
        """
        try:
            data = await self._request("stock/price-target", {"symbol": epic})

            if not data or "targetMean" not in data:
                logger.debug(f"No price target for {epic}")
                return None

            return PriceTarget(
                epic=epic,
                current_price=0.0,  # Should be updated with latest price
                target_price=data["targetMean"],
                upside_pct=0.0,  # Calculated after current_price is set
            )

        except FinnhubError as e:
            logger.warning(f"Finnhub price target failed for {epic}: {e}")
            return None

    async def get_earnings_calendar(
        self, epic: str, start_date: datetime, end_date: datetime
    ) -> list[Earnings]:
        """
        Get upcoming earnings events.

        Args:
            epic: Stock ticker
            start_date: Start date
            end_date: End date

        Returns:
            List of earnings events
        """
        try:
            data = await self._request(
                "calendar/earnings",
                {
                    "symbol": epic,
                    "from": start_date.date().isoformat(),
                    "to": end_date.date().isoformat(),
                },
            )

            if not data.get("earningsCalendar"):
                logger.debug(f"No earnings calendar for {epic}")
                return []

            return [
                Earnings(
                    epic=e["symbol"],
                    date=datetime.fromisoformat(e["date"]),
                    estimate=e.get("epsEstimate"),
                    actual=e.get("epsActual"),
                )
                for e in data["earningsCalendar"]
            ]

        except FinnhubError as e:
            logger.warning(f"Finnhub earnings calendar failed for {epic}: {e}")
            return []

    async def get_news_sentiment_score(self, epic: str) -> float:
        """
        Get aggregated news sentiment for a ticker.

        Args:
            epic: Stock ticker (e.g., "NVDA", "TSLA")

        Returns:
            Sentiment score normalized to [-1.0, 1.0] range (0 = neutral)
        """
        try:
            data = await self._request("news-sentiment", {"symbol": epic})

            # Extract bullish/bearish percentages
            sentiment_data = data.get("sentiment", {})
            bullish = sentiment_data.get("bullishPercent", 0.5)
            bearish = sentiment_data.get("bearishPercent", 0.5)

            # Normalize to [-1, 1]: (bullish - bearish)
            # bullish=0.7, bearish=0.3 → 0.4 (positive)
            # bullish=0.3, bearish=0.7 → -0.4 (negative)
            score = bullish - bearish

            return score

        except FinnhubError as e:
            logger.warning(f"Finnhub news sentiment failed for {epic}: {e}")
            return 0.0

    async def get_company_news(
        self, epic: str, start_date: datetime, end_date: datetime
    ) -> list[NewsArticle]:
        """
        Get company news for a ticker with local FinBERT sentiment.

        Args:
            epic: Stock ticker (e.g., "NVDA", "TSLA")
            start_date: Start date for news
            end_date: End date for news

        Returns:
            List of news articles with per-article FinBERT sentiment scores
        """
        try:
            # Fetch news articles
            data = await self._request(
                "company-news",
                {
                    "symbol": epic,
                    "from": start_date.date().isoformat(),
                    "to": end_date.date().isoformat(),
                },
            )

            articles = []
            for item in data:
                # Finnhub news format: {category, datetime, headline, id, image, related, source, summary, url}
                published_at = datetime.fromtimestamp(item["datetime"])

                # Concatenate title + description for sentiment analysis
                text = f"{item['headline']} {item.get('summary', '')}"

                # Local FinBERT sentiment per-article
                sentiment = 0.0
                if self.sentiment_analyzer:
                    try:
                        sentiment = await self.sentiment_analyzer.predict(text)
                    except Exception as e:
                        logger.warning(f"Sentiment analysis failed, fallback to 0.0: {e}")

                articles.append(
                    NewsArticle(
                        title=item["headline"],
                        description=item.get("summary", ""),
                        url=item["url"],
                        published_at=published_at,
                        sentiment=sentiment,  # Per-article FinBERT score
                        entities=[epic],  # Just the requested symbol
                        source="finnhub",  # Source identifier
                        thumbnail=item.get("image"),  # Thumbnail image URL from Finnhub API
                    )
                )

            logger.info(f"Finnhub fetched {len(articles)} news articles for {epic}")
            return articles

        except FinnhubError as e:
            logger.warning(f"Finnhub company news failed for {epic}: {e}")
            return []

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
