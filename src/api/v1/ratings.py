"""FastAPI router for bulk IMDb ratings refresh from OMDb.

Exposes::

    GET /api/v1/ratings

Fetches current ratings for all movies in ``dim_movie`` and inserts new
``fact_movie_rating`` rows when values change.
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_async_session, get_http_client
from src.config.settings import get_settings
from src.models.exceptions import OmdbApiError
from src.repositories.dim_movie_repository import DimMovieRepository
from src.repositories.fact_movie_rating_repository import FactMovieRatingRepository
from src.services.movie_ratings_refresh_service import MovieRatingsRefreshService
from src.services.omdb_client import OmdbClient

router: APIRouter = APIRouter(prefix="/api/v1/ratings", tags=["ratings"])


class RatingsRefreshResponseDto(BaseModel):
    """Response body for a successful ratings refresh run.

    Attributes:
        total_movies: Movies loaded from ``dim_movie``.
        omdb_calls_made: OMDb HTTP lookups performed.
        ratings_inserted: New rating snapshots inserted.
        ratings_unchanged: Movies with no rating change.
        omdb_not_found: Movies OMDb could not match.
        omdb_errors: Non-fatal per-movie failures.
        duration_ms: Wall-clock duration in milliseconds.
    """

    total_movies: int
    omdb_calls_made: int
    ratings_inserted: int
    ratings_unchanged: int
    omdb_not_found: int
    omdb_errors: int
    duration_ms: float


@router.get(
    "",
    response_model=RatingsRefreshResponseDto,
    summary="Refresh IMDb ratings for all movies from OMDb",
    description=(
        "Loads every row from ``dim_movie``, fetches current IMDb rating and "
        "vote count from OMDb, and inserts new ``fact_movie_rating`` snapshots "
        "only when values differ (SCD Type 2)."
    ),
)
async def get_ratings(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> RatingsRefreshResponseDto:
    """Refresh ratings for all movies and return aggregate counts.

    Args:
        session: Async database session injected by FastAPI.
        http_client: Shared HTTP client injected by FastAPI.

    Returns:
        Summary counts for the refresh run.

    Raises:
        HTTPException: HTTP 422 on OMDb auth or rate-limit failure.
    """
    logger.info("Ratings refresh request received")

    settings = get_settings()
    omdb_client = OmdbClient(
        api_key=settings.omdb_api_key,
        http_client=http_client,
        base_url=settings.omdb_base_url,
    )

    service = MovieRatingsRefreshService(
        dim_movie_repo=DimMovieRepository(session),
        fact_rating_repo=FactMovieRatingRepository(session),
        omdb_client=omdb_client,
    )

    try:
        result = await service.run()
    except OmdbApiError as exc:
        logger.error(
            "Ratings refresh aborted due to OMDb API error",
            extra={"status_code": exc.status_code, "message": exc.message},
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "omdb_api_error",
                "status_code": exc.status_code,
                "detail": exc.message,
            },
        ) from exc

    logger.info(
        "Ratings refresh completed",
        extra={
            "ratings_inserted": result.ratings_inserted,
            "ratings_unchanged": result.ratings_unchanged,
            "duration_ms": result.duration_ms,
        },
    )

    return RatingsRefreshResponseDto(
        total_movies=result.total_movies,
        omdb_calls_made=result.omdb_calls_made,
        ratings_inserted=result.ratings_inserted,
        ratings_unchanged=result.ratings_unchanged,
        omdb_not_found=result.omdb_not_found,
        omdb_errors=result.omdb_errors,
        duration_ms=result.duration_ms,
    )
