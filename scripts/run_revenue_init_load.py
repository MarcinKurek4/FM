"""CLI entry point for initial revenue fact load from CSV.

Reads ``data/raw/revenues_per_day (1).csv``, resolves dimension keys, and
bulk-inserts rows into ``dwh.fact_revenue``. Rows whose movie title cannot
be matched against ``dim_movie`` are written to an error log.

Example::

    poetry run python scripts/run_revenue_init_load.py
"""

import asyncio

from loguru import logger

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.factories.db_session_factory import get_db_session_factory
from src.repositories.dim_date_repository import DimDateRepository
from src.repositories.dim_distributor_repository import DimDistributorRepository
from src.repositories.dim_movie_repository import DimMovieRepository
from src.repositories.fact_revenue_repository import FactRevenueRepository
from src.services.revenue_init_load_service import RevenueInitLoadService


async def _main() -> int:
    """Run the revenue init load pipeline.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    settings = get_settings()
    setup_logging(app_version="0.1.0", log_level=settings.log_level)

    factory = get_db_session_factory()
    try:
        async with factory.get_session() as session:
            service = RevenueInitLoadService(
                dim_distributor_repo=DimDistributorRepository(session),
                dim_date_repo=DimDateRepository(session),
                dim_movie_repo=DimMovieRepository(session),
                fact_revenue_repo=FactRevenueRepository(session),
            )
            result = await service.run()
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.error("Revenue init load failed", extra={"error": str(exc)})
        return 1

    logger.info(
        "Revenue init load succeeded",
        extra={
            "distributors_upserted": result.distributors_upserted,
            "dates_created": result.dates_created,
            "facts_inserted": result.facts_inserted,
            "facts_skipped_duplicate": result.facts_skipped_duplicate,
            "rows_error_movie_not_found": result.rows_error_movie_not_found,
            "error_log_path": (
                str(result.error_log_path) if result.error_log_path else None
            ),
            "duration_ms": result.duration_ms,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
