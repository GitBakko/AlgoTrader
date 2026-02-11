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

# Base prices for mock ticker (paper mode)
_BASE_PRICES = {
    "XAUUSD": 2000.0,
    "BTCUSD": 50000.0,
    "US500": 5000.0,
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

    try:
        while True:
            try:
                tick = await asyncio.wait_for(quote_queue.get(), timeout=5.0)
                await websocket.send_json(tick)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Broker price stream ended: {e}")
    finally:
        if on_quote in listeners:
            listeners.remove(on_quote)


async def prices_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time price streaming."""
    await ws_manager.connect(websocket, "prices")
    try:
        # Check if broker WebSocket is available
        broker_ws = getattr(websocket.app.state, "broker_ws_client", None)
        if broker_ws and getattr(broker_ws, "_connected", False):
            await _broker_price_stream(websocket, broker_ws)
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
