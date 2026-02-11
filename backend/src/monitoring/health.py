"""
Health check system for AlgoTrader AI dependencies.
Monitors PostgreSQL, Redis, and Capital.com API connectivity.
"""

from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import DatabaseManager
from src.utils.config import get_settings


class HealthStatus(str, Enum):
    """Health status enum."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    name: str
    status: HealthStatus
    message: str | None = None
    response_time_ms: float | None = None
    details: dict[str, Any] | None = None


class SystemHealth(BaseModel):
    """Overall system health status."""

    status: HealthStatus
    timestamp: datetime
    components: dict[str, ComponentHealth]

    @property
    def is_healthy(self) -> bool:
        """Check if all components are healthy."""
        return self.status == HealthStatus.HEALTHY


class HealthChecker:
    """
    Health checker for all system dependencies.
    Checks PostgreSQL, Redis, and Capital.com API.
    """

    def __init__(self):
        self.settings = get_settings()

    async def check_all(self) -> SystemHealth:
        """
        Check health of all components.

        Returns:
            System health status
        """
        components: dict[str, ComponentHealth] = {}

        # Check PostgreSQL
        components["database"] = await self.check_database()

        # Check Redis
        components["redis"] = await self.check_redis()

        # Check Capital.com API
        components["capital_com_api"] = await self.check_capital_com()

        # Determine overall status
        unhealthy = [c for c in components.values() if c.status == HealthStatus.UNHEALTHY]
        degraded = [c for c in components.values() if c.status == HealthStatus.DEGRADED]

        if unhealthy:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return SystemHealth(
            status=overall_status, timestamp=datetime.utcnow(), components=components
        )

    async def check_database(self) -> ComponentHealth:
        """
        Check PostgreSQL database connectivity and health.

        Returns:
            Database health status
        """
        start_time = datetime.now()

        try:
            # Get database session
            async with DatabaseManager.session() as session:
                # Execute simple query
                result = await session.execute(text("SELECT 1"))
                result.scalar_one()

                # Get database stats
                stats_result = await session.execute(
                    text("SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active'")
                )
                active_connections = stats_result.scalar_one()

            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            return ComponentHealth(
                name="PostgreSQL",
                status=HealthStatus.HEALTHY,
                message="Database connection successful",
                response_time_ms=response_time_ms,
                details={
                    "active_connections": active_connections,
                    "database": self.settings.postgres_db,
                },
            )

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            return ComponentHealth(
                name="PostgreSQL",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}",
                response_time_ms=response_time_ms,
            )

    async def check_redis(self) -> ComponentHealth:
        """
        Check Redis connectivity and health.

        Returns:
            Redis health status
        """
        start_time = datetime.now()

        try:
            # Import redis here to avoid dependency issues if not installed
            import redis.asyncio as redis

            # Create Redis client
            client = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                password=self.settings.redis_password if self.settings.redis_password else None,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )

            # Ping Redis
            await client.ping()

            # Get Redis info
            info = await client.info("server")
            redis_version = info.get("redis_version", "unknown")

            await client.aclose()

            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            return ComponentHealth(
                name="Redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection successful",
                response_time_ms=response_time_ms,
                details={
                    "version": redis_version,
                    "host": self.settings.redis_host,
                    "port": self.settings.redis_port,
                },
            )

        except ImportError:
            logger.warning("Redis library not installed - skipping health check")
            return ComponentHealth(
                name="Redis",
                status=HealthStatus.DEGRADED,
                message="Redis library not installed",
            )

        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            return ComponentHealth(
                name="Redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(e)}",
                response_time_ms=response_time_ms,
            )

    async def check_capital_com(self) -> ComponentHealth:
        """
        Check Capital.com API connectivity.

        Returns:
            Capital.com API health status
        """
        start_time = datetime.now()

        try:
            # Get API URL based on settings
            api_url = (
                self.settings.capital_demo_api_url
                if self.settings.use_demo
                else self.settings.capital_live_api_url
            )

            # Try to ping Capital.com API
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Use a simple endpoint that doesn't require authentication
                response = await client.get(f"{api_url}/api/v1/ping")

                response_time_ms = (datetime.now() - start_time).total_seconds() * 1000

                if response.status_code == 200:
                    return ComponentHealth(
                        name="Capital.com API",
                        status=HealthStatus.HEALTHY,
                        message="API reachable",
                        response_time_ms=response_time_ms,
                        details={
                            "api_url": api_url,
                            "mode": "demo" if self.settings.use_demo else "live",
                        },
                    )
                else:
                    return ComponentHealth(
                        name="Capital.com API",
                        status=HealthStatus.DEGRADED,
                        message=f"API returned status {response.status_code}",
                        response_time_ms=response_time_ms,
                    )

        except httpx.TimeoutException:
            logger.error("Capital.com API health check timed out")
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            return ComponentHealth(
                name="Capital.com API",
                status=HealthStatus.UNHEALTHY,
                message="API request timed out",
                response_time_ms=response_time_ms,
            )

        except Exception as e:
            logger.error(f"Capital.com API health check failed: {e}")
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            return ComponentHealth(
                name="Capital.com API",
                status=HealthStatus.UNHEALTHY,
                message=f"API check failed: {str(e)}",
                response_time_ms=response_time_ms,
            )
