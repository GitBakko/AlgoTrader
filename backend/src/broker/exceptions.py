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


class ConnectionError(CapitalComError):
    """Raised when connection to API fails."""

    pass


class TimeoutError(CapitalComError):
    """Raised when API request times out."""

    pass


# Error code mapping
ERROR_CODE_MAP: dict[str, type[CapitalComError]] = {
    "error.invalid.session": SessionExpiredError,
    "error.invalid.credentials": AuthenticationError,
    "error.exceeds.rate-limit": RateLimitError,
    "error.insufficient.funds": InsufficientFundsError,
    "error.market.invalid": InvalidMarketError,
    "error.order.rejected": OrderRejectedError,
}


def map_error(error_code: str, message: str = "") -> CapitalComError:
    """
    Map Capital.com error code to appropriate exception.

    Args:
        error_code: Capital.com error code (e.g., "error.invalid.session")
        message: Optional error message

    Returns:
        Appropriate CapitalComError subclass
    """
    exception_class = ERROR_CODE_MAP.get(error_code, CapitalComError)
    return exception_class(message or error_code, error_code)
