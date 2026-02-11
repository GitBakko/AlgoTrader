"""
AlgoTrader AI - FastAPI Application
Main entry point for the backend API.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from src.database.session import DatabaseManager
from src.monitoring.health import HealthChecker
from src.utils.config import get_settings
from src.utils.logger import setup_logger

# Initialize settings
settings = get_settings()

# Setup logging
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting AlgoTrader AI Backend...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug Mode: {settings.debug}")
    logger.info(f"Using {'DEMO' if settings.use_demo else 'LIVE'} Capital.com account")
    logger.info(f"Trading Enabled: {settings.trading_enabled}")
    logger.info(f"Paper Trading: {settings.paper_trading}")

    # Initialize database connections
    DatabaseManager.initialize()

    # TODO: Initialize Redis connections
    # TODO: Initialize Capital.com broker client
    # TODO: Start background tasks (data collection, model inference)

    logger.success("✅ Application startup complete")

    yield

    # Shutdown
    logger.info("🛑 Shutting down AlgoTrader AI Backend...")

    # Close database connections
    await DatabaseManager.close()

    # TODO: Close Redis connections
    # TODO: Close Capital.com WebSocket connections
    # TODO: Stop background tasks

    logger.success("✅ Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered algorithmic trading system for Gold, Bitcoin, and S&P 500",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = datetime.now(timezone.utc)
    logger.info(f"📥 {request.method} {request.url.path}")

    try:
        response = await call_next(request)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"📤 {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Duration: {duration:.3f}s"
        )
        return response
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error(f"❌ {request.method} {request.url.path} - Error: {e} - Duration: {duration:.3f}s")
        raise


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred",
        },
    )


# ===== Health Check Endpoint =====
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Returns application status and all component health checks.
    """
    checker = HealthChecker()
    system_health = await checker.check_all()

    return {
        "success": system_health.is_healthy,
        "data": {
            "status": system_health.status.value,
            "app_name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "timestamp": system_health.timestamp.isoformat(),
            "components": {
                name: {
                    "status": component.status.value,
                    "message": component.message,
                    "response_time_ms": component.response_time_ms,
                    "details": component.details,
                }
                for name, component in system_health.components.items()
            },
            "trading": {
                "enabled": settings.trading_enabled,
                "mode": "paper" if settings.paper_trading else "live",
                "broker": "demo" if settings.use_demo else "live",
            },
        },
    }


# ===== Root Endpoint =====
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint.
    Returns basic API information.
    """
    return {
        "success": True,
        "data": {
            "name": settings.app_name,
            "version": settings.app_version,
            "description": "AI-powered algorithmic trading system",
            "docs": f"{settings.api_host}:{settings.api_port}/docs" if settings.debug else None,
        },
    }


# TODO: Import and register API routers
# from src.api.routes import broker, data, strategy, backtest, monitoring
# app.include_router(broker.router, prefix="/api/broker", tags=["Broker"])
# app.include_router(data.router, prefix="/api/data", tags=["Data"])
# app.include_router(strategy.router, prefix="/api/strategy", tags=["Strategy"])
# app.include_router(backtest.router, prefix="/api/backtest", tags=["Backtest"])
# app.include_router(monitoring.router, prefix="/api/monitoring", tags=["Monitoring"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
