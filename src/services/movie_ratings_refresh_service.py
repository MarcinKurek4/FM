"""Service for refreshing IMDb ratings from OMDb into ``fact_movie_rating``.

Loads every movie from ``dim_movie``, fetches current ``imdbRating`` and
``imdbVotes`` from the OMDb API, and inserts SCD Type 2 snapshots only when
values differ from the current row.

Usage::

    service = MovieRatingsRefreshService(
        dim_movie_repo=movie_repo,
        fact_rating_repo=rating_repo,
        omdb_client=omdb_client,
    )
    result = await service.run()
"""

import asyncio
import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from loguru import logger

from src.interfaces.dim_movie_repository_protocol import DimMovieRepositoryProtocol
from src.interfaces.fact_movie_rating_repository_protocol import (
    FactMovieRatingRepositoryProtocol,
)
from src.interfaces.omdb_client_protocol import OmdbClientProtocol
from src.models.dwh import DimMovieDto, FactMovieRatingDto
from src.models.exceptions import OmdbApiError
from src.models.omdb import OMDB_RATE_LIMIT_ERROR_REASON, OmdbMovieResponse, OmdbTitleFetchOutcome
from src.utils.timing import log_execution_time

_REQUEST_DELAY_SECONDS: float = 0.1
_HTTP_STATUS_UNAUTHORIZED: int = 401


@dataclass(frozen=True, slots=True)
class MovieRatingsRefreshResult:
    """Summary of a bulk OMDb ratings refresh run.

    Attributes:
        total_movies: Number of movies loaded from ``dim_movie``.
        omdb_calls_made: Number of OMDb HTTP lookups performed.
        ratings_inserted: New ``fact_movie_rating`` snapshots inserted.
        ratings_unchanged: Movies whose fetched rating matched the current row.
        omdb_not_found: Movies where OMDb returned no match.
        omdb_errors: Non-fatal per-movie failures (request/validation errors).
        stopped_due_to_rate_limit: ``True`` when the OMDb daily quota was hit
            before every movie was processed.
        duration_ms: Wall-clock duration in milliseconds.
    """

    total_movies: int
    omdb_calls_made: int
    ratings_inserted: int
    ratings_unchanged: int
    omdb_not_found: int
    omdb_errors: int
    stopped_due_to_rate_limit: bool
    duration_ms: float = 0.0


class MovieRatingsRefreshService:
    """Refresh IMDb ratings for all movies in the DWH.

    Attributes:
        _dim_movie_repo: Movie dimension repository.
        _fact_rating_repo: Rating fact repository (SCD Type 2).
        _omdb_client: OMDb API client.
        _request_delay_seconds: Pause between consecutive API calls.

    Example:
        service = MovieRatingsRefreshService(
            dim_movie_repo=movie_repo,
            fact_rating_repo=rating_repo,
            omdb_client=omdb_client,
        )
        result = await service.run()
    """

    __slots__ = (
        "_dim_movie_repo",
        "_fact_rating_repo",
        "_omdb_client",
        "_request_delay_seconds",
    )

    def __init__(
        self: "MovieRatingsRefreshService",
        dim_movie_repo: DimMovieRepositoryProtocol,
        fact_rating_repo: FactMovieRatingRepositoryProtocol,
        omdb_client: OmdbClientProtocol,
        request_delay_seconds: float = _REQUEST_DELAY_SECONDS,
    ) -> None:
        """Initialise the ratings refresh service.

        Args:
            dim_movie_repo: Repository for ``dim_movie``.
            fact_rating_repo: Repository for ``fact_movie_rating``.
            omdb_client: OMDb client satisfying ``OmdbClientProtocol``.
            request_delay_seconds: Delay between API calls to reduce rate-limit
                pressure on the OMDb free tier.
        """
        self._dim_movie_repo = dim_movie_repo
        self._fact_rating_repo = fact_rating_repo
        self._omdb_client = omdb_client
        self._request_delay_seconds = request_delay_seconds

    @log_execution_time(inject_duration_ms=True)
    async def run(self: "MovieRatingsRefreshService") -> MovieRatingsRefreshResult:
        """Refresh ratings for every movie in ``dim_movie``.

        Returns:
            Aggregate counts for the run. When the OMDb daily quota is
            exhausted, already-fetched ratings are persisted and the result
            reports ``stopped_due_to_rate_limit=True``.

        Raises:
            OmdbApiError: When OMDb signals an invalid or unauthorized API key.
        """
        logger.info("Starting movie ratings refresh from OMDb")

        movies = await self._dim_movie_repo.list_all_movies()
        now = _naive_utc_now()

        omdb_calls = 0
        ratings_inserted = 0
        ratings_unchanged = 0
        omdb_not_found = 0
        omdb_errors = 0
        stopped_due_to_rate_limit = False

        for index, movie in enumerate(movies):
            if stopped_due_to_rate_limit:
                break

            if movie.movie_id is None:
                omdb_errors += 1
                logger.warning(
                    "Skipping movie without surrogate key",
                    extra={"imdb_id": movie.imdb_id, "title": movie.title},
                )
                continue

            outcome = await self._fetch_omdb(movie)
            omdb_calls += 1

            if outcome.error_reason == OMDB_RATE_LIMIT_ERROR_REASON:
                stopped_due_to_rate_limit = True
                logger.warning(
                    "OMDb rate limit reached; stopping ratings refresh with partial results",
                    extra={
                        "processed_movies": omdb_calls,
                        "total_movies": len(movies),
                        "error_message": outcome.error_message,
                    },
                )
                break

            _raise_on_unauthorized_omdb_error(outcome)

            if outcome.movie is None or outcome.movie.imdb_rating is None:
                if outcome.error_reason == "not_found":
                    omdb_not_found += 1
                else:
                    omdb_errors += 1
                logger.warning(
                    "OMDb rating unavailable for movie",
                    extra={
                        "movie_id": movie.movie_id,
                        "imdb_id": movie.imdb_id,
                        "title": movie.title,
                        "error_reason": outcome.error_reason,
                    },
                )
            else:
                inserted = await _upsert_rating_if_changed(
                    movie_id=movie.movie_id,
                    omdb_movie=outcome.movie,
                    fact_rating_repo=self._fact_rating_repo,
                    now=now,
                )
                if inserted:
                    ratings_inserted += 1
                else:
                    ratings_unchanged += 1

            if index < len(movies) - 1 and self._request_delay_seconds > 0:
                await asyncio.sleep(self._request_delay_seconds)

        result = MovieRatingsRefreshResult(
            total_movies=len(movies),
            omdb_calls_made=omdb_calls,
            ratings_inserted=ratings_inserted,
            ratings_unchanged=ratings_unchanged,
            omdb_not_found=omdb_not_found,
            omdb_errors=omdb_errors,
            stopped_due_to_rate_limit=stopped_due_to_rate_limit,
        )
        logger.info(
            "Movie ratings refresh finished",
            extra={
                "total_movies": result.total_movies,
                "omdb_calls_made": result.omdb_calls_made,
                "ratings_inserted": result.ratings_inserted,
                "ratings_unchanged": result.ratings_unchanged,
                "omdb_not_found": result.omdb_not_found,
                "omdb_errors": result.omdb_errors,
                "stopped_due_to_rate_limit": result.stopped_due_to_rate_limit,
            },
        )
        return result

    async def _fetch_omdb(self: "MovieRatingsRefreshService", movie: DimMovieDto) -> OmdbTitleFetchOutcome:
        """Call OMDb using ``imdb_id`` when available, otherwise ``title``.

        Args:
            movie: Movie dimension row to look up.

        Returns:
            Structured OMDb fetch outcome.
        """
        if movie.imdb_id and movie.imdb_id.strip():
            return await self._omdb_client.fetch_by_imdb_id_detailed(movie.imdb_id.strip())
        return await self._omdb_client.fetch_by_title_detailed(movie.title)


def _raise_on_unauthorized_omdb_error(outcome: OmdbTitleFetchOutcome) -> None:
    """Raise ``OmdbApiError`` when the outcome signals an invalid API key.

    Args:
        outcome: OMDb fetch outcome for a single movie.

    Raises:
        OmdbApiError: On unauthorized responses that are not rate-limit errors.
    """
    if outcome.error_reason == "http_error":
        error_msg = outcome.error_message or ""
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            raise OmdbApiError(
                status_code=_HTTP_STATUS_UNAUTHORIZED,
                message=error_msg or "OMDb API key is invalid or unauthorized.",
            )


async def _upsert_rating_if_changed(
    movie_id: int,
    omdb_movie: OmdbMovieResponse,
    fact_rating_repo: FactMovieRatingRepositoryProtocol,
    now: datetime.datetime,
) -> bool:
    """Insert a new rating snapshot when values differ from the current row.

    Args:
        movie_id: Surrogate key of the movie.
        omdb_movie: Validated OMDb response containing rating fields.
        fact_rating_repo: Rating fact repository.
        now: Timestamp for ``valid_from`` and ``loaded_at``.

    Returns:
        ``True`` when a new row was inserted, ``False`` when unchanged.
    """
    new_rating = _decimal_or_none(omdb_movie.imdb_rating)
    new_votes = omdb_movie.imdb_votes

    current = await fact_rating_repo.get_current_rating(movie_id)
    if current is not None and _ratings_are_equal(current, new_rating, new_votes):
        return False

    dto = FactMovieRatingDto(
        rating_id=None,
        movie_id=movie_id,
        imdb_rating=new_rating,
        imdb_votes=new_votes,
        valid_from=now,
        valid_to=None,
        is_current=True,
        loaded_at=now,
    )
    await fact_rating_repo.insert_new_rating(dto)
    return True


def _decimal_or_none(value: float | None) -> Decimal | None:
    """Convert a float to ``Decimal`` with one decimal place.

    Args:
        value: IMDb rating as float, or ``None``.

    Returns:
        Quantized ``Decimal``, or ``None``.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.1"))
    except InvalidOperation:
        return None


def _ratings_are_equal(
    current: FactMovieRatingDto,
    new_rating: Decimal | None,
    new_votes: int | None,
) -> bool:
    """Return ``True`` when rating and vote counts match the current row.

    Args:
        current: Active rating snapshot from the database.
        new_rating: Freshly fetched IMDb rating.
        new_votes: Freshly fetched vote count.

    Returns:
        ``True`` when both values are identical to ``current``.
    """
    current_rating = current.imdb_rating
    if current_rating is not None:
        current_rating = current_rating.quantize(Decimal("0.1"))
    if new_rating is not None:
        new_rating = new_rating.quantize(Decimal("0.1"))
    return current_rating == new_rating and current.imdb_votes == new_votes


def _naive_utc_now() -> datetime.datetime:
    """Return the current UTC time as a naive datetime.

    Returns:
        Current UTC time with ``tzinfo`` stripped.
    """
    return datetime.datetime.now(tz=datetime.UTC).replace(tzinfo=None)
