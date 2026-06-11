"""Abstract broker protocol — common surface for Capital.com / Bybit / mocks.

Defined as a `typing.Protocol` so existing concrete clients (CapitalComClient)
satisfy it structurally without inheritance. New brokers (Bybit, mocks)
implement the same methods to plug into the same trading loop, risk stack,
and backtest engine.

Phase 4 of the evolution roadmap migrates BTC trading from Capital.com CFD
to Bybit perpetual futures.  This protocol is the seam that lets both
brokers coexist behind the same call sites.

See `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class BrokerClientProtocol(Protocol):
    """Minimal broker surface used by trading loop, risk, and backtest.

    Any concrete client (Capital.com, Bybit, MockBroker) must expose these
    methods.  Optional broker-specific extensions (funding rate, open
    interest) live on the concrete subclass and are accessed via runtime
    `isinstance` or feature-detect.
    """

    # --- lifecycle ----------------------------------------------------

    async def connect(self) -> None:
        """Open session / authenticate."""
        ...

    async def close(self) -> None:
        """Close session and release resources."""
        ...

    # --- market data --------------------------------------------------

    async def get_market_details(self, epic: str) -> dict:
        """Return full market spec including snapshot bid/offer."""
        ...

    async def search_markets(self, search_term: str) -> list[Market]:
        """Search by name / epic substring."""
        ...

    async def get_historical_prices(
        self,
        epic: str,
        resolution: str = "MINUTE",
        max_records: int = 1000,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return OHLC bars sorted by time ascending."""
        ...

    async def get_client_sentiment(self, epic: str) -> ClientSentiment:
        """Long/short percentages of broker clients on this epic."""
        ...

    # --- positions ----------------------------------------------------

    async def list_positions(self) -> list[Position]:
        """All currently-open positions on the trading account."""
        ...

    async def create_position(self, request: CreatePositionRequest) -> DealConfirmation:
        """Open a new position (market order)."""
        ...

    async def close_position(self, deal_id: str) -> DealConfirmation:
        """Close an open position by dealId."""
        ...

    async def modify_position(
        self,
        deal_id: str,
        stop_level: float | None = None,
        profit_level: float | None = None,
        trailing_stop: bool | None = None,
        trailing_stop_distance: float | None = None,
    ) -> DealConfirmation:
        """Update SL / TP / trailing on an open position."""
        ...

    # --- working orders -----------------------------------------------

    async def create_working_order(
        self,
        request: CreateWorkingOrderRequest,
    ) -> DealConfirmation:
        """Create a pending limit / stop entry order."""
        ...

    async def cancel_working_order(self, deal_id: str) -> DealConfirmation:
        """Cancel a pending working order by dealId."""
        ...

    async def list_working_orders(self) -> list[WorkingOrder]:
        """All currently-pending working orders."""
        ...

    # --- account & history --------------------------------------------

    async def get_accounts(self) -> list[Account]:
        """Account(s) attached to this session."""
        ...

    async def get_transaction_history(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[Transaction]:
        """Realised P&L / fee transactions for close-detection."""
        ...

    async def get_activity_history(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Activity log used by v2 close-detector as authoritative SoT."""
        ...

    async def get_deal_confirmation(self, deal_reference: str) -> DealConfirmation:
        """Re-fetch a deal confirmation by deal_reference."""
        ...
