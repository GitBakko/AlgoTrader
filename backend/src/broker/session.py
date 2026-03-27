"""
Session manager for Capital.com API.
Handles authentication, token refresh, and keep-alive pings.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from loguru import logger

from src.broker.exceptions import AuthenticationError
from src.broker.models import SessionRequest, SessionTokens
from src.utils.config import get_settings


class SessionManager:
    """
    Manages Capital.com API session lifecycle.
    Handles authentication, token refresh, and automatic keep-alive.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        email: str,
        password: str,
        session_timeout_minutes: int = 10,
    ):
        """
        Initialize session manager.

        Args:
            api_url: Capital.com API base URL
            api_key: API key from Capital.com
            email: Account email
            password: API password (not account password)
            session_timeout_minutes: Session timeout in minutes (default: 10)
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.email = email
        self.password = password
        self.session_timeout_minutes = session_timeout_minutes

        self.tokens: SessionTokens | None = None
        self._lock = asyncio.Lock()
        self._ping_task: asyncio.Task | None = None
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with configured timeouts."""
        if self._http_client is None:
            settings = get_settings()
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    timeout=float(settings.http_timeout_seconds),
                    connect=float(settings.http_connect_timeout_seconds),
                ),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http_client

    async def authenticate(self) -> SessionTokens:
        """
        Create a new session and obtain authentication tokens.

        Returns:
            Session tokens (CST + X-SECURITY-TOKEN)

        Raises:
            AuthenticationError: If authentication fails
        """
        async with self._lock:
            return await self._authenticate_inner()

    async def _authenticate_inner(self) -> SessionTokens:
        """Inner auth implementation — caller must hold self._lock."""
        logger.info("Authenticating with Capital.com...")

        client = await self._get_http_client()

        # Create session request
        session_request = SessionRequest(
            identifier=self.email, password=self.password, encrypted_password=False
        )

        try:
            response = await client.post(
                f"{self.api_url}/api/v1/session",
                headers={"X-CAP-API-KEY": self.api_key},
                json=session_request.model_dump(by_alias=True),
            )

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_code = error_data.get("errorCode", "unknown")
                raise AuthenticationError(
                    f"Authentication failed: {response.status_code}", error_code
                )

            # Extract tokens from response headers
            cst = response.headers.get("CST")
            security_token = response.headers.get("X-SECURITY-TOKEN")

            if not cst or not security_token:
                raise AuthenticationError("Missing session tokens in response headers")

            self.tokens = SessionTokens(
                cst=cst, security_token=security_token, created_at=datetime.now(UTC)
            )

            logger.success("Authentication successful")

            # Start keep-alive ping task
            await self._start_ping_task()

            return self.tokens

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during authentication: {e}")
            raise AuthenticationError(f"HTTP error: {e}")

    async def get_tokens(self) -> SessionTokens:
        """
        Get current session tokens.
        Automatically re-authenticates if session expired.

        Returns:
            Valid session tokens

        Raises:
            AuthenticationError: If re-authentication fails
        """
        async with self._lock:
            # Check if tokens exist and are still valid
            if self.tokens is None:
                logger.warning("No active session - authenticating...")
                return await self._authenticate_inner()

            # Check if tokens are about to expire (re-auth 1 min before expiry)
            expiry_time = self.tokens.created_at + timedelta(
                minutes=self.session_timeout_minutes - 1
            )
            if datetime.now(UTC) >= expiry_time:
                logger.warning("Session tokens expired - re-authenticating...")
                return await self._authenticate_inner()

            return self.tokens

    async def ping(self) -> bool:
        """
        Send keep-alive ping to prevent session timeout.

        Returns:
            True if ping successful, False otherwise
        """
        try:
            tokens = await self.get_tokens()
            client = await self._get_http_client()

            response = await client.get(
                f"{self.api_url}/api/v1/ping",
                headers={"CST": tokens.cst, "X-SECURITY-TOKEN": tokens.security_token},
            )

            if response.status_code == 200:
                logger.debug("📡 Keep-alive ping successful")
                return True
            else:
                logger.warning(f"Keep-alive ping failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error sending keep-alive ping: {e}")
            return False

    async def _ping_loop(self) -> None:
        """Background task to send periodic keep-alive pings."""
        ping_interval = 5 * 60  # 5 minutes (before 10min timeout)

        while True:
            try:
                await asyncio.sleep(ping_interval)
                await self.ping()
            except asyncio.CancelledError:
                logger.info("Keep-alive ping task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in keep-alive ping loop: {e}")

    async def _start_ping_task(self) -> None:
        """Start background keep-alive ping task."""
        # Cancel existing task if any
        if self._ping_task is not None and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        # Start new ping task
        self._ping_task = asyncio.create_task(self._ping_loop())
        logger.info("📡 Started keep-alive ping task (every 5 minutes)")

    async def close(self) -> None:
        """Close session and cleanup resources."""
        logger.info("Closing Capital.com session...")

        # Cancel ping task
        if self._ping_task is not None and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        # Close HTTP client
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        self.tokens = None
        logger.success("✅ Session closed")
