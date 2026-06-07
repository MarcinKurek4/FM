"""Unit tests for DWH mapper functions.

This module verifies that all mapper functions correctly convert between
DTOs and SQLModel tables in both directions (round-trip test).
"""

import datetime
import uuid
from decimal import Decimal

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
from src.models.dwh_tables import (
    BridgeMovieDirectorTable,
    BridgeMovieGenreTable,
    DimDateTable,
    DimDirectorTable,
    DimDistributorTable,
    DimGenreTable,
    DimMovieTable,
    DimRatedTable,
    FactMovieRatingTable,
    FactRevenueTable,
)
from src.utils.dwh_mappers import (
    bridge_movie_director_dto_to_table,
    bridge_movie_director_table_to_dto,
    bridge_movie_genre_dto_to_table,
    bridge_movie_genre_table_to_dto,
    dim_date_dto_to_table,
    dim_date_table_to_dto,
    dim_director_dto_to_table,
    dim_director_table_to_dto,
    dim_distributor_dto_to_table,
    dim_distributor_table_to_dto,
    dim_genre_dto_to_table,
    dim_genre_table_to_dto,
    dim_movie_dto_to_table,
    dim_movie_table_to_dto,
    dim_rated_dto_to_table,
    dim_rated_table_to_dto,
    fact_movie_rating_dto_to_table,
    fact_movie_rating_table_to_dto,
    fact_revenue_dto_to_table,
    fact_revenue_table_to_dto,
)


def test_dim_movie_round_trip_preserves_equality() -> None:
    """Verify that DimMovie DTO → Table → DTO preserves all field values."""
    original_dto = DimMovieDto(
        movie_id=1,
        imdb_id="tt1375666",
        title="Inception",
        release_year=2010,
        rated_id=3,
        runtime_min=148,
        plot="A thief who steals corporate secrets.",
        awards="Won 4 Oscars.",
        box_office_omdb=Decimal("292576195.00"),
        omdb_fetched_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = dim_movie_dto_to_table(original_dto)
    restored_dto = dim_movie_table_to_dto(table)

    assert restored_dto == original_dto


def test_dim_date_round_trip_preserves_equality() -> None:
    """Verify that DimDate DTO → Table → DTO preserves all field values."""
    original_dto = DimDateDto(
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

    table = dim_date_dto_to_table(original_dto)
    restored_dto = dim_date_table_to_dto(table)

    assert restored_dto == original_dto


def test_dim_distributor_round_trip_preserves_equality() -> None:
    """Verify that DimDistributor DTO → Table → DTO preserves all field values."""
    original_dto = DimDistributorDto(
        distributor_id=1,
        distributor_name="Paramount Pictures",
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = dim_distributor_dto_to_table(original_dto)
    restored_dto = dim_distributor_table_to_dto(table)

    assert restored_dto == original_dto


def test_dim_genre_round_trip_preserves_equality() -> None:
    """Verify that DimGenre DTO → Table → DTO preserves all field values."""
    original_dto = DimGenreDto(
        genre_id=1,
        genre_name="Action",
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = dim_genre_dto_to_table(original_dto)
    restored_dto = dim_genre_table_to_dto(table)

    assert restored_dto == original_dto


def test_dim_director_round_trip_preserves_equality() -> None:
    """Verify that DimDirector DTO → Table → DTO preserves all field values."""
    original_dto = DimDirectorDto(
        director_id=1,
        director_name="Christopher Nolan",
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = dim_director_dto_to_table(original_dto)
    restored_dto = dim_director_table_to_dto(table)

    assert restored_dto == original_dto


def test_dim_rated_round_trip_preserves_equality() -> None:
    """Verify that DimRated DTO → Table → DTO preserves all field values."""
    original_dto = DimRatedDto(
        rated_id=1,
        rating_code="PG-13",
        rating_description="Parents Strongly Cautioned",
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = dim_rated_dto_to_table(original_dto)
    restored_dto = dim_rated_table_to_dto(table)

    assert restored_dto == original_dto


def test_bridge_movie_genre_round_trip_preserves_equality() -> None:
    """Verify that BridgeMovieGenre DTO → Table → DTO preserves all field values."""
    original_dto = BridgeMovieGenreDto(
        movie_id=1,
        genre_id=2,
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = bridge_movie_genre_dto_to_table(original_dto)
    restored_dto = bridge_movie_genre_table_to_dto(table)

    assert restored_dto == original_dto


def test_bridge_movie_director_round_trip_preserves_equality() -> None:
    """Verify that BridgeMovieDirector DTO → Table → DTO preserves all field values."""
    original_dto = BridgeMovieDirectorDto(
        movie_id=1,
        director_id=3,
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = bridge_movie_director_dto_to_table(original_dto)
    restored_dto = bridge_movie_director_table_to_dto(table)

    assert restored_dto == original_dto


def test_fact_revenue_round_trip_preserves_equality() -> None:
    """Verify that FactRevenue DTO → Table → DTO preserves all field values."""
    source_id = uuid.uuid4()
    original_dto = FactRevenueDto(
        revenue_id=1,
        source_row_id=source_id,
        movie_id=1,
        date_id=20040920,
        distributor_id=1,
        revenue=Decimal("925482.00"),
        theaters=3170,
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = fact_revenue_dto_to_table(original_dto)
    restored_dto = fact_revenue_table_to_dto(table)

    assert restored_dto == original_dto


def test_dim_movie_dto_to_table_handles_none_values() -> None:
    """Verify that mapper correctly handles None for optional fields."""
    dto = DimMovieDto(
        movie_id=None,
        imdb_id="tt1375666",
        title="Inception",
        release_year=None,
        rated_id=None,
        runtime_min=None,
        plot=None,
        awards=None,
        box_office_omdb=None,
        omdb_fetched_at=None,
        loaded_at=datetime.datetime(2026, 6, 5),
    )

    table = dim_movie_dto_to_table(dto)

    assert table.release_year is None
    assert table.rated_id is None
    assert table.runtime_min is None
    assert table.plot is None
    assert table.awards is None
    assert table.box_office_omdb is None
    assert table.omdb_fetched_at is None


def test_fact_movie_rating_round_trip_preserves_equality() -> None:
    """Verify that FactMovieRating DTO → Table → DTO preserves all field values."""
    original_dto = FactMovieRatingDto(
        rating_id=1,
        movie_id=1,
        imdb_rating=Decimal("8.8"),
        imdb_votes=2500000,
        valid_from=datetime.datetime(2026, 6, 1, 0, 0, 0),
        valid_to=None,
        is_current=True,
        loaded_at=datetime.datetime(2026, 6, 5, 12, 0, 0),
    )

    table = fact_movie_rating_dto_to_table(original_dto)
    restored_dto = fact_movie_rating_table_to_dto(table)

    assert restored_dto == original_dto
