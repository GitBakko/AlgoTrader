"""
WebSocket manager for real-time price streaming and trade notifications.
Dual-mode: uses broker WebSocket when available, falls back to mock random walk.
"""

import asyncio
import json
import random
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger


class _BrokerDisconnected(Exception):
    """Sentinel raised when broker WS drops so prices_endpoint falls back to mock."""


class ConnectionManager:
    """Manages active WebSocket connections per channel."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = []
        self._connections[channel].append(websocket)
        logger.info(f"WebSocket connected to channel: {channel}")

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """Remove a WebSocket connection."""
        if channel in self._connections:
            self._connections[channel] = [
                ws for ws in self._connections[channel] if ws != websocket
            ]
        logger.info(f"WebSocket disconnected from channel: {channel}")

    async def broadcast(self, channel: str, data: dict) -> None:
        """Send data to all connections on a channel."""
        if channel not in self._connections:
            return
        dead = []
        for ws in self._connections[channel]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        # Clean up dead connections in a single pass
        if dead:
            dead_set = set(id(ws) for ws in dead)
            self._connections[channel] = [
                ws for ws in self._connections[channel] if id(ws) not in dead_set
            ]

    def get_connection_count(self, channel: str | None = None) -> int:
        """Get number of active connections."""
        if channel:
            return len(self._connections.get(channel, []))
        return sum(len(conns) for conns in self._connections.values())


# Singleton manager
ws_manager = ConnectionManager()

# Base prices for mock ticker (paper mode) — realistic Feb 2026 values
_BASE_PRICES = {
    "XAUUSD": 4994.0, "BTCUSD": 68500.0, "US500": 6836.0, "WTIUSD": 64.0,
    "EURUSD": 1.19, "NVDA": 192.0, "TSLA": 431.0, "XAGUSD": 83.0, "DE40": 25205.0,
    "SOLUSD": 88.0, "ETHUSD": 2085.0, "BNBUSD": 632.0, "DOGUSD": 0.11,
    "DASHUSD": 39.8, "ICPUSD": 2.55, "NATGAS": 3.09, "COPPER": 5.84,
    "PLATINUM": 2067.0, "GBPUSD": 1.37, "USDJPY": 152.7, "NAS100": 227.0,
}


async def _mock_price_stream(websocket: WebSocket) -> None:
    """Generate mock price ticks for paper trading mode."""
    prices = dict(_BASE_PRICES)

    try:
        while True:
            for epic, base in prices.items():
                # Random walk: +-0.1% per tick
                change = base * random.uniform(-0.001, 0.001)
                prices[epic] = round(base + change, 2)
                spread = base * 0.0002  # 0.02% spread

                tick = {
                    "epic": epic,
                    "bid": round(prices[epic], 2),
                    "offer": round(prices[epic] + spread, 2),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await websocket.send_json(tick)

            await asyncio.sleep(1.0)  # 1 tick per second per asset
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Price stream ended: {e}")


async def _broker_price_stream(websocket: WebSocket, broker_ws) -> None:
    """
    Forward real broker quotes to the frontend WebSocket.
    Uses an asyncio.Queue per connection so multiple frontend clients
    can share the single broker WebSocket without overwriting handlers.
    """
    quote_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    def on_quote(quote) -> None:
        try:
            quote_queue.put_nowait({
                "epic": quote.epic,
                "bid": quote.bid,
                "offer": quote.offer,
                "timestamp": quote.timestamp.isoformat() if quote.timestamp else
                    datetime.now(timezone.utc).isoformat(),
            })
        except asyncio.QueueFull:
            pass  # Drop if full — next tick arrives soon

    # Register as additional listener (fan-out pattern for multiple clients)
    listeners: list = getattr(broker_ws, "_quote_listeners", [])
    if not listeners:
        original_handler = getattr(broker_ws, "_quote_handler", None)
        broker_ws._quote_listeners = listeners

        async def _fan_out(quote):
            if original_handler:
                await original_handler(quote)
            for listener in list(listeners):
                listener(quote)

        broker_ws.on_quote(_fan_out)

    listeners.append(on_quote)

    consecutive_heartbeats = 0
    max_heartbeats = 6  # 6 * 5s = 30s without data → broker is dead

    try:
        while True:
            try:
                tick = await asyncio.wait_for(quote_queue.get(), timeout=5.0)
                await websocket.send_json(tick)
                consecutive_heartbeats = 0  # Reset on real data
            except asyncio.TimeoutError:
                consecutive_heartbeats += 1
                # Check if broker WS is still connected
                if not getattr(broker_ws, "_connected", False) or consecutive_heartbeats >= max_heartbeats:
                    logger.warning(
                        f"Broker WS disconnected (connected={getattr(broker_ws, '_connected', False)}, "
                        f"heartbeats={consecutive_heartbeats}), falling back to mock prices"
                    )
                    raise _BrokerDisconnected()
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except _BrokerDisconnected:
        raise  # Propagate to prices_endpoint for fallback
    except Exception as e:
        logger.debug(f"Broker price stream ended: {e}")
    finally:
        if on_quote in listeners:
            listeners.remove(on_quote)


async def prices_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time price streaming.

    Tries broker WS first; if it disconnects mid-stream, falls back to mock.
    """
    await ws_manager.connect(websocket, "prices")
    try:
        # Check if broker WebSocket is available
        broker_ws = getattr(websocket.app.state, "broker_ws_client", None)
        if broker_ws and getattr(broker_ws, "_connected", False):
            try:
                await _broker_price_stream(websocket, broker_ws)
            except _BrokerDisconnected:
                logger.info("Switching to mock price stream after broker disconnect")
                await _mock_price_stream(websocket)
        else:
            await _mock_price_stream(websocket)
    finally:
        ws_manager.disconnect(websocket, "prices")


async def trades_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for trade event notifications."""
    await ws_manager.connect(websocket, "trades")
    try:
        while True:
            # Keep connection alive, waiting for broadcast events
            data = await websocket.receive_text()
            # Client can send ping/pong
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, "trades")
