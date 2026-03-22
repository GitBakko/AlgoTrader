"""Tests for AlphaVantageClient (news sentiment)."""

from unittest.mock import MagicMock, patch

import pytest

from src.external.alpha_vantage_client import (
    AlphaVantageClient,
    EPIC_TOPIC_MAP,
)


@pytest.fixture
def client():
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 60
        mock_settings.return_value.alpha_vantage_api_key = "test_key"
        c = AlphaVantageClient(cache_ttl_minutes=1380)
    return c


@pytest.fixture
def client_no_key():
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 60
        mock_settings.return_value.alpha_vantage_api_key = ""
        c = AlphaVantageClient(cache_ttl_minutes=1380)
    return c


def _mock_feed(scores: list[float]) -> dict:
    """Create mock Alpha Vantage feed with given sentiment scores."""
    return {
        "feed": [
            {"title": f"Article {i}", "overall_sentiment_score": str(s)}
            for i, s in enumerate(scores)
        ]
    }


def _setup_mock_client(client, response_json: dict):
    """Attach a mock HTTP client to the AlphaVantageClient."""
    mock_http = MagicMock()
    mock_http.is_closed = False

    async def mock_get(url, params=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = response_json
        return resp

    mock_http.get = mock_get
    client._client = mock_http


class TestAlphaVantageClientFetch:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_defaults(self, client_no_key):
        result = await client_no_key.fetch(topic="gold")
        assert result.average_sentiment_score == 0.0
        assert result.bullish_ratio == 0.5

    @pytest.mark.asyncio
    async def test_bullish_feed(self, client):
        """Mostly positive articles → high bullish ratio."""
        _setup_mock_client(client, _mock_feed([0.3, 0.5, 0.2, -0.1, 0.4]))
        result = await client.fetch(topic="financial_markets")
        assert result.average_sentiment_score > 0.2
        assert result.bullish_count == 4
        assert result.bearish_count == 0  # -0.1 is neutral (not < -0.15)
        assert result.bullish_ratio == 1.0

    @pytest.mark.asyncio
    async def test_bearish_feed(self, client):
        """Mostly negative articles → low bullish ratio."""
        _setup_mock_client(client, _mock_feed([-0.3, -0.5, -0.2, 0.1, -0.4]))
        result = await client.fetch(topic="financial_markets")
        assert result.average_sentiment_score < -0.2
        assert result.bearish_count == 4
        assert result.bullish_ratio < 0.1

    @pytest.mark.asyncio
    async def test_empty_feed(self, client):
        """No articles → defaults."""
        _setup_mock_client(client, {"feed": []})
        result = await client.fetch(topic="forex")
        assert result.average_sentiment_score == 0.0

    @pytest.mark.asyncio
    async def test_api_rate_limit_message(self, client):
        """API returns rate limit info → graceful default."""
        _setup_mock_client(client, {
            "Information": "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day."
        })
        result = await client.fetch(topic="blockchain")
        assert result.average_sentiment_score == 0.0

    @pytest.mark.asyncio
    async def test_cache_hit(self, client):
        """Second call uses cache."""
        _setup_mock_client(client, _mock_feed([0.3, 0.4]))
        first = await client.fetch(topic="forex")
        # Change mock to bearish
        _setup_mock_client(client, _mock_feed([-0.5]))
        second = await client.fetch(topic="forex")
        assert second.average_sentiment_score == first.average_sentiment_score

    @pytest.mark.asyncio
    async def test_epic_auto_mapping(self, client):
        """Epic maps to correct topic."""
        _setup_mock_client(client, _mock_feed([0.1]))
        await client.fetch(epic="BTCUSD")
        # Should cache under "av_blockchain"
        assert client._is_cache_valid("av_blockchain")

    @pytest.mark.asyncio
    async def test_unknown_epic_uses_default(self, client):
        """Unknown epic → financial_markets topic."""
        _setup_mock_client(client, _mock_feed([0.1]))
        await client.fetch(epic="UNKNOWN_ASSET")
        assert client._is_cache_valid("av_financial_markets")


class TestEpicTopicMap:
    def test_gold_maps_to_financial_markets(self):
        assert EPIC_TOPIC_MAP["XAUUSD"] == "financial_markets"

    def test_bitcoin_maps_to_blockchain(self):
        assert EPIC_TOPIC_MAP["BTCUSD"] == "blockchain"

    def test_eurusd_maps_to_forex(self):
        assert EPIC_TOPIC_MAP["EURUSD"] == "forex"

    def test_us500_maps_to_economy(self):
        assert EPIC_TOPIC_MAP["US500"] == "economy_fiscal"

    def test_nvda_maps_to_technology(self):
        assert EPIC_TOPIC_MAP["NVDA"] == "technology"

    def test_wtiusd_maps_to_energy(self):
        assert EPIC_TOPIC_MAP["WTIUSD"] == "energy_transportation"

    def test_get_topic_for_epic(self):
        assert AlphaVantageClient.get_topic_for_epic("BTCUSD") == "blockchain"
        assert AlphaVantageClient.get_topic_for_epic("UNKNOWN") == "financial_markets"
