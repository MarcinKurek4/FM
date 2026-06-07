"""CLI entry point for bulk OMDb enrichment ranked by total revenue.

Reads titles from ``data/master/revenue_by_title.csv`` (highest revenue
first) and writes ``data/raw/omdb_titles_init_result.json`` plus, when
needed, ``data/raw/omdb_titles_init_errorlog.json``.

Example::

    poetry run python scripts/run_omdb_enrichment_etl.py
    poetry run python scripts/run_omdb_enrichment_etl.py --resume
"""

import argparse
import asyncio
from pathlib import Path

import httpx
from loguru import logger

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.services.omdb_enrichment_etl_service import (
    DEFAULT_REVENUE_BY_TITLE_CSV,
    OmdbEnrichmentEtlService,
    _HTTP_TIMEOUT_SECONDS,
)
from src.services.omdb_client import OmdbClient


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the enrichment ETL CLI.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Fetch OMDb metadata for movie titles ranked by total revenue "
            "from the master CSV."
        ),
    )
    parser.add_argument(
        "--titles-csv",
        type=Path,
        default=DEFAULT_REVENUE_BY_TITLE_CSV,
        help=(
            "Master CSV with title and total_revenue columns "
            f"(default: {DEFAULT_REVENUE_BY_TITLE_CSV.name})."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip titles already present in the result JSON, merge new records "
            "into existing output files, and retry previously failed titles."
        ),
    )
    return parser.parse_args()


async def _main() -> int:
    """Run the OMDb enrichment ETL pipeline.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    args = _parse_args()
    settings = get_settings()
    setup_logging(app_version="0.1.0", log_level=settings.log_level)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as http_client:
        omdb_client = OmdbClient(
            api_key=settings.omdb_api_key,
            http_client=http_client,
            base_url=settings.omdb_base_url,
        )
        service = OmdbEnrichmentEtlService(
            omdb_client=omdb_client,
            revenue_by_title_csv_path=args.titles_csv,
        )
        try:
            result = await service.run(resume=args.resume)
        except (FileNotFoundError, ValueError, OSError) as exc:
            logger.error("OMDb enrichment ETL failed", extra={"error": str(exc)})
            return 1

    if result.stopped_due_to_rate_limit:
        logger.error(
            "OMDb enrichment ETL stopped due to API rate limit",
            extra={
                "result_path": str(result.result_path),
                "errorlog_path": str(result.errorlog_path) if result.errorlog_path else None,
                "processed_count": result.processed_count,
                "skipped_count": result.skipped_count,
                "total_titles": result.total_titles,
                "success_count": result.success_count,
                "error_count": result.error_count,
            },
        )
        return 1

    logger.info(
        "OMDb enrichment ETL succeeded",
        extra={
            "result_path": str(result.result_path),
            "errorlog_path": str(result.errorlog_path) if result.errorlog_path else None,
            "total_titles": result.total_titles,
            "processed_count": result.processed_count,
            "skipped_count": result.skipped_count,
            "success_count": result.success_count,
            "error_count": result.error_count,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
