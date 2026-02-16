"""
FastAPI middleware for audit logging.
Automatically logs all API requests and responses with user context.
"""

from datetime import datetime, timezone

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.audit.logger import AuditLogger
from src.audit.schemas import AuditEventType
from src.database.session import DatabaseManager


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all API requests and responses.
    Captures user context, IP address, and request/response details.
    """

    # Paths to exclude from audit logging (high-frequency endpoints)
    EXCLUDED_PATHS = [
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/ws/",  # WebSocket endpoints
    ]

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and log audit event.

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response from downstream handler
        """
        path = request.url.path

        # Skip audit logging for excluded paths
        if any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS):
            return await call_next(request)

        # Extract request metadata
        method = request.method
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        start_time = datetime.now(timezone.utc)

        # Extract user ID from request state (set by auth dependencies)
        user_id = None
        if hasattr(request.state, "user"):
            user_id = request.state.user.id

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
            success = status_code < 400
        except Exception as e:
            logger.error(f"Request failed: {method} {path} - {e}")
            status_code = 500
            success = False
            raise
        finally:
            # Log audit event asynchronously (non-blocking)
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Only log non-GET requests or failed requests for audit trail
            if method != "GET" or not success:
                try:
                    await self._log_audit_event(
                        user_id=user_id,
                        method=method,
                        path=path,
                        status_code=status_code,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        duration=duration,
                        success=success,
                    )
                except Exception as e:
                    # Don't let audit logging failure break the request
                    logger.warning(f"Audit logging failed: {e}")

        return response

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.
        Handles X-Forwarded-For header for proxied requests.

        Args:
            request: FastAPI request

        Returns:
            Client IP address
        """
        # Check X-Forwarded-For header (for proxied requests)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback to direct client IP
        if request.client:
            return request.client.host

        return "unknown"

    async def _log_audit_event(
        self,
        user_id: int | None,
        method: str,
        path: str,
        status_code: int,
        ip_address: str,
        user_agent: str,
        duration: float,
        success: bool,
    ) -> None:
        """
        Log audit event to database.

        Args:
            user_id: Authenticated user ID
            method: HTTP method
            path: Request path
            status_code: Response status code
            ip_address: Client IP
            user_agent: User agent string
            duration: Request duration in seconds
            success: Whether request succeeded
        """
        # Determine event type and severity
        if not success:
            event_type = AuditEventType.API_ERROR
            severity = "MEDIUM" if status_code >= 500 else "LOW"
        elif status_code == 401 or status_code == 403:
            event_type = AuditEventType.UNAUTHORIZED_ACCESS
            severity = "MEDIUM"
        else:
            event_type = AuditEventType.API_REQUEST
            severity = "INFO"

        message = f"{method} {path} - Status: {status_code} - Duration: {duration:.3f}s"
        if not success:
            message += " (FAILED)"

        # Create database session and log event
        async with DatabaseManager.session() as session:
            audit_logger = AuditLogger(session)
            await audit_logger.log_event(
                event_type=event_type,
                message=message,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=method,
                request_path=path,
                response_status_code=status_code,
                severity=severity,
                component="api",
                details={"duration_seconds": duration},
            )
