"""Shared test fixtures for the FM test suite.

This module provides pytest fixtures for async database sessions, DTO
factories, and other test utilities shared across multiple test modules.
"""

import datetime
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy import Integer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from src.models import dwh_tables as _dwh_tables  # noqa: F401 — register ORM metadata
from src.models.dwh import (
    DimDateDto,
    DimDirectorDto,
    DimDistributorDto,
    DimGenreDto,
    DimMovieDto,
    DimRatedDto,
    FactMovieRatingDto,
    FactRevenueDto,
)

_SQLITE_SCHEMA_MAP: dict[str, str | None] = {"dwh": None}

_SQLITE_AUTOINCREMENT_TABLES: tuple[str, ...] = (
    "dwh.dim_movie",
    "dwh.fact_revenue",
    "dwh.fact_movie_rating",
)


def _adapt_metadata_for_sqlite() -> None:
    """Adjust ORM metadata for SQLite in-memory integration tests.

    SQLite only generates ``AUTOINCREMENT`` values for ``INTEGER PRIMARY KEY``
    columns, so BIGINT surrogate keys are rewritten to INTEGER.

    PostgreSQL-specific constraints (``NULLS NOT DISTINCT``, partial unique
    indexes) are removed because SQLite either rejects them or compiles them
    into stricter equivalents that break SCD Type 2 test scenarios.
    """
    for table_key in _SQLITE_AUTOINCREMENT_TABLES:
        table = SQLModel.metadata.tables[table_key]
        for column in table.primary_key.columns:
            if column.autoincrement:
                column.type = Integer()

    fact_revenue = SQLModel.metadata.tables["dwh.fact_revenue"]
    for constraint in list(fact_revenue.constraints):
        if constraint.name == "uq_fact_revenue_movie_date_distributor":
            fact_revenue.constraints.discard(constraint)

    fact_rating = SQLModel.metadata.tables["dwh.fact_movie_rating"]
    for index in list(fact_rating.indexes):
        if index.name == "uq_fact_movie_rating_movie_id_current":
            fact_rating.indexes.discard(index)


@pytest.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an in-memory SQLite async engine for testing.

    Each test function receives a fresh engine with an independent in-memory
    database. Tables are created before the test runs and disposed after.

    PostgreSQL ``dwh`` schema qualifiers are translated away because SQLite
    does not support schemas.

    Yields:
        An ``AsyncEngine`` connected to an in-memory SQLite database.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": _SQLITE_SCHEMA_MAP},
    )

    def _create_all_tables(sync_conn: object) -> None:
        """Create DWH tables adapted for SQLite autoincrement semantics."""
        from sqlalchemy.engine import Connection

        assert isinstance(sync_conn, Connection)
        _adapt_metadata_for_sqlite()
        SQLModel.metadata.create_all(bind=sync_conn)

    async with engine.begin() as conn:
        await conn.run_sync(_create_all_tables)

    yield engine

    await engine.dispose()


@pytest.fixture(scope="function")
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session for testing.

    The session is automatically rolled back after the test completes,
    ensuring isolation between tests.

    Args:
        async_engine: The async engine fixture.

    Yields:
        An ``AsyncSession`` connected to the test database.
    """
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def dim_movie_dto_factory() -> callable:
    """Return a factory function for creating ``DimMovieDto`` instances.

    Returns:
        A callable that accepts keyword arguments to override default
        field values.

    Example:
        dto = dim_movie_dto_factory(imdb_id="tt9999999", title="Test Movie")
    """

    def _make(**overrides: object) -> DimMovieDto:
        defaults = {
            "movie_id": None,
            "imdb_id": "tt1375666",
            "title": "Inception",
            "release_year": 2010,
            "rated_id": None,
            "runtime_min": 148,
            "plot": "A thief who steals corporate secrets.",
            "awards": "Won 4 Oscars.",
            "box_office_omdb": Decimal("292576195.00"),
            "omdb_fetched_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
            "loaded_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
        }
        return DimMovieDto(**(defaults | overrides))

    return _make


@pytest.fixture
def dim_date_dto_factory() -> callable:
    """Return a factory function for creating ``DimDateDto`` instances."""

    def _make(**overrides: object) -> DimDateDto:
        defaults = {
            "date_id": 20040920,
            "date": datetime.date(2004, 9, 20),
            "year": 2004,
            "quarter": 3,
            "month": 9,
            "month_name": "September",
            "day": 20,
            "day_of_week": 1,
            "day_of_week_name": "Monday",
            "week_number": 39,
            "is_weekend": False,
            "is_holiday": False,
        }
        return DimDateDto(**(defaults | overrides))

    return _make


@pytest.fixture
def dim_distributor_dto_factory() -> callable:
    """Return a factory function for creating ``DimDistributorDto`` instances."""

    def _make(**overrides: object) -> DimDistributorDto:
        defaults = {
            "distributor_id": None,
            "distributor_name": "Paramount Pictures",
            "loaded_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
        }
        return DimDistributorDto(**(defaults | overrides))

    return _make


@pytest.fixture
def dim_genre_dto_factory() -> callable:
    """Return a factory function for creating ``DimGenreDto`` instances."""

    def _make(**overrides: object) -> DimGenreDto:
        defaults = {
            "genre_id": None,
            "genre_name": "Action",
            "loaded_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
        }
        return DimGenreDto(**(defaults | overrides))

    return _make


@pytest.fixture
def dim_director_dto_factory() -> callable:
    """Return a factory function for creating ``DimDirectorDto`` instances."""

    def _make(**overrides: object) -> DimDirectorDto:
        defaults = {
            "director_id": None,
            "director_name": "Christopher Nolan",
            "loaded_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
        }
        return DimDirectorDto(**(defaults | overrides))

    return _make


@pytest.fixture
def dim_rated_dto_factory() -> callable:
    """Return a factory function for creating ``DimRatedDto`` instances."""

    def _make(**overrides: object) -> DimRatedDto:
        defaults = {
            "rated_id": None,
            "rating_code": "PG-13",
            "rating_description": "Parents Strongly Cautioned",
            "loaded_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
        }
        return DimRatedDto(**(defaults | overrides))

    return _make


@pytest.fixture
def fact_revenue_dto_factory() -> callable:
    """Return a factory function for creating ``FactRevenueDto`` instances."""

    def _make(**overrides: object) -> FactRevenueDto:
        defaults = {
            "revenue_id": None,
            "source_row_id": uuid.uuid4(),
            "movie_id": 1,
            "date_id": 20040920,
            "distributor_id": 1,
            "revenue": Decimal("925482.00"),
            "theaters": 3170,
            "loaded_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
        }
        return FactRevenueDto(**(defaults | overrides))

    return _make


@pytest.fixture
def fact_movie_rating_dto_factory() -> callable:
    """Return a factory function for creating ``FactMovieRatingDto`` instances."""

    def _make(**overrides: object) -> FactMovieRatingDto:
        defaults = {
            "rating_id": None,
            "movie_id": 1,
            "imdb_rating": Decimal("8.8"),
            "imdb_votes": 2500000,
            "valid_from": datetime.datetime(2026, 6, 1, 0, 0, 0),
            "valid_to": None,
            "is_current": True,
            "loaded_at": datetime.datetime(2026, 6, 5, 12, 0, 0),
        }
        return FactMovieRatingDto(**(defaults | overrides))

    return _make
