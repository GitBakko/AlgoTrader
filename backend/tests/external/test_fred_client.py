"""Tests for FREDClient (12 economic indicator series)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.external.fred_client import FREDClient, SERIES_FIELD_MAP, SERIES_IDS


@pytest.fixture
def client():
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 60
        mock_settings.return_value.fred_api_key = "test_key"
        c = FREDClient(cache_ttl_minutes=1440)
    return c


@pytest.fixture
def client_no_key():
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 60
        mock_settings.return_value.fred_api_key = ""
        c = FREDClient(cache_ttl_minutes=1440)
    return c


def _mock_fred_response(series_id: str, value: str = "5.25") -> dict:
    """Create a mock FRED API response."""
    return {
        "observations": [
            {"date": "2026-03-07", "value": value}
        ]
    }


class TestFREDClientFetch:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_defaults(self, client_no_key):
        """No API key → empty FREDData with all None."""
        result = await client_no_key.fetch()
        assert result.fed_funds_rate is None
        assert result.real_yield_10y is None
        assert result.timestamp is None

    @pytest.mark.asyncio
    async def test_successful_fetch_all_series(self, client):
        """All 12 series return valid values."""
        mock_client = MagicMock()
        mock_client.is_closed = False
        responses = {}
        for sid in SERIES_IDS:
            responses[sid] = _mock_fred_response(sid, "3.14")

        async def mock_get(url, params=None):
            sid = params["series_id"]
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = responses[sid]
            return resp

        mock_client.get = mock_get
        client._client = mock_client

        result = await client.fetch()
        assert result.fed_funds_rate == 3.14
        assert result.yield_spread_10y2y == 3.14
        assert result.high_yield_spread == 3.14
        assert result.consumer_sentiment == 3.14
        assert result.unemployment_rate == 3.14
        assert result.nonfarm_payrolls == 3.14
        assert result.real_yield_10y == 3.14
        assert result.breakeven_inflation == 3.14
        assert result.nominal_yield_10y == 3.14
        assert result.broad_dollar == 3.14
        assert result.vix_close == 3.14
        assert result.wti_crude == 3.14
        assert result.timestamp is not None

    @pytest.mark.asyncio
    async def test_partial_failure_graceful(self, client):
        """Some series fail → only available ones populated."""
        call_count = 0

        async def mock_get(url, params=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                resp.json.return_value = _mock_fred_response(params["series_id"], "5.0")
                return resp
            raise httpx.HTTPError("timeout")

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = mock_get
        client._client = mock_client

        result = await client.fetch()
        # First 3 series (DFF, T10Y2Y, BAMLH0A0HYM2) succeed
        assert result.fed_funds_rate == 5.0
        assert result.yield_spread_10y2y == 5.0
        assert result.high_yield_spread == 5.0
        # Rest fail → None
        assert result.consumer_sentiment is None

    @pytest.mark.asyncio
    async def test_dot_value_treated_as_missing(self, client):
        """FRED returns '.' for missing data → treated as None."""
        async def mock_get(url, params=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"observations": [{"date": "2026-03-07", "value": "."}]}
            return resp

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = mock_get
        client._client = mock_client

        result = await client.fetch()
        assert result.fed_funds_rate is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, client):
        """Second fetch uses cache."""
        call_count = 0

        async def mock_get(url, params=None):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = _mock_fred_response(params["series_id"])
            return resp

        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.get = mock_get
        client._client = mock_client

        await client.fetch()
        first_call_count = call_count
        await client.fetch()  # Should hit cache
        assert call_count == first_call_count  # No new calls


class TestFREDClientConstants:
    def test_12_series_defined(self):
        assert len(SERIES_IDS) == 12

    def test_field_map_covers_all_series(self):
        assert set(SERIES_FIELD_MAP.keys()) == set(SERIES_IDS)

    def test_field_names_match_fred_data(self):
        from src.external.sil_schemas import FREDData
        fred = FREDData()
        for field_name in SERIES_FIELD_MAP.values():
            assert hasattr(fred, field_name), f"FREDData missing field: {field_name}"
