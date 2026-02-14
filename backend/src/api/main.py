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

from src.api.routers import (
    backtest,
    dashboard,
    markets,
    models,
    monitoring,
    news,
    positions,
    signals,
    strategy,
    system,
    trading,
)
from src.api.websocket import prices_endpoint, trades_endpoint
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

    # Initialize trading services (paper mode by default)
    from src.api.dependencies import init_services

    init_services(app)
    logger.info("Trading services initialized (paper mode)")

    # Initialize Capital.com broker client (graceful degradation)
    try:
        from src.broker.client import CapitalComClient

        broker = CapitalComClient()
        await broker.connect()
        app.state.broker_client = broker
        logger.info("Broker connected to Capital.com demo")

        # Upgrade execution engine if DEMO/LIVE mode requested
        desired = getattr(app.state, "_desired_execution_mode", "PAPER")
        if desired in ("DEMO", "LIVE"):
            from src.execution.execution_engine import ExecutionEngine
            from src.execution.schemas import ExecutionMode

            use_demo = desired == "DEMO" and settings.use_demo
            use_live = desired == "LIVE" and not settings.use_demo
            if use_demo or use_live:
                mode = ExecutionMode.DEMO if use_demo else ExecutionMode.LIVE
                app.state.execution_engine = ExecutionEngine(
                    broker=broker, mode=mode
                )
                logger.info(f"Execution engine upgraded to {mode.value} mode (broker-connected)")

                # Sync risk manager with real broker equity
                try:
                    from src.risk.drawdown_monitor import DrawdownMonitor

                    accounts = await broker.get_accounts()
                    if accounts:
                        acc = accounts[0]
                        base = acc.deposit or acc.available or acc.balance
                        broker_equity = base + acc.profit_loss
                        logger.info(
                            f"Broker account: deposit={acc.deposit}, pnl={acc.profit_loss}, "
                            f"equity={broker_equity:.2f}"
                        )

                        # Auto top-up demo if equity is depleted
                        if broker_equity <= 0 and settings.use_demo:
                            try:
                                top_up_amount = 10000.0
                                await broker.top_up_demo_account(top_up_amount)
                                broker_equity = top_up_amount
                                logger.info(f"Demo account topped up with {top_up_amount:.2f}")
                            except Exception as te:
                                logger.warning(f"Demo top-up failed: {te}")

                        if broker_equity > 0:
                            app.state.risk_manager.initial_equity = broker_equity
                            app.state.risk_manager.drawdown_monitor = DrawdownMonitor(broker_equity)
                            logger.info(f"Risk manager synced with broker equity: {broker_equity:.2f}")
                        else:
                            logger.warning(f"Broker equity is {broker_equity:.2f}, keeping default")
                except Exception as e:
                    logger.warning(f"Broker equity sync failed (using default): {e}")

        # Initialize broker WebSocket for real-time price streaming
        try:
            from src.broker.websocket_client import CapitalComWebSocketClient

            ws_url = settings.capital_ws_url
            broker_ws = CapitalComWebSocketClient(
                ws_url=ws_url,
                session_manager=broker.session_manager,
            )
            await broker_ws.connect()
            await broker_ws.subscribe_quotes([
                # Existing 9 assets
                "XAUUSD", "BTCUSD", "US500", "WTIUSD", "EURUSD",
                "NVDA", "TSLA", "XAGUSD", "DE40",
                # New 12 assets - Phase 12: Portfolio Expansion (21/40 slots)
                "SOLUSD", "ETHUSD", "BNBUSD", "DOGUSD", "DASHUSD", "ICPUSD",
                "NATGAS", "COPPER", "PLATINUM",
                "GBPUSD", "USDJPY",
                "NAS100",
            ])
            app.state.broker_ws_client = broker_ws
            logger.info("Broker WebSocket connected, subscribed to quotes")
        except Exception as e:
            logger.warning(f"Broker WebSocket failed (using mock prices): {e}")
            app.state.broker_ws_client = None
    except Exception as e:
        desired = getattr(app.state, "_desired_execution_mode", "PAPER")
        if desired != "PAPER":
            logger.warning(
                f"Broker failed but {desired} mode requested — falling back to PAPER: {e}"
            )
        else:
            logger.warning(f"Broker connection failed (continuing in PAPER mode): {e}")
        app.state.broker_client = None
        app.state.broker_ws_client = None

    # Initialize Redis event bus (graceful degradation)
    try:
        from src.utils.event_bus import event_bus

        connected = await event_bus.connect(settings.redis_url)
        if connected:
            app.state.event_bus = event_bus
        else:
            app.state.event_bus = None
    except Exception as e:
        logger.warning(f"Redis not available (continuing without): {e}")
        app.state.event_bus = None

    # Start background tasks (data download, scheduler) - non-blocking
    import asyncio
    from src.api.startup_tasks import initial_data_download, start_data_scheduler

    def _bg_task_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"Background task {task.get_name()} failed: {exc}")

    for coro, name in [
        (initial_data_download(app.state), "initial_data_download"),
        (start_data_scheduler(app.state), "data_scheduler"),
    ]:
        task = asyncio.create_task(coro, name=name)
        task.add_done_callback(_bg_task_done)

    # Initialize paper trading loop (does not start automatically)
    from src.trading.paper_loop import PaperTradingLoop

    mode_label = app.state.execution_engine.mode.value
    app.state.paper_loop = PaperTradingLoop(
        prediction_service=app.state.prediction_service,
        strategy_manager=app.state.strategy_manager,
        risk_manager=app.state.risk_manager,
        execution_engine=app.state.execution_engine,
        data_access=app.state.data_access,
        broker=app.state.broker_client,
    )
    logger.info(
        f"Trading loop initialized in {mode_label} mode "
        f"(use POST /api/trading/start to begin)"
    )

    logger.success("✅ Application startup complete")

    yield

    # Shutdown
    logger.info("🛑 Shutting down AlgoTrader AI Backend...")

    # Stop paper trading loop
    if getattr(app.state, "paper_loop", None) and app.state.paper_loop.is_running:
        app.state.paper_loop.stop()

    # Stop data scheduler
    if getattr(app.state, "data_scheduler", None):
        try:
            app.state.data_scheduler.stop()
        except Exception as e:
            logger.warning(f"Scheduler stop error: {e}")

    # Close broker WebSocket
    if getattr(app.state, "broker_ws_client", None):
        try:
            await app.state.broker_ws_client.disconnect()
        except Exception as e:
            logger.warning(f"Broker WS close error: {e}")

    # Close broker connection
    if getattr(app.state, "broker_client", None):
        try:
            await app.state.broker_client.close()
        except Exception as e:
            logger.warning(f"Broker close error: {e}")

    # Close Redis event bus
    if getattr(app.state, "event_bus", None):
        try:
            from src.utils.event_bus import event_bus
            await event_bus.close()
        except Exception as e:
            logger.warning(f"Redis close error: {e}")

    # Close database connections
    await DatabaseManager.close()

    logger.success("✅ Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered algorithmic trading system for multi-asset CFD trading",
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


# Paths excluded from request logging (high-frequency / internal)
_LOG_SKIP_PREFIXES = ("/health", "/ws/")


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests (skips health checks and WebSocket upgrades)."""
    path = request.url.path
    skip_log = any(path.startswith(p) for p in _LOG_SKIP_PREFIXES)

    if skip_log:
        return await call_next(request)

    start_time = datetime.now(timezone.utc)

    try:
        response = await call_next(request)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"{request.method} {path} - "
            f"Status: {response.status_code} - Duration: {duration:.3f}s"
        )
        return response
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error(f"{request.method} {path} - Error: {e} - Duration: {duration:.3f}s")
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


# ===== API Routers =====
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(positions.router, prefix="/api/positions", tags=["Positions"])
app.include_router(signals.router, prefix="/api/signals", tags=["Signals"])
app.include_router(markets.router, prefix="/api/markets", tags=["Markets"])
app.include_router(news.router, prefix="/api/news", tags=["News"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["Backtest"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["Strategy"])
app.include_router(models.router, prefix="/api/models", tags=["Models"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(trading.router, prefix="/api/trading", tags=["Trading"])
app.include_router(monitoring.router, prefix="/api", tags=["Monitoring"])

# ===== WebSocket Endpoints =====
app.websocket("/ws/prices")(prices_endpoint)
app.websocket("/ws/trades")(trades_endpoint)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
