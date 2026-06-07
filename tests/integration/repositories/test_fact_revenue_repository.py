"""Integration tests for FactRevenueRepository.

This module verifies that the repository correctly persists and retrieves
revenue fact records with idempotency guarantees.
"""

import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dwh import DimDateDto, DimDistributorDto, DimMovieDto, FactRevenueDto
from src.repositories.dim_date_repository import DimDateRepository
from src.repositories.dim_distributor_repository import DimDistributorRepository
from src.repositories.dim_movie_repository import DimMovieRepository
from src.repositories.fact_revenue_repository import FactRevenueRepository


@pytest.mark.asyncio
async def test_exists_by_source_row_id_returns_false_when_not_found(
    async_session: AsyncSession,
) -> None:
    """Return False when no fact with the given source_row_id exists."""
    repo = FactRevenueRepository(async_session)

    result = await repo.exists_by_source_row_id(uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_bulk_insert_returns_inserted_count(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
    dim_date_dto_factory: callable,
    dim_distributor_dto_factory: callable,
    fact_revenue_dto_factory: callable,
) -> None:
    """Return the count of inserted records excluding duplicates."""
    movie_repo = DimMovieRepository(async_session)
    date_repo = DimDateRepository(async_session)
    distributor_repo = DimDistributorRepository(async_session)
    fact_repo = FactRevenueRepository(async_session)

    movie = await movie_repo.upsert(dim_movie_dto_factory(imdb_id="tt1234567"))
    date_one = await date_repo.upsert(dim_date_dto_factory(date_id=20040920))
    date_two = await date_repo.upsert(
        dim_date_dto_factory(
            date_id=20040921,
            date=datetime.date(2004, 9, 21),
            day=21,
        )
    )
    distributor = await distributor_repo.upsert(dim_distributor_dto_factory())
    await async_session.commit()

    fact1 = fact_revenue_dto_factory(
        source_row_id=uuid.uuid4(),
        movie_id=movie.movie_id,
        date_id=date_one.date_id,
        distributor_id=distributor.distributor_id,
    )
    fact2 = fact_revenue_dto_factory(
        source_row_id=uuid.uuid4(),
        movie_id=movie.movie_id,
        date_id=date_two.date_id,
        distributor_id=distributor.distributor_id,
    )

    inserted_count = await fact_repo.bulk_insert([fact1, fact2])
    await async_session.commit()

    assert inserted_count == 2


@pytest.mark.asyncio
async def test_bulk_insert_is_idempotent_by_source_row_id(
    async_session: AsyncSession,
    dim_movie_dto_factory: callable,
    dim_date_dto_factory: callable,
    dim_distributor_dto_factory: callable,
    fact_revenue_dto_factory: callable,
) -> None:
    """Skip duplicate records when re-inserting same source_row_id."""
    movie_repo = DimMovieRepository(async_session)
    date_repo = DimDateRepository(async_session)
    distributor_repo = DimDistributorRepository(async_session)
    fact_repo = FactRevenueRepository(async_session)

    movie = await movie_repo.upsert(dim_movie_dto_factory(imdb_id="tt1234567"))
    date = await date_repo.upsert(dim_date_dto_factory(date_id=20040920))
    distributor = await distributor_repo.upsert(dim_distributor_dto_factory())
    await async_session.commit()

    source_id = uuid.uuid4()
    fact = fact_revenue_dto_factory(
        source_row_id=source_id,
        movie_id=movie.movie_id,
        date_id=date.date_id,
        distributor_id=distributor.distributor_id,
    )

    first_insert = await fact_repo.bulk_insert([fact])
    await async_session.commit()
    assert first_insert == 1

    second_insert = await fact_repo.bulk_insert([fact])
    await async_session.commit()
    assert second_insert == 0

    exists = await fact_repo.exists_by_source_row_id(source_id)
    assert exists is True
