"""ETL service for initial bulk load of revenue facts from CSV.

Reads ``revenues_per_day.csv``, resolves all dimension foreign keys, inserts
rows into ``fact_revenue``, and writes an error log for titles that cannot
be matched against ``dim_movie``.

This service is the one-time bootstrap for revenue facts. A subsequent HTTP
endpoint will handle incremental uploads by inserting only rows whose
``source_row_id`` is not yet present in ``fact_revenue``.

Usage::

    from src.services.revenue_init_load_service import RevenueInitLoadService

    service = RevenueInitLoadService(
        dim_distributor_repo=distributor_repo,
        dim_date_repo=date_repo,
        dim_movie_repo=movie_repo,
        fact_revenue_repo=revenue_repo,
    )
    result = await service.run()
"""

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.interfaces.dim_date_repository_protocol import DimDateRepositoryProtocol
from src.interfaces.dim_distributor_repository_protocol import DimDistributorRepositoryProtocol
from src.interfaces.dim_movie_repository_protocol import DimMovieRepositoryProtocol
from src.interfaces.fact_revenue_repository_protocol import FactRevenueRepositoryProtocol
from src.models.dwh import DimDateDto, DimDistributorDto, FactRevenueDto
from src.models.raw_revenues import RawRevenueRow
from src.utils.dim_date_builder import build_dim_date_dto, compute_date_id
from src.utils.timing import log_execution_time
from src.utils.revenue_csv_reader import (
    collect_unique_dates,
    collect_unique_distributor_names,
    read_revenues_csv,
)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR: Path = PROJECT_ROOT / "data" / "raw"
DEFAULT_REVENUES_CSV: Path = DEFAULT_RAW_DIR / "revenues_per_day (1).csv"
DEFAULT_ERRORLOG_PATH: Path = DEFAULT_RAW_DIR / "revenue_init_load_errorlog.json"

_FACT_BATCH_SIZE: int = 500


@dataclass(frozen=True, slots=True)
class RevenueInitLoadResult:
    """Summary of a revenue init load run.

    Attributes:
        distributors_upserted: Number of ``dim_distributor`` rows created or
            updated.
        dates_created: Number of missing ``dim_date`` rows inserted on the
            fly.
        facts_inserted: Number of new ``fact_revenue`` rows inserted.
        facts_skipped_duplicate: Number of CSV rows skipped because their
            ``source_row_id`` already exists in ``fact_revenue``.
        rows_error_movie_not_found: Number of CSV rows whose title could not
            be matched against any ``dim_movie`` record.
        error_log_path: Path to the error log file, or ``None`` when no
            errors occurred.
        duration_ms: Wall-clock duration of the run in milliseconds.
    """

    distributors_upserted: int
    dates_created: int
    facts_inserted: int
    facts_skipped_duplicate: int
    rows_error_movie_not_found: int
    error_log_path: Path | None
    duration_ms: float = 0.0


class RevenueInitLoadService:
    """Load revenue facts from the source CSV into ``fact_revenue``.

    Resolves dimension foreign keys in four phases:

    1. Upsert all distinct distributors into ``dim_distributor``.
    2. Ensure all distinct dates exist in ``dim_date``; create missing rows.
    3. Load the entire ``dim_movie`` title map (uppercase-keyed) in one query.
    4. Iterate CSV rows: matched rows are batch-inserted into ``fact_revenue``;
       unmatched rows (movie not found) are written to an error log.

    Attributes:
        _dim_distributor_repo: Distributor dimension repository.
        _dim_date_repo: Date dimension repository.
        _dim_movie_repo: Movie dimension repository.
        _fact_revenue_repo: Revenue fact repository.
        _revenues_csv_path: Source CSV path.
        _errorlog_path: Destination for error log JSON.
    """

    __slots__ = (
        "_dim_date_repo",
        "_dim_distributor_repo",
        "_dim_movie_repo",
        "_errorlog_path",
        "_fact_revenue_repo",
        "_revenues_csv_path",
    )

    def __init__(
        self: "RevenueInitLoadService",
        dim_distributor_repo: DimDistributorRepositoryProtocol,
        dim_date_repo: DimDateRepositoryProtocol,
        dim_movie_repo: DimMovieRepositoryProtocol,
        fact_revenue_repo: FactRevenueRepositoryProtocol,
        revenues_csv_path: Path | None = None,
        errorlog_path: Path | None = None,
    ) -> None:
        """Initialise the revenue init load service.

        Args:
            dim_distributor_repo: Repository for ``dim_distributor``.
            dim_date_repo: Repository for ``dim_date``.
            dim_movie_repo: Repository for ``dim_movie``.
            fact_revenue_repo: Repository for ``fact_revenue``.
            revenues_csv_path: Source CSV path. Defaults to
                ``data/raw/revenues_per_day (1).csv``.
            errorlog_path: Error log destination. Defaults to
                ``data/raw/revenue_init_load_errorlog.json``.
        """
        self._dim_distributor_repo = dim_distributor_repo
        self._dim_date_repo = dim_date_repo
        self._dim_movie_repo = dim_movie_repo
        self._fact_revenue_repo = fact_revenue_repo
        self._revenues_csv_path = revenues_csv_path or DEFAULT_REVENUES_CSV
        self._errorlog_path = errorlog_path or DEFAULT_ERRORLOG_PATH

    @log_execution_time(inject_duration_ms=True)
    async def run(self: "RevenueInitLoadService") -> RevenueInitLoadResult:
        """Execute the full revenue init load pipeline.

        Returns:
            Summary counts and timing for the run.

        Raises:
            FileNotFoundError: When the revenues CSV is missing.
            ValueError: When the CSV contains unparseable rows.
        """
        logger.info(
            "Starting revenue init load",
            extra={"csv_path": str(self._revenues_csv_path)},
        )

        rows = read_revenues_csv(self._revenues_csv_path)
        now = _naive_utc_now()

        distributor_map, distributors_upserted = await self._load_distributors(rows, now)
        dates_created = await self._ensure_dates(rows, now)
        title_map = await self._dim_movie_repo.bulk_load_title_map()
        date_map = _build_date_id_map(rows)

        facts, errors = _resolve_rows(rows, title_map, distributor_map, date_map, now)

        inserted, skipped = await self._insert_facts(facts)
        error_log_path = _write_error_log(errors, self._errorlog_path)

        result = RevenueInitLoadResult(
            distributors_upserted=distributors_upserted,
            dates_created=dates_created,
            facts_inserted=inserted,
            facts_skipped_duplicate=skipped,
            rows_error_movie_not_found=len(errors),
            error_log_path=error_log_path,
        )
        logger.info(
            "Revenue init load finished",
            extra={
                "distributors_upserted": result.distributors_upserted,
                "dates_created": result.dates_created,
                "facts_inserted": result.facts_inserted,
                "facts_skipped_duplicate": result.facts_skipped_duplicate,
                "rows_error_movie_not_found": result.rows_error_movie_not_found,
                "error_log_path": str(result.error_log_path) if result.error_log_path else None,
            },
        )
        return result

    async def _load_distributors(
        self: "RevenueInitLoadService",
        rows: list[RawRevenueRow],
        now: datetime.datetime,
    ) -> tuple[dict[str, int], int]:
        """Upsert all distinct distributor names and return a name-to-id map.

        Args:
            rows: Parsed revenue rows.
            now: Load timestamp for ``loaded_at``.

        Returns:
            A tuple of ``(distributor_map, upserted_count)``.
        """
        names = collect_unique_distributor_names(rows)
        distributor_map: dict[str, int] = {}
        upserted = 0

        for name in sorted(names):
            dto = DimDistributorDto(
                distributor_id=None,
                distributor_name=name,
                loaded_at=now,
            )
            persisted = await self._dim_distributor_repo.upsert(dto)
            if persisted.distributor_id is not None:
                distributor_map[name] = persisted.distributor_id
            upserted += 1

        logger.info(
            "Distributors loaded",
            extra={"upserted": upserted, "map_size": len(distributor_map)},
        )
        return distributor_map, upserted

    async def _ensure_dates(
        self: "RevenueInitLoadService",
        rows: list[RawRevenueRow],
        now: datetime.datetime,
    ) -> int:
        """Ensure every distinct date in the CSV exists in ``dim_date``.

        Missing dates are built with ``build_dim_date_dto`` and upserted.

        Args:
            rows: Parsed revenue rows.
            now: Unused; retained for symmetry.

        Returns:
            Number of dates created during this run.
        """
        _ = now
        dates = collect_unique_dates(rows)
        created = 0

        for date_value in sorted(dates):
            date_id = compute_date_id(date_value)
            existing = await self._dim_date_repo.get_by_id(date_id)
            if existing is None:
                dto: DimDateDto = build_dim_date_dto(date_value)
                await self._dim_date_repo.upsert(dto)
                created += 1
                logger.warning(
                    "Missing dim_date created on the fly",
                    extra={"date": date_value.isoformat(), "date_id": date_id},
                )

        logger.info(
            "Date dimension verified",
            extra={"total_distinct_dates": len(dates), "dates_created": created},
        )
        return created

    async def _insert_facts(
        self: "RevenueInitLoadService",
        dtos: list[FactRevenueDto],
    ) -> tuple[int, int]:
        """Batch-insert fact records, skipping existing UUIDs.

        Args:
            dtos: Fact records to insert.

        Returns:
            A tuple of ``(inserted_count, skipped_count)``.
        """
        if not dtos:
            return 0, 0

        total_inserted = 0
        for offset in range(0, len(dtos), _FACT_BATCH_SIZE):
            batch = dtos[offset : offset + _FACT_BATCH_SIZE]
            inserted = await self._fact_revenue_repo.bulk_insert(batch)
            total_inserted += inserted
            logger.debug(
                "Fact batch inserted",
                extra={
                    "batch_offset": offset,
                    "batch_size": len(batch),
                    "inserted": inserted,
                },
            )

        skipped = len(dtos) - total_inserted
        return total_inserted, skipped


def _resolve_rows(
    rows: list[RawRevenueRow],
    title_map: dict[str, int],
    distributor_map: dict[str, int],
    date_map: dict[datetime.date, int],
    now: datetime.datetime,
) -> tuple[list[FactRevenueDto], list[dict[str, object]]]:
    """Resolve dimension keys and partition rows into facts and errors.

    Args:
        rows: All parsed revenue rows.
        title_map: Uppercase-keyed ``title → movie_id`` from ``dim_movie``.
        distributor_map: ``distributor_name → distributor_id``.
        date_map: ``date → date_id`` built from the CSV itself.
        now: Load timestamp for ``loaded_at``.

    Returns:
        A tuple of ``(fact_dtos, error_records)``. ``error_records`` contains
        raw dicts suitable for JSON serialisation.
    """
    facts: list[FactRevenueDto] = []
    errors: list[dict[str, object]] = []

    for row in rows:
        movie_id = title_map.get(row.title.upper())
        if movie_id is None:
            errors.append(
                {
                    "source_row_id": str(row.row_id),
                    "date": row.date.isoformat(),
                    "title": row.title,
                    "revenue": str(row.revenue),
                    "theaters": row.theaters,
                    "distributor": row.distributor,
                    "reason": "movie_not_found",
                }
            )
            continue

        if row.distributor is None:
            distributor_id = None
        else:
            distributor_id = distributor_map.get(row.distributor)
            if distributor_id is None:
                errors.append(
                    {
                        "source_row_id": str(row.row_id),
                        "date": row.date.isoformat(),
                        "title": row.title,
                        "revenue": str(row.revenue),
                        "theaters": row.theaters,
                        "distributor": row.distributor,
                        "reason": "distributor_not_resolved",
                    }
                )
                continue

        date_id = date_map.get(row.date)
        if date_id is None:
            errors.append(
                {
                    "source_row_id": str(row.row_id),
                    "date": row.date.isoformat(),
                    "title": row.title,
                    "revenue": str(row.revenue),
                    "theaters": row.theaters,
                    "distributor": row.distributor,
                    "reason": "date_not_resolved",
                }
            )
            continue

        facts.append(
            FactRevenueDto(
                revenue_id=None,
                source_row_id=row.row_id,
                movie_id=movie_id,
                date_id=date_id,
                distributor_id=distributor_id,
                revenue=row.revenue,
                theaters=row.theaters,
                loaded_at=now,
            )
        )

    return facts, errors


def _build_date_id_map(rows: list[RawRevenueRow]) -> dict[datetime.date, int]:
    """Build a ``date → date_id`` map from the CSV row dates.

    Args:
        rows: Parsed revenue rows.

    Returns:
        Mapping from ``datetime.date`` to ``YYYYMMDD`` integer key.
    """
    return {row.date: compute_date_id(row.date) for row in rows}


def _write_error_log(
    errors: list[dict[str, object]],
    path: Path,
) -> Path | None:
    """Write error records to a JSON file when any exist.

    Args:
        errors: Error entries to write.
        path: Destination file path.

    Returns:
        The path written to, or ``None`` when ``errors`` is empty.
    """
    if not errors:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(errors, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.warning(
        "Revenue error log written",
        extra={"path": str(path), "error_count": len(errors)},
    )
    return path


def _naive_utc_now() -> datetime.datetime:
    """Return the current UTC time as a naive datetime.

    PostgreSQL ``TIMESTAMP WITHOUT TIME ZONE`` columns require naive values.
    """
    return datetime.datetime.now(tz=datetime.UTC).replace(tzinfo=None)
