"""
Unit tests for Capital.com session management.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.broker.exceptions import AuthenticationError
from src.broker.models import SessionTokens
from src.broker.session import SessionManager


@pytest.mark.unit
@pytest.mark.broker
class TestSessionManager:
    """Test SessionManager authentication and lifecycle."""

    def test_initialization(self):
        """Test SessionManager initialization."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
            session_timeout_minutes=10,
        )
        assert manager.api_url == "https://demo-api.example.com"
        assert manager.api_key == "test_key"
        assert manager.email == "test@example.com"
        assert manager.password == "test_pass"
        assert manager.session_timeout_minutes == 10
        assert manager.tokens is None

    def test_initialization_strips_trailing_slash(self):
        """Test that trailing slash is removed from API URL."""
        manager = SessionManager(
            api_url="https://demo-api.example.com/",
            api_key="key",
            email="email",
            password="pass",
        )
        assert manager.api_url == "https://demo-api.example.com"

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_session_tokens):
        """Test successful authentication."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Mock httpx response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {
            "CST": "mock_cst_token",
            "X-SECURITY-TOKEN": "mock_security_token",
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch.object(manager, "_get_http_client", return_value=mock_client):
            with patch.object(manager, "_start_ping_task", new_callable=AsyncMock):
                tokens = await manager.authenticate()

        assert tokens.cst == "mock_cst_token"
        assert tokens.security_token == "mock_security_token"
        assert manager.tokens == tokens
        assert isinstance(tokens.created_at, datetime)

        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "api/v1/session" in call_args[0][0]
        assert call_args[1]["headers"]["X-CAP-API-KEY"] == "test_key"

    @pytest.mark.asyncio
    async def test_authenticate_failure_status_code(self):
        """Test authentication failure with non-200 status code."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="wrong_pass",
        )

        # Mock httpx response with error
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.text = '{"errorCode": "error.invalid.credentials"}'
        mock_response.json.return_value = {"errorCode": "error.invalid.credentials"}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch.object(manager, "_get_http_client", return_value=mock_client):
            with pytest.raises(AuthenticationError, match="Authentication failed: 401"):
                await manager.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_missing_tokens_in_headers(self):
        """Test authentication failure when response headers missing tokens."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Mock httpx response with missing tokens
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}  # Missing CST and X-SECURITY-TOKEN

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch.object(manager, "_get_http_client", return_value=mock_client):
            with pytest.raises(AuthenticationError, match="Missing session tokens"):
                await manager.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_http_error(self):
        """Test authentication failure with HTTP error."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError("Connection failed")

        with patch.object(manager, "_get_http_client", return_value=mock_client):
            with pytest.raises(AuthenticationError, match="HTTP error"):
                await manager.authenticate()

    @pytest.mark.asyncio
    async def test_get_tokens_when_none(self):
        """Test get_tokens re-authenticates when no tokens exist."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        assert manager.tokens is None

        # Mock authenticate method
        expected_tokens = SessionTokens(
            cst="new_cst", security_token="new_token", created_at=datetime.now(timezone.utc)
        )

        with patch.object(manager, "authenticate", return_value=expected_tokens) as mock_auth:
            tokens = await manager.get_tokens()

        assert tokens == expected_tokens
        mock_auth.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tokens_when_valid(self):
        """Test get_tokens returns existing valid tokens."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
            session_timeout_minutes=10,
        )

        # Set valid tokens (created recently)
        manager.tokens = SessionTokens(
            cst="valid_cst",
            security_token="valid_token",
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(manager, "authenticate") as mock_auth:
            tokens = await manager.get_tokens()

        # Should return existing tokens without re-authentication
        assert tokens == manager.tokens
        mock_auth.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_tokens_when_expired(self):
        """Test get_tokens re-authenticates when tokens expired."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
            session_timeout_minutes=10,
        )

        # Set expired tokens (created 11 minutes ago)
        manager.tokens = SessionTokens(
            cst="expired_cst",
            security_token="expired_token",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=11),
        )

        new_tokens = SessionTokens(
            cst="new_cst", security_token="new_token", created_at=datetime.now(timezone.utc)
        )

        with patch.object(manager, "authenticate", return_value=new_tokens) as mock_auth:
            tokens = await manager.get_tokens()

        # Should re-authenticate and return new tokens
        assert tokens == new_tokens
        mock_auth.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_success(self):
        """Test successful keep-alive ping."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        manager.tokens = SessionTokens(
            cst="test_cst", security_token="test_token", created_at=datetime.now(timezone.utc)
        )

        # Mock httpx response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with patch.object(manager, "_get_http_client", return_value=mock_client):
            result = await manager.ping()

        assert result is True
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_failure(self):
        """Test failed keep-alive ping."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        manager.tokens = SessionTokens(
            cst="test_cst", security_token="test_token", created_at=datetime.now(timezone.utc)
        )

        # Mock httpx response with error
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 401

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with patch.object(manager, "_get_http_client", return_value=mock_client):
            result = await manager.ping()

        assert result is False

    @pytest.mark.asyncio
    async def test_ping_exception(self):
        """Test ping handles exceptions gracefully."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        manager.tokens = SessionTokens(
            cst="test_cst", security_token="test_token", created_at=datetime.now(timezone.utc)
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("Connection failed")

        with patch.object(manager, "_get_http_client", return_value=mock_client):
            result = await manager.ping()

        assert result is False

    @pytest.mark.asyncio
    async def test_start_ping_task(self):
        """Test starting background ping task."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        assert manager._ping_task is None

        await manager._start_ping_task()

        # Should create a task
        assert manager._ping_task is not None
        assert isinstance(manager._ping_task, asyncio.Task)
        assert not manager._ping_task.done()

        # Cleanup
        manager._ping_task.cancel()
        try:
            await manager._ping_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_start_ping_task_cancels_existing(self):
        """Test starting ping task cancels existing task."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Start first task
        await manager._start_ping_task()
        first_task = manager._ping_task

        # Start second task
        await manager._start_ping_task()
        second_task = manager._ping_task

        # Should be different tasks
        assert first_task is not second_task
        assert first_task.cancelled()

        # Cleanup
        second_task.cancel()
        try:
            await second_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing session and cleanup."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Set up state
        manager.tokens = SessionTokens(
            cst="test_cst", security_token="test_token", created_at=datetime.now(timezone.utc)
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        manager._http_client = mock_client

        await manager._start_ping_task()
        ping_task = manager._ping_task

        # Close session
        await manager.close()

        # Should cleanup everything
        assert manager.tokens is None
        assert manager._http_client is None
        assert ping_task.cancelled()
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_no_resources(self):
        """Test closing session when no resources allocated."""
        manager = SessionManager(
            api_url="https://demo-api.example.com",
            api_key="test_key",
            email="test@example.com",
            password="test_pass",
        )

        # Should not raise any errors
        await manager.close()

        assert manager.tokens is None
        assert manager._http_client is None
