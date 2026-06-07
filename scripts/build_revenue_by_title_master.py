"""CLI entry point for building the revenue-by-title master aggregate.

Reads ``data/raw/revenues_per_day (1).csv``, optionally normalises embedded
``uXXXX`` Unicode escape artefacts in movie titles, aggregates total revenue
per title, and writes a descending-ranked CSV to ``data/master/``.

Example::

    poetry run python scripts/build_revenue_by_title_master.py
    poetry run python scripts/build_revenue_by_title_master.py --no-fix-encoding
"""

import argparse
import sys
from pathlib import Path

import polars as pl
from loguru import logger

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.utils.title_encoding import (
    contains_embedded_unicode_escape,
    decode_embedded_unicode_escapes,
)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
DEFAULT_REVENUES_CSV: Path = PROJECT_ROOT / "data" / "raw" / "revenues_per_day (1).csv"
DEFAULT_MASTER_DIR: Path = PROJECT_ROOT / "data" / "master"
DEFAULT_OUTPUT_CSV: Path = DEFAULT_MASTER_DIR / "revenue_by_title.csv"

_CSV_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.String,
    "date": pl.String,
    "title": pl.String,
    "revenue": pl.Int64,
    "theaters": pl.Int32,
    "distributor": pl.String,
}


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Build a master CSV with total revenue per unique movie title.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_REVENUES_CSV,
        help=f"Source revenues CSV path (default: {DEFAULT_REVENUES_CSV.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help=f"Output master CSV path (default: {DEFAULT_OUTPUT_CSV.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--no-fix-encoding",
        action="store_true",
        help="Skip decoding embedded uXXXX Unicode escape sequences in titles.",
    )
    return parser.parse_args()


def build_revenue_by_title_master(
    input_path: Path,
    output_path: Path,
    *,
    fix_encoding: bool = True,
) -> tuple[int, int]:
    """Aggregate revenue by title and write the master CSV file.

    Args:
        input_path: Path to the daily revenues source CSV.
        output_path: Destination path for the aggregated master CSV.
        fix_encoding: When ``True``, decode embedded ``uXXXX`` sequences in
            titles before aggregation.

    Returns:
        A tuple of ``(unique_title_count, titles_with_encoding_artefacts)``.

    Raises:
        FileNotFoundError: When ``input_path`` does not exist.
        ValueError: When the source CSV contains no rows.
    """
    if not input_path.is_file():
        raise FileNotFoundError(f"Revenues CSV not found: {input_path}")

    frame = pl.scan_csv(input_path, schema_overrides=_CSV_SCHEMA).select("title", "revenue").collect()

    if frame.is_empty():
        raise ValueError(f"No rows found in {input_path}")

    titles_with_artefacts = 0
    if fix_encoding:
        raw_titles = frame.get_column("title").unique().to_list()
        titles_with_artefacts = sum(
            1 for title in raw_titles if contains_embedded_unicode_escape(str(title))
        )
        frame = frame.with_columns(
            pl.col("title")
            .map_elements(
                decode_embedded_unicode_escapes,
                return_dtype=pl.String,
            )
            .alias("title")
        )
        if titles_with_artefacts:
            logger.warning(
                "Decoded embedded Unicode escape sequences in titles",
                extra={"titles_with_artefacts": titles_with_artefacts},
            )

    aggregated = (
        frame.group_by("title")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    aggregated.write_csv(output_path)

    return aggregated.height, titles_with_artefacts


def _main() -> int:
    """Run the revenue-by-title master build.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    args = _parse_args()
    settings = get_settings()
    setup_logging(app_version="0.1.0", log_level=settings.log_level)

    logger.info(
        "Building revenue-by-title master file",
        extra={
            "input_path": str(args.input),
            "output_path": str(args.output),
            "fix_encoding": not args.no_fix_encoding,
        },
    )

    try:
        unique_titles, titles_with_artefacts = build_revenue_by_title_master(
            args.input,
            args.output,
            fix_encoding=not args.no_fix_encoding,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.error("Revenue-by-title master build failed", extra={"error": str(exc)})
        return 1

    logger.info(
        "Revenue-by-title master build succeeded",
        extra={
            "output_path": str(args.output),
            "unique_titles": unique_titles,
            "titles_with_encoding_artefacts": titles_with_artefacts,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
