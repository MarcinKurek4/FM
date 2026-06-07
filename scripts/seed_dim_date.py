"""CLI entry point for initial ``dwh.dim_date`` seeding.

Generates ``data/reference/dim_date.csv`` from the minimum revenue date through
2030-12-31, then upserts all rows into PostgreSQL.

Example::

    poetry run python scripts/seed_dim_date.py
"""

import asyncio
import sys

from loguru import logger

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.services.dim_date_seed_service import DimDateSeedService


async def _main() -> int:
    """Run the dim_date seed pipeline.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    settings = get_settings()
    setup_logging(app_version="0.1.0", log_level=settings.log_level)
    service = DimDateSeedService()
    try:
        result = await service.run()
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.error("dim_date seed failed", extra={"error": str(exc)})
        return 1

    logger.info(
        "dim_date seed succeeded",
        extra={
            "csv_path": str(result.csv_path),
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "row_count": result.row_count,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
