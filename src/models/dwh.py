"""Data Transfer Objects for the DWH star schema.

This module defines frozen dataclasses representing rows from the data
warehouse tables in the ``dwh`` PostgreSQL schema. DTOs are the contract
between the repository layer and the service layer — repositories return
DTOs, never SQLModel table instances.

All monetary values use ``Decimal`` for exactness. Surrogate keys
(``movie_id``, ``revenue_id``, etc.) are ``int | None`` to represent
records before database insertion.

Usage::

    from src.models.dwh import DimMovieDto

    dto = DimMovieDto(
        movie_id=None,
        imdb_id="tt1375666",
        title="Inception",
        ...
    )
"""

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DimMovieDto:
    """One row from the ``dwh.dim_movie`` dimension table.

    Represents a single movie with metadata enriched from the OMDb API.
    The ``movie_id`` is a surrogate key (``None`` before insert); the
    natural key is ``imdb_id``.

    This dimension follows SCD Type 1 — updates overwrite existing records
    for static attributes. Time-varying attributes (IMDb rating, votes) are
    tracked separately in ``fact_movie_rating`` with SCD Type 2.

    Attributes:
        movie_id: Surrogate primary key (BIGINT). ``None`` for new records
            before database insert.
        imdb_id: IMDb title identifier (e.g., ``"tt1375666"``). Natural key;
            must be unique and not null.
        title: Movie title as reported by OMDb.
        release_year: Four-digit release year, or ``None`` when unavailable.
        rated_id: Foreign key to ``dim_rated``. References the MPAA rating
            (G, PG, PG-13, R, NC-17). ``None`` when the movie is unrated or
            rating is unavailable.
        runtime_min: Runtime in minutes, or ``None``.
        plot: Full plot summary text, or ``None``.
        awards: Raw awards string (e.g., ``"Won 2 Oscars..."``) or ``None``.
        box_office_omdb: Domestic box office gross in USD as reported by
            OMDb, or ``None``.
        omdb_fetched_at: Timestamp when the OMDb API response was cached,
            or ``None`` for movies not yet enriched.
        loaded_at: Timestamp when this record was inserted or last updated
            in the database.

    Example:
        dto = DimMovieDto(
            movie_id=1,
            imdb_id="tt1375666",
            title="Inception",
            release_year=2010,
            rated_id=3,
            runtime_min=148,
            plot="A thief who steals corporate secrets...",
            awards="Won 4 Oscars.",
            box_office_omdb=Decimal("292576195.00"),
            omdb_fetched_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    movie_id: int | None
    imdb_id: str
    title: str
    release_year: int | None
    rated_id: int | None
    runtime_min: int | None
    plot: str | None
    awards: str | None
    box_office_omdb: Decimal | None
    omdb_fetched_at: datetime.datetime | None
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class DimDateDto:
    """One row from the ``dwh.dim_date`` dimension table.

    Represents a single calendar date with pre-calculated attributes for
    time-based analytics. The date dimension is typically pre-populated
    (seeded) for a wide range of years (e.g., 2000–2030) before any fact
    data is loaded.

    The ``date_id`` is a BIGINT surrogate key in ``YYYYMMDD`` format
    (e.g., ``20040920`` for 2004-09-20). This format is human-readable in
    queries and sorts naturally.

    Attributes:
        date_id: Surrogate primary key (BIGINT) in ``YYYYMMDD`` format.
        date: The calendar date itself.
        year: Four-digit calendar year.
        quarter: Calendar quarter (1–4).
        month: Month number (1–12).
        month_name: Full month name (e.g., ``"January"``).
        day: Day of month (1–31).
        day_of_week: ISO day of week (1=Monday, 7=Sunday).
        day_of_week_name: Full weekday name (e.g., ``"Monday"``).
        week_number: ISO week number (1–53).
        is_weekend: ``True`` when ``day_of_week`` is 6 (Saturday) or
            7 (Sunday).
        is_holiday: ``True`` when the date is a recognised US public holiday.

    Example:
        dto = DimDateDto(
            date_id=20040920,
            date=datetime.date(2004, 9, 20),
            year=2004,
            quarter=3,
            month=9,
            month_name="September",
            day=20,
            day_of_week=1,
            day_of_week_name="Monday",
            week_number=39,
            is_weekend=False,
            is_holiday=False,
        )
    """

    date_id: int
    date: datetime.date
    year: int
    quarter: int
    month: int
    month_name: str
    day: int
    day_of_week: int
    day_of_week_name: str
    week_number: int
    is_weekend: bool
    is_holiday: bool


@dataclass(frozen=True, slots=True)
class DimDistributorDto:
    """One row from the ``dwh.dim_distributor`` dimension table.

    Represents a single film distribution company. The natural key is
    ``distributor_name`` (unique).

    When the source CSV contains the sentinel value ``"-"`` (indicating
    unknown distributor), the ETL pipeline should reference a pre-seeded
    ``"Unknown"`` record with ``distributor_id = 0``.

    Attributes:
        distributor_id: Surrogate primary key. ``None`` for new records
            before insert.
        distributor_name: Company name (e.g., ``"Paramount Pictures"``).
            Must be unique.
        loaded_at: Timestamp when this record was inserted or last updated.

    Example:
        dto = DimDistributorDto(
            distributor_id=1,
            distributor_name="Paramount Pictures",
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    distributor_id: int | None
    distributor_name: str
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class DimGenreDto:
    """One row from the ``dwh.dim_genre`` dimension table.

    Represents a single movie genre. Genres are extracted from the OMDb
    ``Genre`` field (a comma-separated string like ``"Action, Adventure"``).

    The natural key is ``genre_name`` (unique).

    Attributes:
        genre_id: Surrogate primary key. ``None`` for new records before
            insert.
        genre_name: Genre label (e.g., ``"Action"``, ``"Drama"``). Must be
            unique.
        loaded_at: Timestamp when this record was inserted.

    Example:
        dto = DimGenreDto(
            genre_id=1,
            genre_name="Action",
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    genre_id: int | None
    genre_name: str
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class DimDirectorDto:
    """One row from the ``dwh.dim_director`` dimension table.

    Represents a single film director. Directors are extracted from the
    OMDb ``Director`` field (a comma-separated string when multiple
    directors are credited).

    The natural key is ``director_name`` (unique).

    Attributes:
        director_id: Surrogate primary key. ``None`` for new records before
            insert.
        director_name: Director full name (e.g., ``"Christopher Nolan"``).
            Must be unique.
        loaded_at: Timestamp when this record was inserted.

    Example:
        dto = DimDirectorDto(
            director_id=1,
            director_name="Christopher Nolan",
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    director_id: int | None
    director_name: str
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class DimRatedDto:
    """One row from the ``dwh.dim_rated`` dimension table.

    Represents a single MPAA film rating (G, PG, PG-13, R, NC-17, etc.).
    This mini-dimension normalises the ``rated`` field from OMDb into a
    separate lookup table.

    The natural key is ``rating_code`` (unique).

    Attributes:
        rated_id: Surrogate primary key. ``None`` for new records before
            insert.
        rating_code: MPAA rating code (e.g., ``"PG-13"``, ``"R"``). Must be
            unique.
        rating_description: Human-readable description of the rating
            (e.g., ``"Parental Guidance Suggested"``).
        loaded_at: Timestamp when this record was inserted.

    Example:
        dto = DimRatedDto(
            rated_id=1,
            rating_code="PG-13",
            rating_description="Parents Strongly Cautioned",
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    rated_id: int | None
    rating_code: str
    rating_description: str
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class BridgeMovieGenreDto:
    """One row from the ``dwh.bridge_movie_genre`` many-to-many table.

    Represents a single movie-genre association. A movie may have multiple
    genres, and a genre may be associated with multiple movies.

    The composite primary key is ``(movie_id, genre_id)``.

    Attributes:
        movie_id: Foreign key to ``dwh.dim_movie``.
        genre_id: Foreign key to ``dwh.dim_genre``.
        loaded_at: Timestamp when this association was recorded.

    Example:
        dto = BridgeMovieGenreDto(
            movie_id=1,
            genre_id=2,
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    movie_id: int
    genre_id: int
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class BridgeMovieDirectorDto:
    """One row from the ``dwh.bridge_movie_director`` many-to-many table.

    Represents a single movie-director association. A movie may have
    multiple directors (e.g., co-directors), and a director may be
    associated with multiple movies.

    The composite primary key is ``(movie_id, director_id)``.

    Attributes:
        movie_id: Foreign key to ``dwh.dim_movie``.
        director_id: Foreign key to ``dwh.dim_director``.
        loaded_at: Timestamp when this association was recorded.

    Example:
        dto = BridgeMovieDirectorDto(
            movie_id=1,
            director_id=3,
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    movie_id: int
    director_id: int
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class FactRevenueDto:
    """One row from the ``dwh.fact_revenue`` fact table.

    Represents a single box office revenue observation: one movie, on one
    date, with revenue and theater count. The grain is one row per movie
    per day.

    The natural key is ``source_row_id`` (the UUID from the source CSV),
    which ensures idempotency when re-running the ETL pipeline.

    All measures (``revenue``, ``theaters``) are additive and may be summed
    across any dimension.

    Attributes:
        revenue_id: Surrogate primary key (BIGINT). ``None`` for new records
            before insert.
        source_row_id: Natural key — the UUID from the source CSV. Ensures
            idempotency.
        movie_id: Foreign key to ``dwh.dim_movie`` (BIGINT).
        date_id: Foreign key to ``dwh.dim_date`` (BIGINT in YYYYMMDD format).
        distributor_id: Foreign key to ``dwh.dim_distributor``.
        revenue: Box office revenue in USD for the given date. Stored as
            ``NUMERIC(18, 2)``.
        theaters: Number of theater screens showing the film on that date.
        loaded_at: Timestamp when this fact record was inserted.

    Example:
        dto = FactRevenueDto(
            revenue_id=1,
            source_row_id=uuid.UUID("8b19ad43-3a7e-b14b-49e9-1f7a0eb1568e"),
            movie_id=1,
            date_id=20040920,
            distributor_id=1,
            revenue=Decimal("925482.00"),
            theaters=3170,
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    revenue_id: int | None
    source_row_id: uuid.UUID
    movie_id: int
    date_id: int
    distributor_id: int
    revenue: Decimal
    theaters: int
    loaded_at: datetime.datetime


@dataclass(frozen=True, slots=True)
class FactMovieRatingDto:
    """One row from the ``dwh.fact_movie_rating`` fact table with SCD Type 2.

    Represents a snapshot of a movie's IMDb rating and vote count at a
    specific point in time. This fact table tracks the historical evolution
    of ratings using Slowly Changing Dimension Type 2 semantics.

    The grain is one row per movie per rating change. Each record has a
    validity period defined by ``valid_from`` and ``valid_to``. The
    ``is_current`` flag marks the most recent (active) rating for each movie.

    Attributes:
        rating_id: Surrogate primary key (BIGINT). ``None`` for new records
            before insert.
        movie_id: Foreign key to ``dwh.dim_movie`` (BIGINT).
        imdb_rating: IMDb user rating (0.0–10.0), or ``None``.
        imdb_votes: Total IMDb vote count, or ``None``.
        valid_from: Timestamp when this rating snapshot became effective.
        valid_to: Timestamp when this rating snapshot was superseded by a
            new value. ``None`` for the current (active) record.
        is_current: ``True`` for the most recent rating snapshot; ``False``
            for historical records.
        loaded_at: Timestamp when this fact record was inserted.

    Example:
        dto = FactMovieRatingDto(
            rating_id=1,
            movie_id=1,
            imdb_rating=Decimal("8.8"),
            imdb_votes=2500000,
            valid_from=datetime.datetime(2026, 6, 1, 0, 0, 0),
            valid_to=None,
            is_current=True,
            loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        )
    """

    rating_id: int | None
    movie_id: int
    imdb_rating: Decimal | None
    imdb_votes: int | None
    valid_from: datetime.datetime
    valid_to: datetime.datetime | None
    is_current: bool
    loaded_at: datetime.datetime
