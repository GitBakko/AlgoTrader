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
    """Transaction type for /history/transactions filter param.

    Capital.com live API accepts these values for the `type` query param:
      - TRADE      → trade open/close events (only ones carrying P&L)
      - SWAP       → overnight financing
      - DEPOSIT    → cash deposit
      - WITHDRAWAL → cash withdrawal

    `ALL` is a sentinel used by our client to signal "no filter at all"
    (the broker rejects an explicit type=ALL with empty results).
    Legacy `ALL_DEAL` is kept for backward compatibility but is treated
    as TRADE inside the client (the broker silently returns an empty
    list for it).
    """

    ALL = "ALL"
    ALL_DEAL = "ALL_DEAL"  # deprecated, mapped to TRADE
    TRADE = "TRADE"
    SWAP = "SWAP"
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

    model_config = {"populate_by_name": True}

    deal_id: str = Field(alias="dealId")
    epic: str
    direction: Direction
    size: float
    level: float  # Entry price
    currency: str
    created_date: datetime = Field(alias="createdDate")
    stop_level: float | None = Field(None, alias="stopLevel")
    profit_level: float | None = Field(None, alias="profitLevel")
    upl: float | None = None  # Unrealized P&L from broker
    market_status: str | None = None  # TRADEABLE, CLOSED, etc.


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

    The live demo API (verified 2026-04-21) returns these fields per record:
      - date / dateUtc       → broker-local time / UTC time
      - instrumentName       → broker epic (e.g. "OIL_CRUDE", "DE40")
      - transactionType      → "TRADE", "SWAP", "DEPOSIT", "WITHDRAWAL"
      - reference            → INTERNAL transaction id (NOT deal_reference)
      - dealId               → THE Position deal_id (deterministic match key)
      - size                 → STRING. For TRADE rows it carries the realized
                               P&L in account currency (e.g. "79.37", "-17.45").
                               For SWAP rows it is the financing amount.
      - currency             → e.g. "USDd"
      - note                 → "Trade closed", "Overnight fee", etc.
      - status               → "PROCESSED"

    Some legacy / older accounts may still return openLevel, closeLevel,
    profitAndLoss — they are kept optional for backward compat.
    """

    model_config = {"populate_by_name": True}

    date: datetime
    date_utc: datetime | None = Field(None, alias="dateUtc")
    transaction_type: str | None = Field(None, alias="transactionType")
    reference: str  # internal transaction id, NOT a deal_reference
    deal_id: str | None = Field(None, alias="dealId")
    instrument_name: str | None = Field(None, alias="instrumentName")
    size: str | float | None = None  # for TRADE: realized P&L as string
    note: str | None = None
    status: str | None = None
    open_level: float | None = Field(None, alias="openLevel")
    close_level: float | None = Field(None, alias="closeLevel")
    profit_and_loss: str | None = Field(None, alias="profitAndLoss")
    currency: str | None = None
    amount: float | None = None
    # Legacy alias support: pre-existing test fixtures emit `type=...`
    type: str | None = None

    @model_validator(mode="after")
    def _backfill_transaction_type(self) -> "Transaction":
        if self.transaction_type is None and self.type is not None:
            self.transaction_type = self.type
        return self

    @staticmethod
    def _parse_currency_string(raw: str | None) -> float | None:
        """Parse a Capital.com money string (e.g. 'USD21.73', '-USD6.69',
        '79.37', '-17.45') into a signed float."""
        if raw is None:
            return None
        cleaned = str(raw).strip()
        if not cleaned:
            return None
        sign = 1.0
        if cleaned.startswith("-"):
            sign = -1.0
            cleaned = cleaned[1:]
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

    @property
    def pl_value(self) -> float | None:
        """Realized P&L in transaction currency.

        Resolution order:
          1. Legacy `profitAndLoss` (e.g. "USD21.73") — old schema
          2. `size` field when transaction_type == "TRADE" (current live schema:
             size IS the P&L for trade-close rows)
          3. Legacy `amount` field
        Returns None if no field can be parsed.
        """
        v = self._parse_currency_string(self.profit_and_loss)
        if v is not None:
            return v

        if (self.transaction_type or "").upper() == "TRADE":
            v = self._parse_currency_string(
                self.size if isinstance(self.size, str) else (
                    None if self.size is None else f"{self.size}"
                )
            )
            if v is not None:
                return v

        return self.amount

    def pl_value_in(self, account_currency: str) -> float | None:
        """Return parsed P&L, logging a WARNING if the transaction currency
        differs from `account_currency`.

        Currency resolution:
          1. Prefix on legacy profitAndLoss string ("USD21.73" → "USD")
          2. The dedicated `currency` field (e.g. "USDd" → "USD")

        We DO NOT convert (a reliable FX feed is out of scope).
        """
        from loguru import logger

        value = self.pl_value
        if value is None:
            return None

        raw = (self.profit_and_loss or "").strip()
        prefix = ""
        if raw:
            for ch in raw.lstrip("-"):
                if ch.isdigit() or ch == ".":
                    break
                prefix += ch
        if not prefix and self.currency:
            # Capital.com sometimes appends a 'd' suffix on demo currencies
            # (e.g. "USDd" for USD demo). Strip non-letter trailing chars.
            cur = self.currency.strip()
            prefix = "".join(ch for ch in cur if ch.isalpha()).rstrip("d") or cur
        prefix = prefix.upper()
        account = (account_currency or "").upper()

        if prefix and account and prefix != account:
            logger.warning(
                f"Transaction P&L currency mismatch: "
                f"txn={prefix}{value:+.2f} account={account} "
                f"(ref={self.reference}, instrument={self.instrument_name}) — "
                f"value used as-is, no FX conversion"
            )
        return value


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
