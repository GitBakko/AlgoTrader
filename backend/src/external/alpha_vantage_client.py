"""
Signal Intelligence Layer — Alpha Vantage Client.

Fetches news sentiment via NEWS_SENTIMENT function.
25 requests/day limit → TTL 23 hours (single daily call per topic).
"""

from datetime import datetime, timezone

from loguru import logger

from src.external.sil_base_client import SILBaseClient
from src.external.sil_schemas import AlphaVantageData

# Epic → Alpha Vantage topic mapping
EPIC_TOPIC_MAP: dict[str, str] = {
    "XAUUSD": "financial_markets",
    "XAGUSD": "financial_markets",
    "BTCUSD": "blockchain",
    "ETHUSD": "blockchain",
    "SOLUSD": "blockchain",
    "BNBUSD": "blockchain",
    "DOGUSD": "blockchain",
    "DASHUSD": "blockchain",
    "ICPUSD": "blockchain",
    "EURUSD": "forex",
    "GBPUSD": "forex",
    "USDJPY": "forex",
    "US500": "economy_fiscal",
    "NAS100": "technology",
    "DE40": "economy_fiscal",
    "NVDA": "technology",
    "TSLA": "technology",
    "WTIUSD": "energy_transportation",
    "NATGAS": "energy_transportation",
    "COPPER": "finance",
    "PLATINUM": "finance",
}

DEFAULT_TOPIC = "financial_markets"


class AlphaVantageClient(SILBaseClient):
    """Alpha Vantage NEWS_SENTIMENT client."""

    BASE_URL = "https://www.alphavantage.co/query"
    SENTIMENT_BULLISH_THRESHOLD = 0.15
    SENTIMENT_BEARISH_THRESHOLD = -0.15

    def __init__(self, cache_ttl_minutes: int | None = None):
        super().__init__(
            "alpha_vantage",
            cache_ttl_minutes=cache_ttl_minutes or 23 * 60,  # 23 hours
        )

    async def fetch(self, topic: str | None = None, epic: str | None = None) -> AlphaVantageData:
        """
        Fetch news sentiment for a topic.

        Args:
            topic: Alpha Vantage topic string (e.g., "blockchain", "forex")
            epic: MANTIS epic to auto-map to topic (used if topic is None)

        Returns:
            AlphaVantageData with sentiment scores.
        """
        if topic is None:
            topic = EPIC_TOPIC_MAP.get(epic or "", DEFAULT_TOPIC)

        cache_key = f"av_{topic}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        api_key = self._settings.alpha_vantage_api_key
        if not api_key:
            logger.debug("[AlphaVantageClient] No API key configured")
            return AlphaVantageData()

        try:
            client = await self._get_client()
            resp = await client.get(
                self.BASE_URL,
                params={
                    "function": "NEWS_SENTIMENT",
                    "topics": topic,
                    "apikey": api_key,
                    "limit": 50,
                },
            )
            resp.raise_for_status()
            body = resp.json()

            # Check for API error/rate limit messages
            if "Information" in body or "Error Message" in body:
                msg = body.get("Information", body.get("Error Message", "Unknown"))
                logger.warning(f"[AlphaVantageClient] API message: {msg}")
                return AlphaVantageData()

            feed = body.get("feed", [])
            if not feed:
                logger.debug(f"[AlphaVantageClient] No articles for topic={topic}")
                return AlphaVantageData()

            return self._parse_feed(feed, cache_key)

        except Exception as e:
            logger.warning(f"[AlphaVantageClient] Fetch failed: {e}")
            return AlphaVantageData()

    def _parse_feed(self, feed: list[dict], cache_key: str) -> AlphaVantageData:
        """Parse news feed into sentiment data."""
        scores = []
        bullish = 0
        bearish = 0
        neutral = 0

        for article in feed:
            score = float(article.get("overall_sentiment_score", 0))
            scores.append(score)
            if score > self.SENTIMENT_BULLISH_THRESHOLD:
                bullish += 1
            elif score < self.SENTIMENT_BEARISH_THRESHOLD:
                bearish += 1
            else:
                neutral += 1

        avg_score = sum(scores) / len(scores) if scores else 0.0
        total_directional = bullish + bearish
        bullish_ratio = bullish / total_directional if total_directional > 0 else 0.5

        result = AlphaVantageData(
            average_sentiment_score=round(avg_score, 4),
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            bullish_ratio=round(bullish_ratio, 3),
            timestamp=datetime.now(timezone.utc),
        )
        self._set_cache(cache_key, result)
        logger.info(
            f"[AlphaVantageClient] Parsed {len(feed)} articles: "
            f"avg={avg_score:.3f}, bull={bullish}, bear={bearish}"
        )
        return result

    @staticmethod
    def get_topic_for_epic(epic: str) -> str:
        """Get Alpha Vantage topic for a MANTIS epic."""
        return EPIC_TOPIC_MAP.get(epic, DEFAULT_TOPIC)
