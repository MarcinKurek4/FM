"""CLI entry point for initial OMDb master-data load into the DWH.

Reads ``data/raw/omdb_titles_init_result.json`` and upserts dimensions,
bridge tables, and rating facts.

Example::

    poetry run python scripts/run_omdb_dwh_init_load.py
"""

import asyncio
import sys

from loguru import logger

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.factories.db_session_factory import get_db_session_factory
from src.repositories.bridge_movie_director_repository import BridgeMovieDirectorRepository
from src.repositories.bridge_movie_genre_repository import BridgeMovieGenreRepository
from src.repositories.dim_director_repository import DimDirectorRepository
from src.repositories.dim_genre_repository import DimGenreRepository
from src.repositories.dim_movie_repository import DimMovieRepository
from src.repositories.dim_rated_repository import DimRatedRepository
from src.repositories.fact_movie_rating_repository import FactMovieRatingRepository
from src.services.omdb_dwh_init_load_service import OmdbDwhInitLoadService


async def _main() -> int:
    """Run the OMDb DWH init load pipeline.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    settings = get_settings()
    setup_logging(app_version="0.1.0", log_level=settings.log_level)

    factory = get_db_session_factory()
    try:
        async with factory.get_session() as session:
            service = OmdbDwhInitLoadService(
                dim_rated_repo=DimRatedRepository(session),
                dim_genre_repo=DimGenreRepository(session),
                dim_director_repo=DimDirectorRepository(session),
                dim_movie_repo=DimMovieRepository(session),
                bridge_genre_repo=BridgeMovieGenreRepository(session),
                bridge_director_repo=BridgeMovieDirectorRepository(session),
                fact_rating_repo=FactMovieRatingRepository(session),
            )
            result = await service.run()
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.error("OMDb DWH init load failed", extra={"error": str(exc)})
        return 1

    logger.info(
        "OMDb DWH init load succeeded",
        extra={
            "rated_upserted": result.rated_upserted,
            "genres_upserted": result.genres_upserted,
            "directors_upserted": result.directors_upserted,
            "movies_upserted": result.movies_upserted,
            "bridges_genre_upserted": result.bridges_genre_upserted,
            "bridges_director_upserted": result.bridges_director_upserted,
            "ratings_inserted": result.ratings_inserted,
            "skipped_no_response": result.skipped_no_response,
            "duration_ms": result.duration_ms,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
