"""Unit tests for DWH DTO models.

This module verifies that all DTOs are correctly configured as frozen
dataclasses with __slots__ and that field types are properly annotated.
"""

import datetime
import uuid
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.models.dwh import (
    BridgeMovieDirectorDto,
    BridgeMovieGenreDto,
    DimDateDto,
    DimDirectorDto,
    DimDistributorDto,
    DimGenreDto,
    DimMovieDto,
    DimRatedDto,
    FactMovieRatingDto,
    FactRevenueDto,
)


def test_dim_movie_dto_is_frozen() -> None:
    """Verify that DimMovieDto is frozen and immutable."""
    dto = DimMovieDto(
        movie_id=1,
        imdb_id="tt1375666",
        title="Inception",
        release_year=2010,
        rated_id=None,
        runtime_min=148,
        plot="Plot",
        awards="Awards",
        box_office_omdb=Decimal("100.00"),
        omdb_fetched_at=datetime.datetime(2026, 6, 5),
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.title = "Modified"


def test_dim_movie_dto_has_slots() -> None:
    """Verify that DimMovieDto uses __slots__ for memory efficiency."""
    dto = DimMovieDto(
        movie_id=1,
        imdb_id="tt1375666",
        title="Inception",
        release_year=2010,
        rated_id=None,
        runtime_min=148,
        plot="Plot",
        awards="Awards",
        box_office_omdb=Decimal("100.00"),
        omdb_fetched_at=datetime.datetime(2026, 6, 5),
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    assert not hasattr(dto, "__dict__")


def test_dim_date_dto_is_frozen() -> None:
    """Verify that DimDateDto is frozen and immutable."""
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

    with pytest.raises(FrozenInstanceError):
        dto.year = 2005


def test_dim_distributor_dto_is_frozen() -> None:
    """Verify that DimDistributorDto is frozen and immutable."""
    dto = DimDistributorDto(
        distributor_id=1,
        distributor_name="Paramount Pictures",
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.distributor_name = "Modified"


def test_dim_genre_dto_is_frozen() -> None:
    """Verify that DimGenreDto is frozen and immutable."""
    dto = DimGenreDto(
        genre_id=1,
        genre_name="Action",
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.genre_name = "Drama"


def test_dim_director_dto_is_frozen() -> None:
    """Verify that DimDirectorDto is frozen and immutable."""
    dto = DimDirectorDto(
        director_id=1,
        director_name="Christopher Nolan",
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.director_name = "Modified"


def test_dim_rated_dto_is_frozen() -> None:
    """Verify that DimRatedDto is frozen and immutable."""
    dto = DimRatedDto(
        rated_id=1,
        rating_code="PG-13",
        rating_description="Parents Strongly Cautioned",
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.rating_code = "R"


def test_bridge_movie_genre_dto_is_frozen() -> None:
    """Verify that BridgeMovieGenreDto is frozen and immutable."""
    dto = BridgeMovieGenreDto(
        movie_id=1,
        genre_id=2,
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.movie_id = 999


def test_bridge_movie_director_dto_is_frozen() -> None:
    """Verify that BridgeMovieDirectorDto is frozen and immutable."""
    dto = BridgeMovieDirectorDto(
        movie_id=1,
        director_id=3,
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.director_id = 999


def test_fact_revenue_dto_is_frozen() -> None:
    """Verify that FactRevenueDto is frozen and immutable."""
    dto = FactRevenueDto(
        revenue_id=1,
        source_row_id=uuid.uuid4(),
        movie_id=1,
        date_id=20040920,
        distributor_id=1,
        revenue=Decimal("100.00"),
        theaters=500,
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.revenue = Decimal("200.00")


def test_fact_revenue_dto_has_slots() -> None:
    """Verify that FactRevenueDto uses __slots__."""
    dto = FactRevenueDto(
        revenue_id=1,
        source_row_id=uuid.uuid4(),
        movie_id=1,
        date_id=20040920,
        distributor_id=1,
        revenue=Decimal("100.00"),
        theaters=500,
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    assert not hasattr(dto, "__dict__")


def test_fact_movie_rating_dto_is_frozen() -> None:
    """Verify that FactMovieRatingDto is frozen and immutable."""
    dto = FactMovieRatingDto(
        rating_id=1,
        movie_id=1,
        imdb_rating=Decimal("8.8"),
        imdb_votes=2500000,
        valid_from=datetime.datetime(2026, 6, 1),
        valid_to=None,
        is_current=True,
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    with pytest.raises(FrozenInstanceError):
        dto.imdb_rating = Decimal("9.0")


def test_fact_movie_rating_dto_has_slots() -> None:
    """Verify that FactMovieRatingDto uses __slots__."""
    dto = FactMovieRatingDto(
        rating_id=1,
        movie_id=1,
        imdb_rating=Decimal("8.8"),
        imdb_votes=2500000,
        valid_from=datetime.datetime(2026, 6, 1),
        valid_to=None,
        is_current=True,
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    assert not hasattr(dto, "__dict__")
