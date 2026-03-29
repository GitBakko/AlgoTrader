"""
Pydantic models for Capital.com API requests and responses.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ===== Enums =====
class Direction(str, Enum):
    """Trade direction."""

    BUY = "BUY"
    SELL = "SELL"


class Resolution(str, Enum):
    """OHLC candle resolution."""

    MINUTE = "MINUTE"
    MINUTE_5 = "MINUTE_5"
    MINUTE_15 = "MINUTE_15"
    MINUTE_30 = "MINUTE_30"
    HOUR = "HOUR"
    HOUR_4 = "HOUR_4"
    DAY = "DAY"
    WEEK = "WEEK"


class OrderType(str, Enum):
    """Working order type."""

    LIMIT = "LIMIT"
    STOP = "STOP"


class TransactionType(str, Enum):
    """Transaction type for history."""

    ALL = "ALL"
    ALL_DEAL = "ALL_DEAL"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


# ===== Session Models =====
class SessionRequest(BaseModel):
    """Request to create a new session."""

    identifier: str
    password: str
    encrypted_password: bool = Field(default=False, alias="encryptedPassword")


class SessionTokens(BaseModel):
    """Session authentication tokens."""

    model_config = {"populate_by_name": True}

    cst: str
    security_token: str = Field(alias="x_security_token")
    created_at: datetime = Field(default_factory=datetime.now)


# ===== Market Data Models =====
class Market(BaseModel):
    """Market information."""

    model_config = {"populate_by_name": True}

    epic: str
    instrument_name: str = Field(alias="instrumentName")
    market_id: str | None = Field(None, alias="marketId")
    bid: float | None = None
    offer: float | None = None
    high: float | None = None
    low: float | None = None
    percent_change: float | None = Field(None, alias="percentageChange")


def _parse_price(v: Any) -> float:
    """Parse price from Capital.com API (can be float or {'bid': x, 'ask': y})."""
    if isinstance(v, dict):
        bid = v.get("bid", 0.0)
        ask = v.get("ask", 0.0)
        return (bid + ask) / 2  # mid-price
    return float(v)


class OHLCCandle(BaseModel):
    """OHLC candlestick data."""

    timestamp: datetime = Field(alias="snapshotTime")
    open: float = Field(alias="openPrice")
    high: float = Field(alias="highPrice")
    low: float = Field(alias="lowPrice")
    close: float = Field(alias="closePrice")
    last_traded_volume: int | None = Field(None, alias="lastTradedVolume")

    @field_validator("open", "high", "low", "close", mode="before")
    @classmethod
    def parse_bid_ask_price(cls, v: Any) -> float:
        """Capital.com returns prices as {'bid': x, 'ask': y} or plain float."""
        return _parse_price(v)


class PriceHistory(BaseModel):
    """Historical price data response."""

    prices: list[OHLCCandle]
    instrument_type: str = Field(alias="instrumentType")


class ClientSentiment(BaseModel):
    """Client sentiment data."""

    long_position_percentage: float = Field(alias="longPositionPercentage")
    short_position_percentage: float = Field(alias="shortPositionPercentage")


# ===== Position Models =====
class CreatePositionRequest(BaseModel):
    """Request to open a new position."""

    model_config = {"populate_by_name": True}

    epic: str
    direction: Direction
    size: float = Field(gt=0.0, le=100000.0)
    guaranteed_stop: bool = Field(default=False, alias="guaranteedStop")
    stop_level: float | None = Field(default=None, alias="stopLevel")
    profit_level: float | None = Field(default=None, alias="profitLevel")

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: float) -> float:
        """Validate and normalize position size for broker submission."""
        if v <= 0:
            raise ValueError(f"Position size must be positive, got {v}")
        if v > 100000:
            raise ValueError(f"Position size {v} exceeds maximum of 100000")
        # Round to 4 decimal places (Capital.com precision requirement)
        return round(v, 4)


class ModifyPositionRequest(BaseModel):
    """Request to modify an existing position."""

    model_config = {
        "populate_by_name": True,
        "exclude_none": True,
    }  # HIGH-1 FIX: Don't send None fields

    stop_level: float | None = Field(None, alias="stopLevel")
    profit_level: float | None = Field(None, alias="profitLevel")


class Position(BaseModel):
    """Open position information."""

    deal_id: str = Field(alias="dealId")
    epic: str
    direction: Direction
    size: float
    level: float  # Entry price
    currency: str
    created_date: datetime = Field(alias="createdDate")
    stop_level: float | None = Field(None, alias="stopLevel")
    profit_level: float | None = Field(None, alias="profitLevel")


# ===== Working Order Models =====
class CreateWorkingOrderRequest(BaseModel):
    """Request to create a working order (limit/stop)."""

    epic: str
    direction: Direction
    size: float
    level: float  # Trigger price
    type: OrderType
    good_till_date: datetime | None = Field(None, alias="goodTillDate")
    guaranteed_stop: bool = Field(default=False, alias="guaranteedStop")
    stop_level: float | None = Field(None, alias="stopLevel")
    profit_level: float | None = Field(None, alias="profitLevel")


class WorkingOrder(BaseModel):
    """Working order information."""

    deal_id: str = Field(alias="dealId")
    epic: str
    direction: Direction
    size: float
    level: float
    type: OrderType
    created_date: datetime = Field(alias="createdDate")
    good_till_date: datetime | None = Field(None, alias="goodTillDate")


# ===== Account Models =====
class Account(BaseModel):
    """Account information.

    Capital.com returns balance as a nested dict:
    {"balance": {"balance": 0.0, "deposit": 10000.0, "profitLoss": 0.0, "available": 0.0}}
    This model flattens it automatically.
    """

    account_id: str = Field(alias="accountId")
    account_name: str = Field(alias="accountName")
    account_type: str = Field(alias="accountType")
    currency: str
    balance: float = 0.0
    deposit: float = 0.0
    profit_loss: float = Field(default=0.0, alias="profitLoss")
    available: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def _flatten_balance(cls, data: Any) -> Any:
        """Flatten nested balance dict from Capital.com API."""
        if isinstance(data, dict) and isinstance(data.get("balance"), dict):
            bal = data.pop("balance")
            data["balance"] = bal.get("balance", 0.0)
            data.setdefault("deposit", bal.get("deposit", 0.0))
            data.setdefault("profitLoss", bal.get("profitLoss", 0.0))
            data.setdefault("available", bal.get("available", 0.0))
        return data


class Transaction(BaseModel):
    """Transaction history entry from Capital.com /history/transactions API.

    Capital.com returns fields like instrumentName, openLevel, closeLevel,
    profitAndLoss, size, etc.  We map them here so close detection can use
    the **real** exit price and P&L instead of guessing from the live price.
    """

    model_config = {"populate_by_name": True}

    date: datetime
    type: str
    reference: str  # deal reference (not always deal_id)
    instrument_name: str | None = Field(None, alias="instrumentName")
    size: float | None = None
    open_level: float | None = Field(None, alias="openLevel")
    close_level: float | None = Field(None, alias="closeLevel")
    profit_and_loss: str | None = Field(None, alias="profitAndLoss")
    currency: str | None = None
    # Keep legacy "amount" as optional fallback
    amount: float | None = None

    @property
    def pl_value(self) -> float | None:
        """Parse the profitAndLoss string (e.g. 'USD21.73' or '-USD6.69') into a float."""
        raw = self.profit_and_loss
        if raw is None:
            return self.amount  # fallback to amount field if present
        # Strip currency prefix: "USD21.73" → "21.73", "-USD6.69" → "-6.69"
        cleaned = raw.strip()
        if not cleaned:
            return None
        # Handle negative sign before currency code
        sign = 1.0
        if cleaned.startswith("-"):
            sign = -1.0
            cleaned = cleaned[1:]
        # Strip non-numeric prefix (currency code like "USD", "EUR", etc.)
        i = 0
        while i < len(cleaned) and not (cleaned[i].isdigit() or cleaned[i] == "."):
            i += 1
        num_str = cleaned[i:]
        if not num_str:
            return None
        try:
            return sign * float(num_str)
        except ValueError:
            return None


# ===== Trade Confirmation =====
class DealConfirmation(BaseModel):
    """Trade execution confirmation."""

    deal_id: str = Field(alias="dealId")
    deal_reference: str = Field(alias="dealReference")
    deal_status: str = Field(alias="dealStatus")
    epic: str
    direction: Direction
    size: float
    level: float  # Execution price
    profit_loss: float | None = Field(None, alias="profitLoss")
    status: str
    reason: str | None = None


# ===== API Response Wrapper =====
class CapitalComResponse(BaseModel):
    """Generic wrapper for Capital.com API responses."""

    success: bool = True
    data: Any = None
    error_code: str | None = Field(None, alias="errorCode")
    error_message: str | None = None
