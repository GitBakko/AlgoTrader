"""Task 15 — broker connect retries on 429 before falling back to PAPER."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_retries_on_429_and_eventually_succeeds():
    """connect() raises 429 twice, then succeeds on 3rd attempt."""
    from src.api.main import _connect_broker_with_retry

    broker = AsyncMock()
    # First two calls raise 429-like error, third succeeds
    broker.connect = AsyncMock(side_effect=[
        Exception("Authentication failed: 429"),
        Exception("Authentication failed: 429"),
        None,
    ])

    # initial_wait=0.01 to keep test fast
    await _connect_broker_with_retry(broker, initial_wait=0.01)

    assert broker.connect.await_count == 3


@pytest.mark.asyncio
async def test_raises_on_non_429_immediately():
    """Non-rate-limit errors are not retried."""
    from src.api.main import _connect_broker_with_retry

    broker = AsyncMock()
    broker.connect = AsyncMock(side_effect=Exception("Authentication failed: 401"))

    with pytest.raises(Exception, match="401"):
        await _connect_broker_with_retry(broker, initial_wait=0.01)

    # Only one attempt (no retry on 401)
    assert broker.connect.await_count == 1


@pytest.mark.asyncio
async def test_raises_on_429_after_max_attempts():
    """All attempts fail with 429 → raise the last error."""
    from src.api.main import _connect_broker_with_retry

    broker = AsyncMock()
    broker.connect = AsyncMock(side_effect=Exception("Authentication failed: 429"))

    with pytest.raises(Exception, match="429"):
        await _connect_broker_with_retry(broker, max_attempts=3, initial_wait=0.01)

    assert broker.connect.await_count == 3
