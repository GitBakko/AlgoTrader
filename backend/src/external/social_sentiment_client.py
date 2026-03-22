"""
Signal Intelligence Layer — Social Sentiment Client (Reddit + X).

Reddit: Public JSON API (no auth needed, append .json to URL).
X/Twitter: Free API v2 search (1500 tweets/month) or keyword-based.
Both use simple keyword-based sentiment scoring.
TTL: 15 minutes.
"""

from datetime import datetime, timezone

from loguru import logger

from src.external.sil_base_client import SILBaseClient
from src.external.sil_schemas import SocialSentimentData

# Epic → search keywords for social media
EPIC_KEYWORDS: dict[str, list[str]] = {
    "XAUUSD": ["gold", "XAUUSD", "gold price", "precious metals"],
    "XAGUSD": ["silver", "XAGUSD", "silver price"],
    "BTCUSD": ["bitcoin", "BTC", "BTCUSD"],
    "ETHUSD": ["ethereum", "ETH", "ETHUSD"],
    "SOLUSD": ["solana", "SOL"],
    "BNBUSD": ["BNB", "binance coin"],
    "DOGUSD": ["dogecoin", "DOGE"],
    "EURUSD": ["EURUSD", "euro dollar"],
    "GBPUSD": ["GBPUSD", "pound dollar", "cable"],
    "USDJPY": ["USDJPY", "dollar yen"],
    "US500": ["S&P 500", "SPX", "SP500"],
    "NAS100": ["NASDAQ", "NAS100", "QQQ"],
    "DE40": ["DAX", "DE40", "german index"],
    "NVDA": ["NVDA", "nvidia"],
    "TSLA": ["TSLA", "tesla"],
    "WTIUSD": ["crude oil", "WTI", "oil price"],
    "NATGAS": ["natural gas", "NATGAS"],
    "COPPER": ["copper price", "copper futures"],
    "PLATINUM": ["platinum price", "platinum"],
}

# Subreddits to search per asset class
SUBREDDITS: dict[str, list[str]] = {
    "crypto": ["CryptoCurrency", "Bitcoin", "ethtrader"],
    "stocks": ["wallstreetbets", "stocks", "investing"],
    "forex": ["Forex", "Trading"],
    "commodities": ["Gold", "Commodities", "investing"],
}

EPIC_ASSET_CLASS: dict[str, str] = {
    "XAUUSD": "commodities", "XAGUSD": "commodities",
    "BTCUSD": "crypto", "ETHUSD": "crypto", "SOLUSD": "crypto",
    "BNBUSD": "crypto", "DOGUSD": "crypto", "DASHUSD": "crypto", "ICPUSD": "crypto",
    "EURUSD": "forex", "GBPUSD": "forex", "USDJPY": "forex",
    "US500": "stocks", "NAS100": "stocks", "DE40": "stocks",
    "NVDA": "stocks", "TSLA": "stocks",
    "WTIUSD": "commodities", "NATGAS": "commodities",
    "COPPER": "commodities", "PLATINUM": "commodities",
}

# Simple keyword-based sentiment
BULLISH_WORDS = {
    "bull", "bullish", "buy", "long", "moon", "pump", "rocket",
    "breakout", "higher", "rally", "surge", "soar", "green",
    "calls", "upside", "ATH", "outperform", "strong",
}
BEARISH_WORDS = {
    "bear", "bearish", "sell", "short", "dump", "crash", "plunge",
    "breakdown", "lower", "drop", "tank", "red", "puts",
    "downside", "recession", "weak", "overvalued", "bubble",
}


class SocialSentimentClient(SILBaseClient):
    """Social sentiment from Reddit + X (Twitter)."""

    REDDIT_SEARCH_URL = "https://www.reddit.com/r/{subreddit}/search.json"

    def __init__(self, cache_ttl_minutes: int | None = None):
        super().__init__(
            "social_sentiment",
            cache_ttl_minutes=cache_ttl_minutes or 15,  # 15 min
        )

    async def fetch(self, epic: str = "XAUUSD") -> SocialSentimentData:
        """
        Fetch social sentiment for an epic from Reddit + X.

        Args:
            epic: MANTIS epic.

        Returns:
            SocialSentimentData with combined sentiment.
        """
        cache_key = f"social_{epic}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Fetch Reddit sentiment
        reddit_result = await self._fetch_reddit(epic)

        # Fetch X sentiment (placeholder — needs API key)
        x_result = await self._fetch_x(epic)

        # Combine: weight Reddit 60%, X 40% (Reddit more accessible)
        reddit_weight = 0.6
        x_weight = 0.4

        # If one source has no data, use only the other
        if reddit_result["post_count"] == 0 and x_result["post_count"] == 0:
            combined = 0.5
        elif reddit_result["post_count"] == 0:
            combined = x_result["bullish_ratio"]
        elif x_result["post_count"] == 0:
            combined = reddit_result["bullish_ratio"]
        else:
            combined = (
                reddit_result["bullish_ratio"] * reddit_weight
                + x_result["bullish_ratio"] * x_weight
            )

        result = SocialSentimentData(
            reddit_bullish_ratio=round(reddit_result["bullish_ratio"], 3),
            reddit_post_count=reddit_result["post_count"],
            reddit_sentiment_score=round(reddit_result["sentiment_score"], 3),
            x_bullish_ratio=round(x_result["bullish_ratio"], 3),
            x_post_count=x_result["post_count"],
            x_sentiment_score=round(x_result["sentiment_score"], 3),
            combined_bullish_ratio=round(combined, 3),
            timestamp=datetime.now(timezone.utc),
        )
        self._set_cache(cache_key, result)
        return result

    async def _fetch_reddit(self, epic: str) -> dict:
        """Fetch and analyze Reddit posts for sentiment."""
        default = {"bullish_ratio": 0.5, "post_count": 0, "sentiment_score": 0.0}

        keywords = EPIC_KEYWORDS.get(epic, [epic])
        asset_class = EPIC_ASSET_CLASS.get(epic, "stocks")
        subreddits = SUBREDDITS.get(asset_class, ["investing"])

        all_texts: list[str] = []

        try:
            client = await self._get_client()
            for subreddit in subreddits[:2]:  # Limit to 2 subreddits
                for keyword in keywords[:2]:   # Limit to 2 keywords
                    try:
                        resp = await client.get(
                            self.REDDIT_SEARCH_URL.format(subreddit=subreddit),
                            params={
                                "q": keyword, "sort": "new",
                                "limit": 10, "t": "day",
                            },
                            headers={"User-Agent": "MANTIS-AI/1.0"},
                        )
                        if resp.status_code == 200:
                            posts = resp.json().get("data", {}).get("children", [])
                            for post in posts:
                                title = post.get("data", {}).get("title", "")
                                selftext = post.get("data", {}).get("selftext", "")
                                all_texts.append(f"{title} {selftext}")
                    except Exception:
                        pass  # Individual subreddit/keyword failures are OK
        except Exception as e:
            logger.debug(f"[SocialSentiment] Reddit fetch failed for {epic}: {e}")
            return default

        if not all_texts:
            return default

        return self._analyze_texts(all_texts)

    async def _fetch_x(self, epic: str) -> dict:
        """
        Fetch X/Twitter sentiment. Placeholder — returns defaults.
        Requires X API v2 bearer token for full implementation.
        """
        # TODO: Implement when X API credentials are configured
        return {"bullish_ratio": 0.5, "post_count": 0, "sentiment_score": 0.0}

    @staticmethod
    def _analyze_texts(texts: list[str]) -> dict:
        """Simple keyword-based sentiment analysis on text list."""
        bullish_count = 0
        bearish_count = 0

        for text in texts:
            words = set(text.lower().split())
            bull_hits = len(words & BULLISH_WORDS)
            bear_hits = len(words & BEARISH_WORDS)

            if bull_hits > bear_hits:
                bullish_count += 1
            elif bear_hits > bull_hits:
                bearish_count += 1
            # Tie → neutral, not counted

        total = bullish_count + bearish_count
        if total == 0:
            return {
                "bullish_ratio": 0.5,
                "post_count": len(texts),
                "sentiment_score": 0.0,
            }

        bullish_ratio = bullish_count / total
        # Sentiment score: -1 (all bear) to +1 (all bull)
        sentiment_score = (bullish_count - bearish_count) / total

        return {
            "bullish_ratio": bullish_ratio,
            "post_count": len(texts),
            "sentiment_score": sentiment_score,
        }
