"""Initial seeding of ``dwh.dim_date`` from a reference dimension CSV file.

Generates ``data/reference/dim_date.csv`` aligned with ``DimDateTable``, then
loads it into PostgreSQL via idempotent bulk upsert.

Usage::

    from src.services.dim_date_seed_service import DimDateSeedService

    service = DimDateSeedService()
    result = await service.run()
"""

import datetime
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from loguru import logger

from src.factories.db_session_factory import DbSessionFactory, get_db_session_factory
from src.models.dwh import DimDateDto
from src.repositories.dim_date_repository import DimDateRepository
from src.utils.dim_date_builder import (
    DIM_DATE_END,
    build_dim_date_dto,
    build_dim_date_dtos,
    compute_date_id,
)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR: Path = PROJECT_ROOT / "data" / "raw"
DEFAULT_REFERENCE_DIR: Path = PROJECT_ROOT / "data" / "reference"
DEFAULT_REVENUES_CSV: Path = DEFAULT_RAW_DIR / "revenues_per_day (1).csv"
DEFAULT_DIM_DATE_CSV: Path = DEFAULT_REFERENCE_DIR / "dim_date.csv"

_UPSERT_BATCH_SIZE: int = 1000


@dataclass(frozen=True, slots=True)
class DimDateSeedResult:
    """Outcome of a dim_date seed run.

    Attributes:
        csv_path: Path to the generated reference CSV file.
        start_date: First date included in the seed range.
        end_date: Last date included in the seed range.
        row_count: Number of rows written and upserted.
    """

    csv_path: Path
    start_date: datetime.date
    end_date: datetime.date
    row_count: int


class DimDateSeedService:
    """Generate and load the date dimension for initial DWH population.

    The start date is derived from the minimum ``date`` column in the
    revenues source CSV. The end date defaults to 2030-12-31.

    Attributes:
        _revenues_csv_path: Source file used to resolve the minimum date.
        _dim_date_csv_path: Output path for the generated dimension CSV.
        _end_date: Inclusive upper bound of the generated range.
        _session_factory: Factory providing async database sessions.
    """

    __slots__ = (
        "_dim_date_csv_path",
        "_end_date",
        "_revenues_csv_path",
        "_session_factory",
    )

    def __init__(
        self: "DimDateSeedService",
        revenues_csv_path: Path | None = None,
        dim_date_csv_path: Path | None = None,
        end_date: datetime.date | None = None,
        session_factory: DbSessionFactory | None = None,
    ) -> None:
        """Initialise the seed service with optional path overrides.

        Args:
            revenues_csv_path: Revenues CSV used to detect the minimum date.
                Defaults to ``data/raw/revenues_per_day (1).csv``.
            dim_date_csv_path: Target path for generated ``dim_date.csv``.
                Defaults to ``data/reference/dim_date.csv``.
            end_date: Inclusive end of the date range. Defaults to
                ``2030-12-31``.
            session_factory: Database session factory. Defaults to the
                application singleton.
        """
        self._revenues_csv_path = revenues_csv_path or DEFAULT_REVENUES_CSV
        self._dim_date_csv_path = dim_date_csv_path or DEFAULT_DIM_DATE_CSV
        self._end_date = end_date or DIM_DATE_END
        self._session_factory = session_factory

    def _get_session_factory(self: "DimDateSeedService") -> DbSessionFactory:
        """Return the injected or default database session factory.

        Returns:
            Configured ``DbSessionFactory`` singleton when none was injected.
        """
        if self._session_factory is None:
            self._session_factory = get_db_session_factory()
        return self._session_factory

    def resolve_start_date(self: "DimDateSeedService") -> datetime.date:
        """Read the minimum revenue date from the source CSV.

        Returns:
            Earliest ``date`` value present in the revenues file.

        Raises:
            FileNotFoundError: When the revenues CSV does not exist.
            ValueError: When the file contains no parseable dates.
        """
        if not self._revenues_csv_path.is_file():
            raise FileNotFoundError(f"Revenues CSV not found: {self._revenues_csv_path}")

        minimum = (
            pl.scan_csv(self._revenues_csv_path)
            .select(pl.col("date").str.to_date("%Y-%m-%d").alias("date"))
            .select(pl.col("date").min())
            .collect()
            .item()
        )
        if minimum is None:
            raise ValueError(f"No dates found in {self._revenues_csv_path}")

        return minimum

    def generate_csv(
        self: "DimDateSeedService",
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
    ) -> Path:
        """Write ``dim_date.csv`` for the inclusive date range.

        Args:
            start_date: Range start. When ``None``, resolved from revenues CSV.
            end_date: Range end. When ``None``, uses the service default.

        Returns:
            Path to the written CSV file.

        Raises:
            FileNotFoundError: When revenues CSV is missing and start is unset.
            ValueError: When the resolved range is invalid.
        """
        start = start_date or self.resolve_start_date()
        end = end_date or self._end_date
        if start > end:
            raise ValueError(f"start date {start} must not be after end date {end}")

        dtos = build_dim_date_dtos(start, end)
        rows = [_dim_date_dto_to_csv_row(dto) for dto in dtos]

        self._dim_date_csv_path.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(rows, schema=_POLARS_SCHEMA).write_csv(self._dim_date_csv_path)

        logger.info(
            "dim_date CSV generated",
            extra={
                "path": str(self._dim_date_csv_path),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "row_count": len(rows),
            },
        )
        return self._dim_date_csv_path

    def load_dtos_from_csv(self: "DimDateSeedService", csv_path: Path | None = None) -> list[DimDateDto]:
        """Parse a ``dim_date.csv`` file into DTOs.

        Args:
            csv_path: CSV to read. Defaults to the service output path.

        Returns:
            List of ``DimDateDto`` instances in file order.
        """
        path = csv_path or self._dim_date_csv_path
        frame = pl.read_csv(
            path,
            schema_overrides={
                "date_id": pl.Int64,
                "year": pl.Int32,
                "quarter": pl.Int32,
                "month": pl.Int32,
                "day": pl.Int32,
                "day_of_week": pl.Int32,
                "week_number": pl.Int32,
            },
        )
        return [_csv_row_to_dim_date_dto(row) for row in frame.iter_rows(named=True)]

    async def upsert_from_csv(self: "DimDateSeedService", csv_path: Path | None = None) -> int:
        """Bulk upsert all rows from a ``dim_date.csv`` file.

        Args:
            csv_path: CSV to load. Defaults to the service output path.

        Returns:
            Number of rows upserted.
        """
        dtos = self.load_dtos_from_csv(csv_path)
        async with self._get_session_factory().get_session() as session:
            repository = DimDateRepository(session)
            for offset in range(0, len(dtos), _UPSERT_BATCH_SIZE):
                batch = dtos[offset : offset + _UPSERT_BATCH_SIZE]
                await repository.bulk_upsert(batch)

        logger.info(
            "dim_date upsert completed",
            extra={"row_count": len(dtos), "csv_path": str(csv_path or self._dim_date_csv_path)},
        )
        return len(dtos)

    async def run(self: "DimDateSeedService") -> DimDateSeedResult:
        """Generate ``dim_date.csv`` and upsert all rows into ``dwh.dim_date``.

        Returns:
            Summary of the seed operation.

        Raises:
            FileNotFoundError: When the revenues CSV is missing.
            ValueError: When the date range is invalid.
        """
        start_date = self.resolve_start_date()
        end_date = self._end_date
        csv_path = self.generate_csv(start_date=start_date, end_date=end_date)
        row_count = await self.upsert_from_csv(csv_path)

        result = DimDateSeedResult(
            csv_path=csv_path,
            start_date=start_date,
            end_date=end_date,
            row_count=row_count,
        )
        logger.info(
            "dim_date seed finished",
            extra={
                "csv_path": str(result.csv_path),
                "start_date": result.start_date.isoformat(),
                "end_date": result.end_date.isoformat(),
                "row_count": result.row_count,
            },
        )
        return result


_POLARS_SCHEMA: dict[str, pl.DataType] = {
    "date_id": pl.Int64,
    "date": pl.String,
    "year": pl.Int32,
    "quarter": pl.Int32,
    "month": pl.Int32,
    "month_name": pl.String,
    "day": pl.Int32,
    "day_of_week": pl.Int32,
    "day_of_week_name": pl.String,
    "week_number": pl.Int32,
    "is_weekend": pl.Boolean,
    "is_holiday": pl.Boolean,
}


def _dim_date_dto_to_csv_row(dto: DimDateDto) -> dict[str, object]:
    """Convert a DTO to a CSV row dict with ``DimDateTable`` column names."""
    return {
        "date_id": dto.date_id,
        "date": dto.date.isoformat(),
        "year": dto.year,
        "quarter": dto.quarter,
        "month": dto.month,
        "month_name": dto.month_name,
        "day": dto.day,
        "day_of_week": dto.day_of_week,
        "day_of_week_name": dto.day_of_week_name,
        "week_number": dto.week_number,
        "is_weekend": dto.is_weekend,
        "is_holiday": dto.is_holiday,
    }


def _csv_row_to_dim_date_dto(row: dict[str, object]) -> DimDateDto:
    """Convert a CSV row dict to a ``DimDateDto``."""
    parsed_date = datetime.date.fromisoformat(str(row["date"]))
    date_id = int(row["date_id"])
    if date_id != compute_date_id(parsed_date):
        raise ValueError(
            f"date_id {date_id} does not match date {parsed_date.isoformat()}"
        )
    return build_dim_date_dto(parsed_date)
