"""
Marketaux API client for news with per-ticker sentiment analysis.
API Documentation: https://www.marketaux.com/documentation
Rate limit: 100 requests/day (free tier)
"""

from datetime import datetime, timedelta

import httpx
from loguru import logger

from src.external.exceptions import MarketauxError
from src.external.models import NewsArticle
from src.utils.config import get_settings


class MarketauxClient:
    """
    Marketaux API client for financial news with sentiment scores.

    Features:
    - Per-ticker sentiment analysis
    - In-memory caching (30min TTL)
    - Daily request limit tracking (100 req/day free tier)
    """

    BASE_URL = "https://api.marketaux.com/v1"
    CACHE_TTL_MINUTES = 30
    DAILY_LIMIT = 100

    def __init__(self, api_key: str | None = None, sentiment_analyzer=None):
        """
        Initialize Marketaux client.

        Args:
            api_key: Marketaux API key (uses settings if None)
            sentiment_analyzer: Optional SentimentAnalyzer for local sentiment
        """
        settings = get_settings()
        self.api_key = api_key or settings.marketaux_api_key
        self.sentiment_analyzer = sentiment_analyzer

        if not self.api_key:
            logger.warning("Marketaux API key not configured")

        self._http_client: httpx.AsyncClient | None = None
        self._daily_count = 0
        self._cache: dict[str, tuple[datetime, list[NewsArticle]]] = {}
        self._cache_ttl = timedelta(minutes=self.CACHE_TTL_MINUTES)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client (lazy init pattern)."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    def _cache_key(self, epic: str, limit: int, days: int) -> str:
        """Generate cache key for request."""
        return f"{epic}|{limit}|{days}"

    def _is_cache_valid(self, cache_time: datetime) -> bool:
        """Check if cached data is still valid."""
        return datetime.now() - cache_time < self._cache_ttl

    async def get_news_sentiment(
        self, epic: str, limit: int = 20, days: int = 7
    ) -> list[NewsArticle]:
        """
        Get news articles with sentiment scores for a ticker.

        Args:
            epic: Stock ticker (e.g., "NVDA", "TSLA")
            limit: Maximum articles to return (1-50)
            days: Lookback period in days (1-30)

        Returns:
            List of news articles with sentiment scores
        """
        logger.info(f"[MarketauxClient] get_news_sentiment called: epic={epic}, limit={limit}, days={days}")

        # Check cache first
        cache_key = self._cache_key(epic, limit, days)
        cached = self._cache.get(cache_key)

        if cached:
            cache_time, articles = cached
            if self._is_cache_valid(cache_time):
                logger.debug(f"Marketaux cache hit for {epic} ({len(articles)} articles)")
                return articles

        # Check daily limit
        logger.debug(f"Marketaux daily count: {self._daily_count}/{self.DAILY_LIMIT}")
        # TEMPORARILY DISABLED FOR TESTING
        # if self._daily_count >= self.DAILY_LIMIT:
        #     logger.warning(
        #         f"Marketaux daily limit ({self.DAILY_LIMIT}) reached, using cached data"
        #     )
        #     return cached[1] if cached else []

        try:
            self._daily_count += 1
            client = await self._get_client()

            # Marketaux expects YYYY-MM-DD format, not ISO with time
            published_after = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            params = {
                "api_token": self.api_key,
                "symbols": epic,
                "filter_entities": True,  # Boolean, not string
                "language": "en",
                "limit": min(limit, 50),
                "published_after": published_after,
            }

            url = f"{self.BASE_URL}/news/all"
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            articles = []
            for item in data.get("data", []):
                # Concatenate title + description for sentiment analysis
                text = f"{item['title']} {item.get('description', '')}"

                # Local FinBERT sentiment per-article (primary source)
                finbert_sentiment = 0.0
                if self.sentiment_analyzer:
                    try:
                        finbert_sentiment = await self.sentiment_analyzer.predict(text)
                    except Exception as e:
                        logger.warning(f"FinBERT sentiment failed: {e}")

                # Extract Marketaux API sentiment (if available)
                marketaux_sentiment = 0.0
                for entity in item.get("entities", []):
                    if entity.get("symbol") == epic:
                        marketaux_sentiment = entity.get("sentiment_score", 0.0)
                        break

                # Weighted average: FinBERT (weight 1.0) + Marketaux (weight 0.3)
                # Final = (finbert*1.0 + marketaux*0.3) / 1.3
                if marketaux_sentiment != 0.0:
                    sentiment = (finbert_sentiment * 1.0 + marketaux_sentiment * 0.3) / 1.3
                    logger.debug(
                        f"Weighted sentiment: FinBERT={finbert_sentiment:.2f}, "
                        f"Marketaux={marketaux_sentiment:.2f}, Final={sentiment:.2f}"
                    )
                else:
                    # Marketaux unavailable, use only FinBERT
                    sentiment = finbert_sentiment

                # Parse timestamp (handle Z suffix)
                published_at_str = item["published_at"].replace("Z", "+00:00")
                published_at = datetime.fromisoformat(published_at_str)

                articles.append(
                    NewsArticle(
                        title=item["title"],
                        description=item.get("description", ""),
                        url=item["url"],
                        published_at=published_at,
                        sentiment=sentiment,  # Per-article FinBERT score
                        entities=[e["symbol"] for e in item.get("entities", [])],
                        source="marketaux",
                        thumbnail=item.get("image_url"),  # Thumbnail image URL from Marketaux API
                    )
                )

            # Update cache
            self._cache[cache_key] = (datetime.now(), articles)
            logger.info(f"Marketaux fetched {len(articles)} articles for {epic}")
            return articles

        except httpx.HTTPError as e:
            logger.error(f"Marketaux API failed for {epic}: {e}")
            # Return cached data if available
            return cached[1] if cached else []

    async def get_aggregated_sentiment(self, epic: str, days: int = 7) -> float:
        """
        Get average sentiment score across recent news.

        Args:
            epic: Stock ticker
            days: Lookback period in days

        Returns:
            Average sentiment score in range [-1.0, 1.0]
        """
        articles = await self.get_news_sentiment(epic, limit=50, days=days)

        if not articles:
            return 0.0

        # Filter out neutral sentiment (0.0) and calculate mean
        sentiments = [a.sentiment for a in articles if a.sentiment != 0.0]

        if not sentiments:
            return 0.0

        return sum(sentiments) / len(sentiments)

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
