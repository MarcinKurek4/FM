"""Unit tests for MovieRatingsRefreshService."""

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.dwh import DimMovieDto, FactMovieRatingDto
from src.models.exceptions import OmdbApiError
from src.models.omdb import OMDB_RATE_LIMIT_ERROR_REASON, OmdbMovieResponse, OmdbTitleFetchOutcome
from src.services.movie_ratings_refresh_service import MovieRatingsRefreshService

_NOW: datetime.datetime = datetime.datetime(2026, 6, 5, 12, 0, 0)


def _movie_dto(
    movie_id: int = 1,
    title: str = "Inception",
    imdb_id: str = "tt1375666",
) -> DimMovieDto:
    return DimMovieDto(
        movie_id=movie_id,
        imdb_id=imdb_id,
        title=title,
        release_year=2010,
        rated_id=None,
        runtime_min=148,
        plot=None,
        awards=None,
        box_office_omdb=None,
        omdb_fetched_at=_NOW,
        loaded_at=_NOW,
    )


def _omdb_response(rating: float = 8.8, votes: int = 2_500_000) -> OmdbMovieResponse:
    return OmdbMovieResponse.model_validate(
        {
            "Title": "Inception",
            "Year": "2010",
            "Rated": "PG-13",
            "Genre": "Action",
            "Director": "Christopher Nolan",
            "Actors": "N/A",
            "Plot": "N/A",
            "Awards": "N/A",
            "imdbRating": str(rating),
            "imdbVotes": f"{votes:,}",
            "imdbID": "tt1375666",
            "Runtime": "148 min",
            "BoxOffice": "N/A",
            "Response": "True",
        }
    )


def _build_service(
    *,
    movies: list[DimMovieDto] | None = None,
    omdb_outcomes: list[OmdbTitleFetchOutcome] | None = None,
    current_rating: FactMovieRatingDto | None = None,
) -> tuple[MovieRatingsRefreshService, dict[str, Any]]:
    dim_movie_repo = AsyncMock()
    dim_movie_repo.list_all_movies.return_value = movies or [_movie_dto()]

    fact_rating_repo = AsyncMock()
    fact_rating_repo.get_current_rating.return_value = current_rating
    fact_rating_repo.insert_new_rating.return_value = MagicMock()

    omdb_client = AsyncMock()
    if omdb_outcomes is not None:
        omdb_client.fetch_by_imdb_id_detailed.side_effect = omdb_outcomes
    else:
        omdb_client.fetch_by_imdb_id_detailed.return_value = OmdbTitleFetchOutcome(
            request_title="tt1375666",
            movie=_omdb_response(),
        )

    service = MovieRatingsRefreshService(
        dim_movie_repo=dim_movie_repo,
        fact_rating_repo=fact_rating_repo,
        omdb_client=omdb_client,
        request_delay_seconds=0,
    )
    return service, {
        "dim_movie_repo": dim_movie_repo,
        "fact_rating_repo": fact_rating_repo,
        "omdb_client": omdb_client,
    }


@pytest.mark.asyncio
async def test_run_inserts_rating_when_no_current_row() -> None:
    service, mocks = _build_service(current_rating=None)

    result = await service.run()

    assert result.ratings_inserted == 1
    assert result.ratings_unchanged == 0
    assert result.omdb_calls_made == 1
    mocks["fact_rating_repo"].insert_new_rating.assert_called_once()


@pytest.mark.asyncio
async def test_run_skips_insert_when_rating_unchanged() -> None:
    current = FactMovieRatingDto(
        rating_id=10,
        movie_id=1,
        imdb_rating=Decimal("8.8"),
        imdb_votes=2_500_000,
        valid_from=_NOW,
        valid_to=None,
        is_current=True,
        loaded_at=_NOW,
    )
    service, mocks = _build_service(current_rating=current)

    result = await service.run()

    assert result.ratings_inserted == 0
    assert result.ratings_unchanged == 1
    mocks["fact_rating_repo"].insert_new_rating.assert_not_called()


@pytest.mark.asyncio
async def test_run_rate_limit_stops_with_partial_results() -> None:
    movies = [_movie_dto(movie_id=1, imdb_id="tt1"), _movie_dto(movie_id=2, imdb_id="tt2")]
    outcomes = [
        OmdbTitleFetchOutcome(request_title="tt1", movie=_omdb_response(7.0, 100)),
        OmdbTitleFetchOutcome(
            request_title="tt2",
            movie=None,
            error_reason=OMDB_RATE_LIMIT_ERROR_REASON,
            error_message="Daily request limit reached!",
        ),
    ]
    service, mocks = _build_service(movies=movies, omdb_outcomes=outcomes)

    result = await service.run()

    assert result.stopped_due_to_rate_limit is True
    assert result.ratings_inserted == 1
    assert result.omdb_calls_made == 2
    mocks["fact_rating_repo"].insert_new_rating.assert_called_once()


@pytest.mark.asyncio
async def test_run_unauthorized_raises_omdb_api_error() -> None:
    outcome = OmdbTitleFetchOutcome(
        request_title="tt1375666",
        movie=None,
        error_reason="http_error",
        error_message="401 Unauthorized: invalid API key",
    )
    service, _ = _build_service(omdb_outcomes=[outcome])

    with pytest.raises(OmdbApiError) as exc_info:
        await service.run()

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_run_omdb_not_found_increments_counter() -> None:
    outcome = OmdbTitleFetchOutcome(
        request_title="tt1375666",
        movie=None,
        error_reason="not_found",
        error_message="Movie not found!",
    )
    service, mocks = _build_service(omdb_outcomes=[outcome])

    result = await service.run()

    assert result.omdb_not_found == 1
    assert result.ratings_inserted == 0
    mocks["fact_rating_repo"].insert_new_rating.assert_not_called()


@pytest.mark.asyncio
async def test_run_multiple_movies_aggregates_counts() -> None:
    movies = [_movie_dto(movie_id=1, imdb_id="tt1"), _movie_dto(movie_id=2, imdb_id="tt2")]
    outcomes = [
        OmdbTitleFetchOutcome(request_title="tt1", movie=_omdb_response(7.0, 100)),
        OmdbTitleFetchOutcome(request_title="tt2", movie=_omdb_response(9.0, 200)),
    ]
    service, mocks = _build_service(movies=movies, omdb_outcomes=outcomes)

    result = await service.run()

    assert result.total_movies == 2
    assert result.omdb_calls_made == 2
    assert result.ratings_inserted == 2
    assert mocks["fact_rating_repo"].insert_new_rating.call_count == 2
