"""
Capital.com REST API client.
Provides high-level interface for market data, trading, and account management.
"""

from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from src.broker.exceptions import CapitalComError, map_error
from src.broker.models import (
    Account,
    ClientSentiment,
    CreatePositionRequest,
    CreateWorkingOrderRequest,
    DealConfirmation,
    Market,
    ModifyPositionRequest,
    OHLCCandle,
    Position,
    PriceHistory,
    Resolution,
    Transaction,
    TransactionType,
    WorkingOrder,
)
from src.broker.rate_limiter import RateLimiter
from src.broker.session import SessionManager
from src.utils.config import get_settings
from src.utils.sanitization import sanitize_dict


# Map internal epic names → Capital.com API epic codes
# Internal names (XAUUSD, BTCUSD, US500) are used throughout the codebase.
# Capital.com uses different codes for some assets.
EPIC_TO_BROKER: dict[str, str] = {
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "WTIUSD": "OIL_CRUDE",
}
BROKER_TO_EPIC: dict[str, str] = {v: k for k, v in EPIC_TO_BROKER.items()}


class CapitalComClient:
    """
    Capital.com API client.
    Provides methods for market data, trading, and account management.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        email: str | None = None,
        password: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        """
        Initialize Capital.com client.

        Args:
            api_url: API base URL (uses settings if None)
            api_key: API key (uses settings if None)
            email: Account email (uses settings if None)
            password: API password (uses settings if None)
            rate_limiter: Rate limiter instance (creates new if None)
        """
        settings = get_settings()

        # Use demo or live credentials based on settings
        if settings.use_demo:
            self.api_url = api_url or settings.capital_demo_api_url
            self.api_key = api_key or settings.capital_demo_api_key
            self.email = email or settings.capital_demo_email
            self.password = password or settings.capital_demo_password
        else:
            self.api_url = api_url or settings.capital_live_api_url
            self.api_key = api_key or settings.capital_live_api_key
            self.email = email or settings.capital_live_email
            self.password = password or settings.capital_live_password

        # Initialize components
        self.session_manager = SessionManager(
            api_url=self.api_url,
            api_key=self.api_key,
            email=self.email,
            password=self.password,
            session_timeout_minutes=settings.session_timeout_minutes,
        )

        self.rate_limiter = rate_limiter or RateLimiter(
            requests_per_second=settings.rate_limit_requests_per_second
        )

        self._http_client: httpx.AsyncClient | None = None

    @staticmethod
    def _to_broker_epic(epic: str) -> str:
        """Translate internal epic name to Capital.com API epic code."""
        return EPIC_TO_BROKER.get(epic, epic)

    @staticmethod
    def _from_broker_epic(broker_epic: str) -> str:
        """Translate Capital.com API epic code back to internal name."""
        return BROKER_TO_EPIC.get(broker_epic, broker_epic)

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with configured timeouts."""
        if self._http_client is None:
            settings = get_settings()
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    timeout=float(settings.http_timeout_seconds),
                    connect=float(settings.http_connect_timeout_seconds),
                ),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http_client

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make authenticated API request with rate limiting.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters

        Returns:
            Response JSON data

        Raises:
            CapitalComError: If request fails
        """
        # Rate limit
        acquired = await self.rate_limiter.acquire(timeout=10.0)
        if not acquired:
            raise CapitalComError("Rate limit timeout - API too busy")

        # Get session tokens
        tokens = await self.session_manager.get_tokens()

        # Make request
        client = await self._get_http_client()
        url = f"{self.api_url}{endpoint}"

        headers = {"CST": tokens.cst, "X-SECURITY-TOKEN": tokens.security_token}

        try:
            start_time = datetime.now()
            response = await client.request(method, url, headers=headers, json=json, params=params)
            duration = (datetime.now() - start_time).total_seconds()

            # Sanitize JSON for logging (remove sensitive fields)
            safe_json = sanitize_dict(json) if json else None
            logger.debug(
                f"{method} {endpoint} - Status: {response.status_code} - Duration: {duration:.3f}s"
                + (f" - Body: {safe_json}" if safe_json and method in ["POST", "PUT"] else "")
            )

            # Handle errors
            if response.status_code >= 400:
                error_data = response.json() if response.text else {}
                error_code = error_data.get("errorCode", "unknown")
                error_message = error_data.get("errorMessage", "")
                # Capital.com sometimes puts the full message inside errorCode
                # (e.g., "Rejected. TSLA is currently closed. Timetable in place: ...")
                if len(error_code) > 50 or (" " in error_code and error_code != "unknown"):
                    error_message = error_message or error_code
                    error_code = error_code  # keep for fuzzy matching in map_error
                raise map_error(error_code, error_message or response.text)

            # Parse response
            if response.text:
                return response.json()
            return {}

        except httpx.HTTPError as e:
            logger.error(f"HTTP error for {method} {endpoint}: {e}")
            raise CapitalComError(f"HTTP error: {e}")

    # ===== Market Data Methods =====

    async def get_market_details(self, epic: str) -> dict:
        """
        Get detailed market info including status, trading hours, and instrument specs.

        Uses GET /api/v1/markets/{epic} — returns snapshot with marketStatus
        (TRADEABLE, CLOSED, etc.), instrument details, and dealing rules.

        Args:
            epic: Internal epic code (e.g., "XAUUSD", "TSLA")

        Returns:
            Raw dict from Capital.com (includes 'snapshot', 'instrument', 'dealingRules')
        """
        broker_epic = self._to_broker_epic(epic)
        return await self._request("GET", f"/api/v1/markets/{broker_epic}")

    async def search_markets(self, search_term: str) -> list[Market]:
        """
        Search for markets by name or epic.

        Args:
            search_term: Search term (e.g., "gold", "bitcoin", "US500")

        Returns:
            List of matching markets
        """
        response = await self._request("GET", "/api/v1/markets", params={"searchTerm": search_term})
        markets_data = response.get("markets", [])
        return [Market(**market) for market in markets_data]

    async def get_historical_prices(
        self,
        epic: str,
        resolution: Resolution,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        max_candles: int | None = None,
    ) -> list[OHLCCandle]:
        """
        Get historical OHLC price data.

        Args:
            epic: Market epic code (e.g., "GOLD", "BITCOIN", "US500")
            resolution: Candle resolution (MINUTE, HOUR, DAY, etc.)
            from_date: Start date (optional)
            to_date: End date (optional)
            max_candles: Maximum number of candles (optional)

        Returns:
            List of OHLC candles
        """
        params: dict[str, Any] = {"resolution": resolution.value}

        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%dT%H:%M:%S")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%dT%H:%M:%S")
        if max_candles:
            params["max"] = max_candles

        broker_epic = self._to_broker_epic(epic)
        response = await self._request("GET", f"/api/v1/prices/{broker_epic}", params=params)
        price_history = PriceHistory(**response)
        return price_history.prices

    async def get_client_sentiment(self, epic: str) -> ClientSentiment:
        """
        Get client sentiment (long/short percentage) for a market.

        Args:
            epic: Market epic code

        Returns:
            Client sentiment data
        """
        broker_epic = self._to_broker_epic(epic)
        response = await self._request("GET", f"/api/v1/clientsentiment/{broker_epic}")
        return ClientSentiment(**response)

    # ===== Position Management =====

    async def create_position(self, request: CreatePositionRequest) -> DealConfirmation:
        """
        Open a new position (market order).

        Capital.com flow: POST returns {dealReference}, then GET /confirms/{ref}
        returns the full DealConfirmation with dealId, level, status, etc.

        Args:
            request: Position creation request

        Returns:
            Deal confirmation
        """
        payload = request.model_dump(by_alias=True)
        payload["epic"] = self._to_broker_epic(payload.get("epic", ""))
        response = await self._request("POST", "/api/v1/positions", json=payload)

        deal_ref = response.get("dealReference")
        if deal_ref:
            # Two-step flow: fetch full confirmation
            import asyncio
            await asyncio.sleep(0.3)  # brief pause for broker to process
            return await self.get_deal_confirmation(deal_ref)

        # Fallback: some API versions return full confirmation directly
        return DealConfirmation(**response)

    async def close_position(self, deal_id: str) -> DealConfirmation:
        """
        Close an open position.

        Args:
            deal_id: Position deal ID

        Returns:
            Deal confirmation
        """
        response = await self._request("DELETE", f"/api/v1/positions/{deal_id}")

        deal_ref = response.get("dealReference")
        if deal_ref:
            import asyncio
            await asyncio.sleep(0.3)
            return await self.get_deal_confirmation(deal_ref)

        return DealConfirmation(**response)

    async def modify_position(
        self, deal_id: str, request: ModifyPositionRequest
    ) -> DealConfirmation:
        """
        Modify an open position (update SL/TP).

        Args:
            deal_id: Position deal ID
            request: Modification request (stop_level, profit_level)

        Returns:
            Deal confirmation
        """
        response = await self._request("PUT", f"/api/v1/positions/{deal_id}", json=request.model_dump(by_alias=True))
        return DealConfirmation(**response)

    async def list_positions(self) -> list[Position]:
        """
        List all open positions.

        Returns:
            List of open positions
        """
        response = await self._request("GET", "/api/v1/positions")
        positions_data = response.get("positions", [])
        positions = []
        for pos in positions_data:
            # Capital.com returns nested {position: {...}, market: {...}}
            pos_inner = pos.get("position", pos)
            market_inner = pos.get("market", {})
            flat = {**pos_inner}
            if "epic" not in flat and "epic" in market_inner:
                flat["epic"] = market_inner["epic"]
            positions.append(Position(**flat))
        # Translate broker epics back to internal names
        for p in positions:
            p.epic = self._from_broker_epic(p.epic)
        return positions

    # ===== Working Orders =====

    async def create_working_order(self, request: CreateWorkingOrderRequest) -> DealConfirmation:
        """
        Create a working order (limit/stop order).

        Args:
            request: Working order request

        Returns:
            Deal confirmation
        """
        response = await self._request("POST", "/api/v1/workingorders", json=request.model_dump(by_alias=True))
        return DealConfirmation(**response)

    async def cancel_working_order(self, deal_id: str) -> DealConfirmation:
        """
        Cancel a working order.

        Args:
            deal_id: Working order deal ID

        Returns:
            Deal confirmation
        """
        response = await self._request("DELETE", f"/api/v1/workingorders/{deal_id}")
        return DealConfirmation(**response)

    async def list_working_orders(self) -> list[WorkingOrder]:
        """
        List all working orders.

        Returns:
            List of working orders
        """
        response = await self._request("GET", "/api/v1/workingorders")
        orders_data = response.get("workingOrders", [])
        return [WorkingOrder(**order) for order in orders_data]

    # ===== Account Management =====

    async def get_accounts(self) -> list[Account]:
        """
        Get account information and balance.

        Returns:
            List of accounts
        """
        response = await self._request("GET", "/api/v1/accounts")
        accounts_data = response.get("accounts", [])
        return [Account(**acc) for acc in accounts_data]

    async def get_transaction_history(
        self,
        from_date: datetime,
        to_date: datetime,
        transaction_type: TransactionType = TransactionType.ALL,
    ) -> list[Transaction]:
        """
        Get transaction history.

        Args:
            from_date: Start date
            to_date: End date
            transaction_type: Type of transactions to retrieve

        Returns:
            List of transactions
        """
        params = {
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "to": to_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "type": transaction_type.value,
        }
        response = await self._request("GET", "/api/v1/history/transactions", params=params)
        transactions_data = response.get("transactions", [])
        return [Transaction(**txn) for txn in transactions_data]

    async def top_up_demo_account(self, amount: float) -> dict[str, Any]:
        """
        Top up demo account balance (demo only).

        Args:
            amount: Amount to add to demo account

        Returns:
            Response data
        """
        return await self._request("POST", "/api/v1/accounts/topUp", json={"amount": amount})

    # ===== Deal Confirmation =====

    async def get_deal_confirmation(self, deal_reference: str) -> DealConfirmation:
        """
        Get trade execution confirmation.

        Args:
            deal_reference: Deal reference from position/order creation

        Returns:
            Deal confirmation
        """
        response = await self._request("GET", f"/api/v1/confirms/{deal_reference}")
        return DealConfirmation(**response)

    # ===== Lifecycle Management =====

    async def connect(self) -> None:
        """Initialize connection and authenticate."""
        logger.info("🔌 Connecting to Capital.com...")
        await self.session_manager.authenticate()
        logger.success("✅ Connected to Capital.com")

    async def close(self) -> None:
        """Close connection and cleanup resources."""
        logger.info("Disconnecting from Capital.com...")
        await self.session_manager.close()
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
        logger.success("✅ Disconnected from Capital.com")
