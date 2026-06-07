"""SQLModel table definitions for the DWH star schema.

This module defines SQLModel classes with ``table=True`` that map to physical
tables in the PostgreSQL ``dwh`` schema. Each table class corresponds to a
DTO in ``src.models.dwh``.

These tables are never exposed outside the repository layer — repositories
map table instances to DTOs before returning results.

All tables use the ``dwh`` PostgreSQL schema via ``__table_args__``.

Usage::

    from sqlmodel import select
    from src.models.dwh_tables import DimMovieTable

    result = await session.execute(select(DimMovieTable).where(...))
    row = result.scalar_one_or_none()
"""

import datetime
import uuid

from decimal import Decimal
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Numeric, Text
from sqlmodel import Field, SQLModel


class DimMovieTable(SQLModel, table=True):
    """SQLModel table for ``dwh.dim_movie``.

    Maps one-to-one with ``DimMovieDto``. The surrogate key ``movie_id``
    is auto-generated on insert. The natural key ``imdb_id`` has a unique
    constraint.

    Time-varying attributes (IMDb rating, votes) are tracked in
    ``fact_movie_rating`` with SCD Type 2.

    Foreign key ``rated_id`` references ``dwh.dim_rated``.
    """

    __tablename__ = "dim_movie"
    __table_args__ = {"schema": "dwh"}

    movie_id: int | None = Field(
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
        default=None,
    )
    imdb_id: str = Field(max_length=15, unique=True, nullable=False, index=True)
    title: str = Field(max_length=500, nullable=False)
    release_year: int | None = Field(default=None)
    rated_id: int | None = Field(default=None, foreign_key="dwh.dim_rated.rated_id", index=True)
    runtime_min: int | None = Field(default=None)
    plot: str | None = Field(sa_column=Column(Text), default=None)
    awards: str | None = Field(sa_column=Column(Text), default=None)
    box_office_omdb: Decimal | None = Field(
        sa_column=Column(Numeric(18, 2)),
        default=None,
    )
    omdb_fetched_at: datetime.datetime | None = Field(default=None)
    loaded_at: datetime.datetime = Field(nullable=False)


class DimDateTable(SQLModel, table=True):
    """SQLModel table for ``dwh.dim_date``.

    Maps one-to-one with ``DimDateDto``. The primary key ``date_id`` is a
    BIGINT in ``YYYYMMDD`` format (e.g., 20040920). This dimension is
    typically pre-seeded for a wide date range.
    """

    __tablename__ = "dim_date"
    __table_args__ = {"schema": "dwh"}

    date_id: int = Field(
        sa_column=Column(BigInteger, primary_key=True, autoincrement=False),
    )
    date: datetime.date = Field(unique=True, nullable=False, index=True)
    year: int = Field(nullable=False)
    quarter: int = Field(nullable=False)
    month: int = Field(nullable=False)
    month_name: str = Field(max_length=20, nullable=False)
    day: int = Field(nullable=False)
    day_of_week: int = Field(nullable=False)
    day_of_week_name: str = Field(max_length=20, nullable=False)
    week_number: int = Field(nullable=False)
    is_weekend: bool = Field(nullable=False)
    is_holiday: bool = Field(default=False, nullable=False)


class DimDistributorTable(SQLModel, table=True):
    """SQLModel table for ``dwh.dim_distributor``.

    Maps one-to-one with ``DimDistributorDto``. The natural key
    ``distributor_name`` has a unique constraint.
    """

    __tablename__ = "dim_distributor"
    __table_args__ = {"schema": "dwh"}

    distributor_id: int | None = Field(
        sa_column=Column(Integer, primary_key=True, autoincrement=True),
        default=None,
    )
    distributor_name: str = Field(max_length=200, unique=True, nullable=False, index=True)
    loaded_at: datetime.datetime = Field(nullable=False)


class DimGenreTable(SQLModel, table=True):
    """SQLModel table for ``dwh.dim_genre``.

    Maps one-to-one with ``DimGenreDto``. The natural key ``genre_name``
    has a unique constraint.
    """

    __tablename__ = "dim_genre"
    __table_args__ = {"schema": "dwh"}

    genre_id: int | None = Field(
        sa_column=Column(Integer, primary_key=True, autoincrement=True),
        default=None,
    )
    genre_name: str = Field(max_length=100, unique=True, nullable=False, index=True)
    loaded_at: datetime.datetime = Field(nullable=False)


class DimDirectorTable(SQLModel, table=True):
    """SQLModel table for ``dwh.dim_director``.

    Maps one-to-one with ``DimDirectorDto``. The natural key
    ``director_name`` has a unique constraint.
    """

    __tablename__ = "dim_director"
    __table_args__ = {"schema": "dwh"}

    director_id: int | None = Field(
        sa_column=Column(Integer, primary_key=True, autoincrement=True),
        default=None,
    )
    director_name: str = Field(max_length=200, unique=True, nullable=False, index=True)
    loaded_at: datetime.datetime = Field(nullable=False)


class DimRatedTable(SQLModel, table=True):
    """SQLModel table for ``dwh.dim_rated``.

    Maps one-to-one with ``DimRatedDto``. The natural key ``rating_code``
    has a unique constraint.
    """

    __tablename__ = "dim_rated"
    __table_args__ = {"schema": "dwh"}

    rated_id: int | None = Field(
        sa_column=Column(Integer, primary_key=True, autoincrement=True),
        default=None,
    )
    rating_code: str = Field(max_length=20, unique=True, nullable=False, index=True)
    rating_description: str = Field(max_length=200, nullable=False)
    loaded_at: datetime.datetime = Field(nullable=False)


class BridgeMovieGenreTable(SQLModel, table=True):
    """SQLModel table for ``dwh.bridge_movie_genre``.

    Many-to-many association between movies and genres. The composite
    primary key is ``(movie_id, genre_id)``.
    """

    __tablename__ = "bridge_movie_genre"
    __table_args__ = {"schema": "dwh"}

    movie_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("dwh.dim_movie.movie_id"),
            primary_key=True,
            nullable=False,
        ),
    )
    genre_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("dwh.dim_genre.genre_id"),
            primary_key=True,
            nullable=False,
        ),
    )
    loaded_at: datetime.datetime = Field(nullable=False)


class BridgeMovieDirectorTable(SQLModel, table=True):
    """SQLModel table for ``dwh.bridge_movie_director``.

    Many-to-many association between movies and directors. The composite
    primary key is ``(movie_id, director_id)``.
    """

    __tablename__ = "bridge_movie_director"
    __table_args__ = {"schema": "dwh"}

    movie_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("dwh.dim_movie.movie_id"),
            primary_key=True,
            nullable=False,
        ),
    )
    director_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("dwh.dim_director.director_id"),
            primary_key=True,
            nullable=False,
        ),
    )
    loaded_at: datetime.datetime = Field(nullable=False)


class FactRevenueTable(SQLModel, table=True):
    """SQLModel table for ``dwh.fact_revenue``.

    Maps one-to-one with ``FactRevenueDto``. The surrogate key
    ``revenue_id`` is auto-generated. The natural key ``source_row_id``
    (UUID from the source CSV) has a unique constraint for idempotency.

    Foreign keys reference ``dim_movie`` (BIGINT), ``dim_date`` (BIGINT),
    and ``dim_distributor``.
    """

    __tablename__ = "fact_revenue"
    __table_args__ = {"schema": "dwh"}

    revenue_id: int | None = Field(
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
        default=None,
    )
    source_row_id: uuid.UUID = Field(unique=True, nullable=False, index=True)
    movie_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("dwh.dim_movie.movie_id"),
            nullable=False,
            index=True,
        ),
    )
    date_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("dwh.dim_date.date_id"),
            nullable=False,
            index=True,
        ),
    )
    distributor_id: int | None = Field(
        default=None,
        foreign_key="dwh.dim_distributor.distributor_id",
        nullable=True,
        index=True,
    )
    revenue: Decimal = Field(
        sa_column=Column(Numeric(18, 2), nullable=False),
    )
    theaters: int | None = Field(default=None, nullable=True)
    loaded_at: datetime.datetime = Field(nullable=False)


class FactMovieRatingTable(SQLModel, table=True):
    """SQLModel table for ``dwh.fact_movie_rating`` with SCD Type 2.

    Maps one-to-one with ``FactMovieRatingDto``. Tracks historical changes
    to IMDb ratings and vote counts using Slowly Changing Dimension Type 2.

    Each movie may have multiple rows (one per rating change). The
    ``is_current`` flag marks the active record. The validity period is
    defined by ``valid_from`` and ``valid_to``.
    """

    __tablename__ = "fact_movie_rating"
    __table_args__ = {"schema": "dwh"}

    rating_id: int | None = Field(
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
        default=None,
    )
    movie_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("dwh.dim_movie.movie_id"),
            nullable=False,
            index=True,
        ),
    )
    imdb_rating: Decimal | None = Field(
        sa_column=Column(Numeric(3, 1)),
        default=None,
    )
    imdb_votes: int | None = Field(default=None)
    valid_from: datetime.datetime = Field(nullable=False, index=True)
    valid_to: datetime.datetime | None = Field(default=None, index=True)
    is_current: bool = Field(nullable=False, index=True)
    loaded_at: datetime.datetime = Field(nullable=False)
