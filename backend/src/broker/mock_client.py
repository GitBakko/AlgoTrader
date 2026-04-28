"""In-memory mock broker that satisfies `BrokerClientProtocol`.

Used for:
- Protocol-conformance tests (the real client + the stub Bybit client are
  both checked structurally against this same protocol).
- Unit tests that need a deterministic broker without HTTP.
- Local smoke tests of the trading loop without any live API.

Simulates a tiny in-memory positions ledger plus a deterministic
`get_market_details` snapshot.  Methods that aren't useful for the
common test cases raise `NotImplementedError` so tests fail loudly when
a code path drifts onto an un-mocked surface.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MockBrokerClient:
    """Deterministic in-memory broker for tests and local smoke runs."""

    def __init__(
        self,
        snapshot: dict[str, dict[str, float]] | None = None,
    ) -> None:
        # Per-epic bid/offer snapshot.  Defaults to a small set of common
        # epics with realistic spreads so backtests run without setup.
        self._snapshot = snapshot or {
            "BTCUSD": {"bid": 76000.0, "offer": 76060.0},
            "ETHUSD": {"bid": 2270.0, "offer": 2272.0},
            "SOLUSD": {"bid": 83.0, "offer": 83.5},
            "BNBUSD": {"bid": 620.0, "offer": 624.0},
            "GOLD":   {"bid": 4577.0, "offer": 4577.5},
        }
        self._positions: dict[str, Position] = {}
        self._working_orders: dict[str, WorkingOrder] = {}
        self._transactions: list[Transaction] = []
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_market_details(self, epic: str) -> dict:
        if epic not in self._snapshot:
            return {"snapshot": {"bid": 0.0, "offer": 0.0}, "instrument": {"epic": epic}}
        snap = self._snapshot[epic]
        return {
            "snapshot": {"bid": snap["bid"], "offer": snap["offer"]},
            "instrument": {"epic": epic},
        }

    async def search_markets(self, search_term: str) -> list[Market]:
        return []

    async def get_historical_prices(
        self,
        epic: str,
        resolution: str = "MINUTE",
        max_records: int = 1000,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def get_client_sentiment(self, epic: str) -> ClientSentiment:
        return ClientSentiment.model_validate({
            "longPositionPercentage": 50.0,
            "shortPositionPercentage": 50.0,
        })

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def list_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def create_position(self, request: CreatePositionRequest) -> DealConfirmation:
        deal_id = uuid4().hex
        deal_ref = f"MOCK-{deal_id[:8]}"
        snap = self._snapshot.get(request.epic, {"bid": 0.0, "offer": 0.0})
        level = snap["offer"] if request.direction == "BUY" else snap["bid"]
        now = datetime.now(timezone.utc)
        pos = Position.model_validate({
            "dealId": deal_id,
            "epic": request.epic,
            "direction": request.direction,
            "size": request.size,
            "level": level,
            "currency": "USD",
            "createdDate": now,
            "stopLevel": request.stop_level,
            "profitLevel": request.profit_level,
            "upl": 0.0,
            "market_status": "TRADEABLE",
        })
        self._positions[deal_id] = pos
        return DealConfirmation.model_validate({
            "dealId": deal_id, "dealReference": deal_ref,
            "dealStatus": "OPEN", "status": "OPEN",
            "epic": request.epic, "direction": request.direction,
            "size": request.size, "level": level,
        })

    async def close_position(self, deal_id: str) -> DealConfirmation:
        pos = self._positions.pop(deal_id, None)
        if pos is None:
            from src.broker.exceptions import BrokerError
            raise BrokerError(f"Position {deal_id} not found")
        return DealConfirmation.model_validate({
            "dealId": deal_id, "dealReference": f"MOCK-{deal_id[:8]}",
            "dealStatus": "CLOSED", "status": "CLOSED",
            "epic": pos.epic, "direction": pos.direction,
            "size": pos.size, "level": pos.level,
        })

    async def modify_position(
        self,
        deal_id: str,
        stop_level: float | None = None,
        profit_level: float | None = None,
        trailing_stop: bool | None = None,
        trailing_stop_distance: float | None = None,
    ) -> DealConfirmation:
        pos = self._positions.get(deal_id)
        if pos is None:
            from src.broker.exceptions import BrokerError
            raise BrokerError(f"Position {deal_id} not found")
        if stop_level is not None:
            pos.stop_level = stop_level
        if profit_level is not None:
            pos.profit_level = profit_level
        return DealConfirmation.model_validate({
            "dealId": deal_id, "dealReference": f"MOCK-{deal_id[:8]}",
            "dealStatus": "AMENDED", "status": "AMENDED",
            "epic": pos.epic, "direction": pos.direction,
            "size": pos.size, "level": pos.level,
        })

    # ------------------------------------------------------------------
    # Working orders
    # ------------------------------------------------------------------

    async def create_working_order(
        self, request: CreateWorkingOrderRequest,
    ) -> DealConfirmation:
        deal_id = uuid4().hex
        deal_ref = f"MOCK-WO-{deal_id[:8]}"
        now = datetime.now(timezone.utc)
        order = WorkingOrder.model_validate({
            "dealId": deal_id,
            "epic": request.epic,
            "direction": request.direction,
            "size": request.size,
            "level": request.level,
            "type": request.type,
            "createdDate": now,
        })
        self._working_orders[deal_id] = order
        return DealConfirmation.model_validate({
            "dealId": deal_id, "dealReference": deal_ref,
            "dealStatus": "OPEN", "status": "OPEN",
            "epic": request.epic, "direction": request.direction,
            "size": request.size, "level": request.level,
        })

    async def cancel_working_order(self, deal_id: str) -> DealConfirmation:
        order = self._working_orders.pop(deal_id, None)
        if order is None:
            from src.broker.exceptions import BrokerError
            raise BrokerError(f"Working order {deal_id} not found")
        return DealConfirmation.model_validate({
            "dealId": deal_id, "dealReference": f"MOCK-WO-{deal_id[:8]}",
            "dealStatus": "DELETED", "status": "DELETED",
            "epic": order.epic, "direction": order.direction,
            "size": order.size, "level": order.level,
        })

    async def list_working_orders(self) -> list[WorkingOrder]:
        return list(self._working_orders.values())

    # ------------------------------------------------------------------
    # Account & history
    # ------------------------------------------------------------------

    async def get_accounts(self) -> list[Account]:
        return [
            Account.model_validate({
                "accountId": "MOCK-001",
                "accountName": "Mock Demo",
                "accountType": "CFD",
                "currency": "USD",
                "balance": 10_000.0,
                "deposit": 10_000.0,
                "profitLoss": 0.0,
                "available": 10_000.0,
            }),
        ]

    async def get_transaction_history(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[Transaction]:
        return list(self._transactions)

    async def get_activity_history(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return []

    async def get_deal_confirmation(self, deal_reference: str) -> DealConfirmation:
        from src.broker.exceptions import BrokerError
        raise BrokerError(f"deal_reference {deal_reference} not tracked by mock")

    # ------------------------------------------------------------------
    # Test helpers (not part of the protocol)
    # ------------------------------------------------------------------

    def set_snapshot(self, epic: str, bid: float, offer: float) -> None:
        self._snapshot[epic] = {"bid": bid, "offer": offer}

    def add_transaction(self, tx: Transaction) -> None:
        self._transactions.append(tx)
