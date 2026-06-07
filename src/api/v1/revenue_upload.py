"""FastAPI router for incremental revenue CSV uploads.

Exposes a single endpoint:

    POST /api/v1/revenue/upload

Accepts a multipart CSV file upload, runs the incremental ETL pipeline,
and returns a summary of inserted rows. When the OMDb daily quota is
exhausted, rows that do not require further OMDb enrichment are still loaded.
An invalid API key returns HTTP 422.

Usage::

    from src.api.v1.revenue_upload import router

    app.include_router(router)
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_async_session, get_http_client
from src.config.settings import get_settings
from src.models.exceptions import OmdbApiError
from src.repositories.bridge_movie_director_repository import BridgeMovieDirectorRepository
from src.repositories.bridge_movie_genre_repository import BridgeMovieGenreRepository
from src.repositories.dim_date_repository import DimDateRepository
from src.repositories.dim_director_repository import DimDirectorRepository
from src.repositories.dim_distributor_repository import DimDistributorRepository
from src.repositories.dim_genre_repository import DimGenreRepository
from src.repositories.dim_movie_repository import DimMovieRepository
from src.repositories.dim_rated_repository import DimRatedRepository
from src.repositories.fact_movie_rating_repository import FactMovieRatingRepository
from src.repositories.fact_revenue_repository import FactRevenueRepository
from src.services.omdb_client import OmdbClient
from src.services.revenue_upload_etl_service import RevenueUploadEtlService

router: APIRouter = APIRouter(prefix="/api/v1/revenue", tags=["revenue"])


class RevenueUploadResponseDto(BaseModel):
    """Response body for a successful revenue upload.

    Attributes:
        facts_inserted: Number of new ``fact_revenue`` rows inserted.
        facts_skipped_duplicate: Rows skipped because their ``source_row_id``
            was already present in ``fact_revenue``.
        distributors_upserted: ``dim_distributor`` rows created or updated.
        dates_created: ``dim_date`` rows created on the fly.
        movies_enriched_from_omdb: New movies fetched from OMDb and loaded
            into ``dim_movie`` and related tables.
        titles_not_found_in_omdb: Distinct CSV titles that OMDb could not match.
        rows_error_movie_not_found: CSV rows whose title could not be resolved
            to any ``dim_movie`` record after OMDb lookup.
        stopped_due_to_rate_limit: ``True`` when OMDb enrichment stopped early
            because the daily quota was exhausted.
        duration_ms: Wall-clock duration of the ETL run in milliseconds.
    """

    facts_inserted: int
    facts_skipped_duplicate: int
    distributors_upserted: int
    dates_created: int
    movies_enriched_from_omdb: int
    titles_not_found_in_omdb: int
    rows_error_movie_not_found: int
    stopped_due_to_rate_limit: bool
    duration_ms: float


@router.post(
    "/upload",
    response_model=RevenueUploadResponseDto,
    summary="Upload an incremental revenue CSV file",
    description=(
        "Accepts a multipart CSV file upload in the same format as "
        "``revenues_per_day.csv``. Inserts only new rows into ``fact_revenue``. "
        "Titles absent from ``dim_movie`` are enriched on the fly via the OMDb API."
    ),
)
async def upload_revenue_csv(
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> RevenueUploadResponseDto:
    """Process an uploaded revenue CSV and return ETL summary counts.

    Args:
        file: Multipart CSV file uploaded by the client.
        session: Async database session injected by FastAPI.
        http_client: Shared HTTP client injected by FastAPI.

    Returns:
        A ``RevenueUploadResponseDto`` with row-count summaries.

    Raises:
        HTTPException: HTTP 422 when the OMDb API key is invalid.
        HTTPException: HTTP 400 when the uploaded file cannot be parsed as CSV.
        HTTPException: HTTP 500 on unexpected internal failures.
    """
    logger.info(
        "Revenue upload request received",
        extra={"filename": file.filename, "content_type": file.content_type},
    )

    csv_bytes = await file.read()

    settings = get_settings()
    omdb_client = OmdbClient(
        api_key=settings.omdb_api_key,
        http_client=http_client,
        base_url=settings.omdb_base_url,
    )

    service = RevenueUploadEtlService(
        dim_distributor_repo=DimDistributorRepository(session),
        dim_date_repo=DimDateRepository(session),
        dim_movie_repo=DimMovieRepository(session),
        fact_revenue_repo=FactRevenueRepository(session),
        dim_rated_repo=DimRatedRepository(session),
        dim_genre_repo=DimGenreRepository(session),
        dim_director_repo=DimDirectorRepository(session),
        bridge_genre_repo=BridgeMovieGenreRepository(session),
        bridge_director_repo=BridgeMovieDirectorRepository(session),
        fact_rating_repo=FactMovieRatingRepository(session),
        omdb_client=omdb_client,
    )

    try:
        result = await service.run(csv_bytes)
    except OmdbApiError as exc:
        logger.error(
            "Revenue upload aborted due to OMDb API error",
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
    except (ValueError, OSError) as exc:
        logger.error(
            "Revenue upload failed due to invalid CSV",
            extra={"error": str(exc)},
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_csv", "detail": str(exc)},
        ) from exc

    logger.info(
        "Revenue upload completed",
        extra={
            "facts_inserted": result.facts_inserted,
            "facts_skipped_duplicate": result.facts_skipped_duplicate,
            "movies_enriched_from_omdb": result.movies_enriched_from_omdb,
            "duration_ms": result.duration_ms,
        },
    )

    return RevenueUploadResponseDto(
        facts_inserted=result.facts_inserted,
        facts_skipped_duplicate=result.facts_skipped_duplicate,
        distributors_upserted=result.distributors_upserted,
        dates_created=result.dates_created,
        movies_enriched_from_omdb=result.movies_enriched_from_omdb,
        titles_not_found_in_omdb=result.titles_not_found_in_omdb,
        rows_error_movie_not_found=result.rows_error_movie_not_found,
        stopped_due_to_rate_limit=result.stopped_due_to_rate_limit,
        duration_ms=result.duration_ms,
    )
