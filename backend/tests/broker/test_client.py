"""
Unit tests for Capital.com REST API client.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.broker.client import CapitalComClient
from src.broker.exceptions import CapitalComError, RateLimitError
from src.broker.models import (
    CreatePositionRequest,
    Direction,
    ModifyPositionRequest,
    Resolution,
)


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComClient:
    """Test CapitalComClient initialization and configuration."""

    def test_initialization_demo_mode(self):
        """Test client initialization in demo mode."""
        with patch("src.broker.client.get_settings") as mock_settings:
            mock_settings.return_value.use_demo = True
            mock_settings.return_value.capital_demo_api_url = "https://demo-api.example.com"
            mock_settings.return_value.capital_demo_api_key = "demo_key"
            mock_settings.return_value.capital_demo_email = "demo@example.com"
            mock_settings.return_value.capital_demo_password = "demo_pass"
            mock_settings.return_value.session_timeout_minutes = 10
            mock_settings.return_value.rate_limit_requests_per_second = 10

            client = CapitalComClient()

            assert client.api_url == "https://demo-api.example.com"
            assert client.api_key == "demo_key"
            assert client.email == "demo@example.com"
            assert client.password == "demo_pass"

    def test_initialization_live_mode(self):
        """Test client initialization in live mode."""
        with patch("src.broker.client.get_settings") as mock_settings:
            mock_settings.return_value.use_demo = False
            mock_settings.return_value.capital_live_api_url = "https://live-api.example.com"
            mock_settings.return_value.capital_live_api_key = "live_key"
            mock_settings.return_value.capital_live_email = "live@example.com"
            mock_settings.return_value.capital_live_password = "live_pass"
            mock_settings.return_value.session_timeout_minutes = 10
            mock_settings.return_value.rate_limit_requests_per_second = 10

            client = CapitalComClient()

            assert client.api_url == "https://live-api.example.com"
            assert client.api_key == "live_key"
            assert client.email == "live@example.com"
            assert client.password == "live_pass"

    def test_initialization_with_custom_values(self):
        """Test client initialization with custom parameters."""
        client = CapitalComClient(
            api_url="https://custom-api.example.com",
            api_key="custom_key",
            email="custom@example.com",
            password="custom_pass",
        )

        assert client.api_url == "https://custom-api.example.com"
        assert client.api_key == "custom_key"
        assert client.email == "custom@example.com"
        assert client.password == "custom_pass"


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComClientRequests:
    """Test HTTP request handling."""

    @pytest.mark.asyncio
    async def test_request_success(self):
        """Test successful API request."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Mock rate limiter
        client.rate_limiter.acquire = AsyncMock(return_value=True)

        # Mock session manager
        mock_tokens = Mock()
        mock_tokens.cst = "mock_cst"
        mock_tokens.security_token = "mock_token"
        client.session_manager.get_tokens = AsyncMock(return_value=mock_tokens)

        # Mock HTTP response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = '{"key": "value"}'
        mock_response.json.return_value = {"key": "value"}

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.request.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_http_client):
            result = await client._request("GET", "/api/v1/test")

        assert result == {"key": "value"}
        mock_http_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_rate_limit_timeout(self):
        """Test request fails when rate limit times out."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Mock rate limiter to return False (timeout)
        client.rate_limiter.acquire = AsyncMock(return_value=False)

        with pytest.raises(CapitalComError, match="Rate limit timeout"):
            await client._request("GET", "/api/v1/test")

    @pytest.mark.asyncio
    async def test_request_http_error(self):
        """Test request handles HTTP errors."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Mock rate limiter
        client.rate_limiter.acquire = AsyncMock(return_value=True)

        # Mock session manager
        mock_tokens = Mock()
        mock_tokens.cst = "mock_cst"
        mock_tokens.security_token = "mock_token"
        client.session_manager.get_tokens = AsyncMock(return_value=mock_tokens)

        # Mock HTTP client to raise error
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.request.side_effect = httpx.ConnectError("Connection failed")

        with patch.object(client, "_get_http_client", return_value=mock_http_client):
            with pytest.raises(CapitalComError, match="HTTP error"):
                await client._request("GET", "/api/v1/test")

    @pytest.mark.asyncio
    async def test_request_api_error_400(self):
        """Test request handles 400+ API errors."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Mock rate limiter
        client.rate_limiter.acquire = AsyncMock(return_value=True)

        # Mock session manager
        mock_tokens = Mock()
        mock_tokens.cst = "mock_cst"
        mock_tokens.security_token = "mock_token"
        client.session_manager.get_tokens = AsyncMock(return_value=mock_tokens)

        # Mock HTTP response with error
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.text = '{"errorCode": "error.exceeds.rate-limit", "errorMessage": "Too many requests"}'
        mock_response.json.return_value = {
            "errorCode": "error.exceeds.rate-limit",
            "errorMessage": "Too many requests",
        }

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.request.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_http_client):
            with pytest.raises(RateLimitError):
                await client._request("GET", "/api/v1/test")

    @pytest.mark.asyncio
    async def test_request_empty_response(self):
        """Test request handles empty response body."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Mock rate limiter
        client.rate_limiter.acquire = AsyncMock(return_value=True)

        # Mock session manager
        mock_tokens = Mock()
        mock_tokens.cst = "mock_cst"
        mock_tokens.security_token = "mock_token"
        client.session_manager.get_tokens = AsyncMock(return_value=mock_tokens)

        # Mock HTTP response with empty body
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 204
        mock_response.text = ""

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.request.return_value = mock_response

        with patch.object(client, "_get_http_client", return_value=mock_http_client):
            result = await client._request("DELETE", "/api/v1/test")

        assert result == {}


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComClientMarketData:
    """Test market data methods."""

    @pytest.mark.asyncio
    async def test_search_markets(self):
        """Test searching for markets."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "markets": [
                {
                    "epic": "GOLD",
                    "instrumentName": "Gold",
                    "marketId": "GOLD_ID",
                    "bid": 2080.0,
                    "offer": 2081.0,
                    "high": 2100.0,
                    "low": 2050.0,
                }
            ]
        }

        with patch.object(client, "_request", return_value=mock_response):
            markets = await client.search_markets("gold")

        assert len(markets) == 1
        assert markets[0].epic == "GOLD"
        assert markets[0].instrument_name == "Gold"

    @pytest.mark.asyncio
    async def test_get_historical_prices(self):
        """Test getting historical price data."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "prices": [
                {
                    "snapshotTime": "2026-02-10T12:00:00",
                    "openPrice": 2075.0,
                    "highPrice": 2080.0,
                    "lowPrice": 2070.0,
                    "closePrice": 2078.0,
                    "lastTradedVolume": 1000,
                }
            ],
            "instrumentType": "COMMODITIES",
        }

        with patch.object(client, "_request", return_value=mock_response):
            candles = await client.get_historical_prices("GOLD", Resolution.HOUR)

        assert len(candles) == 1
        assert candles[0].open == 2075.0
        assert candles[0].close == 2078.0

    @pytest.mark.asyncio
    async def test_get_historical_prices_with_date_range(self):
        """Test getting historical prices with date range and max candles."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "prices": [],
            "instrumentType": "COMMODITIES",
        }

        from_date = datetime(2026, 2, 1)
        to_date = datetime(2026, 2, 10)

        with patch.object(client, "_request", return_value=mock_response):
            candles = await client.get_historical_prices(
                "GOLD", Resolution.DAY, from_date=from_date, to_date=to_date, max_candles=100
            )

        assert len(candles) == 0

    @pytest.mark.asyncio
    async def test_get_historical_prices_tz_aware_normalized_to_utc(self):
        """Tz-aware datetimes must be converted to UTC before formatting.

        Capital.com /api/v1/prices/ expects naive ``yyyy-MM-dd'T'HH:mm:ss``
        strings interpreted as UTC — same contract as /history/transactions.
        Passing a tz-aware local-time datetime must not leak local wall
        clock into the query; it has to be astimezone'd to UTC first.
        See memory `project_timezone_followup.md`.
        """
        from datetime import timedelta, timezone

        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # 10:00 in UTC+2 == 08:00 UTC
        cest = timezone(timedelta(hours=2))
        from_date = datetime(2026, 2, 1, 10, 0, 0, tzinfo=cest)
        to_date = datetime(2026, 2, 1, 12, 0, 0, tzinfo=cest)

        captured: dict = {}

        async def _spy(method, path, params=None, **kwargs):
            captured["params"] = params
            return {"prices": [], "instrumentType": "INDICES"}

        with patch.object(client, "_request", side_effect=_spy):
            await client.get_historical_prices(
                "GOLD", Resolution.HOUR, from_date=from_date, to_date=to_date
            )

        assert captured["params"]["from"] == "2026-02-01T08:00:00"
        assert captured["params"]["to"] == "2026-02-01T10:00:00"
        # No Z / offset suffix — server rejects those with error.invalid.from.
        assert "Z" not in captured["params"]["from"]
        assert "+" not in captured["params"]["from"]


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComClientPositions:
    """Test position management methods."""

    @pytest.mark.asyncio
    async def test_create_position(self):
        """Test creating a new position."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "dealId": "DEAL123",
            "dealReference": "REF123",
            "dealStatus": "ACCEPTED",
            "epic": "GOLD",
            "direction": Direction.BUY,
            "size": 1.0,
            "level": 2075.0,
            "status": "OPEN",
            "reason": "SUCCESS",
        }

        request = CreatePositionRequest(
            epic="GOLD", direction=Direction.BUY, size=1.0, stopLevel=2050.0, profitLevel=2100.0
        )

        with patch.object(client, "_request", return_value=mock_response):
            confirmation = await client.create_position(request)

        assert confirmation.deal_id == "DEAL123"
        assert confirmation.deal_status == "ACCEPTED"

    @pytest.mark.asyncio
    async def test_close_position(self):
        """Test closing an open position."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "dealId": "DEAL123",
            "dealReference": "REF_CLOSE",
            "dealStatus": "ACCEPTED",
            "epic": "GOLD",
            "direction": Direction.SELL,
            "size": 1.0,
            "level": 2080.0,
            "status": "CLOSED",
            "reason": "SUCCESS",
        }

        with patch.object(client, "_request", return_value=mock_response):
            confirmation = await client.close_position("DEAL123")

        assert confirmation.deal_status == "ACCEPTED"
        assert confirmation.status == "CLOSED"

    @pytest.mark.asyncio
    async def test_modify_position(self):
        """Test modifying position SL/TP."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "dealId": "DEAL123",
            "dealReference": "REF_MODIFY",
            "dealStatus": "ACCEPTED",
            "epic": "GOLD",
            "direction": Direction.BUY,
            "size": 1.0,
            "level": 2075.0,
            "status": "OPEN",
            "reason": "SUCCESS",
        }

        request = ModifyPositionRequest(stopLevel=2055.0, profitLevel=2105.0)

        with patch.object(client, "_request", return_value=mock_response):
            confirmation = await client.modify_position("DEAL123", request)

        assert confirmation.deal_status == "ACCEPTED"

    @pytest.mark.asyncio
    async def test_list_positions(self):
        """Test listing all open positions."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "positions": [
                {
                    "dealId": "DEAL123",
                    "epic": "GOLD",
                    "direction": Direction.BUY,
                    "size": 1.0,
                    "level": 2075.0,
                    "currency": "USD",
                    "createdDate": "2026-02-10T10:00:00",
                    "stopLevel": 2050.0,
                    "profitLevel": 2100.0,
                }
            ]
        }

        with patch.object(client, "_request", return_value=mock_response):
            positions = await client.list_positions()

        assert len(positions) == 1
        assert positions[0].deal_id == "DEAL123"
        assert positions[0].epic == "XAUUSD"  # GOLD is mapped back to internal name


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComClientAccount:
    """Test account management methods."""

    @pytest.mark.asyncio
    async def test_get_accounts(self):
        """Test getting account information."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "accounts": [
                {
                    "accountId": "ACC123",
                    "accountName": "Demo Account",
                    "accountType": "CFD",
                    "currency": "USD",
                    "balance": 10000.0,
                    "deposit": 10000.0,
                    "profitLoss": 150.0,
                    "available": 9500.0,
                }
            ]
        }

        with patch.object(client, "_request", return_value=mock_response):
            accounts = await client.get_accounts()

        assert len(accounts) == 1
        assert accounts[0].account_id == "ACC123"
        assert accounts[0].balance == 10000.0

    @pytest.mark.asyncio
    async def test_get_transaction_history(self):
        """Test getting transaction history."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "transactions": [
                {
                    "date": "2026-02-10T12:00:00",
                    "type": "TRADE",
                    "reference": "REF123",
                    "amount": -50.0,
                    "currency": "USD",
                }
            ]
        }

        from_date = datetime(2026, 2, 1)
        to_date = datetime(2026, 2, 10)

        with patch.object(client, "_request", return_value=mock_response):
            transactions = await client.get_transaction_history(from_date, to_date)

        assert len(transactions) == 1
        assert transactions[0].reference == "REF123"
        assert transactions[0].amount == -50.0


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComClientWorkingOrders:
    """Test working order methods."""

    @pytest.mark.asyncio
    async def test_create_working_order(self):
        """Test creating a working order."""
        from src.broker.models import CreateWorkingOrderRequest, OrderType

        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "dealId": "ORDER123",
            "dealReference": "REF_ORDER",
            "dealStatus": "ACCEPTED",
            "epic": "GOLD",
            "direction": Direction.BUY,
            "size": 1.0,
            "level": 2070.0,
            "status": "OPEN",
            "reason": "SUCCESS",
        }

        request = CreateWorkingOrderRequest(
            epic="GOLD",
            direction=Direction.BUY,
            size=1.0,
            level=2070.0,
            type=OrderType.LIMIT,
        )

        with patch.object(client, "_request", return_value=mock_response):
            confirmation = await client.create_working_order(request)

        assert confirmation.deal_id == "ORDER123"
        assert confirmation.deal_status == "ACCEPTED"

    @pytest.mark.asyncio
    async def test_cancel_working_order(self):
        """Test canceling a working order."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {
            "dealId": "ORDER123",
            "dealReference": "REF_CANCEL",
            "dealStatus": "ACCEPTED",
            "epic": "GOLD",
            "direction": Direction.BUY,
            "size": 1.0,
            "level": 2070.0,
            "status": "CANCELLED",
            "reason": "SUCCESS",
        }

        with patch.object(client, "_request", return_value=mock_response):
            confirmation = await client.cancel_working_order("ORDER123")

        assert confirmation.deal_status == "ACCEPTED"
        assert confirmation.status == "CANCELLED"

    @pytest.mark.asyncio
    async def test_list_working_orders(self):
        """Test listing all working orders."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        from datetime import datetime

        mock_response = {
            "workingOrders": [
                {
                    "dealId": "ORDER123",
                    "epic": "GOLD",
                    "direction": Direction.BUY,
                    "size": 1.0,
                    "level": 2070.0,
                    "type": "LIMIT",
                    "createdDate": datetime.utcnow().isoformat(),
                }
            ]
        }

        with patch.object(client, "_request", return_value=mock_response):
            orders = await client.list_working_orders()

        assert len(orders) == 1
        assert orders[0].deal_id == "ORDER123"
        assert orders[0].epic == "GOLD"


@pytest.mark.unit
@pytest.mark.broker
class TestCapitalComClientOtherMethods:
    """Test other client methods."""

    @pytest.mark.asyncio
    async def test_get_client_sentiment(self):
        """Test getting client sentiment data."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {"longPositionPercentage": 65.5, "shortPositionPercentage": 34.5}

        with patch.object(client, "_request", return_value=mock_response):
            sentiment = await client.get_client_sentiment("GOLD")

        assert sentiment.long_position_percentage == 65.5
        assert sentiment.short_position_percentage == 34.5

    @pytest.mark.asyncio
    async def test_top_up_demo_account(self):
        """Test topping up demo account."""
        client = CapitalComClient(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_response = {"success": True, "newBalance": 20000.0}

        with patch.object(client, "_request", return_value=mock_response):
            result = await client.top_up_demo_account(10000.0)

        assert result["success"] is True
        assert result["newBalance"] == 20000.0
