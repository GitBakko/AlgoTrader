"""
Pydantic models for Capital.com API requests and responses.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ===== Timezone helpers =====
# Capital.com ``/positions`` returns ``createdDate`` as a naive wall-clock
# string in Europe/Berlin (verified live 2026-04-22: a position opened at
# 12:16 UTC carries ``createdDate="2026-04-22T14:16:50"`` — broker-local
# CEST). Downstream code (CloseDetector window / match, DB writes,
# analytics) assumes UTC-aware datetimes, so naive broker timestamps get
# normalised here at the ingest boundary.
_BROKER_LOCAL_TZ_NAME = "Europe/Berlin"


def _normalize_broker_datetime(v: Any) -> Any:
    """Pydantic ``mode='before'`` validator helper.

    - ``None`` / empty / non-datetime values pass through unchanged.
    - Strings are parsed via ``datetime.fromisoformat``; on failure the
      raw value is returned so pydantic's own parser can raise the usual
      validation error.
    - Naive datetimes are interpreted as broker-local (Europe/Berlin)
      and converted to UTC.
    - tz-aware datetimes are converted to UTC.
    """
    if v is None or v == "":
        return v
    dt: datetime | None = None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            return v  # let pydantic complain
    else:
        return v
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo

            dt = dt.replace(tzinfo=ZoneInfo(_BROKER_LOCAL_TZ_NAME))
        except Exception:
            dt = dt.replace(tzinfo=UTC)  # safest fallback
    return dt.astimezone(UTC)


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
    # M3-BROKER fix: tz-aware default so expiry comparisons against
    # tz-aware datetime.now(UTC) don't TypeError silently in tests.
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    # snapshotTime is SERVER-LOCAL wall-clock (UTC+2 in summer); snapshotTimeUTC
    # is the true UTC bar-start. Any intraday window filter MUST use this field
    # (naive == UTC). Optional: defensive vs responses that omit it.
    timestamp_utc: datetime | None = Field(None, alias="snapshotTimeUTC")
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

    @field_validator("created_date", mode="before")
    @classmethod
    def _normalize_created_date(cls, v: Any) -> Any:
        """Normalise the naive-Berlin ``createdDate`` to UTC-aware.

        See module-level ``_normalize_broker_datetime`` for the rationale.
        Once this runs, every downstream consumer of ``Position.created_date``
        (paper_loop._previous_positions, CloseDetector activity window /
        ``date > opened_at`` guard, DB writes) gets a correct UTC value.
        """
        return _normalize_broker_datetime(v)


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
                self.size
                if isinstance(self.size, str)
                else (None if self.size is None else f"{self.size}")
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


# ===== Activity History (Capital.com /api/v1/history/activity) =====
#
# The activity endpoint is the AUTHORITATIVE source for close-event linkage.
# Unlike /history/transactions (which only exposes the realized P&L and a
# close-side dealId that may differ from the Position.dealId — verified
# 2026-04-21: broker-initiated TP/SL closes emit position_dealId+1), activity
# events carry:
#   - `source`        → close reason (TP / SL / USER / SYSTEM / STOP_OUT / …)
#   - `details.openPrice` → the ORIGINAL position entry price
#   - `details.direction` → reversed direction on the close event
# This lets us deterministically link a close event back to our Position row
# via (epic, openPrice, reverse direction, date > opened_at) WITHOUT relying
# on stable dealIds. See plan calm-questing-quail.md and project memory
# `project_capital_com_dealid_mutation.md`.


class ActivitySource(str, Enum):
    """Origin of an activity event. Non-exhaustive — unknown values accepted
    via the pydantic `use_enum_values` on the model.

    CLOSE sources (mark a closed position):
      - TP          → take-profit hit
      - SL          → stop-loss hit
      - STOP_OUT    → liquidation / forced close
      - MARGIN_CALL → margin-call close
      - USER        → closed by the user (e.g. our close API call)
      - SYSTEM      → closed by broker system logic
      - DEALER      → manual dealer intervention

    NON-CLOSE sources (create / amend / fund):
      - CLOSE_POSITION is a user close in some docs; treated as USER
    """

    TP = "TP"
    SL = "SL"
    STOP_OUT = "STOP_OUT"
    MARGIN_CALL = "MARGIN_CALL"
    USER = "USER"
    SYSTEM = "SYSTEM"
    DEALER = "DEALER"
    CLOSE_POSITION = "CLOSE_POSITION"


CLOSE_SOURCES: set[str] = {
    ActivitySource.TP.value,
    ActivitySource.SL.value,
    ActivitySource.STOP_OUT.value,
    ActivitySource.MARGIN_CALL.value,
    ActivitySource.USER.value,
    ActivitySource.SYSTEM.value,
    ActivitySource.DEALER.value,
    ActivitySource.CLOSE_POSITION.value,
}


class ActivityType(str, Enum):
    """Activity event type."""

    POSITION = "POSITION"
    WORKING_ORDER = "WORKING_ORDER"
    EDIT_STOP_AND_LIMIT = "EDIT_STOP_AND_LIMIT"
    SWAP = "SWAP"


class ActivityStatus(str, Enum):
    """Activity event status."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


class ActivityEventDetails(BaseModel):
    """Nested `details` object on an activity event.

    Only the fields we use are typed strictly; unknown keys are ignored.
    """

    model_config = {"populate_by_name": True, "extra": "ignore"}

    deal_reference: str | None = Field(None, alias="dealReference")
    working_order_id: str | None = Field(None, alias="workingOrderId")
    market_name: str | None = Field(None, alias="marketName")
    currency: str | None = None
    size: float | None = None
    direction: Direction | None = None
    level: float | None = None
    stop_level: float | None = Field(None, alias="stopLevel")
    profit_level: float | None = Field(None, alias="profitLevel")
    guaranteed_stop: bool | None = Field(None, alias="guaranteedStop")
    # Present on close-side POSITION events — this is the ORIGINAL entry
    # price of the position being closed. Our strongest, most portable link
    # from a close event back to our Position row.
    open_price: float | None = Field(None, alias="openPrice")
    swap: float | None = None


class ActivityEvent(BaseModel):
    """A single event from `/api/v1/history/activity`.

    Schema is intentionally permissive: Capital.com occasionally adds new
    source / type values without warning. We accept unknown strings for
    `source`, `type`, `status` and defer classification to helper methods so
    a broker-side enum extension never breaks ingestion.
    """

    model_config = {"populate_by_name": True, "extra": "ignore"}

    date: datetime
    date_utc: datetime | None = Field(None, alias="dateUTC")
    epic: str
    # Keep as raw strings so unknown new values do not blow up parsing.
    source: str
    type: str
    status: str
    # Close-side dealId (e.g. the TP/SL-generated id); equal to the
    # Position.dealId only for user-initiated closes.
    deal_id: str = Field(alias="dealId")
    details: ActivityEventDetails = Field(default_factory=ActivityEventDetails)

    def is_close_event(self) -> bool:
        """True if this event represents a position close we should reconcile.

        The invariant is that close-side POSITION events carry
        ``details.openPrice`` (the original entry price). OPEN-side POSITION
        events emitted at position creation time have the same
        ``type=POSITION / status=ACCEPTED`` shape but do NOT carry
        ``openPrice``. Requiring it here is what cleanly separates the two
        and is exactly the field we rely on to link the close back to our
        Position row in v2 close detection.
        """
        return (
            self.type == ActivityType.POSITION.value
            and self.status == ActivityStatus.ACCEPTED.value
            and self.source.upper() in CLOSE_SOURCES
            and self.details.open_price is not None
        )

    def close_reason_label(self) -> str:
        """Short label used as Position.close_reason."""
        s = (self.source or "").upper()
        if s == ActivitySource.TP.value:
            return "TAKE_PROFIT_HIT"
        if s == ActivitySource.SL.value:
            return "STOP_LOSS_HIT"
        if s in (ActivitySource.STOP_OUT.value, ActivitySource.MARGIN_CALL.value):
            return "LIQUIDATION"
        if s in (ActivitySource.USER.value, ActivitySource.CLOSE_POSITION.value):
            return "USER_CLOSE"
        if s == ActivitySource.DEALER.value:
            return "DEALER_CLOSE"
        if s == ActivitySource.SYSTEM.value:
            return "SYSTEM_CLOSE"
        return f"EXTERNAL_{s}"


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
