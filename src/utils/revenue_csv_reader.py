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


def read_revenues_csv(path: Path) -> list[RawRevenueRow]:
    """Load and parse the revenues CSV into typed row objects.

    Uses a Polars ``LazyFrame`` for memory-efficient scanning. All rows are
    collected into memory as ``RawRevenueRow`` instances.

    Empty ``theaters`` and ``distributor`` CSV fields are stored as ``None``.
    The sentinel distributor value ``"-"`` is also mapped to ``None``.

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
    for record in frame.iter_rows(named=True):
        theaters_raw = record["theaters"]
        theaters: int | None = int(theaters_raw) if theaters_raw is not None else None

        distributor_raw: str | None = record["distributor"]
        distributor: str | None = _normalise_distributor(distributor_raw)

        rows.append(
            RawRevenueRow(
                row_id=uuid.UUID(record["id"]),
                date=datetime.date.fromisoformat(record["date"]),
                title=record["title"],
                revenue=Decimal(record["revenue"]),
                theaters=theaters,
                distributor=distributor,
            )
        )

    logger.info(
        "Revenues CSV loaded",
        extra={"path": str(path), "row_count": len(rows)},
    )
    return rows


def _normalise_distributor(raw_value: str | None) -> str | None:
    """Map empty or sentinel distributor CSV values to ``None``.

    Args:
        raw_value: Raw distributor cell from the CSV.

    Returns:
        A trimmed distributor name, or ``None`` when the value is missing.
    """
    if raw_value is None:
        return None
    stripped = raw_value.strip()
    if not stripped or stripped == MISSING_DISTRIBUTOR_SENTINEL:
        return None
    return stripped


def collect_unique_distributor_names(rows: list[RawRevenueRow]) -> set[str]:
    """Return distinct non-null distributor names from parsed rows.

    Args:
        rows: Parsed revenue rows.

    Returns:
        Set of distributor name strings present in the CSV.

    Example:
        names = collect_unique_distributor_names(rows)
    """
    return {row.distributor for row in rows if row.distributor is not None}


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
