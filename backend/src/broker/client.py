"""
Capital.com REST API client.
Provides high-level interface for market data, trading, and account management.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger

from src.broker.exceptions import CapitalComError, map_error
from src.broker.models import (
    Account,
    ActivityEvent,
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
    "DOGUSD": "DOGEUSD",  # Dogecoin
    "NATGAS": "NATURALGAS",  # Natural Gas
    "NAS100": "QTEC",  # Nasdaq 100
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

        # HIGH-2/HIGH-3 FIX: Store retry and delay settings
        self._retry_attempts = settings.broker_retry_attempts
        self._retry_base_delay = settings.broker_retry_base_delay
        self._deal_confirmation_delay = settings.deal_confirmation_delay

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
        Make authenticated API request with rate limiting and retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters

        Returns:
            Response JSON data

        Raises:
            CapitalComError: If request fails after all retries
        """
        # HIGH-2 FIX: Add retry logic for transient 5xx errors (server-side issues)
        import asyncio

        last_error: Exception | None = None

        for attempt in range(self._retry_attempts):
            try:
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

                start_time = datetime.now()
                response = await client.request(
                    method, url, headers=headers, json=json, params=params
                )
                duration = (datetime.now() - start_time).total_seconds()

                # Sanitize JSON for logging (remove sensitive fields)
                safe_json = sanitize_dict(json) if json else None
                logger.debug(
                    f"{method} {endpoint} - Status: {response.status_code} - Duration: {duration:.3f}s"
                    + (f" - Body: {safe_json}" if safe_json and method in ["POST", "PUT"] else "")
                )

                # HIGH-2 FIX: Retry on 5xx errors (server-side transient failures)
                if response.status_code >= 500:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get("errorMessage", f"HTTP {response.status_code}")

                    if attempt < self._retry_attempts - 1:
                        retry_delay = self._retry_base_delay * (2**attempt)  # Exponential backoff
                        logger.warning(
                            f"5xx error from broker ({response.status_code}): {error_msg} - "
                            f"Retry {attempt + 1}/{self._retry_attempts} after {retry_delay:.2f}s"
                        )
                        await asyncio.sleep(retry_delay)
                        continue  # Retry
                    else:
                        # Final attempt failed
                        raise CapitalComError(
                            f"Broker 5xx error (after {self._retry_attempts} retries): {error_msg}"
                        )

                # Handle 4xx errors (client errors - don't retry)
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

                # Success - parse response
                if response.text:
                    return response.json()
                return {}

            except httpx.HTTPError as e:
                last_error = e
                if attempt < self._retry_attempts - 1:
                    retry_delay = self._retry_base_delay * (2**attempt)
                    logger.warning(
                        f"HTTP error for {method} {endpoint}: {e} - Retry {attempt + 1}/{self._retry_attempts} after {retry_delay:.2f}s"
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    logger.error(
                        f"HTTP error for {method} {endpoint}: {e} (after {self._retry_attempts} retries)"
                    )
                    raise CapitalComError(f"HTTP error: {e}")
            except CapitalComError:
                # Don't retry on CapitalComError (4xx client errors) - these are not transient
                raise

        # Should not reach here, but just in case
        if last_error:
            raise CapitalComError(f"HTTP error: {last_error}")
        raise CapitalComError("Request failed after all retry attempts")

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

        # Capital.com historical-prices endpoint expects naive
        # `yyyy-MM-dd'T'HH:mm:ss` strings in UTC (no `Z`, no offset —
        # mirrors the /history/transactions contract). Normalise tz-aware
        # inputs to UTC before formatting so callers passing a local-
        # tz datetime don't silently skew the window. Naive inputs are
        # assumed to already be UTC.
        if from_date:
            f = from_date.astimezone(UTC) if from_date.tzinfo else from_date
            params["from"] = f.strftime("%Y-%m-%dT%H:%M:%S")
        if to_date:
            t = to_date.astimezone(UTC) if to_date.tzinfo else to_date
            params["to"] = t.strftime("%Y-%m-%dT%H:%M:%S")
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
        # CRITICAL FIX: exclude_none=True prevents sending "stopLevel": null to broker
        # Capital.com rejects/ignores explicit null values
        payload = request.model_dump(by_alias=True, exclude_none=True)
        payload["epic"] = self._to_broker_epic(payload.get("epic", ""))

        response = await self._request("POST", "/api/v1/positions", json=payload)

        deal_ref = response.get("dealReference")
        if deal_ref:
            # Two-step flow: fetch full confirmation
            import asyncio

            # HIGH-3 FIX: Use configurable delay instead of hardcoded 300ms
            await asyncio.sleep(self._deal_confirmation_delay)
            confirmation = await self.get_deal_confirmation(deal_ref)

            return confirmation

        # Fallback: some API versions return full confirmation directly
        confirmation = DealConfirmation(**response)
        logger.info(
            f"📥 Broker response (direct): dealId={confirmation.deal_id} "
            f"status={confirmation.deal_status}"
        )
        return confirmation

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

            # HIGH-3 FIX: Use configurable delay instead of hardcoded 300ms
            await asyncio.sleep(self._deal_confirmation_delay)
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
        response = await self._request(
            "PUT", f"/api/v1/positions/{deal_id}", json=request.model_dump(by_alias=True)
        )
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
            # Propagate market status from market block
            if "marketStatus" in market_inner:
                flat["market_status"] = market_inner["marketStatus"]
            position = Position(**flat)
            positions.append(position)

            # 🔍 DEBUG: Log SL/TP values on open positions
            logger.debug(
                f"📊 Position {position.deal_id}: {position.epic} {position.direction.value} "
                f"entry={position.level:.2f} "
                f"SL={position.stop_level if position.stop_level else 'NONE'} "
                f"TP={position.profit_level if position.profit_level else 'NONE'}"
            )

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
        response = await self._request(
            "POST", "/api/v1/workingorders", json=request.model_dump(by_alias=True)
        )
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
        transaction_type: TransactionType = TransactionType.TRADE,
    ) -> list[Transaction]:
        """
        Get transaction history from Capital.com.

        Args:
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            transaction_type: Filter by transaction type. Defaults to TRADE
                (the only type that carries realized P&L for close detection).
                Pass `TransactionType.ALL` (or the deprecated `ALL_DEAL`) to
                fetch every record without a server-side filter — the broker
                rejects an explicit `type=ALL` value with empty results, so
                we drop the param entirely in that case.

        Returns:
            List of Transaction objects ordered by date descending.
        """
        # Capital.com history/transactions expects `yyyy-MM-dd'T'HH:mm:ss`
        # WITHOUT any timezone suffix (neither `Z` nor `+00:00`). The server
        # interprets it in its own timezone. We still normalize the input to
        # UTC here so the serialized string is unambiguous to us, but we
        # must strip the timezone marker before sending or the endpoint
        # returns error.invalid.from (HTTP 400).
        params: dict[str, Any] = {
            "from": from_date.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "to": to_date.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if transaction_type not in (TransactionType.ALL, TransactionType.ALL_DEAL):
            params["type"] = transaction_type.value
        response = await self._request("GET", "/api/v1/history/transactions", params=params)
        transactions_data = response.get("transactions", [])
        return [Transaction(**txn) for txn in transactions_data]

    async def get_activity_history(
        self,
        from_date: datetime,
        to_date: datetime,
        detailed: bool = True,
    ) -> list[ActivityEvent]:
        """Fetch activity history from Capital.com `/api/v1/history/activity`.

        This is the authoritative source for close-event linkage in
        MANTIS v2 close detection. Each broker-initiated close (TP / SL /
        STOP_OUT / MARGIN_CALL) emits a POSITION event with:

        - `source` = close reason (TP, SL, STOP_OUT, MARGIN_CALL, USER, …)
        - `details.openPrice` = original position entry price
        - `details.direction` = the reverse direction on the close
        - `dealId` = the close-side dealId (matches the TRADE row in
          `/history/transactions` for P&L lookup)

        Together those fields let the close detector deterministically
        link a broker close to our Position row without depending on
        stable `dealId` equality, which Capital.com mutates on broker-
        initiated closes (verified 2026-04-21).

        Args:
            from_date: Start of the activity window (inclusive).
            to_date:   End of the activity window (inclusive).
            detailed:  Whether to request the detailed payload (required
                for `details.openPrice` / `stopLevel` / etc.). Defaults
                to True — the un-detailed payload is useless for us.

        Returns:
            List of ActivityEvent objects ordered by date descending.
        """
        # Same timestamp rules as /history/transactions: naive
        # `yyyy-MM-dd'T'HH:mm:ss`, no timezone suffix. Server rejects tz
        # suffix with `error.invalid.from`.
        params: dict[str, Any] = {
            "from": from_date.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "to": to_date.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "detailed": "true" if detailed else "false",
        }
        response = await self._request("GET", "/api/v1/history/activity", params=params)
        activities_data = response.get("activities", [])
        return [ActivityEvent(**act) for act in activities_data]

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
