"""Tests for FearGreedClient (composite Fear & Greed index)."""

from unittest.mock import AsyncMock, patch

import pytest

from src.external.fear_greed_client import FearGreedClient


@pytest.fixture
def client():
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 60
        c = FearGreedClient(cache_ttl_minutes=60)
    return c


class TestFearGreedComposite:
    @pytest.mark.asyncio
    async def test_all_none_returns_neutral(self, client):
        """No data → neutral 50."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch()
        assert result.value == 50.0
        assert result.classification == "neutral"
        assert result.gold_bias == 0.0

    @pytest.mark.asyncio
    async def test_extreme_fear_from_high_vix(self, client):
        """VIX=40 → extreme fear."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch(vix=40.0)
        assert result.value <= 5.0
        assert result.is_extreme_fear is True
        assert result.gold_bias > 0.8

    @pytest.mark.asyncio
    async def test_extreme_greed_from_low_vix(self, client):
        """VIX=12 → extreme greed."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch(vix=12.0)
        assert result.value >= 95.0
        assert result.is_extreme_greed is True
        assert result.gold_bias < -0.8

    @pytest.mark.asyncio
    async def test_vix_momentum_increases_fear(self, client):
        """Rapid VIX increase → lower F&G."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        calm = await client.fetch(vix_change_5d=-0.10)
        client._clear_cache()
        spike = await client.fetch(vix_change_5d=0.20)
        assert spike.value < calm.value

    @pytest.mark.asyncio
    async def test_safe_haven_demand_gold_outperforms(self, client):
        """Gold outperforming S&P → fear."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch(gold_vs_sp500_20d=0.05)
        assert result.value < 50.0

    @pytest.mark.asyncio
    async def test_breadth_high_is_greed(self, client):
        """80% of assets above 20d SMA → greed."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch(breadth_pct=80.0)
        assert result.value >= 70.0
        assert result.classification in ("greed", "extreme_greed")

    @pytest.mark.asyncio
    async def test_breadth_low_is_fear(self, client):
        """20% of assets above 20d SMA → fear."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch(breadth_pct=20.0)
        assert result.value <= 30.0

    @pytest.mark.asyncio
    async def test_crypto_fg_included(self, client):
        """Crypto F&G (10) pulls composite toward fear."""
        client._fetch_alternative_me = AsyncMock(return_value=10.0)
        result = await client.fetch(vix=20.0)
        client._clear_cache()
        # Compare with crypto F&G absent
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result_no_crypto = await client.fetch(vix=20.0)
        assert result.value < result_no_crypto.value

    @pytest.mark.asyncio
    async def test_cache_hit(self, client):
        """Second call uses cache, ignores different inputs."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        first = await client.fetch(vix=25.0)
        second = await client.fetch(vix=40.0)  # Should be cached
        assert second.value == first.value

    @pytest.mark.asyncio
    async def test_all_components_combined(self, client):
        """All 4 non-crypto components + crypto F&G."""
        client._fetch_alternative_me = AsyncMock(return_value=50.0)
        result = await client.fetch(
            vix=25.0, vix_change_5d=0.0,
            gold_vs_sp500_20d=0.0, breadth_pct=50.0,
        )
        # All neutral inputs → should be near 50
        assert 40.0 <= result.value <= 60.0
        assert result.classification == "neutral"


class TestFearGreedClassification:
    def test_extreme_fear(self):
        assert FearGreedClient._classify(10) == "extreme_fear"

    def test_fear(self):
        assert FearGreedClient._classify(30) == "fear"

    def test_neutral(self):
        assert FearGreedClient._classify(50) == "neutral"

    def test_greed(self):
        assert FearGreedClient._classify(70) == "greed"

    def test_extreme_greed(self):
        assert FearGreedClient._classify(90) == "extreme_greed"

    def test_boundary_20(self):
        assert FearGreedClient._classify(20) == "extreme_fear"

    def test_boundary_40(self):
        assert FearGreedClient._classify(40) == "fear"

    def test_boundary_60(self):
        assert FearGreedClient._classify(60) == "neutral"

    def test_boundary_80(self):
        assert FearGreedClient._classify(80) == "greed"


class TestGoldBias:
    @pytest.mark.asyncio
    async def test_fear_gives_positive_gold_bias(self, client):
        """Fear → positive gold bias (gold as safe haven)."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch(vix=35.0)
        assert result.gold_bias > 0

    @pytest.mark.asyncio
    async def test_greed_gives_negative_gold_bias(self, client):
        """Greed → negative gold bias (risk-on)."""
        client._fetch_alternative_me = AsyncMock(return_value=None)
        result = await client.fetch(vix=13.0)
        assert result.gold_bias < 0

    @pytest.mark.asyncio
    async def test_neutral_gives_near_zero_gold_bias(self, client):
        """Neutral F&G → gold bias near 0."""
        client._fetch_alternative_me = AsyncMock(return_value=50.0)
        result = await client.fetch(breadth_pct=50.0)
        assert -0.2 <= result.gold_bias <= 0.2
