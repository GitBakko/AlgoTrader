"""Tests for SIL base client."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.external.sil_base_client import SILBaseClient


@pytest.fixture
def base_client():
    """Create a base client with 60-minute TTL."""
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 60
        client = SILBaseClient(name="test", cache_ttl_minutes=60)
    return client


class TestSILBaseClientCache:
    def test_empty_cache_returns_none(self, base_client):
        assert base_client._get_cached("key") is None

    def test_set_and_get_cache(self, base_client):
        base_client._set_cache("key", {"value": 42})
        result = base_client._get_cached("key")
        assert result == {"value": 42}

    def test_cache_valid_within_ttl(self, base_client):
        base_client._set_cache("key", "data")
        assert base_client._is_cache_valid("key") is True

    def test_cache_expired_beyond_ttl(self, base_client):
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=61)
        base_client._cache["key"] = (expired_time, "old_data")
        assert base_client._is_cache_valid("key") is False
        assert base_client._get_cached("key") is None

    def test_clear_specific_key(self, base_client):
        base_client._set_cache("a", 1)
        base_client._set_cache("b", 2)
        base_client._clear_cache("a")
        assert base_client._get_cached("a") is None
        assert base_client._get_cached("b") == 2

    def test_clear_all(self, base_client):
        base_client._set_cache("a", 1)
        base_client._set_cache("b", 2)
        base_client._clear_cache()
        assert base_client._get_cached("a") is None
        assert base_client._get_cached("b") is None

    def test_cache_age_minutes(self, base_client):
        base_client._set_cache("key", "data")
        age = base_client.cache_age_minutes("key")
        assert age is not None
        assert age < 1.0  # Just set, should be < 1 minute

    def test_cache_age_missing_key(self, base_client):
        assert base_client.cache_age_minutes("missing") is None


class TestSILBaseClientHTTP:
    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, base_client):
        client = await base_client._get_client()
        assert client is not None
        assert not client.is_closed
        await base_client.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, base_client):
        """Close on already-closed or never-opened client doesn't raise."""
        await base_client.close()  # Never opened
        await base_client.close()  # Double close

    @pytest.mark.asyncio
    async def test_close_and_reopen(self, base_client):
        client1 = await base_client._get_client()
        await base_client.close()
        client2 = await base_client._get_client()
        assert client2 is not client1


class TestSILBaseClientRepr:
    def test_repr(self, base_client):
        base_client._set_cache("fred", {})
        r = repr(base_client)
        assert "test" in r
        assert "fred" in r
