"""
Database session management for AlgoTrader AI.
Provides async SQLAlchemy engine and session factory.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.utils.config import get_settings


class DatabaseManager:
    """
    Manages database engine and session lifecycle.
    Singleton pattern for shared engine across application.
    """

    _engine: AsyncEngine | None = None
    _session_factory: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def initialize(cls) -> None:
        """
        Initialize database engine and session factory.
        Call this during application startup.
        """
        if cls._engine is not None:
            logger.warning("Database already initialized, skipping...")
            return

        settings = get_settings()

        # Convert psycopg2 URL to asyncpg URL for async support
        async_database_url = settings.database_url.replace(
            "postgresql://", "postgresql+asyncpg://"
        ).replace("postgresql+psycopg2://", "postgresql+asyncpg://")

        logger.info(f"🗄️  Connecting to database: {settings.safe_database_url}")

        # Create async engine with appropriate pool settings
        engine_kwargs = {
            "echo": settings.debug,  # Log SQL queries in debug mode
        }

        if settings.debug:
            # Use NullPool in debug mode (no pooling)
            engine_kwargs["poolclass"] = NullPool
        else:
            # Use connection pooling in production
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_size"] = 20
            engine_kwargs["max_overflow"] = 10

        cls._engine = create_async_engine(async_database_url, **engine_kwargs)

        # Create session factory
        cls._session_factory = async_sessionmaker(
            cls._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Don't expire objects after commit
            autocommit=False,
            autoflush=False,
        )

        logger.success("✅ Database initialized")

    @classmethod
    async def close(cls) -> None:
        """
        Close database engine and cleanup resources.
        Call this during application shutdown.
        """
        if cls._engine is None:
            return

        logger.info("Closing database connection...")
        await cls._engine.dispose()
        cls._engine = None
        cls._session_factory = None
        logger.success("✅ Database connection closed")

    @classmethod
    def get_session_factory(cls) -> async_sessionmaker[AsyncSession]:
        """
        Get session factory for creating database sessions.

        Returns:
            Session factory

        Raises:
            RuntimeError: If database not initialized
        """
        if cls._session_factory is None:
            raise RuntimeError("Database not initialized. Call DatabaseManager.initialize() first.")
        return cls._session_factory

    @classmethod
    @asynccontextmanager
    async def session(cls) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database sessions.
        Automatically commits on success, rolls back on error.

        Usage:
            async with DatabaseManager.session() as session:
                result = await session.execute(query)

        Yields:
            Database session
        """
        session_factory = cls.get_session_factory()
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


# Dependency for FastAPI endpoints
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    Usage:
        @app.get("/endpoint")
        async def endpoint(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with DatabaseManager.session() as session:
        yield session
