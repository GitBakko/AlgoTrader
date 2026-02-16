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


# State Recovery fixtures


@pytest.fixture
def sample_positions():
    """Sample position data for state recovery testing."""
    return [
        {
            "deal_id": "POS001",
            "epic": "XAUUSD",
            "direction": "BUY",
            "size": 1.0,
            "level": 2075.50,
            "stop_loss": 2050.00,
            "take_profit": 2100.00,
            "unrealized_pnl": 25.00,
            "created_at": "2026-02-15T10:00:00Z",
        },
        {
            "deal_id": "POS002",
            "epic": "BTCUSD",
            "direction": "SELL",
            "size": 0.5,
            "level": 98500.00,
            "stop_loss": 99000.00,
            "take_profit": 97500.00,
            "unrealized_pnl": -50.00,
            "created_at": "2026-02-15T11:00:00Z",
        },
    ]


@pytest.fixture
def sample_trailing_stop_states():
    """Sample trailing stop states for recovery testing."""
    from decimal import Decimal

    return [
        {
            "deal_id": "POS001",
            "epic": "XAUUSD",
            "direction": "BUY",
            "entry_price": Decimal("2075.50"),
            "current_stop": Decimal("2070.00"),
            "phase": 2,
            "tp1_level": Decimal("2090.00"),
            "tp2_level": Decimal("2100.00"),
            "highest_price": Decimal("2085.00"),
            "lowest_price": None,
        },
        {
            "deal_id": "POS002",
            "epic": "BTCUSD",
            "direction": "SELL",
            "entry_price": Decimal("98500.00"),
            "current_stop": Decimal("98800.00"),
            "phase": 1,
            "tp1_level": Decimal("98000.00"),
            "tp2_level": Decimal("97500.00"),
            "highest_price": None,
            "lowest_price": Decimal("98200.00"),
        },
    ]


@pytest.fixture
def sample_risk_snapshot():
    """Sample risk state snapshot for recovery testing."""
    from decimal import Decimal

    return {
        "peak_equity": Decimal("10500.00"),
        "daily_start_equity": Decimal("10000.00"),
        "current_equity": Decimal("10150.00"),
        "consecutive_losses": 2,
        "tripped_breakers": {"US500": "2026-02-15T09:00:00Z"},
        "equity_curve_points": [10000.0, 10050.0, 10100.0, 10150.0],
    }


@pytest.fixture
def mock_risk_manager_with_state():
    """Mock RiskManager with fully initialized state for recovery tests."""
    from unittest.mock import MagicMock
    from decimal import Decimal

    risk_manager = MagicMock()

    # DrawdownMonitor with state
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.drawdown_monitor.state = MagicMock()
    risk_manager.drawdown_monitor.state.peak_equity = Decimal("10500.00")
    risk_manager.drawdown_monitor.state.daily_start_equity = Decimal("10000.00")
    risk_manager.drawdown_monitor.state.current_equity = Decimal("10150.00")
    risk_manager.drawdown_monitor.check_all = MagicMock(return_value=[])

    # CircuitBreakers
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.circuit_breakers.tripped_breakers = {}

    # EquityCurveFilter
    risk_manager.equity_curve_filter = MagicMock()
    risk_manager.equity_curve_filter.equity_curve = []

    return risk_manager


@pytest.fixture
def sample_trade_history():
    """Sample trade history for Kelly sizing recovery testing."""
    return [
        {"pnl": 50.00},
        {"pnl": -25.00},
        {"pnl": 75.00},
        {"pnl": -15.00},
        {"pnl": 100.00},
    ]


@pytest.fixture
async def mock_state_recovery_service(sample_positions, sample_trailing_stop_states):
    """Mock StateRecoveryService with sample data."""
    from unittest.mock import AsyncMock, MagicMock

    from src.execution.schemas import ExecutionMode
    from src.execution.state_recovery import StateRecoveryService

    # Mock dependencies
    execution_engine = MagicMock()
    execution_engine.mode = ExecutionMode.PAPER
    execution_engine._position_tracker = MagicMock()

    risk_manager = MagicMock()
    risk_manager.drawdown_monitor = MagicMock()
    risk_manager.circuit_breakers = MagicMock()
    risk_manager.equity_curve_filter = MagicMock()

    trailing_stop_manager = MagicMock()

    # Create service with mocks
    service = StateRecoveryService(
        execution_engine=execution_engine,
        risk_manager=risk_manager,
        trailing_stop_manager=trailing_stop_manager,
        broker=None,
        db_session_factory=None,
    )

    return service


@pytest.fixture
def mock_broker_client():
    """Mock Capital.com broker client for testing."""
    from unittest.mock import AsyncMock

    broker = AsyncMock()
    broker.list_positions = AsyncMock(return_value=[])
    broker.get_account = AsyncMock(
        return_value={"balance": 10000.0, "available": 9500.0, "deposit": 10000.0}
    )
    return broker


@pytest.fixture
async def mock_db_session():
    """Mock async database session for testing."""
    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()

    return session


@pytest.fixture
def async_db_session_factory(mock_db_session):
    """
    Factory that returns async context manager yielding mock DB session.
    Required for StateRecoveryService and repository tests.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        """Async context manager that yields mock DB session."""
        yield mock_db_session

    return factory
