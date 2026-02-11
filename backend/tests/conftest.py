"""
Pytest configuration and shared fixtures for AlgoTrader AI tests.
"""

import asyncio
from datetime import datetime
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient, Response

from src.broker.models import (
    Account,
    DealConfirmation,
    Market,
    OHLCCandle,
    Position,
    SessionTokens,
    WorkingOrder,
)
from src.utils.config import get_settings


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings():
    """Get application settings."""
    return get_settings()


@pytest.fixture
def mock_session_tokens():
    """Mock Capital.com session tokens."""
    return SessionTokens(
        cst="mock_cst_token_12345",
        security_token="mock_security_token_67890",
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def mock_market():
    """Mock market data."""
    return Market(
        epic="GOLD",
        instrument_name="Gold",
        instrument_type="COMMODITIES",
        market_id="GOLD",
        expiry=None,
        high=2100.50,
        low=2050.25,
        offer=2080.00,
        bid=2079.50,
        update_time="2026-02-10T12:00:00",
    )


@pytest.fixture
def mock_ohlc_candle():
    """Mock OHLC candle."""
    return OHLCCandle(
        snapshot_time="2026-02-10T12:00:00",
        open_price=2075.00,
        high_price=2080.00,
        low_price=2070.00,
        close_price=2078.00,
        last_traded_volume=1000,
    )


@pytest.fixture
def mock_position():
    """Mock open position."""
    return Position(
        deal_id="DEAL123456",
        deal_reference="REF789",
        epic="GOLD",
        direction="BUY",
        size=1.0,
        level=2075.00,
        created_date="2026-02-10T10:00:00",
        profit_loss=150.00,
        stop_level=2050.00,
        limit_level=2100.00,
    )


@pytest.fixture
def mock_account():
    """Mock account data."""
    return Account(
        account_id="ACC123",
        account_name="Demo Account",
        balance=10000.00,
        deposit=10000.00,
        profit_loss=150.00,
        available=9500.00,
    )


@pytest.fixture
def mock_deal_confirmation():
    """Mock deal confirmation."""
    return DealConfirmation(
        deal_reference="REF123456",
        deal_status="ACCEPTED",
        epic="GOLD",
        status="OPEN",
        reason="SUCCESS",
        deal_id="DEAL789",
        affected_deals=[],
        level=2075.00,
        size=1.0,
        direction="BUY",
        profit_loss=0.0,
    )


@pytest.fixture
async def mock_httpx_client():
    """Mock httpx async client for API testing."""
    async with AsyncClient(base_url="https://demo-api-capital.backend-capital.com") as client:
        yield client


@pytest.fixture
def mock_api_response():
    """Factory for creating mock API responses."""

    def _create_response(
        status_code: int = 200, json_data: dict | None = None, headers: dict | None = None
    ) -> Response:
        """Create a mock Response object."""
        return Response(
            status_code=status_code,
            json=json_data or {},
            headers=headers or {},
        )

    return _create_response


# Broker module fixtures


@pytest.fixture
def mock_rate_limiter_tokens():
    """Mock rate limiter with pre-filled tokens."""
    from src.broker.rate_limiter import RateLimiter

    limiter = RateLimiter(requests_per_second=10, burst_capacity=20)
    limiter._available_tokens = 10.0  # Pre-fill tokens
    return limiter
