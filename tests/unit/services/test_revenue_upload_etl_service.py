"""Unit tests for RevenueUploadEtlService.

Tests cover all six scenarios defined in ADR-0004:

1. All CSV titles already in ``dim_movie`` — no OMDb call made.
2. New title, OMDb returns a valid record — movie enriched and fact inserted.
3. New title, OMDb returns HTTP 429 (rate limit) — ``OmdbApiError`` raised.
4. New title, OMDb returns HTTP 401 (unauthorized) — ``OmdbApiError`` raised.
5. New title, OMDb returns no match — counted in ``titles_not_found_in_omdb``.
6. Duplicate ``source_row_id`` in CSV — counted in ``facts_skipped_duplicate``.

No real database or HTTP connections are made in any test.
"""

import datetime
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.dwh import (
    DimDateDto,
    DimDirectorDto,
    DimDistributorDto,
    DimGenreDto,
    DimMovieDto,
    DimRatedDto,
    FactRevenueDto,
)
from src.models.exceptions import OmdbApiError
from src.models.omdb import OMDB_RATE_LIMIT_ERROR_REASON, OmdbMovieResponse, OmdbTitleFetchOutcome
from src.services.revenue_upload_etl_service import RevenueUploadEtlService

_NOW: datetime.datetime = datetime.datetime(2026, 6, 5, 12, 0, 0)
_DATE: datetime.date = datetime.date(2026, 6, 5)
_DATE_ID: int = 20260605


def _make_omdb_response(title: str = "New Movie", imdb_id: str = "tt9999999") -> OmdbMovieResponse:
    """Build a minimal valid ``OmdbMovieResponse`` for testing.

    Args:
        title: Movie title.
        imdb_id: IMDb identifier.

    Returns:
        A populated ``OmdbMovieResponse`` instance.
    """
    return OmdbMovieResponse.model_validate(
        {
            "Title": title,
            "Year": "2024",
            "Rated": "PG-13",
            "Genre": "Action",
            "Director": "Test Director",
            "Actors": "N/A",
            "Plot": "A test plot.",
            "Awards": "N/A",
            "imdbRating": "7.5",
            "imdbVotes": "100,000",
            "imdbID": imdb_id,
            "Runtime": "120 min",
            "BoxOffice": "$10,000,000",
            "Response": "True",
        }
    )


def _csv_bytes(title: str, row_id: uuid.UUID | None = None) -> bytes:
    """Build minimal CSV bytes with a single revenue row.

    Args:
        title: Movie title to include in the CSV.
        row_id: Optional UUID for the row. Generated if not provided.

    Returns:
        CSV content as bytes.
    """
    rid = row_id or uuid.uuid4()
    return (
        f"id,date,title,revenue,theaters,distributor\n"
        f"{rid},{_DATE.isoformat()},{title},1000000,500,Distributor Inc\n"
    ).encode("utf-8")


def _make_dim_date_dto() -> DimDateDto:
    return DimDateDto(
        date_id=_DATE_ID,
        date=_DATE,
        year=2026,
        quarter=2,
        month=6,
        month_name="June",
        day=5,
        day_of_week=5,
        day_of_week_name="Friday",
        week_number=23,
        is_weekend=False,
        is_holiday=False,
    )


def _make_dim_distributor_dto(name: str = "Distributor Inc") -> DimDistributorDto:
    return DimDistributorDto(distributor_id=1, distributor_name=name, loaded_at=_NOW)


def _build_service(
    *,
    title_map: dict[str, int] | None = None,
    bulk_insert_return: int = 1,
    omdb_outcome: OmdbTitleFetchOutcome | None = None,
) -> tuple[RevenueUploadEtlService, dict[str, Any]]:
    """Construct a ``RevenueUploadEtlService`` with all mocked dependencies.

    Args:
        title_map: Mapping of uppercase title to ``movie_id``. Defaults to
            empty, meaning all titles are treated as unknown.
        bulk_insert_return: Number of rows the mocked fact repository reports
            as inserted.
        omdb_outcome: The ``OmdbTitleFetchOutcome`` the mocked OMDb client
            returns from ``fetch_by_title_detailed``.

    Returns:
        A tuple of ``(service, mocks_dict)`` where ``mocks_dict`` provides
        direct access to the individual mock objects for assertion.
    """
    dim_distributor_repo = AsyncMock()
    dim_distributor_repo.upsert.return_value = _make_dim_distributor_dto()

    dim_date_repo = AsyncMock()
    dim_date_repo.get_by_id.return_value = _make_dim_date_dto()

    dim_movie_repo = AsyncMock()
    dim_movie_repo.bulk_load_title_map.return_value = title_map or {}
    dim_movie_repo.upsert.return_value = DimMovieDto(
        movie_id=42,
        imdb_id="tt9999999",
        title="New Movie",
        release_year=2024,
        rated_id=None,
        runtime_min=120,
        plot="A test plot.",
        awards=None,
        box_office_omdb=Decimal("10000000"),
        omdb_fetched_at=_NOW,
        loaded_at=_NOW,
    )

    fact_revenue_repo = AsyncMock()
    fact_revenue_repo.bulk_insert.return_value = bulk_insert_return

    dim_rated_repo = AsyncMock()
    dim_rated_repo.upsert.return_value = DimRatedDto(
        rated_id=1, rating_code="PG-13", rating_description="Parents Strongly Cautioned", loaded_at=_NOW
    )

    dim_genre_repo = AsyncMock()
    dim_genre_repo.upsert.return_value = DimGenreDto(genre_id=1, genre_name="Action", loaded_at=_NOW)

    dim_director_repo = AsyncMock()
    dim_director_repo.upsert.return_value = DimDirectorDto(
        director_id=1, director_name="Test Director", loaded_at=_NOW
    )

    bridge_genre_repo = AsyncMock()
    bridge_genre_repo.bulk_upsert.return_value = ([], 1)

    bridge_director_repo = AsyncMock()
    bridge_director_repo.bulk_upsert.return_value = ([], 1)

    fact_rating_repo = AsyncMock()
    fact_rating_repo.get_current_rating.return_value = None
    fact_rating_repo.insert_new_rating.return_value = MagicMock()

    omdb_client = AsyncMock()
    if omdb_outcome is not None:
        omdb_client.fetch_by_title_detailed.return_value = omdb_outcome

    service = RevenueUploadEtlService(
        dim_distributor_repo=dim_distributor_repo,
        dim_date_repo=dim_date_repo,
        dim_movie_repo=dim_movie_repo,
        fact_revenue_repo=fact_revenue_repo,
        dim_rated_repo=dim_rated_repo,
        dim_genre_repo=dim_genre_repo,
        dim_director_repo=dim_director_repo,
        bridge_genre_repo=bridge_genre_repo,
        bridge_director_repo=bridge_director_repo,
        fact_rating_repo=fact_rating_repo,
        omdb_client=omdb_client,
    )

    mocks: dict[str, Any] = {
        "dim_distributor_repo": dim_distributor_repo,
        "dim_date_repo": dim_date_repo,
        "dim_movie_repo": dim_movie_repo,
        "fact_revenue_repo": fact_revenue_repo,
        "dim_rated_repo": dim_rated_repo,
        "dim_genre_repo": dim_genre_repo,
        "dim_director_repo": dim_director_repo,
        "bridge_genre_repo": bridge_genre_repo,
        "bridge_director_repo": bridge_director_repo,
        "fact_rating_repo": fact_rating_repo,
        "omdb_client": omdb_client,
    }

    return service, mocks


@pytest.mark.asyncio
async def test_run_all_titles_known_no_omdb_call() -> None:
    """All CSV titles already present in dim_movie; no OMDb call is made."""
    title = "Inception"
    csv = _csv_bytes(title)
    service, mocks = _build_service(
        title_map={"INCEPTION": 1},
        bulk_insert_return=1,
    )

    result = await service.run(csv)

    mocks["omdb_client"].fetch_by_title_detailed.assert_not_called()
    assert result.movies_enriched_from_omdb == 0
    assert result.titles_not_found_in_omdb == 0
    assert result.facts_inserted == 1
    assert result.facts_skipped_duplicate == 0
    assert result.rows_error_movie_not_found == 0


@pytest.mark.asyncio
async def test_run_new_title_omdb_success_enriches_movie_and_inserts_fact() -> None:
    """New title fetched from OMDb; movie persisted and fact inserted."""
    title = "New Movie"
    csv = _csv_bytes(title)
    movie_response = _make_omdb_response(title=title)
    outcome = OmdbTitleFetchOutcome(
        request_title=title,
        movie=movie_response,
        error_reason=None,
    )
    service, mocks = _build_service(
        title_map={},
        bulk_insert_return=1,
        omdb_outcome=outcome,
    )

    result = await service.run(csv)

    mocks["omdb_client"].fetch_by_title_detailed.assert_called_once_with(title)
    mocks["dim_movie_repo"].upsert.assert_called_once()
    assert result.movies_enriched_from_omdb == 1
    assert result.titles_not_found_in_omdb == 0
    assert result.facts_inserted == 1
    assert result.rows_error_movie_not_found == 0


@pytest.mark.asyncio
async def test_run_new_title_omdb_rate_limit_raises_omdb_api_error() -> None:
    """OMDb returns rate-limit signal; OmdbApiError is raised with status 429."""
    title = "Rate Limited Movie"
    csv = _csv_bytes(title)
    outcome = OmdbTitleFetchOutcome(
        request_title=title,
        movie=None,
        error_reason=OMDB_RATE_LIMIT_ERROR_REASON,
        error_message="Daily request limit reached!",
    )
    service, _ = _build_service(title_map={}, omdb_outcome=outcome)

    with pytest.raises(OmdbApiError) as exc_info:
        await service.run(csv)

    assert exc_info.value.status_code == 429
    assert "limit" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_run_new_title_omdb_unauthorized_raises_omdb_api_error() -> None:
    """OMDb returns HTTP error with 401 detail; OmdbApiError is raised with status 401."""
    title = "Unauthorized Movie"
    csv = _csv_bytes(title)
    outcome = OmdbTitleFetchOutcome(
        request_title=title,
        movie=None,
        error_reason="http_error",
        error_message="401 Unauthorized: invalid API key",
    )
    service, _ = _build_service(title_map={}, omdb_outcome=outcome)

    with pytest.raises(OmdbApiError) as exc_info:
        await service.run(csv)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_run_new_title_omdb_not_found_counted_in_titles_not_found() -> None:
    """OMDb returns no match; title counted in titles_not_found_in_omdb."""
    title = "Ghost Title"
    csv = _csv_bytes(title)
    outcome = OmdbTitleFetchOutcome(
        request_title=title,
        movie=None,
        error_reason="not_found",
        error_message="Movie not found!",
    )
    service, mocks = _build_service(title_map={}, omdb_outcome=outcome)

    result = await service.run(csv)

    assert result.titles_not_found_in_omdb == 1
    assert result.movies_enriched_from_omdb == 0
    assert result.rows_error_movie_not_found == 1
    assert result.facts_inserted == 0
    mocks["dim_movie_repo"].upsert.assert_not_called()


@pytest.mark.asyncio
async def test_run_duplicate_source_row_id_counted_as_skipped() -> None:
    """Duplicate source_row_id is counted in facts_skipped_duplicate."""
    title = "Known Movie"
    row_id = uuid.uuid4()
    csv = _csv_bytes(title, row_id=row_id)
    service, mocks = _build_service(
        title_map={"KNOWN MOVIE": 1},
        bulk_insert_return=0,
    )

    result = await service.run(csv)

    assert result.facts_inserted == 0
    assert result.facts_skipped_duplicate == 1
    assert result.rows_error_movie_not_found == 0
    mocks["omdb_client"].fetch_by_title_detailed.assert_not_called()
