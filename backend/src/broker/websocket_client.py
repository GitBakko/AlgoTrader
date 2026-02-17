"""
Capital.com WebSocket streaming client.
Provides real-time market data (quotes, OHLC candles) via WebSocket.
"""

import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable

import websockets
from loguru import logger
from pydantic import BaseModel, Field
from websockets.exceptions import WebSocketException

from src.broker.client import BROKER_TO_EPIC, EPIC_TO_BROKER
from src.broker.exceptions import ConnectionError as BrokerConnectionError
from src.broker.session import SessionManager


# ===== WebSocket Models =====
class WSDestination(str, Enum):
    """WebSocket message destinations."""

    MARKET_DATA_SUBSCRIBE = "marketData.subscribe"
    MARKET_DATA_UNSUBSCRIBE = "marketData.unsubscribe"
    OHLC_SUBSCRIBE = "OHLCMarketData.subscribe"
    OHLC_UNSUBSCRIBE = "OHLCMarketData.unsubscribe"
    PING = "ping"


class QuoteData(BaseModel):
    """Real-time quote data."""

    epic: str
    bid: float
    offer: float = Field(alias="ofr")
    timestamp: datetime


class OHLCData(BaseModel):
    """Real-time OHLC candle data."""

    epic: str
    resolution: str
    timestamp: int = Field(alias="t")  # Unix timestamp in milliseconds
    open: float = Field(alias="o")
    high: float = Field(alias="h")
    low: float = Field(alias="l")
    close: float = Field(alias="c")
    type: str = "classic"
    price_type: str = Field(default="mid", alias="priceType")

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000.0)


# ===== WebSocket Client =====
class CapitalComWebSocketClient:
    """
    Capital.com WebSocket client for real-time market data streaming.
    Supports quotes, OHLC candles, automatic reconnection, and keep-alive.
    """

    def __init__(
        self,
        ws_url: str,
        session_manager: SessionManager,
        max_reconnect_attempts: int = 5,
        reconnect_delay_seconds: int = 5,
    ):
        """
        Initialize WebSocket client.

        Args:
            ws_url: WebSocket URL
            session_manager: Session manager for authentication tokens
            max_reconnect_attempts: Maximum reconnection attempts
            reconnect_delay_seconds: Base delay between reconnection attempts
        """
        self.ws_url = ws_url
        self.session_manager = session_manager
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay_seconds = reconnect_delay_seconds

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = False
        self._subscribed_quotes: set[str] = set()
        self._subscribed_ohlc: dict[str, list[str]] = {}  # epic -> [resolutions]

        # Event handlers
        self._quote_handler: Callable[[QuoteData], None] | None = None
        self._ohlc_handler: Callable[[OHLCData], None] | None = None

        # Background tasks
        self._receive_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None

        # Reconnection guard — prevents unlimited concurrent connect() tasks
        self._reconnecting = False

    def on_quote(self, handler: Callable[[QuoteData], None]) -> None:
        """
        Register callback for quote events.

        Args:
            handler: Async callback function that receives QuoteData
        """
        self._quote_handler = handler

    def on_ohlc(self, handler: Callable[[OHLCData], None]) -> None:
        """
        Register callback for OHLC candle events.

        Args:
            handler: Async callback function that receives OHLCData
        """
        self._ohlc_handler = handler

    async def connect(self) -> None:
        """
        Connect to WebSocket server with automatic reconnection.

        Raises:
            BrokerConnectionError: If connection fails after max retries
        """
        # Cancel any existing background tasks before reconnecting
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()

        for attempt in range(self.max_reconnect_attempts):
            try:
                logger.info(f"🔌 Connecting to Capital.com WebSocket (attempt {attempt + 1})")

                # Close existing socket if any
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

                self._ws = await websockets.connect(
                    self.ws_url, ping_interval=None  # We handle pings manually
                )

                self._connected = True
                self._reconnecting = False  # Reset reconnection guard
                logger.success("✅ WebSocket connected")

                # Start background tasks
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._ping_task = asyncio.create_task(self._ping_loop())

                # Re-subscribe to previously subscribed instruments
                await self._resubscribe()

                return

            except Exception as e:
                logger.error(f"WebSocket connection failed: {e}")

                if attempt < self.max_reconnect_attempts - 1:
                    delay = self.reconnect_delay_seconds * (2**attempt)  # Exponential backoff
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    self._reconnecting = False
                    self._connected = False
                    raise BrokerConnectionError(f"Failed to connect after {self.max_reconnect_attempts} attempts")

    async def _safe_reconnect(self) -> None:
        """
        Safely trigger reconnection with a guard to prevent reconnection storms.
        Only one reconnection attempt runs at a time.
        """
        if self._reconnecting:
            logger.debug("Reconnection already in progress, skipping duplicate")
            return

        self._reconnecting = True
        self._connected = False
        logger.info("🔄 Scheduling safe WebSocket reconnection...")

        try:
            await asyncio.sleep(self.reconnect_delay_seconds)  # Brief cooldown
            await self.connect()
        except BrokerConnectionError:
            logger.error(
                "❌ WebSocket reconnection failed after all attempts. "
                "Will retry on next trading iteration."
            )
            self._reconnecting = False
        except Exception as e:
            logger.error(f"❌ Unexpected error during reconnection: {e}")
            self._reconnecting = False

    async def disconnect(self) -> None:
        """Disconnect from WebSocket server."""
        logger.info("Disconnecting from WebSocket...")

        self._connected = False

        # Cancel background tasks
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        logger.success("✅ WebSocket disconnected")

    async def subscribe_quotes(self, epics: list[str]) -> None:
        """
        Subscribe to real-time quote updates for instruments.

        Args:
            epics: List of internal epic codes (max 40 total subscriptions).
                   Internal names (e.g. XAUUSD) are mapped to broker names
                   (e.g. GOLD) automatically.
        """
        if len(self._subscribed_quotes) + len(epics) > 40:
            raise ValueError("Maximum 40 WebSocket subscriptions allowed")

        # Map internal names → broker names for the API
        broker_epics = [EPIC_TO_BROKER.get(e, e) for e in epics]

        tokens = await self.session_manager.get_tokens()

        message = {
            "destination": WSDestination.MARKET_DATA_SUBSCRIBE.value,
            "correlationId": f"quote-sub-{datetime.now().timestamp()}",
            "cst": tokens.cst,
            "securityToken": tokens.security_token,
            "payload": {"epics": broker_epics},
        }

        await self._send(message)
        self._subscribed_quotes.update(epics)  # Track internal names
        logger.info(f"📊 Subscribed to quotes: {epics} (broker: {broker_epics})")

    async def unsubscribe_quotes(self, epics: list[str]) -> None:
        """
        Unsubscribe from quote updates.

        Args:
            epics: List of internal epic codes to unsubscribe
        """
        broker_epics = [EPIC_TO_BROKER.get(e, e) for e in epics]

        tokens = await self.session_manager.get_tokens()

        message = {
            "destination": WSDestination.MARKET_DATA_UNSUBSCRIBE.value,
            "correlationId": f"quote-unsub-{datetime.now().timestamp()}",
            "cst": tokens.cst,
            "securityToken": tokens.security_token,
            "payload": {"epics": broker_epics},
        }

        await self._send(message)
        self._subscribed_quotes.difference_update(epics)
        logger.info(f"Unsubscribed from quotes: {epics}")

    async def subscribe_ohlc(self, epics: list[str], resolutions: list[str]) -> None:
        """
        Subscribe to real-time OHLC candle updates.

        Args:
            epics: List of internal epic codes
            resolutions: List of resolutions (e.g., ["MINUTE_5", "HOUR"])
        """
        broker_epics = [EPIC_TO_BROKER.get(e, e) for e in epics]

        tokens = await self.session_manager.get_tokens()

        message = {
            "destination": WSDestination.OHLC_SUBSCRIBE.value,
            "correlationId": f"ohlc-sub-{datetime.now().timestamp()}",
            "cst": tokens.cst,
            "securityToken": tokens.security_token,
            "payload": {"epics": broker_epics, "resolutions": resolutions, "type": "classic"},
        }

        await self._send(message)

        # Track subscriptions with internal names
        for epic in epics:
            if epic not in self._subscribed_ohlc:
                self._subscribed_ohlc[epic] = []
            self._subscribed_ohlc[epic].extend(resolutions)

        logger.info(f"📊 Subscribed to OHLC: {epics} @ {resolutions}")

    async def _send(self, message: dict[str, Any]) -> None:
        """Send message to WebSocket."""
        if not self._connected or not self._ws:
            raise BrokerConnectionError("WebSocket not connected")

        await self._ws.send(json.dumps(message))

    async def _receive_loop(self) -> None:
        """Background task to receive and process WebSocket messages."""
        try:
            while self._connected and self._ws:
                try:
                    message = await self._ws.recv()
                    await self._handle_message(message)
                except asyncio.CancelledError:
                    break
                except WebSocketException as e:
                    logger.error(f"WebSocket error in receive loop: {e}")
                    # Attempt reconnection with guard to prevent storm
                    await self._safe_reconnect()
                    break

        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            if self._connected:
                await self._safe_reconnect()

    async def _handle_message(self, message: str) -> None:
        """
        Handle incoming WebSocket message.

        Args:
            message: Raw WebSocket message (JSON string)
        """
        try:
            data = json.loads(message)
            destination = data.get("destination")

            if destination == "quote":
                # Real-time quote — map broker epic back to internal name
                payload = data.get("payload", {})
                if "epic" in payload:
                    payload["epic"] = BROKER_TO_EPIC.get(payload["epic"], payload["epic"])
                quote = QuoteData(**payload)
                if self._quote_handler:
                    await self._quote_handler(quote)

            elif destination == "ohlc.event":
                # OHLC candle — map broker epic back to internal name
                payload = data.get("payload", {})
                if "epic" in payload:
                    payload["epic"] = BROKER_TO_EPIC.get(payload["epic"], payload["epic"])
                ohlc = OHLCData(**payload)
                if self._ohlc_handler:
                    await self._ohlc_handler(ohlc)

            elif destination == "oob.event":
                # Out-of-band event (account updates, fills, etc.)
                logger.debug(f"OOB event: {data}")

            else:
                logger.debug(f"Unhandled WebSocket message: {destination}")

        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    async def _ping_loop(self) -> None:
        """Background task to send keep-alive pings every 5 minutes."""
        ping_interval = 5 * 60  # 5 minutes

        try:
            while self._connected:
                await asyncio.sleep(ping_interval)

                try:
                    tokens = await self.session_manager.get_tokens()
                    ping_message = {
                        "destination": WSDestination.PING.value,
                        "correlationId": f"ping-{datetime.now().timestamp()}",
                        "cst": tokens.cst,
                        "securityToken": tokens.security_token,
                    }
                    await self._send(ping_message)
                    logger.debug("📡 WebSocket ping sent")

                except Exception as e:
                    logger.error(f"Error sending WebSocket ping: {e}")

        except asyncio.CancelledError:
            pass

    async def _resubscribe(self) -> None:
        """Re-subscribe to all previously subscribed instruments after reconnection."""
        if self._subscribed_quotes:
            await self.subscribe_quotes(list(self._subscribed_quotes))

        for epic, resolutions in self._subscribed_ohlc.items():
            await self.subscribe_ohlc([epic], resolutions)
