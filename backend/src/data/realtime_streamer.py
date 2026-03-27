"""
Real-time data streamer.
Receives WebSocket OHLC data, buffers in Redis, flushes to Parquet periodically.
"""

import asyncio
from datetime import datetime, timezone

import redis.asyncio as redis
from loguru import logger

from src.broker.websocket_client import CapitalComWebSocketClient, OHLCData
from src.data.models import DataSource, OHLCBar
from src.data.storage import ParquetStorageManager
from src.data.utils import timeframe_to_resolution
from src.utils.config import get_settings

# Resolution map: WS resolution string → our timeframe string
WS_RESOLUTION_TO_TIMEFRAME = {
    "MINUTE": "1min",
    "MINUTE_5": "5min",
    "MINUTE_15": "15min",
    "MINUTE_30": "30min",
    "HOUR": "1h",
    "HOUR_4": "4h",
    "DAY": "1d",
    "WEEK": "1w",
}


class RealtimeStreamer:
    """
    Streams real-time OHLC data from WebSocket to storage.

    Pipeline: WebSocket → In-memory buffer → Periodic flush to Parquet
    Optionally publishes to Redis pub/sub for other consumers.
    """

    def __init__(
        self,
        ws_client: CapitalComWebSocketClient,
        storage: ParquetStorageManager,
        redis_url: str | None = None,
        flush_interval_seconds: int = 60,
        flush_threshold: int = 100,
    ):
        """
        Args:
            ws_client: Capital.com WebSocket client
            storage: Parquet storage manager
            redis_url: Redis URL for pub/sub (optional)
            flush_interval_seconds: Seconds between periodic flushes
            flush_threshold: Flush when buffer exceeds this count
        """
        self.ws_client = ws_client
        self.storage = storage
        self.flush_interval = flush_interval_seconds
        self.flush_threshold = flush_threshold

        self._redis_url = redis_url or get_settings().redis_url
        self._redis: redis.Redis | None = None

        # In-memory buffer: {epic/timeframe: [OHLCBar]}
        self._buffer: dict[str, list[OHLCBar]] = {}
        self._buffer_lock = asyncio.Lock()

        # Control
        self._running = False
        self._flush_task: asyncio.Task | None = None

        # Stats
        self._received_count = 0
        self._flushed_count = 0

    async def start(
        self,
        epics: list[str] | None = None,
        timeframes: list[str] | None = None,
    ) -> None:
        """
        Start streaming real-time data.

        Args:
            epics: Assets to stream (default: XAUUSD, BTCUSD, US500)
            timeframes: Timeframes to stream (default: 1h, 4h)
        """
        if epics is None:
            epics = ["XAUUSD", "BTCUSD", "US500"]
        if timeframes is None:
            timeframes = ["1h", "4h"]

        # Convert timeframes to WS resolutions
        resolutions = []
        for tf in timeframes:
            res = timeframe_to_resolution(tf)
            resolutions.append(res.value)

        # Connect Redis (optional)
        try:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis connected for real-time pub/sub")
        except Exception as e:
            logger.warning(f"Redis not available, skipping pub/sub: {e}")
            self._redis = None

        # Register OHLC handler
        self.ws_client.on_ohlc(self._on_ohlc_data)

        # Subscribe to OHLC data
        await self.ws_client.subscribe_ohlc(epics, resolutions)

        # Start flush loop
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

        logger.info(
            f"Streaming started: {epics} @ {timeframes} "
            f"(flush every {self.flush_interval}s or {self.flush_threshold} candles)"
        )

    async def stop(self) -> None:
        """Stop streaming and flush remaining buffer."""
        logger.info("Stopping real-time streamer...")
        self._running = False

        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()

        # Final flush
        await self._flush_all()

        # Close Redis
        if self._redis:
            await self._redis.aclose()
            self._redis = None

        logger.info(
            f"Streamer stopped. Total received: {self._received_count}, "
            f"flushed: {self._flushed_count}"
        )

    async def _on_ohlc_data(self, data: OHLCData) -> None:
        """Handle incoming OHLC data from WebSocket."""
        timeframe = WS_RESOLUTION_TO_TIMEFRAME.get(data.resolution)
        if timeframe is None:
            logger.warning(f"Unknown resolution: {data.resolution}")
            return

        bar = OHLCBar(
            timestamp=data.datetime.replace(tzinfo=timezone.utc),
            open=data.open,
            high=data.high,
            low=data.low,
            close=data.close,
            volume=None,  # WS OHLC doesn't include volume
            epic=data.epic,
            timeframe=timeframe,
            source=DataSource.REALTIME,
        )

        # Buffer the candle
        buffer_key = f"{data.epic}/{timeframe}"
        async with self._buffer_lock:
            if buffer_key not in self._buffer:
                self._buffer[buffer_key] = []
            self._buffer[buffer_key].append(bar)

        self._received_count += 1

        # Publish to Redis pub/sub for other consumers
        if self._redis:
            try:
                await self._redis.publish(
                    f"ohlc:{data.epic}:{timeframe}",
                    bar.model_dump_json(),
                )
            except Exception as e:
                logger.debug(f"Redis publish failed: {e}")

        # Check if buffer needs flushing (read under lock)
        async with self._buffer_lock:
            total_buffered = sum(len(v) for v in self._buffer.values())
        if total_buffered >= self.flush_threshold:
            await self._flush_all()

    async def _flush_loop(self) -> None:
        """Periodically flush buffer to Parquet."""
        try:
            while self._running:
                await asyncio.sleep(self.flush_interval)
                await self._flush_all()
        except asyncio.CancelledError:
            pass

    async def _flush_all(self) -> None:
        """Flush all buffered candles to Parquet storage."""
        async with self._buffer_lock:
            if not self._buffer:
                return

            buffer_copy = dict(self._buffer)
            self._buffer.clear()

        for key, candles in buffer_copy.items():
            if not candles:
                continue

            epic, timeframe = key.split("/", 1)
            try:
                new_count = self.storage.append_candles(candles, epic, timeframe)
                self._flushed_count += new_count
                logger.debug(f"Flushed {len(candles)} candles for {key} " f"({new_count} new)")
            except Exception as e:
                logger.error(f"Failed to flush {key}: {e}")
                # Put candles back in buffer
                async with self._buffer_lock:
                    if key not in self._buffer:
                        self._buffer[key] = []
                    self._buffer[key] = candles + self._buffer[key]

    @property
    def stats(self) -> dict:
        """Current streaming statistics."""
        return {
            "running": self._running,
            "received": self._received_count,
            "flushed": self._flushed_count,
            "buffered": sum(len(v) for v in self._buffer.values()),
            "buffer_keys": list(self._buffer.keys()),
        }
