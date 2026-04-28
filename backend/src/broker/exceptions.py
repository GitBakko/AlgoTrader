"""
Custom exceptions for Capital.com API integration.
Maps Capital.com error codes to Python exceptions.
"""


class CapitalComError(Exception):
    """Base exception for all Capital.com API errors."""

    def __init__(self, message: str, error_code: str | None = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class AuthenticationError(CapitalComError):
    """Raised when authentication fails (invalid credentials)."""

    pass


class SessionExpiredError(CapitalComError):
    """Raised when session tokens have expired."""

    pass


class RateLimitError(CapitalComError):
    """Raised when API rate limit is exceeded."""

    pass


class InsufficientFundsError(CapitalComError):
    """Raised when account has insufficient funds for trade."""

    pass


class InvalidMarketError(CapitalComError):
    """Raised when epic/market is invalid or unavailable."""

    pass


class OrderRejectedError(CapitalComError):
    """Raised when order is rejected by broker."""

    pass


class MarketClosedError(CapitalComError):
    """Raised when market is currently closed."""

    pass


class ConnectionError(CapitalComError):
    """Raised when connection to API fails."""

    pass


class TimeoutError(CapitalComError):
    """Raised when API request times out."""

    pass


class NoPricesAvailableError(CapitalComError):
    """Broker has no candles in the requested window.

    Often a benign mid-bar edge case on Capital.com demo: requesting a
    HOUR_4 window that starts in the second half of an in-progress 4h bar
    returns 404 `error.prices.not-found` even though the market is healthy.
    Callers should treat this as "no data" rather than a hard failure.
    """

    pass


# Error code mapping
ERROR_CODE_MAP: dict[str, type[CapitalComError]] = {
    "error.invalid.session": SessionExpiredError,
    "error.invalid.credentials": AuthenticationError,
    "error.exceeds.rate-limit": RateLimitError,
    "error.insufficient.funds": InsufficientFundsError,
    "error.market.invalid": InvalidMarketError,
    "error.order.rejected": OrderRejectedError,
    "error.prices.not-found": NoPricesAvailableError,
}


def map_error(error_code: str, message: str = "") -> CapitalComError:
    """
    Map Capital.com error code to appropriate exception.

    Capital.com sometimes puts the full error message inside the errorCode field
    instead of using a structured code. This function handles both patterns:
    1. Exact match on known error codes (e.g., "error.invalid.session")
    2. Fuzzy match on message content (e.g., "Rejected. TSLA is currently closed...")

    Args:
        error_code: Capital.com error code or error message
        message: Optional additional error message

    Returns:
        Appropriate CapitalComError subclass
    """
    # 1. Exact match on known error codes
    if error_code in ERROR_CODE_MAP:
        return ERROR_CODE_MAP[error_code](message or error_code, error_code)

    # 2. Fuzzy match: Capital.com sometimes puts the full message in errorCode
    code_lower = (error_code or "").lower()
    full_msg = message or error_code

    if "currently closed" in code_lower or "timetable" in code_lower:
        return MarketClosedError(full_msg, "market.closed")
    if "insufficient" in code_lower and "fund" in code_lower:
        return InsufficientFundsError(full_msg, "error.insufficient.funds")
    if "rate" in code_lower and "limit" in code_lower:
        return RateLimitError(full_msg, "error.exceeds.rate-limit")
    if "minimum" in code_lower and "size" in code_lower:
        return OrderRejectedError(full_msg, "error.minimum.size")
    if "maximum" in code_lower and "position" in code_lower:
        return OrderRejectedError(full_msg, "error.max.positions")

    # 3. Fallback
    return CapitalComError(full_msg, error_code)
