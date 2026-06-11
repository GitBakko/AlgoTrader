"""Bybit broker adapter — Phase 4 perpetual-futures spec stub.

This is a placeholder skeleton that satisfies `BrokerClientProtocol`
without performing real API calls.  It is intentionally minimal so we
can:
  1. Compile + import in CI without a Bybit API key,
  2. Run protocol-conformance tests against this class,
  3. Be filled in incrementally once the live Bybit account is open
     (scheduled for next month).

When implementation lands, replace the stub bodies with real REST +
WebSocket calls per Bybit V5 API.

Bybit V5 documentation:
- REST base: https://api.bybit.com/v5
- Testnet:   https://api-testnet.bybit.com/v5
- WS public: wss://stream.bybit.com/v5/public/linear
- WS private: wss://stream.bybit.com/v5/private

Phase 4 prerequisites tracked here for future-self:
- Auth: API key + secret with HMAC-SHA256 signing per request.
- Symbols: BTCUSDT (linear perpetual) is primary; convert internal
  epics via a `EPIC_TO_BYBIT_SYMBOL` mapping kept here at module level.
- Funding rate: 8h cycle, fetched from `/v5/market/funding/history`.
- Open interest: `/v5/market/open-interest`.
- Order types: Market + Limit + Stop with TIF GTC default.
- Fee schedule: 0.055 % taker / 0.018 % maker on linear (subject to VIP).

See `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from src.broker.exceptions import BrokerError
from src.broker.models import (
    Account,
    ClientSentiment,
    CreatePositionRequest,
    CreateWorkingOrderRequest,
    DealConfirmation,
    Market,
    Position,
    Transaction,
    WorkingOrder,
)

# Bybit V5 symbol mapping for the top-5 KEEP basket epics that have
# linear-perpetual equivalents.  Phase 4 starts with BTC only.
EPIC_TO_BYBIT_SYMBOL: dict[str, str] = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "SOLUSD": "SOLUSDT",
    "BNBUSD": "BNBUSDT",
}

BYBIT_SYMBOL_TO_EPIC: dict[str, str] = {v: k for k, v in EPIC_TO_BYBIT_SYMBOL.items()}


class BybitNotImplementedError(BrokerError):
    """Raised when a stub method is called.  Replace once Phase 4 ships."""


class BybitClient:
    """Bybit V5 perpetual-futures client (stub)."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = True,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = (
            "https://api-testnet.bybit.com/v5" if testnet else "https://api.bybit.com/v5"
        )
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Validate credentials and warm the HTTP client.  Stub: no-op."""
        logger.info(f"BybitClient.connect() stub — base_url={self._base_url}")
        self._connected = True

    async def close(self) -> None:
        logger.info("BybitClient.close() stub")
        self._connected = False

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_market_details(self, epic: str) -> dict:
        symbol = self._symbol_or_raise(epic)
        raise BybitNotImplementedError(
            f"get_market_details({symbol}) — Phase 4 not yet implemented",
        )

    async def search_markets(self, search_term: str) -> list[Market]:
        raise BybitNotImplementedError("search_markets — Phase 4 not yet implemented")

    async def get_historical_prices(
        self,
        epic: str,
        resolution: str = "MINUTE",
        max_records: int = 1000,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        symbol = self._symbol_or_raise(epic)
        raise BybitNotImplementedError(
            f"get_historical_prices({symbol}) — Phase 4 not yet implemented",
        )

    async def get_client_sentiment(self, epic: str) -> ClientSentiment:
        # Bybit doesn't publish this directly; long/short ratio comes via
        # the futures sentiment endpoint.  Phase 4 plumbing TBD.
        raise BybitNotImplementedError(
            "get_client_sentiment — long/short ratio sourcing TBD for Bybit",
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def list_positions(self) -> list[Position]:
        raise BybitNotImplementedError("list_positions — Phase 4 not yet implemented")

    async def create_position(self, request: CreatePositionRequest) -> DealConfirmation:
        symbol = self._symbol_or_raise(request.epic)
        raise BybitNotImplementedError(
            f"create_position({symbol}) — Phase 4 not yet implemented",
        )

    async def close_position(self, deal_id: str) -> DealConfirmation:
        raise BybitNotImplementedError("close_position — Phase 4 not yet implemented")

    async def modify_position(
        self,
        deal_id: str,
        stop_level: float | None = None,
        profit_level: float | None = None,
        trailing_stop: bool | None = None,
        trailing_stop_distance: float | None = None,
    ) -> DealConfirmation:
        raise BybitNotImplementedError("modify_position — Phase 4 not yet implemented")

    # ------------------------------------------------------------------
    # Working orders
    # ------------------------------------------------------------------

    async def create_working_order(
        self,
        request: CreateWorkingOrderRequest,
    ) -> DealConfirmation:
        raise BybitNotImplementedError(
            "create_working_order — Phase 4 not yet implemented",
        )

    async def cancel_working_order(self, deal_id: str) -> DealConfirmation:
        raise BybitNotImplementedError(
            "cancel_working_order — Phase 4 not yet implemented",
        )

    async def list_working_orders(self) -> list[WorkingOrder]:
        raise BybitNotImplementedError(
            "list_working_orders — Phase 4 not yet implemented",
        )

    # ------------------------------------------------------------------
    # Account & history
    # ------------------------------------------------------------------

    async def get_accounts(self) -> list[Account]:
        raise BybitNotImplementedError("get_accounts — Phase 4 not yet implemented")

    async def get_transaction_history(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[Transaction]:
        raise BybitNotImplementedError(
            "get_transaction_history — Phase 4 not yet implemented",
        )

    async def get_activity_history(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        raise BybitNotImplementedError(
            "get_activity_history — Phase 4 not yet implemented",
        )

    async def get_deal_confirmation(self, deal_reference: str) -> DealConfirmation:
        raise BybitNotImplementedError(
            "get_deal_confirmation — Phase 4 not yet implemented",
        )

    # ------------------------------------------------------------------
    # Bybit-specific extensions (Phase 4 alpha sources)
    # ------------------------------------------------------------------

    async def get_funding_rate_history(
        self,
        epic: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Funding rate history for the epic's perpetual.

        Used by `BybitFundingRateFetcher` (planned) to produce 14
        funding-rate features fed to XGBoost.  Roadmap §Phase 4 sprint 2.
        """
        symbol = self._symbol_or_raise(epic)
        raise BybitNotImplementedError(
            f"get_funding_rate_history({symbol}) — Phase 4 not yet implemented",
        )

    async def get_open_interest(self, epic: str) -> dict[str, Any]:
        """Current open interest for the epic's perpetual."""
        symbol = self._symbol_or_raise(epic)
        raise BybitNotImplementedError(
            f"get_open_interest({symbol}) — Phase 4 not yet implemented",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _symbol_or_raise(self, epic: str) -> str:
        symbol = EPIC_TO_BYBIT_SYMBOL.get(epic)
        if symbol is None:
            raise BrokerError(
                f"No Bybit symbol mapping for epic {epic}; " "extend EPIC_TO_BYBIT_SYMBOL.",
            )
        return symbol
