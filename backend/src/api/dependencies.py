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
from src.risk.kelly_sizer import AdaptiveKellySizer
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
        TradeJournalNoteRepository,
        TradeRepository,
    )
    from src.external.finnhub_client import FinnhubClient
    from src.external.marketaux_client import MarketauxClient
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


def get_finnhub_client(request: Request) -> FinnhubClient | None:
    """Get the FinnhubClient from app state."""
    return getattr(request.app.state, "finnhub_client", None)


def get_marketaux_client(request: Request) -> MarketauxClient | None:
    """Get the MarketauxClient from app state."""
    return getattr(request.app.state, "marketaux_client", None)


def get_sentiment_analyzer(request: Request):
    """Get the SentimentAnalyzer from app state."""
    return getattr(request.app.state, "sentiment_analyzer", None)


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

    try:
        async with db_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    except OSError:
        # PostgreSQL not reachable — fall back to in-memory mode
        yield None


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


async def get_journal_note_repo(
    session: AsyncSession | None = Depends(get_db_session),
) -> TradeJournalNoteRepository | None:
    """Get TradeJournalNoteRepository for this request (None if no DB)."""
    if session is None:
        return None
    from src.database.repositories import TradeJournalNoteRepository
    return TradeJournalNoteRepository(session)


# ── Initialization ──


def init_services(app) -> None:
    """Initialize all services and store in app.state. Called during lifespan startup."""
    settings = get_settings()

    # Store desired execution mode for upgrade after broker connects
    app.state._desired_execution_mode = settings.execution_mode.upper()

    limits = RiskLimits(
        max_risk_per_trade=settings.max_risk_per_trade,
        max_daily_drawdown=settings.max_daily_drawdown,
        max_total_drawdown=settings.max_total_drawdown,
        max_total_exposure=settings.max_total_exposure,
    )

    # Core trading services
    from src.risk.circuit_breakers import CircuitBreakerConfig
    cb_config = CircuitBreakerConfig(daily_loss_limit=settings.cb_daily_loss_limit)

    app.state.execution_engine = ExecutionEngine(mode=ExecutionMode.PAPER)
    app.state.risk_manager = RiskManager(
        initial_equity=10000.0,
        limits=limits,
        circuit_breaker_config=cb_config,
        kelly_sizer=AdaptiveKellySizer(),
    )
    app.state.strategy_manager = StrategyManager.from_optimal_thresholds()

    # Enable scalp mode if configured
    if settings.scalp_mode_enabled:
        from src.strategy.scalp_score_strategy import ScalpScoreStrategy
        app.state.strategy_manager.scalp_mode = True
        app.state.strategy_manager._scalp_strategy = ScalpScoreStrategy()
        # Stricter circuit breaker for scalp (4 consecutive losses)
        app.state.risk_manager.circuit_breakers.config.max_consecutive_losses = 4
        logger.info(
            f"Scalp mode ENABLED — {settings.scalp_candle_resolution} candles, "
            f"check every {settings.scalp_check_interval}s, CB=4 losses"
        )

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

    # Initialize sentiment analyzer (lazy model loading)
    try:
        from src.external.sentiment_analyzer import SentimentAnalyzer

        app.state.sentiment_analyzer = SentimentAnalyzer(
            model_name="ProsusAI/finbert",
            device="cpu",  # Auto-detects GPU if available
            enable_cache=True,
        )
        logger.info("SentimentAnalyzer initialized (FinBERT lazy-loads on first predict)")
    except Exception as e:
        logger.warning(f"SentimentAnalyzer init failed: {e}, sentiment will be 0.0")
        app.state.sentiment_analyzer = None

    # Initialize external API clients (graceful if keys not configured)
    try:
        from src.external.finnhub_client import FinnhubClient

        app.state.finnhub_client = FinnhubClient(
            sentiment_analyzer=app.state.sentiment_analyzer  # Inject analyzer
        )
        logger.info("FinnhubClient initialized")
    except Exception as e:
        logger.warning(f"FinnhubClient init failed: {e}")
        app.state.finnhub_client = None

    try:
        from src.external.marketaux_client import MarketauxClient

        app.state.marketaux_client = MarketauxClient(
            sentiment_analyzer=app.state.sentiment_analyzer  # Inject analyzer
        )
        logger.info("MarketauxClient initialized")
    except Exception as e:
        logger.warning(f"MarketauxClient init failed: {e}")
        app.state.marketaux_client = None

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
