"""
Signal Intelligence Layer (SIL) — Base client.
Shared caching, HTTP client management, and graceful degradation.
"""

from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from src.utils.config import get_settings


class SILBaseClient:
    """Base class for SIL external clients with caching and graceful degradation."""

    def __init__(self, name: str, cache_ttl_minutes: int | None = None):
        self.name = name
        self._settings = get_settings()
        self._cache_ttl = cache_ttl_minutes or self._settings.sil_cache_ttl_minutes
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached entry is still within TTL."""
        if key not in self._cache:
            return False
        cached_at, _ = self._cache[key]
        age_minutes = (datetime.now(timezone.utc) - cached_at).total_seconds() / 60
        return age_minutes < self._cache_ttl

    def _get_cached(self, key: str) -> Any | None:
        """Return cached data if valid, else None."""
        if self._is_cache_valid(key):
            _, data = self._cache[key]
            return data
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        """Store data in cache with current timestamp."""
        self._cache[key] = (datetime.now(timezone.utc), data)

    def _clear_cache(self, key: str | None = None) -> None:
        """Clear specific key or entire cache."""
        if key is not None:
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def cache_age_minutes(self, key: str) -> float | None:
        """Return age of cached entry in minutes, or None if not cached."""
        if key not in self._cache:
            return None
        cached_at, _ = self._cache[key]
        return (datetime.now(timezone.utc) - cached_at).total_seconds() / 60

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def __repr__(self) -> str:
        cached_keys = list(self._cache.keys())
        return f"<{self.__class__.__name__} name={self.name!r} cached={cached_keys}>"
