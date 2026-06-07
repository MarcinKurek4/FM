"""Bidirectional mappers between DWH DTOs and SQLModel tables.

This module provides pure functions that convert between DTOs (defined in
``src.models.dwh``) and SQLModel table instances (defined in
``src.models.dwh_tables``).

All mappers are stateless and free of side effects. They perform field-level
1:1 copying with no transformation logic.

Usage::

    from src.utils.dwh_mappers import dim_movie_table_to_dto

    table = DimMovieTable(...)
    dto = dim_movie_table_to_dto(table)
"""

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


def dim_movie_table_to_dto(table: DimMovieTable) -> DimMovieDto:
    """Convert a ``DimMovieTable`` instance to a ``DimMovieDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = dim_movie_table_to_dto(table)
    """
    return DimMovieDto(
        movie_id=table.movie_id,
        imdb_id=table.imdb_id,
        title=table.title,
        release_year=table.release_year,
        rated_id=table.rated_id,
        runtime_min=table.runtime_min,
        plot=table.plot,
        awards=table.awards,
        box_office_omdb=table.box_office_omdb,
        omdb_fetched_at=table.omdb_fetched_at,
        loaded_at=table.loaded_at,
    )


def dim_movie_dto_to_table(dto: DimMovieDto) -> DimMovieTable:
    """Convert a ``DimMovieDto`` to a ``DimMovieTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = dim_movie_dto_to_table(dto)
    """
    return DimMovieTable(
        movie_id=dto.movie_id,
        imdb_id=dto.imdb_id,
        title=dto.title,
        release_year=dto.release_year,
        rated_id=dto.rated_id,
        runtime_min=dto.runtime_min,
        plot=dto.plot,
        awards=dto.awards,
        box_office_omdb=dto.box_office_omdb,
        omdb_fetched_at=dto.omdb_fetched_at,
        loaded_at=dto.loaded_at,
    )


def dim_date_table_to_dto(table: DimDateTable) -> DimDateDto:
    """Convert a ``DimDateTable`` instance to a ``DimDateDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = dim_date_table_to_dto(table)
    """
    return DimDateDto(
        date_id=table.date_id,
        date=table.date,
        year=table.year,
        quarter=table.quarter,
        month=table.month,
        month_name=table.month_name,
        day=table.day,
        day_of_week=table.day_of_week,
        day_of_week_name=table.day_of_week_name,
        week_number=table.week_number,
        is_weekend=table.is_weekend,
        is_holiday=table.is_holiday,
    )


def dim_date_dto_to_table(dto: DimDateDto) -> DimDateTable:
    """Convert a ``DimDateDto`` to a ``DimDateTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = dim_date_dto_to_table(dto)
    """
    return DimDateTable(
        date_id=dto.date_id,
        date=dto.date,
        year=dto.year,
        quarter=dto.quarter,
        month=dto.month,
        month_name=dto.month_name,
        day=dto.day,
        day_of_week=dto.day_of_week,
        day_of_week_name=dto.day_of_week_name,
        week_number=dto.week_number,
        is_weekend=dto.is_weekend,
        is_holiday=dto.is_holiday,
    )


def dim_distributor_table_to_dto(table: DimDistributorTable) -> DimDistributorDto:
    """Convert a ``DimDistributorTable`` instance to a ``DimDistributorDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = dim_distributor_table_to_dto(table)
    """
    return DimDistributorDto(
        distributor_id=table.distributor_id,
        distributor_name=table.distributor_name,
        loaded_at=table.loaded_at,
    )


def dim_distributor_dto_to_table(dto: DimDistributorDto) -> DimDistributorTable:
    """Convert a ``DimDistributorDto`` to a ``DimDistributorTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = dim_distributor_dto_to_table(dto)
    """
    return DimDistributorTable(
        distributor_id=dto.distributor_id,
        distributor_name=dto.distributor_name,
        loaded_at=dto.loaded_at,
    )


def dim_genre_table_to_dto(table: DimGenreTable) -> DimGenreDto:
    """Convert a ``DimGenreTable`` instance to a ``DimGenreDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = dim_genre_table_to_dto(table)
    """
    return DimGenreDto(
        genre_id=table.genre_id,
        genre_name=table.genre_name,
        loaded_at=table.loaded_at,
    )


def dim_genre_dto_to_table(dto: DimGenreDto) -> DimGenreTable:
    """Convert a ``DimGenreDto`` to a ``DimGenreTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = dim_genre_dto_to_table(dto)
    """
    return DimGenreTable(
        genre_id=dto.genre_id,
        genre_name=dto.genre_name,
        loaded_at=dto.loaded_at,
    )


def dim_director_table_to_dto(table: DimDirectorTable) -> DimDirectorDto:
    """Convert a ``DimDirectorTable`` instance to a ``DimDirectorDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = dim_director_table_to_dto(table)
    """
    return DimDirectorDto(
        director_id=table.director_id,
        director_name=table.director_name,
        loaded_at=table.loaded_at,
    )


def dim_director_dto_to_table(dto: DimDirectorDto) -> DimDirectorTable:
    """Convert a ``DimDirectorDto`` to a ``DimDirectorTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = dim_director_dto_to_table(dto)
    """
    return DimDirectorTable(
        director_id=dto.director_id,
        director_name=dto.director_name,
        loaded_at=dto.loaded_at,
    )


def dim_rated_table_to_dto(table: DimRatedTable) -> DimRatedDto:
    """Convert a ``DimRatedTable`` instance to a ``DimRatedDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = dim_rated_table_to_dto(table)
    """
    return DimRatedDto(
        rated_id=table.rated_id,
        rating_code=table.rating_code,
        rating_description=table.rating_description,
        loaded_at=table.loaded_at,
    )


def dim_rated_dto_to_table(dto: DimRatedDto) -> DimRatedTable:
    """Convert a ``DimRatedDto`` to a ``DimRatedTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = dim_rated_dto_to_table(dto)
    """
    return DimRatedTable(
        rated_id=dto.rated_id,
        rating_code=dto.rating_code,
        rating_description=dto.rating_description,
        loaded_at=dto.loaded_at,
    )


def bridge_movie_genre_table_to_dto(table: BridgeMovieGenreTable) -> BridgeMovieGenreDto:
    """Convert a ``BridgeMovieGenreTable`` instance to a ``BridgeMovieGenreDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = bridge_movie_genre_table_to_dto(table)
    """
    return BridgeMovieGenreDto(
        movie_id=table.movie_id,
        genre_id=table.genre_id,
        loaded_at=table.loaded_at,
    )


def bridge_movie_genre_dto_to_table(dto: BridgeMovieGenreDto) -> BridgeMovieGenreTable:
    """Convert a ``BridgeMovieGenreDto`` to a ``BridgeMovieGenreTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = bridge_movie_genre_dto_to_table(dto)
    """
    return BridgeMovieGenreTable(
        movie_id=dto.movie_id,
        genre_id=dto.genre_id,
        loaded_at=dto.loaded_at,
    )


def bridge_movie_director_table_to_dto(table: BridgeMovieDirectorTable) -> BridgeMovieDirectorDto:
    """Convert a ``BridgeMovieDirectorTable`` instance to a ``BridgeMovieDirectorDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = bridge_movie_director_table_to_dto(table)
    """
    return BridgeMovieDirectorDto(
        movie_id=table.movie_id,
        director_id=table.director_id,
        loaded_at=table.loaded_at,
    )


def bridge_movie_director_dto_to_table(dto: BridgeMovieDirectorDto) -> BridgeMovieDirectorTable:
    """Convert a ``BridgeMovieDirectorDto`` to a ``BridgeMovieDirectorTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = bridge_movie_director_dto_to_table(dto)
    """
    return BridgeMovieDirectorTable(
        movie_id=dto.movie_id,
        director_id=dto.director_id,
        loaded_at=dto.loaded_at,
    )


def fact_revenue_table_to_dto(table: FactRevenueTable) -> FactRevenueDto:
    """Convert a ``FactRevenueTable`` instance to a ``FactRevenueDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = fact_revenue_table_to_dto(table)
    """
    return FactRevenueDto(
        revenue_id=table.revenue_id,
        source_row_id=table.source_row_id,
        movie_id=table.movie_id,
        date_id=table.date_id,
        distributor_id=table.distributor_id,
        revenue=table.revenue,
        theaters=table.theaters,
        loaded_at=table.loaded_at,
    )


def fact_revenue_dto_to_table(dto: FactRevenueDto) -> FactRevenueTable:
    """Convert a ``FactRevenueDto`` to a ``FactRevenueTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = fact_revenue_dto_to_table(dto)
    """
    return FactRevenueTable(
        revenue_id=dto.revenue_id,
        source_row_id=dto.source_row_id,
        movie_id=dto.movie_id,
        date_id=dto.date_id,
        distributor_id=dto.distributor_id,
        revenue=dto.revenue,
        theaters=dto.theaters,
        loaded_at=dto.loaded_at,
    )


def fact_movie_rating_table_to_dto(table: FactMovieRatingTable) -> FactMovieRatingDto:
    """Convert a ``FactMovieRatingTable`` instance to a ``FactMovieRatingDto``.

    Args:
        table: SQLModel table instance from the database.

    Returns:
        A frozen DTO with the same field values.

    Example:
        dto = fact_movie_rating_table_to_dto(table)
    """
    return FactMovieRatingDto(
        rating_id=table.rating_id,
        movie_id=table.movie_id,
        imdb_rating=table.imdb_rating,
        imdb_votes=table.imdb_votes,
        valid_from=table.valid_from,
        valid_to=table.valid_to,
        is_current=table.is_current,
        loaded_at=table.loaded_at,
    )


def fact_movie_rating_dto_to_table(dto: FactMovieRatingDto) -> FactMovieRatingTable:
    """Convert a ``FactMovieRatingDto`` to a ``FactMovieRatingTable`` instance.

    Args:
        dto: Frozen DTO to convert.

    Returns:
        A SQLModel table instance ready for insert or update.

    Example:
        table = fact_movie_rating_dto_to_table(dto)
    """
    return FactMovieRatingTable(
        rating_id=dto.rating_id,
        movie_id=dto.movie_id,
        imdb_rating=dto.imdb_rating,
        imdb_votes=dto.imdb_votes,
        valid_from=dto.valid_from,
        valid_to=dto.valid_to,
        is_current=dto.is_current,
        loaded_at=dto.loaded_at,
    )
