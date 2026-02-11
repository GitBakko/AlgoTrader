"""
FastAPI dependency injection for shared services.
Services are initialized once in lifespan and stored in app.state.
Per-request dependencies (DB repositories) are created fresh each request.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.strategy_manager import StrategyManager
from src.utils.config import get_settings

if TYPE_CHECKING:
    from src.broker.client import CapitalComClient
    from src.data.data_access import DataAccessLayer
    from src.database.repositories import (
        PositionRepository,
        SignalRepository,
        StrategyRepository,
        TradeRepository,
    )
    from src.features.builder import FeatureBuilder
    from src.models.prediction_service import PredictionService
    from src.models.versioning import ModelVersioning


# ── Singleton services (from app.state) ──


def get_execution_engine(request: Request) -> ExecutionEngine:
    """Get the singleton ExecutionEngine from app state."""
    return request.app.state.execution_engine


def get_risk_manager(request: Request) -> RiskManager:
    """Get the singleton RiskManager from app state."""
    return request.app.state.risk_manager


def get_strategy_manager(request: Request) -> StrategyManager:
    """Get the singleton StrategyManager from app state."""
    return request.app.state.strategy_manager


def get_broker_client(request: Request) -> CapitalComClient | None:
    """Get the CapitalComClient from app state (may be None)."""
    return getattr(request.app.state, "broker_client", None)


def get_data_access(request: Request) -> DataAccessLayer | None:
    """Get the DataAccessLayer from app state."""
    return getattr(request.app.state, "data_access", None)


def get_feature_builder(request: Request) -> FeatureBuilder | None:
    """Get the FeatureBuilder from app state."""
    return getattr(request.app.state, "feature_builder", None)


def get_prediction_service(request: Request) -> PredictionService | None:
    """Get the PredictionService from app state."""
    return getattr(request.app.state, "prediction_service", None)


def get_model_versioning(request: Request) -> ModelVersioning | None:
    """Get the ModelVersioning from app state."""
    return getattr(request.app.state, "model_versioning", None)


# ── Per-request DB dependencies ──


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession | None, None]:
    """
    Get a DB session if database is available, otherwise yield None.
    Graceful degradation: routers can check for None and fall back to in-memory.
    """
    db_factory = getattr(request.app.state, "db_session_factory", None)
    if db_factory is None:
        yield None
        return

    async with db_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_position_repo(
    session: AsyncSession | None = Depends(get_db_session),
) -> PositionRepository | None:
    """Get PositionRepository for this request (None if no DB)."""
    if session is None:
        return None
    from src.database.repositories import PositionRepository
    return PositionRepository(session)


async def get_signal_repo(
    session: AsyncSession | None = Depends(get_db_session),
) -> SignalRepository | None:
    """Get SignalRepository for this request (None if no DB)."""
    if session is None:
        return None
    from src.database.repositories import SignalRepository
    return SignalRepository(session)


async def get_trade_repo(
    session: AsyncSession | None = Depends(get_db_session),
) -> TradeRepository | None:
    """Get TradeRepository for this request (None if no DB)."""
    if session is None:
        return None
    from src.database.repositories import TradeRepository
    return TradeRepository(session)


async def get_strategy_repo(
    session: AsyncSession | None = Depends(get_db_session),
) -> StrategyRepository | None:
    """Get StrategyRepository for this request (None if no DB)."""
    if session is None:
        return None
    from src.database.repositories import StrategyRepository
    return StrategyRepository(session)


# ── Initialization ──


def init_services(app) -> None:
    """Initialize all services and store in app.state. Called during lifespan startup."""
    settings = get_settings()

    limits = RiskLimits(
        max_risk_per_trade=settings.max_risk_per_trade,
        max_daily_drawdown=settings.max_daily_drawdown,
        max_total_drawdown=settings.max_total_drawdown,
    )

    # Core trading services
    app.state.execution_engine = ExecutionEngine(mode=ExecutionMode.PAPER)
    app.state.risk_manager = RiskManager(
        initial_equity=10000.0,
        limits=limits,
    )
    app.state.strategy_manager = StrategyManager()

    # In-memory stores (fallback when DB not available)
    app.state.signal_history = []
    app.state.backtest_runs = {}

    # Data pipeline services
    from src.data.data_access import DataAccessLayer
    from src.data.storage import ParquetStorageManager
    from src.features.builder import FeatureBuilder
    from src.models.versioning import ModelVersioning

    app.state.storage = ParquetStorageManager()
    app.state.data_access = DataAccessLayer(storage=app.state.storage)
    app.state.feature_builder = FeatureBuilder(data_access=app.state.data_access)
    app.state.model_versioning = ModelVersioning()

    # Prediction service (uses feature builder + model versioning)
    from src.models.prediction_service import PredictionService

    app.state.prediction_service = PredictionService(
        feature_builder=app.state.feature_builder,
        model_versioning=app.state.model_versioning,
        data_access=app.state.data_access,
    )

    # Try to load pre-trained models (non-blocking, may have none)
    try:
        loaded = app.state.prediction_service.load_models()
        if loaded > 0:
            logger.info(f"Loaded {loaded} pre-trained ML models")
        else:
            logger.info("No pre-trained models found (train models first)")
    except Exception as e:
        logger.warning(f"Model loading failed: {e}")

    # Placeholders (initialized in lifespan if available)
    app.state.broker_client = None
    app.state.broker_ws_client = None
    app.state.db_session_factory = None

    # Try to set up DB session factory (graceful if DB not available)
    try:
        from src.database.session import DatabaseManager
        factory = DatabaseManager.get_session_factory()
        app.state.db_session_factory = factory
        logger.info("Database session factory configured")
    except RuntimeError:
        logger.warning("Database not initialized, running without persistence")

    logger.info("All services initialized")
