"""Tests for CapitalComClient.get_transaction_history parameter serialization."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.broker.client import CapitalComClient
from src.broker.models import TransactionType


@pytest.mark.asyncio
async def test_transaction_history_sends_iso8601_utc_with_z_suffix():
    """from/to params MUST carry the 'Z' UTC suffix, otherwise Capital.com
    interprets them in server-local time and the window can miss recent
    closes (root cause of the 2026-04-20 incident)."""
    client = CapitalComClient.__new__(CapitalComClient)
    client._request = AsyncMock(return_value={"transactions": []})

    from_dt = datetime(2026, 4, 19, 20, 0, 0, tzinfo=timezone.utc)
    to_dt = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)

    await client.get_transaction_history(from_dt, to_dt, TransactionType.ALL_DEAL)

    assert client._request.await_count == 1
    _, kwargs = client._request.await_args
    params = kwargs["params"]
    assert params["from"].endswith("Z"), f"from must end with Z, got {params['from']!r}"
    assert params["to"].endswith("Z"), f"to must end with Z, got {params['to']!r}"
    assert params["from"] == "2026-04-19T20:00:00Z"
    assert params["to"] == "2026-04-20T00:00:00Z"
    assert params["type"] == TransactionType.ALL_DEAL.value
