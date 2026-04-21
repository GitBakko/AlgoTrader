"""Tests for CapitalComClient.get_transaction_history parameter serialization."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.broker.client import CapitalComClient
from src.broker.models import TransactionType


@pytest.mark.asyncio
async def test_transaction_history_serializes_params_in_utc_without_suffix():
    """Capital.com /history/transactions rejects any timezone suffix
    ('Z' or '+00:00') with error.invalid.from (HTTP 400). We normalize the
    input to UTC so the string is unambiguous to us, but must strip the
    suffix before sending. Empirically verified against demo-api on
    2026-04-20 after the Z-suffix regression."""
    client = CapitalComClient.__new__(CapitalComClient)
    client._request = AsyncMock(return_value={"transactions": []})

    from_dt = datetime(2026, 4, 19, 20, 0, 0, tzinfo=UTC)
    to_dt = datetime(2026, 4, 20, 0, 0, 0, tzinfo=UTC)

    await client.get_transaction_history(from_dt, to_dt, TransactionType.TRADE)

    assert client._request.await_count == 1
    _, kwargs = client._request.await_args
    params = kwargs["params"]
    # No 'Z' suffix, no '+00:00' offset — Capital.com rejects those
    assert not params["from"].endswith("Z"), f"from must NOT end with Z, got {params['from']!r}"
    assert "+" not in params["from"], f"from must NOT carry offset, got {params['from']!r}"
    assert params["from"] == "2026-04-19T20:00:00"
    assert params["to"] == "2026-04-20T00:00:00"
    assert params["type"] == TransactionType.TRADE.value


@pytest.mark.asyncio
async def test_transaction_history_converts_non_utc_input_to_utc():
    """Non-UTC inputs are converted to UTC before serialization."""
    from datetime import timedelta, timezone

    client = CapitalComClient.__new__(CapitalComClient)
    client._request = AsyncMock(return_value={"transactions": []})

    # 22:00 Europe/Rome (UTC+2 in DST) == 20:00 UTC
    rome = timezone(timedelta(hours=2))
    from_dt = datetime(2026, 4, 19, 22, 0, 0, tzinfo=rome)

    await client.get_transaction_history(from_dt, datetime(2026, 4, 20, 0, 0, 0, tzinfo=UTC))

    params = client._request.await_args.kwargs["params"]
    assert params["from"] == "2026-04-19T20:00:00"


@pytest.mark.asyncio
async def test_transaction_history_drops_type_param_for_all_and_legacy_all_deal():
    """The Capital.com endpoint silently returns an empty list when `type=ALL`
    or `type=ALL_DEAL` is sent (verified against demo-api 2026-04-21).
    Our client must drop the `type` param entirely in those cases so the
    server returns every transaction in the requested window."""
    client = CapitalComClient.__new__(CapitalComClient)
    client._request = AsyncMock(return_value={"transactions": []})

    from_dt = datetime(2026, 4, 19, 20, 0, 0, tzinfo=UTC)
    to_dt = datetime(2026, 4, 20, 0, 0, 0, tzinfo=UTC)

    await client.get_transaction_history(from_dt, to_dt, TransactionType.ALL)
    params = client._request.await_args.kwargs["params"]
    assert "type" not in params, f"type param must be dropped for ALL, got {params!r}"

    client._request.reset_mock()
    await client.get_transaction_history(from_dt, to_dt, TransactionType.ALL_DEAL)
    params = client._request.await_args.kwargs["params"]
    assert "type" not in params, (
        f"type param must be dropped for legacy ALL_DEAL, got {params!r}"
    )


@pytest.mark.asyncio
async def test_transaction_history_default_type_is_trade():
    """Default filter is TRADE because that's the only transaction_type that
    carries a realized P&L on the live Capital.com schema (SWAP rows are
    overnight financing, not closes)."""
    client = CapitalComClient.__new__(CapitalComClient)
    client._request = AsyncMock(return_value={"transactions": []})

    from_dt = datetime(2026, 4, 19, 20, 0, 0, tzinfo=UTC)
    to_dt = datetime(2026, 4, 20, 0, 0, 0, tzinfo=UTC)

    await client.get_transaction_history(from_dt, to_dt)

    params = client._request.await_args.kwargs["params"]
    assert params["type"] == "TRADE"
