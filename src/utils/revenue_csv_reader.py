"""Reader for the revenues_per_day CSV source file.

Loads the revenues CSV using a Polars ``LazyFrame`` and returns a list of
typed ``RawRevenueRow`` instances. All type conversions are performed here;
no business logic is applied.

Usage::

    from pathlib import Path
    from src.utils.revenue_csv_reader import read_revenues_csv

    rows = read_revenues_csv(Path("data/raw/revenues_per_day (1).csv"))
"""

import datetime
import uuid
from decimal import Decimal
from pathlib import Path

import polars as pl
from loguru import logger

from src.models.raw_revenues import MISSING_DISTRIBUTOR_SENTINEL, RawRevenueRow

_CSV_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.String,
    "date": pl.String,
    "title": pl.String,
    "revenue": pl.Int64,
    "theaters": pl.Int32,
    "distributor": pl.String,
}

_UNKNOWN_DISTRIBUTOR: str = "Unknown"


def read_revenues_csv(path: Path) -> list[RawRevenueRow]:
    """Load and parse the revenues CSV into typed row objects.

    Uses a Polars ``LazyFrame`` for memory-efficient scanning. All rows are
    collected into memory as ``RawRevenueRow`` instances.

    The sentinel distributor value ``"-"`` is mapped to ``None`` in
    ``RawRevenueRow.distributor``.

    Args:
        path: Path to the revenues CSV file.

    Returns:
        List of ``RawRevenueRow`` instances in file order.

    Raises:
        FileNotFoundError: When ``path`` does not exist.
        ValueError: When any row contains unparseable field values.

    Example:
        rows = read_revenues_csv(Path("data/raw/revenues_per_day (1).csv"))
    """
    if not path.is_file():
        raise FileNotFoundError(f"Revenues CSV not found: {path}")

    frame = (
        pl.scan_csv(path, schema_overrides=_CSV_SCHEMA)
        .collect()
    )

    rows: list[RawRevenueRow] = []
    skipped_null = 0
    for record in frame.iter_rows(named=True):
        theaters_raw = record["theaters"]
        if theaters_raw is None:
            skipped_null += 1
            logger.warning(
                "Skipping revenue row with null theaters",
                extra={"id": record["id"], "title": record["title"]},
            )
            continue

        distributor_raw: str | None = record["distributor"]
        distributor: str | None = (
            None if distributor_raw == MISSING_DISTRIBUTOR_SENTINEL else distributor_raw
        )

        rows.append(
            RawRevenueRow(
                row_id=uuid.UUID(record["id"]),
                date=datetime.date.fromisoformat(record["date"]),
                title=record["title"],
                revenue=Decimal(record["revenue"]),
                theaters=int(theaters_raw),
                distributor=distributor,
            )
        )

    if skipped_null:
        logger.warning(
            "Skipped rows with null theaters",
            extra={"skipped_count": skipped_null, "path": str(path)},
        )

    logger.info(
        "Revenues CSV loaded",
        extra={"path": str(path), "row_count": len(rows)},
    )
    return rows


def collect_unique_distributor_names(rows: list[RawRevenueRow]) -> set[str]:
    """Return the set of effective distributor names from parsed rows.

    Rows where ``distributor`` is ``None`` (sentinel ``"-"``) contribute the
    name ``"Unknown"`` to represent missing distributors.

    Args:
        rows: Parsed revenue rows.

    Returns:
        Set of non-empty distributor name strings.

    Example:
        names = collect_unique_distributor_names(rows)
        assert "Unknown" in names
    """
    names: set[str] = set()
    for row in rows:
        names.add(row.distributor if row.distributor is not None else _UNKNOWN_DISTRIBUTOR)
    return names


def collect_unique_dates(rows: list[RawRevenueRow]) -> set[datetime.date]:
    """Return the set of distinct calendar dates from parsed rows.

    Args:
        rows: Parsed revenue rows.

    Returns:
        Set of ``datetime.date`` values.

    Example:
        dates = collect_unique_dates(rows)
    """
    return {row.date for row in rows}


UNKNOWN_DISTRIBUTOR_NAME: str = _UNKNOWN_DISTRIBUTOR
