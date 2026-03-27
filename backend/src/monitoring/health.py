"""
Health check system for AlgoTrader AI dependencies.
Monitors PostgreSQL, Redis, and Capital.com API connectivity.
"""

import asyncio
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import psutil
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import text

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
        # Run all checks in parallel
        results = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
            self.check_capital_com(),
            self.check_data_freshness(),
            self.check_system_resources(),  # NEW
            self.check_websocket(),  # NEW
            self.check_ml_models(),  # NEW
            return_exceptions=True,
        )

        db_check, redis_check, api_check, data_check, system_check, ws_check, ml_check = results

        components: dict[str, ComponentHealth] = {
            "database": db_check,
            "redis": redis_check,
            "capital_com_api": api_check,
            "data_freshness": data_check,
            "system_resources": system_check,  # NEW
            "websocket": ws_check,  # NEW
            "ml_models": ml_check,  # NEW
        }

        # Determine overall status
        # Critical components: database, redis, capital_com_api, system_resources
        critical_components = ["database", "redis", "capital_com_api", "system_resources"]
        critical_unhealthy = any(
            components[k].status == HealthStatus.UNHEALTHY
            for k in critical_components
            if k in components and isinstance(components[k], ComponentHealth)
        )

        any_degraded = any(
            c.status == HealthStatus.DEGRADED
            for c in components.values()
            if isinstance(c, ComponentHealth)
        )

        if critical_unhealthy:
            overall_status = HealthStatus.UNHEALTHY
        elif any_degraded:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return SystemHealth(
            status=overall_status, timestamp=datetime.now(UTC), components=components
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

    async def check_data_freshness(self) -> ComponentHealth:
        """
        Check data freshness: last candle timestamp for each epic/timeframe.
        Stale if latest candle > 2 hours old for 1h timeframe.
        """
        try:
            from src.data.storage import ParquetStorageManager

            storage = ParquetStorageManager()
            details = {}
            stale_count = 0
            now = datetime.now(UTC)

            for epic in ["XAUUSD", "BTCUSD", "US500"]:
                for tf in ["1h"]:
                    last_ts = storage.get_latest_timestamp(epic=epic, timeframe=tf)
                    if last_ts is None:
                        details[f"{epic}/{tf}"] = "no_data"
                        stale_count += 1
                        continue

                    # Polars datetime -> python datetime
                    if hasattr(last_ts, "to_pydatetime"):
                        last_ts = last_ts.to_pydatetime()
                    # Ensure timezone-aware for comparison with now(utc)
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=UTC)

                    bar_count = storage.get_bar_count(epic=epic, timeframe=tf)
                    age_hours = (now - last_ts).total_seconds() / 3600
                    is_stale = age_hours > 2.0
                    if is_stale:
                        stale_count += 1

                    details[f"{epic}/{tf}"] = {
                        "last_candle": last_ts.isoformat(),
                        "age_hours": round(age_hours, 1),
                        "stale": is_stale,
                        "bars": bar_count,
                    }

            if stale_count == 0:
                status = HealthStatus.HEALTHY
                msg = "All data series are fresh"
            elif stale_count < 3:
                status = HealthStatus.DEGRADED
                msg = f"{stale_count} data series are stale"
            else:
                status = HealthStatus.UNHEALTHY
                msg = "All data series are stale or missing"

            return ComponentHealth(
                name="Data Freshness",
                status=status,
                message=msg,
                details=details,
            )

        except Exception as e:
            logger.error(f"Data freshness check failed: {e}")
            return ComponentHealth(
                name="Data Freshness",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {str(e)}",
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
                response = await client.get(f"{api_url}/api/v1/time")

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

    async def check_system_resources(self) -> ComponentHealth:
        """Check memory and CPU usage."""
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)  # 100ms sample

            status = HealthStatus.HEALTHY
            if memory.percent > 90 or cpu_percent > 90:
                status = HealthStatus.DEGRADED
            if memory.percent > 95 or cpu_percent > 95:
                status = HealthStatus.UNHEALTHY

            return ComponentHealth(
                name="System Resources",
                status=status,
                message=f"Memory: {memory.percent:.1f}%, CPU: {cpu_percent:.1f}%",
                details={
                    "memory_percent": round(memory.percent, 1),
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "memory_total_gb": round(memory.total / (1024**3), 2),
                    "memory_used_gb": round(memory.used / (1024**3), 2),
                    "cpu_percent": round(cpu_percent, 1),
                },
            )
        except Exception as e:
            logger.error(f"System resources check failed: {e}")
            return ComponentHealth(
                name="System Resources",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
            )

    async def check_websocket(self) -> ComponentHealth:
        """Check WebSocket connection health (placeholder for now)."""
        try:
            # Note: Actual WebSocket check would require app state access
            # This is a basic implementation
            return ComponentHealth(
                name="WebSocket",
                status=HealthStatus.HEALTHY,
                message="WebSocket check not fully implemented (app state required)",
                details={
                    "note": "Full check requires app state from main.py",
                },
            )
        except Exception as e:
            logger.error(f"WebSocket check failed: {e}")
            return ComponentHealth(
                name="WebSocket",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
            )

    async def check_ml_models(self) -> ComponentHealth:
        """Check if ML models are loaded and accessible."""
        try:
            # Use absolute path based on this file's location to avoid CWD issues
            backend_root = Path(__file__).resolve().parent.parent.parent
            model_dir = backend_root / self.settings.model_dir
            if not model_dir.exists():
                return ComponentHealth(
                    name="ML Models",
                    status=HealthStatus.DEGRADED,
                    message=f"Model directory not found: {model_dir}",
                )

            # Check for XGBoost models (model.json in subdirs) and PyTorch models (.pt)
            xgb_models = list(model_dir.glob("**/model.json"))
            pt_models = list(model_dir.glob("**/*.pt"))
            total_models = len(xgb_models) + len(pt_models)
            logger.debug(f"ML model check: found {len(xgb_models)} xgb, {len(pt_models)} pt")

            status = HealthStatus.HEALTHY if total_models > 0 else HealthStatus.DEGRADED

            return ComponentHealth(
                name="ML Models",
                status=status,
                message=f"Found {total_models} models ({len(xgb_models)} XGBoost, {len(pt_models)} PyTorch)",
                details={
                    "models_found": total_models,
                    "xgboost_models": len(xgb_models),
                    "pytorch_models": len(pt_models),
                    "model_files": [f.name for f in (xgb_models + pt_models)[:5]],  # First 5
                },
            )
        except Exception as e:
            logger.error(f"ML models check failed: {e}")
            return ComponentHealth(
                name="ML Models",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}",
            )
