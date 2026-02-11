"""
Redis pub/sub event bus for decoupled communication.
Fire-and-forget: if Redis is down, events are silently dropped.
The database is the source of truth, not Redis.
"""

import json

from loguru import logger


class EventBus:
    """
    Redis pub/sub event bus.

    Channels:
    - signal:{epic}     - New ML signals
    - trade:{epic}      - Trade executions
    - system:events     - System events (errors, circuit breaker)
    """

    def __init__(self):
        self._redis = None

    async def connect(self, redis_url: str) -> bool:
        """
        Connect to Redis.

        Returns:
            True if connected, False otherwise
        """
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis EventBus connected")
            return True
        except ImportError:
            logger.warning("redis package not installed, EventBus disabled")
            self._redis = None
            return False
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            self._redis = None
            return False

    async def publish(self, channel: str, data: dict) -> None:
        """
        Publish event to a channel. Fire-and-forget.
        Does nothing if Redis is not connected.
        """
        if self._redis is None:
            return
        try:
            await self._redis.publish(channel, json.dumps(data, default=str))
        except Exception as e:
            logger.debug(f"Event publish failed on {channel}: {e}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
            logger.info("Redis EventBus closed")

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        return self._redis is not None


# Singleton instance
event_bus = EventBus()
