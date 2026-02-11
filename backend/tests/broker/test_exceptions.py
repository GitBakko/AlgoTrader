"""
Unit tests for broker exception handling and error mapping.
"""

import pytest

from src.broker.exceptions import (
    AuthenticationError,
    CapitalComError,
    ConnectionError,
    InsufficientFundsError,
    InvalidMarketError,
    OrderRejectedError,
    RateLimitError,
    SessionExpiredError,
    TimeoutError,
    map_error,
)


@pytest.mark.unit
@pytest.mark.broker
class TestExceptionHierarchy:
    """Test exception class hierarchy and inheritance."""

    def test_base_exception_creation(self):
        """Test CapitalComError base exception creation."""
        error = CapitalComError("Test error", "TEST_CODE")
        assert error.message == "Test error"
        assert error.error_code == "TEST_CODE"
        assert str(error) == "Test error"

    def test_base_exception_without_code(self):
        """Test CapitalComError without error code."""
        error = CapitalComError("Test error")
        assert error.message == "Test error"
        assert error.error_code is None

    def test_authentication_error_inheritance(self):
        """Test AuthenticationError inherits from CapitalComError."""
        error = AuthenticationError("Invalid credentials", "AUTH_ERROR")
        assert isinstance(error, CapitalComError)
        assert error.message == "Invalid credentials"
        assert error.error_code == "AUTH_ERROR"

    def test_session_expired_error_inheritance(self):
        """Test SessionExpiredError inherits from CapitalComError."""
        error = SessionExpiredError("Session expired", "SESSION_ERROR")
        assert isinstance(error, CapitalComError)
        assert error.message == "Session expired"

    def test_rate_limit_error_inheritance(self):
        """Test RateLimitError inherits from CapitalComError."""
        error = RateLimitError("Rate limit exceeded", "RATE_LIMIT")
        assert isinstance(error, CapitalComError)
        assert error.message == "Rate limit exceeded"

    def test_insufficient_funds_error_inheritance(self):
        """Test InsufficientFundsError inherits from CapitalComError."""
        error = InsufficientFundsError("Not enough funds", "FUNDS_ERROR")
        assert isinstance(error, CapitalComError)
        assert error.message == "Not enough funds"

    def test_invalid_market_error_inheritance(self):
        """Test InvalidMarketError inherits from CapitalComError."""
        error = InvalidMarketError("Invalid market", "MARKET_ERROR")
        assert isinstance(error, CapitalComError)
        assert error.message == "Invalid market"

    def test_order_rejected_error_inheritance(self):
        """Test OrderRejectedError inherits from CapitalComError."""
        error = OrderRejectedError("Order rejected", "ORDER_ERROR")
        assert isinstance(error, CapitalComError)
        assert error.message == "Order rejected"

    def test_connection_error_inheritance(self):
        """Test ConnectionError inherits from CapitalComError."""
        error = ConnectionError("Connection failed", "CONN_ERROR")
        assert isinstance(error, CapitalComError)
        assert error.message == "Connection failed"

    def test_timeout_error_inheritance(self):
        """Test TimeoutError inherits from CapitalComError."""
        error = TimeoutError("Request timeout", "TIMEOUT_ERROR")
        assert isinstance(error, CapitalComError)
        assert error.message == "Request timeout"


@pytest.mark.unit
@pytest.mark.broker
class TestErrorMapping:
    """Test error code mapping functionality."""

    def test_map_session_expired(self):
        """Test mapping of session expired error code."""
        error = map_error("error.invalid.session", "Your session has expired")
        assert isinstance(error, SessionExpiredError)
        assert error.message == "Your session has expired"
        assert error.error_code == "error.invalid.session"

    def test_map_invalid_credentials(self):
        """Test mapping of invalid credentials error code."""
        error = map_error("error.invalid.credentials", "Login failed")
        assert isinstance(error, AuthenticationError)
        assert error.message == "Login failed"
        assert error.error_code == "error.invalid.credentials"

    def test_map_rate_limit(self):
        """Test mapping of rate limit error code."""
        error = map_error("error.exceeds.rate-limit", "Too many requests")
        assert isinstance(error, RateLimitError)
        assert error.message == "Too many requests"
        assert error.error_code == "error.exceeds.rate-limit"

    def test_map_insufficient_funds(self):
        """Test mapping of insufficient funds error code."""
        error = map_error("error.insufficient.funds", "Not enough balance")
        assert isinstance(error, InsufficientFundsError)
        assert error.message == "Not enough balance"
        assert error.error_code == "error.insufficient.funds"

    def test_map_invalid_market(self):
        """Test mapping of invalid market error code."""
        error = map_error("error.market.invalid", "Market not found")
        assert isinstance(error, InvalidMarketError)
        assert error.message == "Market not found"
        assert error.error_code == "error.market.invalid"

    def test_map_order_rejected(self):
        """Test mapping of order rejected error code."""
        error = map_error("error.order.rejected", "Order was rejected")
        assert isinstance(error, OrderRejectedError)
        assert error.message == "Order was rejected"
        assert error.error_code == "error.order.rejected"

    def test_map_unknown_error_code(self):
        """Test mapping of unknown error code falls back to base exception."""
        error = map_error("error.unknown.code", "Unknown error")
        assert isinstance(error, CapitalComError)
        assert not isinstance(error, (AuthenticationError, SessionExpiredError, RateLimitError))
        assert error.message == "Unknown error"
        assert error.error_code == "error.unknown.code"

    def test_map_error_without_message(self):
        """Test mapping error code without custom message uses code as message."""
        error = map_error("error.invalid.session")
        assert isinstance(error, SessionExpiredError)
        assert error.message == "error.invalid.session"
        assert error.error_code == "error.invalid.session"

    def test_map_error_empty_message(self):
        """Test mapping error code with empty message uses code as message."""
        error = map_error("error.invalid.credentials", "")
        assert isinstance(error, AuthenticationError)
        assert error.message == "error.invalid.credentials"
        assert error.error_code == "error.invalid.credentials"
