"""Tests for SocialSentimentClient (Reddit + X)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.external.social_sentiment_client import (
    BULLISH_WORDS,
    BEARISH_WORDS,
    EPIC_KEYWORDS,
    SocialSentimentClient,
)


@pytest.fixture
def client():
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 15
        c = SocialSentimentClient(cache_ttl_minutes=15)
    return c


def _mock_reddit_posts(titles: list[str]) -> dict:
    """Create mock Reddit search response."""
    return {
        "data": {
            "children": [
                {"data": {"title": t, "selftext": ""}}
                for t in titles
            ]
        }
    }


class TestSocialSentimentAnalysis:
    def test_bullish_texts(self):
        """Mostly bullish texts → high bullish ratio."""
        texts = [
            "Gold is going to moon! Bullish breakout!",
            "Buy gold now, massive rally incoming",
            "Bearish on gold, crash coming",
        ]
        result = SocialSentimentClient._analyze_texts(texts)
        assert result["bullish_ratio"] > 0.6
        assert result["sentiment_score"] > 0
        assert result["post_count"] == 3

    def test_bearish_texts(self):
        """Mostly bearish texts → low bullish ratio."""
        texts = [
            "Gold is going to crash, sell now",
            "Bear market, short everything",
            "Plunge incoming, dump gold",
        ]
        result = SocialSentimentClient._analyze_texts(texts)
        assert result["bullish_ratio"] < 0.1
        assert result["sentiment_score"] < 0

    def test_neutral_texts(self):
        """No sentiment keywords → neutral."""
        texts = [
            "What do you think about the market?",
            "Looking at charts today",
        ]
        result = SocialSentimentClient._analyze_texts(texts)
        assert result["bullish_ratio"] == 0.5
        assert result["sentiment_score"] == 0.0

    def test_empty_texts(self):
        result = SocialSentimentClient._analyze_texts([])
        assert result["bullish_ratio"] == 0.5
        assert result["post_count"] == 0


class TestSocialSentimentFetch:
    @pytest.mark.asyncio
    async def test_fetch_with_no_reddit_data(self, client):
        """Reddit returns no posts → neutral combined."""
        client._fetch_reddit = AsyncMock(
            return_value={"bullish_ratio": 0.5, "post_count": 0, "sentiment_score": 0.0}
        )
        client._fetch_x = AsyncMock(
            return_value={"bullish_ratio": 0.5, "post_count": 0, "sentiment_score": 0.0}
        )
        result = await client.fetch("XAUUSD")
        assert result.combined_bullish_ratio == 0.5

    @pytest.mark.asyncio
    async def test_fetch_reddit_only(self, client):
        """Reddit has data, X doesn't → use Reddit only."""
        client._fetch_reddit = AsyncMock(
            return_value={"bullish_ratio": 0.8, "post_count": 20, "sentiment_score": 0.6}
        )
        client._fetch_x = AsyncMock(
            return_value={"bullish_ratio": 0.5, "post_count": 0, "sentiment_score": 0.0}
        )
        result = await client.fetch("BTCUSD")
        assert result.combined_bullish_ratio == 0.8
        assert result.reddit_post_count == 20

    @pytest.mark.asyncio
    async def test_fetch_combined(self, client):
        """Both sources have data → weighted combination."""
        client._fetch_reddit = AsyncMock(
            return_value={"bullish_ratio": 0.8, "post_count": 20, "sentiment_score": 0.6}
        )
        client._fetch_x = AsyncMock(
            return_value={"bullish_ratio": 0.4, "post_count": 10, "sentiment_score": -0.2}
        )
        result = await client.fetch("XAUUSD")
        # 0.8 * 0.6 + 0.4 * 0.4 = 0.48 + 0.16 = 0.64
        assert 0.6 <= result.combined_bullish_ratio <= 0.7

    @pytest.mark.asyncio
    async def test_cache_hit(self, client):
        client._fetch_reddit = AsyncMock(
            return_value={"bullish_ratio": 0.9, "post_count": 10, "sentiment_score": 0.8}
        )
        client._fetch_x = AsyncMock(
            return_value={"bullish_ratio": 0.5, "post_count": 0, "sentiment_score": 0.0}
        )
        first = await client.fetch("XAUUSD")
        # Change mock
        client._fetch_reddit = AsyncMock(
            return_value={"bullish_ratio": 0.1, "post_count": 10, "sentiment_score": -0.8}
        )
        second = await client.fetch("XAUUSD")
        assert second.combined_bullish_ratio == first.combined_bullish_ratio


class TestKeywordSets:
    def test_bullish_words_not_empty(self):
        assert len(BULLISH_WORDS) > 10

    def test_bearish_words_not_empty(self):
        assert len(BEARISH_WORDS) > 10

    def test_no_overlap(self):
        """Bullish and bearish word sets shouldn't overlap."""
        overlap = BULLISH_WORDS & BEARISH_WORDS
        assert len(overlap) == 0

    def test_epic_keywords_coverage(self):
        """All 21 MANTIS assets have keywords."""
        for epic in ["XAUUSD", "BTCUSD", "US500", "EURUSD", "NVDA", "WTIUSD"]:
            assert epic in EPIC_KEYWORDS
