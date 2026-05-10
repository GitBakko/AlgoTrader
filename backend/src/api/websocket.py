"""
WebSocket manager for real-time price streaming and trade notifications.
Dual-mode: uses broker WebSocket when available, falls back to mock random walk.
Auto-reconnects to broker WS when mock is active.
Sends initial price snapshot on connect so closed markets have prices too.
"""

import asyncio
import random
import time
from datetime import UTC, datetime

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from src.utils.constants import ALL_ASSETS

# Dashboard v2 (D2:A) — per-connection round-trip latency, ms.
# Populated by _latency_tracker on pong reply; read by the price streams
# to piggyback a {type: 'ws_status', latency_ms: ...} message.
ws_latency_state: dict[int, int] = {}
# Interval between server-initiated ping frames on /ws/prices.
_WS_PING_INTERVAL_SECONDS = 10


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
        """Send data to all connections on a channel.

        H5-API fix: snapshot the connection list at the start so a
        cooperative-async ``connect()`` interleaved between iteration
        and the dead-cleanup rebuild can't drop the new client.
        """
        if channel not in self._connections:
            return
        # Snapshot — keep iteration immune to concurrent connect/disconnect.
        connections = list(self._connections.get(channel, []))
        dead = []
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        # Clean up dead connections in a single pass against the live list.
        if dead:
            dead_set = {id(ws) for ws in dead}
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

# Global WS status tracking (readable from status endpoint)
ws_price_status = {
    "source": "disconnected",  # "broker" | "mock" | "disconnected"
    "reconnect_attempts": 0,
    "max_reconnect_attempts": 12,  # ~6 minutes of retries (30s each)
    "last_reconnect_at": None,
}

# Base prices for mock ticker (paper mode) — updated 2026-02-22 from Capital.com
_BASE_PRICES = {
    "XAUUSD": 5107.0,
    "BTCUSD": 68180.0,
    "US500": 6910.0,
    "WTIUSD": 66.31,
    "EURUSD": 1.178,
    "NVDA": 189.3,
    "TSLA": 411.0,
    "XAGUSD": 84.6,
    "DE40": 25233.0,
    "SOLUSD": 85.15,
    "ETHUSD": 1980.0,
    "BNBUSD": 622.6,
    "DOGUSD": 0.0975,
    "DASHUSD": 33.9,
    "ICPUSD": 2.16,
    "NATGAS": 2.992,
    "COPPER": 5.84,
    "PLATINUM": 2067.0,
    "GBPUSD": 1.349,
    "USDJPY": 155.05,
    "NAS100": 227.0,
}

# Reconnect interval (seconds) between broker WS reconnect attempts during mock
_RECONNECT_INTERVAL = 30


async def _latency_tracker(websocket: WebSocket) -> None:
    """
    Reads pong replies from the frontend on /ws/prices and records the
    measured round-trip latency in ws_latency_state, keyed by the
    WebSocket identity. Price streams piggyback the latest value on
    their periodic ws_status broadcasts.
    """
    conn_id = id(websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            if mtype == "pong":
                server_ts = msg.get("server_ts")
                if isinstance(server_ts, (int, float)):
                    rtt = int(time.time() * 1000 - float(server_ts))
                    if 0 <= rtt < 60_000:  # discard impossible/stale values
                        ws_latency_state[conn_id] = rtt
            # "ping" from client also treated as keepalive — reply pong
            elif mtype == "ping":
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    pass
    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.debug(f"latency tracker ended: {e}")
    finally:
        ws_latency_state.pop(conn_id, None)


async def _ping_broadcaster(websocket: WebSocket) -> None:
    """
    Emits a server-initiated ping every _WS_PING_INTERVAL_SECONDS on
    /ws/prices, then rebroadcasts ws_status with the latest latency_ms
    so every live client always sees fresh timing.
    """
    conn_id = id(websocket)
    try:
        while True:
            server_ts = int(time.time() * 1000)
            try:
                await websocket.send_json({"type": "ping", "server_ts": server_ts})
            except Exception:
                return
            await asyncio.sleep(0.5)  # let client reply before broadcasting status
            latency = ws_latency_state.get(conn_id)
            try:
                await websocket.send_json({
                    "type": "ws_status",
                    "price_source": ws_price_status.get("source", "unknown"),
                    "reconnect_attempts": ws_price_status.get("reconnect_attempts", 0),
                    "max_reconnect_attempts": ws_price_status.get("max_reconnect_attempts", 12),
                    "latency_ms": latency,
                })
            except Exception:
                return
            await asyncio.sleep(_WS_PING_INTERVAL_SECONDS - 0.5)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.debug(f"ping broadcaster ended: {e}")


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
                    "timestamp": datetime.now(UTC).isoformat(),
                    "price_source": "mock",
                }
                await websocket.send_json(tick)

            await asyncio.sleep(1.0)  # 1 tick per second per asset
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Price stream ended: {e}")


async def _mock_price_stream_with_reconnect(websocket: WebSocket, app_state) -> None:
    """
    Send mock prices while periodically attempting to reconnect to broker WS.
    When reconnection succeeds, raises _BrokerReconnected to switch back.
    """
    prices = dict(_BASE_PRICES)
    ticks_since_reconnect_check = 0
    ticks_per_reconnect = _RECONNECT_INTERVAL  # ~30s (1 cycle/s × 30)

    ws_price_status["source"] = "mock"
    ws_price_status["reconnect_attempts"] = 0

    try:
        while True:
            for epic, base in prices.items():
                change = base * random.uniform(-0.001, 0.001)
                prices[epic] = round(base + change, 2)
                spread = base * 0.0002

                tick = {
                    "epic": epic,
                    "bid": round(prices[epic], 2),
                    "offer": round(prices[epic] + spread, 2),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "price_source": "mock",
                }
                await websocket.send_json(tick)

            ticks_since_reconnect_check += 1
            await asyncio.sleep(1.0)

            # Periodically attempt broker WS reconnection
            if ticks_since_reconnect_check >= ticks_per_reconnect:
                ticks_since_reconnect_check = 0
                max_attempts = ws_price_status["max_reconnect_attempts"]

                if ws_price_status["reconnect_attempts"] < max_attempts:
                    ws_price_status["reconnect_attempts"] += 1
                    ws_price_status["last_reconnect_at"] = datetime.now(UTC).isoformat()
                    attempt = ws_price_status["reconnect_attempts"]

                    # Send status update to frontend
                    await websocket.send_json(
                        {
                            "type": "ws_status",
                            "price_source": "mock",
                            "reconnect_attempts": attempt,
                            "max_reconnect_attempts": max_attempts,
                            "latency_ms": ws_latency_state.get(id(websocket)),
                        }
                    )

                    broker_ws = getattr(app_state, "broker_ws_client", None)
                    if broker_ws:
                        try:
                            logger.info(
                                f"Attempting broker WS reconnect ({attempt}/{max_attempts})..."
                            )
                            await broker_ws.connect()
                            if getattr(broker_ws, "_connected", False):
                                logger.success(f"Broker WS reconnected after {attempt} attempts!")
                                ws_price_status["source"] = "broker"
                                ws_price_status["reconnect_attempts"] = 0
                                # Notify frontend of reconnection
                                await websocket.send_json(
                                    {
                                        "type": "ws_status",
                                        "price_source": "broker",
                                        "reconnect_attempts": 0,
                                        "max_reconnect_attempts": max_attempts,
                                        "latency_ms": ws_latency_state.get(id(websocket)),
                                    }
                                )
                                return  # Exit mock → caller switches to broker stream
                        except Exception as e:
                            logger.warning(
                                f"Broker WS reconnect attempt {attempt}/{max_attempts} "
                                f"failed: {e}"
                            )
                    else:
                        logger.debug("No broker WS client available for reconnect")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Mock price stream ended: {e}")


async def _broker_price_stream(websocket: WebSocket, broker_ws) -> None:
    """
    Forward real broker quotes to the frontend WebSocket.
    Uses an asyncio.Queue per connection so multiple frontend clients
    can share the single broker WebSocket without overwriting handlers.
    """
    quote_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    def on_quote(quote) -> None:
        try:
            quote_queue.put_nowait(
                {
                    "epic": quote.epic,
                    "bid": quote.bid,
                    "offer": quote.offer,
                    "timestamp": (
                        quote.timestamp.isoformat()
                        if quote.timestamp
                        else datetime.now(UTC).isoformat()
                    ),
                    "price_source": "broker",
                }
            )
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

    ws_price_status["source"] = "broker"
    ws_price_status["reconnect_attempts"] = 0

    # Send initial status (include latency if we already have a reading).
    await websocket.send_json(
        {
            "type": "ws_status",
            "price_source": "broker",
            "reconnect_attempts": 0,
            "max_reconnect_attempts": ws_price_status["max_reconnect_attempts"],
            "latency_ms": ws_latency_state.get(id(websocket)),
        }
    )

    try:
        while True:
            try:
                tick = await asyncio.wait_for(quote_queue.get(), timeout=5.0)
                await websocket.send_json(tick)
                consecutive_heartbeats = 0  # Reset on real data
            except TimeoutError:
                consecutive_heartbeats += 1
                # Check if broker WS is still connected
                if (
                    not getattr(broker_ws, "_connected", False)
                    or consecutive_heartbeats >= max_heartbeats
                ):
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


async def _send_initial_price_snapshot(websocket: WebSocket, app_state) -> None:
    """
    Fetch current prices for ALL assets from the broker REST API and send
    them as an initial snapshot.  This ensures the frontend has prices even
    for closed markets that won't emit WebSocket ticks.
    """
    broker = getattr(app_state, "broker_client", None)
    if not broker:
        return

    from src.broker.client import EPIC_TO_BROKER

    sent = 0
    for epic in ALL_ASSETS:
        try:
            EPIC_TO_BROKER.get(epic, epic)
            details = await broker.get_market_details(epic)
            if not isinstance(details, dict):
                continue
            snap = details.get("snapshot", {})
            bid = snap.get("bid")
            offer = snap.get("offer")
            if bid is not None and offer is not None:
                await websocket.send_json(
                    {
                        "epic": epic,
                        "bid": bid,
                        "offer": offer,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "price_source": "broker",
                    }
                )
                sent += 1
        except WebSocketDisconnect:
            return  # Client gone
        except Exception as e:
            logger.debug(f"Snapshot price fetch failed for {epic}: {e}")
        # Small delay between API calls to respect rate limits (10 req/s)
        await asyncio.sleep(0.12)

    if sent:
        logger.info(f"Sent initial price snapshot: {sent}/{len(ALL_ASSETS)} assets")


async def prices_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time price streaming.

    Sends initial price snapshot via REST API, then streams live ticks.
    Tries broker WS first; if it disconnects, falls back to mock with
    automatic reconnection attempts. Loops between broker → mock → broker.

    Dashboard v2 (D2:A): spawns two background tasks per connection —
    `_latency_tracker` reads pong replies, `_ping_broadcaster` emits
    periodic pings + ws_status with latency_ms piggybacked.
    """
    await ws_manager.connect(websocket, "prices")
    tracker_task = asyncio.create_task(_latency_tracker(websocket))
    pinger_task = asyncio.create_task(_ping_broadcaster(websocket))
    try:
        # Send initial prices for ALL assets (including closed markets)
        try:
            await _send_initial_price_snapshot(websocket, websocket.app.state)
        except Exception as e:
            logger.warning(f"Initial price snapshot failed: {e}")
        while True:
            broker_ws = getattr(websocket.app.state, "broker_ws_client", None)

            if broker_ws and getattr(broker_ws, "_connected", False):
                try:
                    await _broker_price_stream(websocket, broker_ws)
                except _BrokerDisconnected:
                    logger.info("Switching to mock prices with auto-reconnect")
                    # Fall through to mock+reconnect below
                else:
                    break  # Clean exit (client disconnected)

            # Mock with reconnect — returns when broker reconnects
            await _mock_price_stream_with_reconnect(websocket, websocket.app.state)

            # Check if reconnect succeeded (source changed to "broker")
            if ws_price_status["source"] == "broker":
                logger.info("Reconnected to broker, switching back to live prices")
                continue  # Loop back to _broker_price_stream
            else:
                break  # Max retries exhausted or client disconnected

    finally:
        for task in (tracker_task, pinger_task):
            if not task.done():
                task.cancel()
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


async def notifications_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time in-app notifications."""
    await ws_manager.connect(websocket, "notifications")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, "notifications")


async def training_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time training status updates."""
    await ws_manager.connect(websocket, "training")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, "training")


async def markets_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for per-epic market state updates (Dashboard v2).

    Broadcasts ``{type: 'swap_update', epic, rate_pct, notional, direction,
    source, ts}`` when paper_loop opens/closes a position or when the
    daily snapshot job runs. Frontend replaces the 30-60s polling of
    ``/api/markets/{epic}/overnight-swap`` with a passive subscription.
    """
    await ws_manager.connect(websocket, "markets")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, "markets")


async def broadcast_swap_update(
    epic: str,
    *,
    rate_pct: float | None,
    notional: float,
    direction: str,
    source: str,
    currency: str | None = None,
) -> None:
    """Push a single swap_update event to every /ws/markets subscriber.

    Safe to call from any async context — a bad channel state just
    silently drops. Callers do not need to await a response.
    """
    payload = {
        "type": "swap_update",
        "epic": epic,
        "rate_pct": rate_pct,
        "notional": notional,
        "direction": direction,
        "source": source,
        "currency": currency,
        "ts": datetime.now(UTC).isoformat(),
    }
    try:
        await ws_manager.broadcast("markets", payload)
    except Exception as e:
        logger.debug(f"broadcast_swap_update failed for {epic}: {e}")
