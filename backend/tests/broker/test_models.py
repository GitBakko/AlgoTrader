"""
Unit tests for broker Pydantic models.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.broker.models import (
    Account,
    CreatePositionRequest,
    DealConfirmation,
    Direction,
    Market,
    ModifyPositionRequest,
    OHLCCandle,
    OrderType,
    Position,
    Resolution,
    SessionRequest,
    SessionTokens,
    TransactionType,
    WorkingOrder,
)


@pytest.mark.unit
@pytest.mark.broker
class TestSessionModels:
    """Test session-related models."""

    def test_session_request_valid(self):
        """Test valid session request creation."""
        request = SessionRequest(
            identifier="test@example.com", password="test123", encrypted_password=False
        )
        assert request.identifier == "test@example.com"
        assert request.password == "test123"
        assert request.encrypted_password is False

    def test_session_request_model_dump(self):
        """Test session request serialization with aliases."""
        request = SessionRequest(
            identifier="test@example.com", password="test123", encrypted_password=False
        )
        dumped = request.model_dump(by_alias=True)
        assert dumped["identifier"] == "test@example.com"
        assert dumped["encryptedPassword"] is False

    def test_session_tokens_valid(self):
        """Test valid session tokens creation."""
        tokens = SessionTokens(
            cst="mock_cst", security_token="mock_token", created_at=datetime.utcnow()
        )
        assert tokens.cst == "mock_cst"
        assert tokens.security_token == "mock_token"
        assert isinstance(tokens.created_at, datetime)


@pytest.mark.unit
@pytest.mark.broker
class TestMarketModels:
    """Test market data models."""

    def test_market_valid(self):
        """Test valid market creation."""
        market = Market(
            epic="GOLD",
            instrument_name="Gold",
            instrument_type="COMMODITIES",
            market_id="GOLD_ID",
            expiry=None,
            high=2100.0,
            low=2050.0,
            offer=2080.0,
            bid=2079.0,
            update_time="2026-02-10T12:00:00",
        )
        assert market.epic == "GOLD"
        assert market.instrument_name == "Gold"
        assert market.high == 2100.0

    def test_ohlc_candle_valid(self):
        """Test valid OHLC candle creation."""
        from datetime import datetime

        candle = OHLCCandle(
            snapshotTime=datetime.fromisoformat("2026-02-10T12:00:00"),
            openPrice=2075.0,
            highPrice=2080.0,
            lowPrice=2070.0,
            closePrice=2078.0,
            lastTradedVolume=1000,
        )
        assert candle.open == 2075.0
        assert candle.close == 2078.0
        assert candle.last_traded_volume == 1000


@pytest.mark.unit
@pytest.mark.broker
class TestPositionModels:
    """Test position-related models."""

    def test_position_valid(self):
        """Test valid position creation."""
        from datetime import datetime

        position = Position(
            dealId="DEAL123",
            epic="GOLD",
            direction=Direction.BUY,
            size=1.0,
            level=2075.0,
            currency="USD",
            createdDate=datetime.fromisoformat("2026-02-10T10:00:00"),
            stopLevel=2050.0,
            profitLevel=2100.0,
        )
        assert position.deal_id == "DEAL123"
        assert position.direction == Direction.BUY
        assert position.stop_level == 2050.0

    def test_create_position_request_valid(self):
        """Test valid create position request."""
        request = CreatePositionRequest(
            epic="GOLD",
            direction=Direction.BUY,
            size=1.0,
            stop_level=2050.0,
            profit_level=2100.0,
        )
        assert request.epic == "GOLD"
        assert request.direction == Direction.BUY
        assert request.size == 1.0

    def test_create_position_request_serialization(self):
        """Test create position request serialization with aliases."""
        request = CreatePositionRequest(
            epic="GOLD",
            direction=Direction.BUY,
            size=1.0,
            stopLevel=2050.0,
            profitLevel=2100.0,
        )
        dumped = request.model_dump(by_alias=True)
        assert dumped["stopLevel"] == 2050.0
        assert dumped["profitLevel"] == 2100.0

    def test_modify_position_request_valid(self):
        """Test valid modify position request."""
        request = ModifyPositionRequest(stopLevel=2055.0, profitLevel=2105.0)
        assert request.stop_level == 2055.0
        assert request.profit_level == 2105.0


@pytest.mark.unit
@pytest.mark.broker
class TestEnums:
    """Test enum types."""

    def test_direction_enum(self):
        """Test Direction enum values."""
        assert Direction.BUY.value == "BUY"
        assert Direction.SELL.value == "SELL"

    def test_resolution_enum(self):
        """Test Resolution enum values."""
        assert Resolution.MINUTE.value == "MINUTE"
        assert Resolution.HOUR.value == "HOUR"
        assert Resolution.DAY.value == "DAY"

    def test_order_type_enum(self):
        """Test OrderType enum values."""
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP.value == "STOP"

    def test_transaction_type_enum(self):
        """Test TransactionType enum values."""
        assert TransactionType.ALL.value == "ALL"
        assert TransactionType.DEPOSIT.value == "DEPOSIT"


@pytest.mark.unit
@pytest.mark.broker
class TestAccountModels:
    """Test account-related models."""

    def test_account_valid(self):
        """Test valid account creation."""
        account = Account(
            accountId="ACC123",
            accountName="Demo Account",
            accountType="CFD",
            currency="USD",
            balance=10000.0,
            deposit=10000.0,
            profitLoss=150.0,
            available=9500.0,
        )
        assert account.account_id == "ACC123"
        assert account.balance == 10000.0
        assert account.profit_loss == 150.0


@pytest.mark.unit
@pytest.mark.broker
class TestDealConfirmation:
    """Test deal confirmation model."""

    def test_deal_confirmation_valid(self):
        """Test valid deal confirmation."""
        confirmation = DealConfirmation(
            dealId="DEAL123",
            dealReference="REF123",
            dealStatus="ACCEPTED",
            epic="GOLD",
            direction=Direction.BUY,
            size=1.0,
            level=2075.0,
            profitLoss=0.0,
            status="OPEN",
            reason="SUCCESS",
        )
        assert confirmation.deal_status == "ACCEPTED"
        assert confirmation.reason == "SUCCESS"
        assert confirmation.size == 1.0
