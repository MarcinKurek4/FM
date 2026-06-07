"""Integration tests for FactMovieRatingRepository with SCD Type 2.

This module verifies that the repository correctly implements Slowly
Changing Dimension Type 2 logic for tracking rating changes over time.
"""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dwh import DimMovieDto, FactMovieRatingDto
from src.repositories.dim_movie_repository import DimMovieRepository
from src.repositories.fact_movie_rating_repository import FactMovieRatingRepository


@pytest.mark.asyncio
async def test_get_current_rating_returns_none_when_not_found(
    async_session: AsyncSession,
) -> None:
    """Return None when no rating exists for the given movie."""
    repo = FactMovieRatingRepository(async_session)

    result = await repo.get_current_rating(movie_id=999)

    assert result is None


@pytest.mark.asyncio
async def test_insert_new_rating_creates_first_record(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
    fact_movie_rating_dto_factory: callable,
) -> None:
    """Insert the first rating record for a movie."""
    movie_repo = DimMovieRepository(async_session)
    rating_repo = FactMovieRatingRepository(async_session)

    movie = await movie_repo.upsert(dim_movie_dto_factory(imdb_id="tt1234567"))
    await async_session.commit()

    rating = fact_movie_rating_dto_factory(movie_id=movie.movie_id)
    result = await rating_repo.insert_new_rating(rating)
    await async_session.commit()

    assert result.rating_id is not None
    assert result.is_current is True
    assert result.valid_to is None

    current = await rating_repo.get_current_rating(movie.movie_id)
    assert current is not None
    assert current.rating_id == result.rating_id


@pytest.mark.asyncio
async def test_insert_new_rating_closes_previous_record(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
    fact_movie_rating_dto_factory: callable,
) -> None:
    """Close the previous current record when inserting a new rating (SCD Type 2)."""
    movie_repo = DimMovieRepository(async_session)
    rating_repo = FactMovieRatingRepository(async_session)

    movie = await movie_repo.upsert(dim_movie_dto_factory(imdb_id="tt1234567"))
    await async_session.commit()

    from decimal import Decimal

    first_rating = fact_movie_rating_dto_factory(
        movie_id=movie.movie_id,
        imdb_rating=Decimal("8.5"),
        valid_from=datetime.datetime(2026, 6, 1, 0, 0, 0),
    )
    first_result = await rating_repo.insert_new_rating(first_rating)
    await async_session.commit()

    second_rating = fact_movie_rating_dto_factory(
        movie_id=movie.movie_id,
        imdb_rating=Decimal("8.8"),
        valid_from=datetime.datetime(2026, 6, 3, 0, 0, 0),
    )
    second_result = await rating_repo.insert_new_rating(second_rating)
    await async_session.commit()

    current = await rating_repo.get_current_rating(movie.movie_id)
    assert current is not None
    assert current.rating_id == second_result.rating_id
    assert current.imdb_rating == Decimal("8.8")
    assert current.is_current is True
    assert current.valid_to is None

    history = await rating_repo.get_rating_history(movie.movie_id)
    assert len(history) == 2
    assert history[0].rating_id == first_result.rating_id
    assert history[0].is_current is False
    assert history[0].valid_to == datetime.datetime(2026, 6, 3, 0, 0, 0)
    assert history[1].rating_id == second_result.rating_id
    assert history[1].is_current is True


@pytest.mark.asyncio
async def test_get_rating_history_returns_ordered_list(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
    fact_movie_rating_dto_factory: callable,
) -> None:
    """Return rating history ordered by valid_from ascending."""
    movie_repo = DimMovieRepository(async_session)
    rating_repo = FactMovieRatingRepository(async_session)

    movie = await movie_repo.upsert(dim_movie_dto_factory(imdb_id="tt1234567"))
    await async_session.commit()

    from decimal import Decimal

    for i, rating_value in enumerate([Decimal("8.0"), Decimal("8.3"), Decimal("8.7")]):
        rating = fact_movie_rating_dto_factory(
            movie_id=movie.movie_id,
            imdb_rating=rating_value,
            valid_from=datetime.datetime(2026, 6, 1 + i, 0, 0, 0),
        )
        await rating_repo.insert_new_rating(rating)
        await async_session.commit()

    history = await rating_repo.get_rating_history(movie.movie_id)

    assert len(history) == 3
    assert history[0].imdb_rating == Decimal("8.0")
    assert history[0].is_current is False
    assert history[1].imdb_rating == Decimal("8.3")
    assert history[1].is_current is False
    assert history[2].imdb_rating == Decimal("8.7")
    assert history[2].is_current is True
