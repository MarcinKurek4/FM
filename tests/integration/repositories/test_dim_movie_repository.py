"""Integration tests for DimMovieRepository.

This module verifies that the repository correctly persists and retrieves
movie dimension records using a real (in-memory) database.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dwh import DimMovieDto
from src.repositories.dim_movie_repository import DimMovieRepository


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_not_found(
    async_session: AsyncSession,
) -> None:
    """Return None when no movie with the given ID exists."""
    repo = DimMovieRepository(async_session)

    result = await repo.get_by_id(999)

    assert result is None


@pytest.mark.asyncio
async def test_get_by_natural_key_returns_none_when_not_found(
    async_session: AsyncSession,
) -> None:
    """Return None when no movie with the given IMDb ID exists."""
    repo = DimMovieRepository(async_session)

    result = await repo.get_by_natural_key("tt9999999")

    assert result is None


@pytest.mark.asyncio
async def test_upsert_inserts_on_first_call(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
) -> None:
    """Insert a new movie record on first upsert call."""
    repo = DimMovieRepository(async_session)
    dto = dim_movie_dto_factory(imdb_id="tt1234567")

    result = await repo.upsert(dto)
    await async_session.commit()

    assert result.movie_id is not None
    assert result.imdb_id == "tt1234567"

    fetched = await repo.get_by_natural_key("tt1234567")
    assert fetched is not None
    assert fetched.imdb_id == "tt1234567"


@pytest.mark.asyncio
async def test_upsert_updates_on_second_call(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
) -> None:
    """Update an existing movie record on second upsert call (idempotency)."""
    repo = DimMovieRepository(async_session)
    original_dto = dim_movie_dto_factory(imdb_id="tt1234567", title="Original Title")

    first_result = await repo.upsert(original_dto)
    await async_session.commit()

    updated_dto = dim_movie_dto_factory(
        imdb_id="tt1234567",
        title="Updated Title",
        movie_id=first_result.movie_id,
    )
    second_result = await repo.upsert(updated_dto)
    await async_session.commit()

    assert second_result.movie_id == first_result.movie_id
    assert second_result.title == "Updated Title"

    fetched = await repo.get_by_natural_key("tt1234567")
    assert fetched is not None
    assert fetched.title == "Updated Title"


@pytest.mark.asyncio
async def test_bulk_upsert_handles_empty_sequence(
    async_session: AsyncSession,
) -> None:
    """Return empty list when upserting an empty sequence."""
    repo = DimMovieRepository(async_session)

    result = await repo.bulk_upsert([])

    assert result == []


@pytest.mark.asyncio
async def test_bulk_upsert_deduplicates_by_natural_key(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
) -> None:
    """Deduplicate movies by IMDb ID during bulk upsert."""
    repo = DimMovieRepository(async_session)

    dto1 = dim_movie_dto_factory(imdb_id="tt1111111", title="First")
    dto2 = dim_movie_dto_factory(imdb_id="tt1111111", title="Second")

    results = await repo.bulk_upsert([dto1, dto2])
    await async_session.commit()

    assert len(results) == 2
    assert results[0].movie_id == results[1].movie_id
    assert results[1].title == "Second"
