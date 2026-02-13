"""Tests for EventBus (Redis pub/sub)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.event_bus import EventBus


@pytest.mark.asyncio
class TestEventBus:
    async def test_not_connected_initially(self):
        bus = EventBus()
        assert bus.is_connected is False

    async def test_publish_when_not_connected_is_noop(self):
        bus = EventBus()
        # Should not raise
        await bus.publish("test:channel", {"key": "value"})

    async def test_close_when_not_connected_is_noop(self):
        bus = EventBus()
        await bus.close()
        assert bus.is_connected is False

    async def test_connect_with_import_error(self):
        bus = EventBus()
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            with patch("builtins.__import__", side_effect=ImportError("no redis")):
                result = await bus.connect("redis://localhost:6379/0")
        assert result is False
        assert bus.is_connected is False

    async def test_connect_with_connection_error(self):
        bus = EventBus()
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = ConnectionError("refused")
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await bus.connect("redis://localhost:6379/0")
        assert result is False

    async def test_publish_with_redis_error(self):
        bus = EventBus()
        bus._redis = AsyncMock()
        bus._redis.publish.side_effect = Exception("publish failed")
        # Should not raise, just log
        await bus.publish("channel", {"data": 1})

    async def test_close_with_redis_error(self):
        bus = EventBus()
        bus._redis = AsyncMock()
        bus._redis.aclose.side_effect = Exception("close failed")
        await bus.close()
        assert bus._redis is None

    async def test_publish_success(self):
        bus = EventBus()
        bus._redis = AsyncMock()
        await bus.publish("test:ch", {"msg": "hello"})
        bus._redis.publish.assert_called_once()

    async def test_close_success(self):
        bus = EventBus()
        mock_redis = AsyncMock()
        bus._redis = mock_redis
        await bus.close()
        mock_redis.aclose.assert_called_once()
        assert bus._redis is None
