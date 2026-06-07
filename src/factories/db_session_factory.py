"""Database session factory for async PostgreSQL connections.

This module provides a Singleton factory that creates and manages the
SQLAlchemy async engine and session maker. The factory is initialised once
at application startup and reused throughout the application lifecycle.

Usage::

    from src.factories.db_session_factory import get_db_session_factory

    factory = get_db_session_factory()
    async with factory.get_session() as session:
        result = await session.execute(select(...))
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from src.config.settings import get_settings


class DbSessionFactory:
    """Singleton factory for creating async database sessions.

    Manages the lifecycle of a single ``AsyncEngine`` instance and provides
    an ``async_sessionmaker`` for creating independent ``AsyncSession``
    instances on demand.

    The engine is configured with connection pooling and statement logging
    at DEBUG level. All SQLModel table metadata is bound to this engine.

    Attributes:
        _engine: Shared async SQLAlchemy engine.
        _session_maker: Factory for creating new async sessions.

    Example:
        factory = DbSessionFactory(database_url="postgresql+asyncpg://...")
        async with factory.get_session() as session:
            await session.execute(...)
    """

    __slots__ = ("_engine", "_session_maker")

    def __init__(self: "DbSessionFactory", database_url: str) -> None:
        """Initialise the factory with a database connection URL.

        Args:
            database_url: Async PostgreSQL connection string in the format
                ``postgresql+asyncpg://user:pass@host:port/dbname``.
        """
        logger.info("Initialising database session factory", extra={"url_safe": self._mask_password(database_url)})

        self._engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )

        self._session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        logger.debug("Database session factory ready")

    @staticmethod
    def _mask_password(url: str) -> str:
        """Mask the password in a connection URL for safe logging.

        Args:
            url: Full database connection string.

        Returns:
            Connection string with the password replaced by ``***``.
        """
        if "@" not in url:
            return url
        prefix, suffix = url.split("@", 1)
        if ":" in prefix:
            user_part, _ = prefix.rsplit(":", 1)
            return f"{user_part}:***@{suffix}"
        return url

    @asynccontextmanager
    async def get_session(self: "DbSessionFactory") -> AsyncGenerator[AsyncSession, None]:
        """Provide an async context manager for a database session.

        The session is automatically committed on successful exit and rolled
        back on exception. The connection is returned to the pool when the
        context exits.

        Yields:
            An independent ``AsyncSession`` instance.

        Example:
            async with factory.get_session() as session:
                result = await session.execute(select(DimMovieTable))
                await session.commit()
        """
        async with self._session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_tables(self: "DbSessionFactory") -> None:
        """Create all SQLModel tables in the database.

        This method is intended for local development and testing. In
        production, schema management is handled exclusively via Alembic
        migrations.

        All tables registered with ``SQLModel.metadata`` are created if they
        do not already exist. Existing tables are not modified.
        """
        logger.info("Creating database tables")
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database tables created")

    async def close(self: "DbSessionFactory") -> None:
        """Close the async engine and release all connections.

        This method should be called during application shutdown to ensure
        all database connections are cleanly closed.
        """
        logger.info("Closing database session factory")
        await self._engine.dispose()
        logger.info("Database session factory closed")


@lru_cache(maxsize=1)
def get_db_session_factory() -> DbSessionFactory:
    """Return the cached database session factory singleton.

    The factory is initialised once on first call using the database URL
    from application settings. Subsequent calls return the same instance.

    Returns:
        The singleton ``DbSessionFactory`` instance.

    Example:
        factory = get_db_session_factory()
        async with factory.get_session() as session:
            ...
    """
    settings = get_settings()
    return DbSessionFactory(database_url=settings.database_url)
