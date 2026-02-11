"""
Unit tests for Capital.com WebSocket client.
Note: These are basic tests for initialization and callback registration.
Full WebSocket functionality testing requires integration tests with mock WebSocket server.
"""

import pytest

from src.broker.session import SessionManager
from src.broker.websocket_client import (
    CapitalComWebSocketClient,
    OHLCData,
    QuoteData,
    WSDestination,
)


@pytest.mark.unit
@pytest.mark.broker
class TestWebSocketEnums:
    """Test WebSocket enumerations."""

    def test_ws_destination_enum(self):
        """Test WSDestination enum values."""
        assert WSDestination.MARKET_DATA_SUBSCRIBE.value == "marketData.subscribe"
        assert WSDestination.MARKET_DATA_UNSUBSCRIBE.value == "marketData.unsubscribe"
        assert WSDestination.OHLC_SUBSCRIBE.value == "OHLCMarketData.subscribe"
        assert WSDestination.OHLC_UNSUBSCRIBE.value == "OHLCMarketData.unsubscribe"
        assert WSDestination.PING.value == "ping"


@pytest.mark.unit
@pytest.mark.broker
class TestWebSocketModels:
    """Test WebSocket data models."""

    def test_quote_data_creation(self):
        """Test QuoteData model creation."""
        from datetime import datetime

        quote = QuoteData(epic="GOLD", bid=2080.0, ofr=2081.0, timestamp=datetime.utcnow())

        assert quote.epic == "GOLD"
        assert quote.bid == 2080.0
        assert quote.offer == 2081.0

    def test_ohlc_data_creation(self):
        """Test OHLCData model creation."""
        ohlc = OHLCData(
            epic="GOLD",
            resolution="MINUTE",
            t=1707566400000,  # Unix timestamp in milliseconds
            o=2075.0,
            h=2080.0,
            l=2070.0,
            c=2078.0,
        )

        assert ohlc.epic == "GOLD"
        assert ohlc.resolution == "MINUTE"
        assert ohlc.open == 2075.0
        assert ohlc.high == 2080.0
        assert ohlc.low == 2070.0
        assert ohlc.close == 2078.0

    def test_ohlc_data_datetime_property(self):
        """Test OHLCData datetime conversion."""
        ohlc = OHLCData(
            epic="GOLD",
            resolution="MINUTE",
            t=1707566400000,
            o=2075.0,
            h=2080.0,
            l=2070.0,
            c=2078.0,
        )

        dt = ohlc.datetime
        assert dt.year == 2024
        assert dt.month == 2
        assert dt.day == 10


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComWebSocketClient:
    """Test WebSocket client initialization and basic functionality."""

    def test_initialization(self):
        """Test WebSocket client initialization."""
        session_manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        ws_client = CapitalComWebSocketClient(
            ws_url="wss://demo-ws.example.com",
            session_manager=session_manager,
            max_reconnect_attempts=5,
            reconnect_delay_seconds=5,
        )

        assert ws_client.ws_url == "wss://demo-ws.example.com"
        assert ws_client.session_manager == session_manager
        assert ws_client.max_reconnect_attempts == 5
        assert ws_client.reconnect_delay_seconds == 5
        assert ws_client._connected is False
        assert len(ws_client._subscribed_quotes) == 0
        assert len(ws_client._subscribed_ohlc) == 0

    def test_on_quote_callback_registration(self):
        """Test registering quote event callback."""
        session_manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        ws_client = CapitalComWebSocketClient(
            ws_url="wss://demo-ws.example.com", session_manager=session_manager
        )

        def quote_handler(quote: QuoteData):
            pass

        ws_client.on_quote(quote_handler)

        assert ws_client._quote_handler == quote_handler

    def test_on_ohlc_callback_registration(self):
        """Test registering OHLC event callback."""
        session_manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        ws_client = CapitalComWebSocketClient(
            ws_url="wss://demo-ws.example.com", session_manager=session_manager
        )

        def ohlc_handler(ohlc: OHLCData):
            pass

        ws_client.on_ohlc(ohlc_handler)

        assert ws_client._ohlc_handler == ohlc_handler

    def test_initialization_defaults(self):
        """Test WebSocket client initialization with default values."""
        session_manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        ws_client = CapitalComWebSocketClient(
            ws_url="wss://demo-ws.example.com", session_manager=session_manager
        )

        # Should use default values
        assert ws_client.max_reconnect_attempts == 5
        assert ws_client.reconnect_delay_seconds == 5
        assert ws_client._ws is None
        assert ws_client._receive_task is None
        assert ws_client._ping_task is None
        assert ws_client._quote_handler is None
        assert ws_client._ohlc_handler is None
