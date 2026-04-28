"""Phase 4 prep — protocol conformance for broker clients.

Verifies that:
- `BybitClient` (stub) satisfies `BrokerClientProtocol` structurally.
- `MockBrokerClient` satisfies `BrokerClientProtocol` and behaves
  deterministically for the trading-loop happy paths.
- `CapitalComClient` is structurally compatible (no instantiation —
  it requires real credentials in __init__ — but we walk the methods).

This file is the Phase 4 contract: any broker added to MANTIS must
make these tests pass before being wired into the trading loop.
"""

from __future__ import annotations

import inspect

import pytest

from src.broker.bybit_client import BybitClient, EPIC_TO_BYBIT_SYMBOL, BybitNotImplementedError
from src.broker.client import CapitalComClient
from src.broker.exceptions import BrokerError, CapitalComError
from src.broker.mock_client import MockBrokerClient
from src.broker.models import CreatePositionRequest
from src.broker.protocol import BrokerClientProtocol


# ──────────────────────────────────────────────────────────────────────
# Protocol conformance — structural checks
# ──────────────────────────────────────────────────────────────────────

REQUIRED_METHODS = (
    "connect", "close",
    "get_market_details", "search_markets", "get_historical_prices",
    "get_client_sentiment",
    "list_positions", "create_position", "close_position", "modify_position",
    "create_working_order", "cancel_working_order", "list_working_orders",
    "get_accounts", "get_transaction_history", "get_activity_history",
    "get_deal_confirmation",
)


@pytest.mark.parametrize("client_cls", [CapitalComClient, BybitClient, MockBrokerClient])
def test_client_has_all_protocol_methods(client_cls):
    for name in REQUIRED_METHODS:
        method = getattr(client_cls, name, None)
        assert method is not None, f"{client_cls.__name__} missing {name}"
        assert callable(method), f"{client_cls.__name__}.{name} is not callable"


@pytest.mark.parametrize("client_cls", [BybitClient, MockBrokerClient])
def test_protocol_methods_are_async(client_cls):
    for name in REQUIRED_METHODS:
        method = getattr(client_cls, name)
        assert inspect.iscoroutinefunction(method), (
            f"{client_cls.__name__}.{name} must be async"
        )


# ──────────────────────────────────────────────────────────────────────
# MockBrokerClient — behavioural happy path
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mock_lifecycle_and_market_details():
    client = MockBrokerClient()
    await client.connect()
    md = await client.get_market_details("BTCUSD")
    assert md["snapshot"]["bid"] > 0
    assert md["snapshot"]["offer"] > md["snapshot"]["bid"]
    await client.close()


@pytest.mark.asyncio
async def test_mock_create_list_close_position():
    client = MockBrokerClient()
    await client.connect()
    req = CreatePositionRequest(epic="BTCUSD", direction="BUY", size=0.01)
    confirm = await client.create_position(req)
    assert confirm.deal_id
    assert confirm.epic == "BTCUSD"
    positions = await client.list_positions()
    assert len(positions) == 1
    closed = await client.close_position(confirm.deal_id)
    assert closed.deal_id == confirm.deal_id
    assert (await client.list_positions()) == []


@pytest.mark.asyncio
async def test_mock_modify_position_updates_levels():
    client = MockBrokerClient()
    await client.connect()
    req = CreatePositionRequest(epic="ETHUSD", direction="BUY", size=0.1)
    confirm = await client.create_position(req)
    await client.modify_position(
        confirm.deal_id, stop_level=2200.0, profit_level=2400.0,
    )
    pos = (await client.list_positions())[0]
    assert pos.stop_level == 2200.0
    assert pos.profit_level == 2400.0


@pytest.mark.asyncio
async def test_mock_close_unknown_position_raises_broker_error():
    client = MockBrokerClient()
    await client.connect()
    with pytest.raises(BrokerError):
        await client.close_position("NOT-A-DEAL")


# ──────────────────────────────────────────────────────────────────────
# BybitClient — stub behaviour
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bybit_connect_and_close_no_op():
    client = BybitClient(testnet=True)
    await client.connect()
    await client.close()


@pytest.mark.asyncio
async def test_bybit_get_market_details_raises_not_implemented():
    client = BybitClient(testnet=True)
    with pytest.raises(BybitNotImplementedError):
        await client.get_market_details("BTCUSD")


@pytest.mark.asyncio
async def test_bybit_unknown_epic_raises_broker_error():
    client = BybitClient(testnet=True)
    with pytest.raises(BrokerError):
        await client.get_market_details("XAUUSD")  # not in EPIC_TO_BYBIT_SYMBOL


def test_bybit_symbol_mapping_covers_top_basket():
    assert "BTCUSD" in EPIC_TO_BYBIT_SYMBOL
    assert EPIC_TO_BYBIT_SYMBOL["BTCUSD"] == "BTCUSDT"
    assert EPIC_TO_BYBIT_SYMBOL["ETHUSD"] == "ETHUSDT"


# ──────────────────────────────────────────────────────────────────────
# Exception hierarchy
# ──────────────────────────────────────────────────────────────────────


def test_capital_com_error_inherits_broker_error():
    assert issubclass(CapitalComError, BrokerError)


def test_bybit_not_implemented_inherits_broker_error():
    assert issubclass(BybitNotImplementedError, BrokerError)


# ──────────────────────────────────────────────────────────────────────
# Protocol runtime check (limited — Protocol with method bodies is
# structural, runtime_checkable only verifies attribute presence)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("client_cls", [BybitClient, MockBrokerClient])
def test_runtime_protocol_check(client_cls):
    instance = (
        client_cls(testnet=True) if client_cls is BybitClient else client_cls()
    )
    assert isinstance(instance, BrokerClientProtocol)
