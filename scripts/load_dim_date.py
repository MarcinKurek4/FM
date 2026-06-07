"""CLI entry point for loading ``dwh.dim_date`` from a pre-built CSV file.

Upserts rows from ``data/reference/dim_date.csv`` without regenerating the file.
Intended for container startup after Alembic migrations.

Example::

    poetry run python scripts/load_dim_date.py
"""

import asyncio
import sys
from pathlib import Path

from loguru import logger

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.services.dim_date_seed_service import DEFAULT_DIM_DATE_CSV, DimDateSeedService


async def _main(csv_path: Path) -> int:
    """Load dim_date rows from CSV into PostgreSQL.

    Args:
        csv_path: Path to the dimension CSV file.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    settings = get_settings()
    setup_logging(app_version="0.1.0", log_level=settings.log_level)

    if not csv_path.is_file():
        logger.error("dim_date CSV not found", extra={"path": str(csv_path)})
        return 1

    service = DimDateSeedService(dim_date_csv_path=csv_path)
    try:
        row_count = await service.upsert_from_csv(csv_path)
    except (ValueError, OSError) as exc:
        logger.error("dim_date load failed", extra={"error": str(exc), "path": str(csv_path)})
        return 1

    logger.info(
        "dim_date load succeeded",
        extra={"path": str(csv_path), "row_count": row_count},
    )
    return 0


if __name__ == "__main__":
    target = DEFAULT_DIM_DATE_CSV
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    raise SystemExit(asyncio.run(_main(target)))
