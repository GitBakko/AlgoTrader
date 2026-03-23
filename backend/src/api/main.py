"""
AlgoTrader AI - FastAPI Application
Main entry point for the backend API.
"""

import asyncio
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.routers import (
    analytics,
    auth,
    backtest,
    dashboard,
    drl,
    export,
    markets,
    models,
    monitoring,
    news,
    notifications,
    positions,
    signals,
    sil,
    strategy,
    system,
    trading,
    vision,
)
from src.api.websocket import notifications_endpoint, prices_endpoint, trades_endpoint
from src.database.session import DatabaseManager
from src.monitoring.health import HealthChecker
from src.utils.config import get_settings
from src.utils.constants import ALL_ASSETS
from src.utils.logger import setup_logger

# Initialize settings
settings = get_settings()

# Setup logging
setup_logger()

# Initialize rate limiter with Redis backend (falls back to in-memory if Redis unavailable)
_redis_uri = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url(_redis_uri, socket_connect_timeout=1)
    _r.ping()
    _r.close()
    _storage_uri = _redis_uri
    logger.info("Rate limiter using Redis backend")
except Exception:
    _storage_uri = "memory://"
    logger.info("Redis unavailable, rate limiter using in-memory backend")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute", "10/second"],  # Global default
    storage_uri=_storage_uri,
    strategy="moving-window",  # More accurate than fixed-window
)


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

    # Initialize shutdown flag
    app.state.is_shutting_down = False

    # Initialize database connections
    DatabaseManager.initialize()
    app.state.db_session_factory = DatabaseManager.session
    logger.info("Database session factory registered on app.state")

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
                    broker=broker, mode=mode,
                    db_session_factory=getattr(app.state, "db_session_factory", None),
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
            await broker_ws.subscribe_quotes(ALL_ASSETS)
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

    # ══════════════════════════════════════════════════════════
    # 🔄 STATE RECOVERY PHASE (Phase 14)
    # ══════════════════════════════════════════════════════════
    logger.info("🔄 Starting state recovery...")

    from src.execution.state_recovery import StateRecoveryService
    from src.risk.trailing_stop_manager import TrailingStopConfig, TrailingStopManager

    # Create trailing stop manager with config from settings
    _ts_settings = get_settings()
    temp_trailing_stop_manager = TrailingStopManager(
        TrailingStopConfig(
            tp1_risk_multiple=_ts_settings.scalp_tp1_risk_multiple,
            tp2_risk_multiple=_ts_settings.scalp_tp2_risk_multiple,
        )
    )

    recovery_service = StateRecoveryService(
        execution_engine=app.state.execution_engine,
        risk_manager=app.state.risk_manager,
        trailing_stop_manager=temp_trailing_stop_manager,
        broker=app.state.broker_client,
        db_session_factory=getattr(app.state, 'db_session_factory', None),
    )

    recovery_report = await recovery_service.recover_all_state()
    app.state.last_recovery_report = recovery_report  # Store for /api/system/recovery-report

    if recovery_report.errors:
        logger.error(
            f"❌ State recovery completed with ERRORS: "
            f"{recovery_report.positions_recovered} positions from {recovery_report.positions_source}, "
            f"{recovery_report.trailing_stops_restored} stops, "
            f"{recovery_report.trade_history_count} trades — ERRORS: {recovery_report.errors}"
        )
    elif recovery_report.warnings:
        logger.warning(
            f"⚠️  State recovery completed with warnings: "
            f"{recovery_report.positions_recovered} positions from {recovery_report.positions_source}, "
            f"{recovery_report.trailing_stops_restored} stops, "
            f"{recovery_report.trade_history_count} trades — WARNINGS: {recovery_report.warnings}"
        )
    else:
        logger.success(
            f"✅ State recovery successful: "
            f"{recovery_report.positions_recovered} positions from {recovery_report.positions_source}, "
            f"{recovery_report.trailing_stops_restored} stops, "
            f"{recovery_report.trade_history_count} trades"
        )

    # Store recovered trailing stop manager for PaperTradingLoop
    app.state.recovered_trailing_stop_manager = temp_trailing_stop_manager

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
        db_session_factory=getattr(app.state, "db_session_factory", None),
        trailing_stop_manager=app.state.recovered_trailing_stop_manager,
        signal_repo_factory=getattr(app.state, "db_session_factory", None),
    )

    # Phase 14: Inject recovered trade history for Kelly sizing + circuit breaker
    if recovery_report.trade_history_count > 0:
        trade_history = await recovery_service._restore_trade_history_list()
        app.state.paper_loop._trade_history = trade_history
        from src.risk.circuit_breakers import CircuitBreakerType
        cb = app.state.paper_loop.risk_manager.circuit_breakers
        # Save snapshot value — if manually reset to 0, we honour it
        snapshot_consecutive = cb._consecutive_losses
        cb._consecutive_losses = 0
        cb._tripped.pop(CircuitBreakerType.CONSECUTIVE_LOSSES, None)
        cb._tripped_at.pop(CircuitBreakerType.CONSECUTIVE_LOSSES, None)
        # trade_history is newest-first (from DB), reverse for chronological replay
        for t in reversed(trade_history):
            pnl = t.get("pnl", 0)
            cb.record_trade_result(is_win=(pnl > 0))
        # If snapshot was manually reset to 0, honour the manual reset
        if snapshot_consecutive == 0 and cb._consecutive_losses > 0:
            logger.info(f"CB snapshot was manually reset to 0, overriding replay value ({cb._consecutive_losses})")
            cb._consecutive_losses = 0
            cb._tripped.pop(CircuitBreakerType.CONSECUTIVE_LOSSES, None)
            cb._tripped_at.pop(CircuitBreakerType.CONSECUTIVE_LOSSES, None)
        logger.info(f"Injected {len(trade_history)} trades into Kelly history + circuit breaker (consecutive_losses={cb._consecutive_losses})")

    # ══════════════════════════════════════════════════════════
    # 📦 PRE-FETCH MARKET SPECS (minDealSize cache)
    # ══════════════════════════════════════════════════════════
    environment = "DEMO" if settings.use_demo else "LIVE"
    db_sf = getattr(app.state, "db_session_factory", None)

    # 1. Instant load from DB (no API calls)
    from src.trading.market_spec_prefetch import (
        load_market_specs_from_db,
        prefetch_market_specs,
    )

    try:
        db_specs = await load_market_specs_from_db(db_sf, environment)
        if db_specs:
            app.state.paper_loop.seed_min_deal_sizes(db_specs)
            logger.info(f"Seeded {len(db_specs)} min deal sizes from DB")
    except Exception as e:
        logger.warning(f"DB market spec load failed: {e}")

    # 2. Background pre-fetch from broker (updates DB + memory)
    if app.state.broker_client:
        async def _prefetch_and_seed():
            try:
                fresh = await prefetch_market_specs(
                    app.state.broker_client, db_sf, environment
                )
                if fresh:
                    app.state.paper_loop.seed_min_deal_sizes(fresh)
            except Exception as e:
                logger.warning(f"Background market spec pre-fetch failed: {e}")

        prefetch_task = asyncio.create_task(
            _prefetch_and_seed(), name="market_spec_prefetch"
        )
        prefetch_task.add_done_callback(_bg_task_done)

    logger.info(
        f"Trading loop initialized in {mode_label} mode "
        f"(use POST /api/trading/start to begin, state persistence: {'enabled' if app.state.db_session_factory else 'disabled'})"
    )

    # Inject DB factory into InAppChannel for notification persistence
    from src.monitoring.alerting.alert_manager import get_alert_manager
    alert_mgr = get_alert_manager()
    if hasattr(alert_mgr, 'in_app_channel') and app.state.db_session_factory:
        alert_mgr.in_app_channel.set_db_session_factory(app.state.db_session_factory)
        logger.info("InAppChannel DB session factory injected")

    # Register signal handlers for graceful shutdown
    try:
        setup_signal_handlers(app)
    except Exception as e:
        logger.warning(f"Signal handlers registration failed (Windows compatibility): {e}")

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


async def shutdown_handler(signum, frame, app_instance):
    """Handle graceful shutdown on SIGTERM/SIGINT."""
    logger.warning(f"Received signal {signum}, initiating graceful shutdown...")

    # 1. Stop accepting new requests
    app_instance.state.is_shutting_down = True
    logger.info("Stopped accepting new requests")

    # 2. Close WebSocket connections
    if hasattr(app_instance.state, "broker_ws_client") and app_instance.state.broker_ws_client:
        try:
            await app_instance.state.broker_ws_client.disconnect()
            logger.info("WebSocket connections closed")
        except Exception as e:
            logger.error(f"WebSocket disconnect failed: {e}")

    # 3. Stop paper trading loop
    if hasattr(app_instance.state, "paper_loop") and app_instance.state.paper_loop.is_running:
        try:
            app_instance.state.paper_loop.stop()
            logger.info("Paper trading loop stopped")
        except Exception as e:
            logger.error(f"Paper loop stop failed: {e}")

    # 4. Close open positions (paper mode only)
    if settings.execution_mode == "PAPER":
        try:
            open_positions = []
            if hasattr(app_instance.state, "paper_loop"):
                open_positions = app_instance.state.paper_loop.get_paper_positions()

            logger.info(f"Closing {len(open_positions)} open positions before shutdown")

            for pos in open_positions:
                try:
                    await app_instance.state.paper_loop.close_paper_position(
                        deal_id=pos.get("deal_id", ""),
                        reason="Graceful shutdown",
                    )
                except Exception as e:
                    logger.error(f"Failed to close position {pos.get('deal_id')}: {e}")

            if open_positions:
                logger.success(f"Closed {len(open_positions)} positions")
        except Exception as e:
            logger.error(f"Position closure failed: {e}")

    # 5. Disconnect broker
    if hasattr(app_instance.state, "broker_client") and app_instance.state.broker_client:
        try:
            await app_instance.state.broker_client.close()
            logger.info("Broker disconnected")
        except Exception as e:
            logger.error(f"Broker disconnect failed: {e}")

    # 6. Close database connections
    try:
        await DatabaseManager.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Database close failed: {e}")

    logger.success("Graceful shutdown complete")
    sys.exit(0)


def setup_signal_handlers(app_instance):
    """Register signal handlers for graceful shutdown."""
    loop = asyncio.get_event_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown_handler(s, None, app_instance)),
        )

    logger.info("Signal handlers registered (SIGTERM, SIGINT)")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered algorithmic trading system for multi-asset CFD trading",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Configure GZip compression (responses > 1KB)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Configure security headers
from src.api.security_headers import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition"],
)

# Configure audit logging middleware
from src.audit.middleware import AuditMiddleware

app.add_middleware(AuditMiddleware)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure Prometheus metrics
from prometheus_fastapi_instrumentator import Instrumentator

from src.monitoring.metrics import MetricsCollector

instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=False,
    should_respect_env_var=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics", "/health", "/ws/.*"],
    env_var_name="ENABLE_METRICS",
    inprogress_name="mantis_http_requests_inprogress",
    inprogress_labels=True,
)

instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Initialize system info metrics
MetricsCollector.update_system_info(
    app_name=settings.app_name,
    version=settings.app_version,
    environment=settings.environment,
)


# Paths excluded from request logging (high-frequency / internal)
_LOG_SKIP_PREFIXES = ("/health", "/ws/")


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with correlation ID (skips health checks and WS)."""
    path = request.url.path
    skip_log = any(path.startswith(p) for p in _LOG_SKIP_PREFIXES)

    # Generate request correlation ID (use incoming header or create new)
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])

    if skip_log:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    start_time = datetime.now(timezone.utc)

    with logger.contextualize(request_id=request_id):
        try:
            response = await call_next(request)
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                f"{request.method} {path} - "
                f"Status: {response.status_code} - Duration: {duration:.3f}s"
            )
            response.headers["X-Request-ID"] = request_id
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
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
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
app.include_router(export.router, prefix="/api/export", tags=["Export"])
app.include_router(monitoring.router, prefix="/api", tags=["Monitoring"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(sil.router, prefix="/api/sil", tags=["SIL"])
app.include_router(vision.router, prefix="/api/vision", tags=["Vision AI"])
app.include_router(drl.router, prefix="/api/drl", tags=["DRL Ensemble"])

# ===== WebSocket Endpoints =====
app.websocket("/ws/prices")(prices_endpoint)
app.websocket("/ws/trades")(trades_endpoint)
app.websocket("/ws/notifications")(notifications_endpoint)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
