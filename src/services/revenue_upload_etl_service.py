"""ETL service for incremental revenue uploads via HTTP.

Accepts CSV bytes uploaded through the API, resolves all dimension foreign
keys, fetches OMDb metadata for titles not yet present in ``dim_movie``, and
inserts only new rows into ``fact_revenue``.

The pipeline is idempotent: re-running it on the same CSV bytes produces no
duplicate ``fact_revenue`` rows because ``bulk_insert`` uses
``ON CONFLICT DO NOTHING`` on ``source_row_id``.

Usage::

    service = RevenueUploadEtlService(
        dim_distributor_repo=distributor_repo,
        dim_date_repo=date_repo,
        dim_movie_repo=movie_repo,
        fact_revenue_repo=revenue_repo,
        dim_rated_repo=rated_repo,
        dim_genre_repo=genre_repo,
        dim_director_repo=director_repo,
        bridge_genre_repo=bridge_genre_repo,
        bridge_director_repo=bridge_director_repo,
        fact_rating_repo=fact_rating_repo,
        omdb_client=omdb_client,
    )
    result = await service.run(csv_bytes)
"""

import datetime
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from loguru import logger

from src.interfaces.bridge_movie_director_repository_protocol import (
    BridgeMovieDirectorRepositoryProtocol,
)
from src.interfaces.bridge_movie_genre_repository_protocol import (
    BridgeMovieGenreRepositoryProtocol,
)
from src.interfaces.dim_date_repository_protocol import DimDateRepositoryProtocol
from src.interfaces.dim_director_repository_protocol import DimDirectorRepositoryProtocol
from src.interfaces.dim_distributor_repository_protocol import DimDistributorRepositoryProtocol
from src.interfaces.dim_genre_repository_protocol import DimGenreRepositoryProtocol
from src.interfaces.dim_movie_repository_protocol import DimMovieRepositoryProtocol
from src.interfaces.dim_rated_repository_protocol import DimRatedRepositoryProtocol
from src.interfaces.fact_movie_rating_repository_protocol import (
    FactMovieRatingRepositoryProtocol,
)
from src.interfaces.fact_revenue_repository_protocol import FactRevenueRepositoryProtocol
from src.interfaces.omdb_client_protocol import OmdbClientProtocol
from src.models.dwh import (
    BridgeMovieDirectorDto,
    BridgeMovieGenreDto,
    DimDirectorDto,
    DimDistributorDto,
    DimGenreDto,
    DimMovieDto,
    DimRatedDto,
    FactMovieRatingDto,
    FactRevenueDto,
)
from src.models.exceptions import OmdbApiError
from src.models.omdb import OMDB_RATE_LIMIT_ERROR_REASON, OmdbMovieResponse
from src.models.raw_revenues import RawRevenueRow
from src.utils.dim_date_builder import build_dim_date_dto, compute_date_id
from src.utils.omdb_json_reader import split_csv_field
from src.utils.rated_descriptions import get_rating_description
from src.utils.revenue_csv_reader import (
    UNKNOWN_DISTRIBUTOR_NAME,
    collect_unique_dates,
    collect_unique_distributor_names,
    read_revenues_csv,
)

_FACT_BATCH_SIZE: int = 500

_HTTP_STATUS_UNAUTHORIZED: int = 401
_HTTP_STATUS_RATE_LIMIT: int = 429


@dataclass(frozen=True, slots=True)
class RevenueUploadEtlResult:
    """Summary of a single incremental revenue upload ETL run.

    Attributes:
        facts_inserted: Number of new ``fact_revenue`` rows inserted.
        facts_skipped_duplicate: Number of CSV rows skipped because their
            ``source_row_id`` already exists in ``fact_revenue``.
        distributors_upserted: Number of ``dim_distributor`` rows created or
            updated during this run.
        dates_created: Number of ``dim_date`` rows created on the fly.
        movies_enriched_from_omdb: Number of new movies fetched from OMDb and
            loaded into ``dim_movie`` and related tables.
        titles_not_found_in_omdb: Number of distinct CSV titles that could not
            be matched by the OMDb API and therefore have no ``dim_movie`` row.
        rows_error_movie_not_found: Number of CSV rows whose title could not be
            resolved to any ``dim_movie`` record after OMDb lookup.
        duration_ms: Wall-clock duration of the run in milliseconds.
    """

    facts_inserted: int
    facts_skipped_duplicate: int
    distributors_upserted: int
    dates_created: int
    movies_enriched_from_omdb: int
    titles_not_found_in_omdb: int
    rows_error_movie_not_found: int
    duration_ms: float


class RevenueUploadEtlService:
    """Incremental revenue ETL service for file-upload requests.

    Processes a CSV file uploaded via HTTP. For each movie title absent from
    ``dim_movie``, the service fetches metadata from the OMDb API and persists
    all related dimension and bridge records before inserting the revenue facts.

    If OMDb returns HTTP 401 (invalid API key) or HTTP 429 (daily quota
    exhausted), ``OmdbApiError`` is raised immediately and the entire upload
    is aborted. No partial data is committed.

    Attributes:
        _dim_distributor_repo: Distributor dimension repository.
        _dim_date_repo: Date dimension repository.
        _dim_movie_repo: Movie dimension repository.
        _fact_revenue_repo: Revenue fact repository.
        _dim_rated_repo: MPAA rating dimension repository.
        _dim_genre_repo: Genre dimension repository.
        _dim_director_repo: Director dimension repository.
        _bridge_genre_repo: Movie-genre bridge repository.
        _bridge_director_repo: Movie-director bridge repository.
        _fact_rating_repo: Movie rating fact repository.
        _omdb_client: OMDb API client.

    Example:
        service = RevenueUploadEtlService(
            dim_distributor_repo=distributor_repo,
            dim_date_repo=date_repo,
            dim_movie_repo=movie_repo,
            fact_revenue_repo=revenue_repo,
            dim_rated_repo=rated_repo,
            dim_genre_repo=genre_repo,
            dim_director_repo=director_repo,
            bridge_genre_repo=bridge_genre_repo,
            bridge_director_repo=bridge_director_repo,
            fact_rating_repo=fact_rating_repo,
            omdb_client=omdb_client,
        )
        result = await service.run(csv_bytes)
    """

    __slots__ = (
        "_bridge_director_repo",
        "_bridge_genre_repo",
        "_dim_date_repo",
        "_dim_director_repo",
        "_dim_distributor_repo",
        "_dim_genre_repo",
        "_dim_movie_repo",
        "_dim_rated_repo",
        "_fact_rating_repo",
        "_fact_revenue_repo",
        "_omdb_client",
    )

    def __init__(
        self: "RevenueUploadEtlService",
        dim_distributor_repo: DimDistributorRepositoryProtocol,
        dim_date_repo: DimDateRepositoryProtocol,
        dim_movie_repo: DimMovieRepositoryProtocol,
        fact_revenue_repo: FactRevenueRepositoryProtocol,
        dim_rated_repo: DimRatedRepositoryProtocol,
        dim_genre_repo: DimGenreRepositoryProtocol,
        dim_director_repo: DimDirectorRepositoryProtocol,
        bridge_genre_repo: BridgeMovieGenreRepositoryProtocol,
        bridge_director_repo: BridgeMovieDirectorRepositoryProtocol,
        fact_rating_repo: FactMovieRatingRepositoryProtocol,
        omdb_client: OmdbClientProtocol,
    ) -> None:
        """Initialise the upload ETL service with all required dependencies.

        Args:
            dim_distributor_repo: Repository for ``dim_distributor``.
            dim_date_repo: Repository for ``dim_date``.
            dim_movie_repo: Repository for ``dim_movie``.
            fact_revenue_repo: Repository for ``fact_revenue``.
            dim_rated_repo: Repository for ``dim_rated``.
            dim_genre_repo: Repository for ``dim_genre``.
            dim_director_repo: Repository for ``dim_director``.
            bridge_genre_repo: Repository for ``bridge_movie_genre``.
            bridge_director_repo: Repository for ``bridge_movie_director``.
            fact_rating_repo: Repository for ``fact_movie_rating``.
            omdb_client: OMDb API client satisfying ``OmdbClientProtocol``.
        """
        self._dim_distributor_repo = dim_distributor_repo
        self._dim_date_repo = dim_date_repo
        self._dim_movie_repo = dim_movie_repo
        self._fact_revenue_repo = fact_revenue_repo
        self._dim_rated_repo = dim_rated_repo
        self._dim_genre_repo = dim_genre_repo
        self._dim_director_repo = dim_director_repo
        self._bridge_genre_repo = bridge_genre_repo
        self._bridge_director_repo = bridge_director_repo
        self._fact_rating_repo = fact_rating_repo
        self._omdb_client = omdb_client

    async def run(
        self: "RevenueUploadEtlService",
        csv_bytes: bytes,
    ) -> RevenueUploadEtlResult:
        """Execute the incremental revenue upload ETL pipeline.

        Args:
            csv_bytes: Raw CSV file bytes received from the HTTP upload.

        Returns:
            Summary counts and timing for the run.

        Raises:
            OmdbApiError: When the OMDb API returns HTTP 401 or 429.
            FileNotFoundError: When the temporary CSV file cannot be written.
            ValueError: When the CSV contains unparseable rows.
            OSError: On unexpected I/O failure.
        """
        wall_start = time.perf_counter()
        logger.info("Starting incremental revenue upload ETL", extra={"csv_size_bytes": len(csv_bytes)})

        rows = _parse_csv_bytes(csv_bytes)
        now = _naive_utc_now()

        distributor_map, distributors_upserted = await self._load_distributors(rows, now)
        dates_created = await self._ensure_dates(rows, now)
        title_map = await self._dim_movie_repo.bulk_load_title_map()

        movies_enriched, titles_not_found = await self._enrich_missing_titles(rows, title_map, now)

        date_map = _build_date_id_map(rows)
        facts, errors = _resolve_rows(rows, title_map, distributor_map, date_map, now)

        inserted, skipped = await self._insert_facts(facts)

        duration_ms = (time.perf_counter() - wall_start) * 1000
        result = RevenueUploadEtlResult(
            facts_inserted=inserted,
            facts_skipped_duplicate=skipped,
            distributors_upserted=distributors_upserted,
            dates_created=dates_created,
            movies_enriched_from_omdb=movies_enriched,
            titles_not_found_in_omdb=titles_not_found,
            rows_error_movie_not_found=len(errors),
            duration_ms=duration_ms,
        )
        logger.info(
            "Incremental revenue upload ETL finished",
            extra={
                "facts_inserted": result.facts_inserted,
                "facts_skipped_duplicate": result.facts_skipped_duplicate,
                "distributors_upserted": result.distributors_upserted,
                "dates_created": result.dates_created,
                "movies_enriched_from_omdb": result.movies_enriched_from_omdb,
                "titles_not_found_in_omdb": result.titles_not_found_in_omdb,
                "rows_error_movie_not_found": result.rows_error_movie_not_found,
                "duration_ms": result.duration_ms,
            },
        )
        return result

    async def _load_distributors(
        self: "RevenueUploadEtlService",
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
        self: "RevenueUploadEtlService",
        rows: list[RawRevenueRow],
        now: datetime.datetime,
    ) -> int:
        """Ensure every distinct date in the CSV exists in ``dim_date``.

        Args:
            rows: Parsed revenue rows.
            now: Unused; retained for symmetry with the init load service.

        Returns:
            Number of ``dim_date`` rows created during this run.
        """
        _ = now
        dates = collect_unique_dates(rows)
        created = 0

        for date_value in sorted(dates):
            date_id = compute_date_id(date_value)
            existing = await self._dim_date_repo.get_by_id(date_id)
            if existing is None:
                dto = build_dim_date_dto(date_value)
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

    async def _enrich_missing_titles(
        self: "RevenueUploadEtlService",
        rows: list[RawRevenueRow],
        title_map: dict[str, int],
        now: datetime.datetime,
    ) -> tuple[int, int]:
        """Fetch OMDb metadata for titles absent from ``dim_movie``.

        Mutates ``title_map`` in place: after each successful OMDb fetch and
        dimension upsert, the new ``title → movie_id`` mapping is added so
        that subsequent rows for the same title resolve without an additional
        DB query.

        Args:
            rows: Parsed revenue rows.
            title_map: Mutable uppercase-keyed ``title → movie_id`` map loaded
                from the database. Extended in place as new movies are persisted.
            now: Load timestamp for ``loaded_at``.

        Returns:
            A tuple of ``(movies_enriched, titles_not_found_in_omdb)``.

        Raises:
            OmdbApiError: When the OMDb API returns HTTP 401 or 429.
        """
        missing_titles: set[str] = {
            row.title for row in rows if row.title.upper() not in title_map
        }

        if not missing_titles:
            logger.info("All CSV titles resolved from dim_movie; no OMDb calls required")
            return 0, 0

        logger.info(
            "Fetching OMDb metadata for missing titles",
            extra={"missing_count": len(missing_titles)},
        )

        enriched = 0
        not_found = 0

        for title in sorted(missing_titles):
            outcome = await self._omdb_client.fetch_by_title_detailed(title)

            if outcome.error_reason == OMDB_RATE_LIMIT_ERROR_REASON:
                raise OmdbApiError(
                    status_code=_HTTP_STATUS_RATE_LIMIT,
                    message=outcome.error_message or "OMDb daily request limit reached.",
                )

            if outcome.error_reason == "http_error":
                error_msg = outcome.error_message or ""
                if "401" in error_msg or "Unauthorized" in error_msg.lower():
                    raise OmdbApiError(
                        status_code=_HTTP_STATUS_UNAUTHORIZED,
                        message=error_msg or "OMDb API key is invalid or unauthorized.",
                    )

            if outcome.movie is None:
                logger.warning(
                    "OMDb title not found; row will be recorded as error",
                    extra={"title": title, "error_reason": outcome.error_reason},
                )
                not_found += 1
                continue

            movie_id = await _persist_omdb_record(
                movie=outcome.movie,
                now=now,
                dim_rated_repo=self._dim_rated_repo,
                dim_genre_repo=self._dim_genre_repo,
                dim_director_repo=self._dim_director_repo,
                dim_movie_repo=self._dim_movie_repo,
                bridge_genre_repo=self._bridge_genre_repo,
                bridge_director_repo=self._bridge_director_repo,
                fact_rating_repo=self._fact_rating_repo,
            )

            if movie_id is not None:
                title_map[outcome.movie.title.upper()] = movie_id
                enriched += 1
                logger.info(
                    "OMDb record persisted",
                    extra={"title": outcome.movie.title, "movie_id": movie_id},
                )

        return enriched, not_found

    async def _insert_facts(
        self: "RevenueUploadEtlService",
        dtos: list[FactRevenueDto],
    ) -> tuple[int, int]:
        """Batch-insert fact records, skipping existing ``source_row_id`` values.

        Args:
            dtos: Fact records to insert.

        Returns:
            A tuple of ``(inserted_count, skipped_count)``.
        """
        if not dtos:
            return 0, 0

        total_inserted = 0
        for offset in range(0, len(dtos), _FACT_BATCH_SIZE):
            batch = dtos[offset: offset + _FACT_BATCH_SIZE]
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


async def _persist_omdb_record(
    movie: OmdbMovieResponse,
    now: datetime.datetime,
    dim_rated_repo: DimRatedRepositoryProtocol,
    dim_genre_repo: DimGenreRepositoryProtocol,
    dim_director_repo: DimDirectorRepositoryProtocol,
    dim_movie_repo: DimMovieRepositoryProtocol,
    bridge_genre_repo: BridgeMovieGenreRepositoryProtocol,
    bridge_director_repo: BridgeMovieDirectorRepositoryProtocol,
    fact_rating_repo: FactMovieRatingRepositoryProtocol,
) -> int | None:
    """Persist a single OMDb response into all relevant dimension and fact tables.

    Mirrors the logic of ``OmdbDwhInitLoadService`` for a single record.
    Operates on an already-validated ``OmdbMovieResponse`` rather than reading
    from a JSON file.

    Args:
        movie: Validated OMDb API response for one title.
        now: Load timestamp applied to all ``loaded_at`` fields.
        dim_rated_repo: Repository for ``dim_rated``.
        dim_genre_repo: Repository for ``dim_genre``.
        dim_director_repo: Repository for ``dim_director``.
        dim_movie_repo: Repository for ``dim_movie``.
        bridge_genre_repo: Repository for ``bridge_movie_genre``.
        bridge_director_repo: Repository for ``bridge_movie_director``.
        fact_rating_repo: Repository for ``fact_movie_rating``.

    Returns:
        The surrogate ``movie_id`` assigned by the database, or ``None`` when
        the upsert did not return an ID.
    """
    rated_id: int | None = None
    if movie.rated and movie.rated.strip():
        rated_code = movie.rated.strip()
        rated_dto = DimRatedDto(
            rated_id=None,
            rating_code=rated_code,
            rating_description=get_rating_description(rated_code),
            loaded_at=now,
        )
        persisted_rated = await dim_rated_repo.upsert(rated_dto)
        rated_id = persisted_rated.rated_id

    genre_map: dict[str, int] = {}
    for genre_name in split_csv_field(movie.genre):
        dto = DimGenreDto(genre_id=None, genre_name=genre_name, loaded_at=now)
        persisted = await dim_genre_repo.upsert(dto)
        if persisted.genre_id is not None:
            genre_map[genre_name] = persisted.genre_id

    director_map: dict[str, int] = {}
    for director_name in split_csv_field(movie.director):
        dto = DimDirectorDto(director_id=None, director_name=director_name, loaded_at=now)
        persisted = await dim_director_repo.upsert(dto)
        if persisted.director_id is not None:
            director_map[director_name] = persisted.director_id

    movie_dto = DimMovieDto(
        movie_id=None,
        imdb_id=movie.imdb_id,
        title=movie.title,
        release_year=movie.year,
        rated_id=rated_id,
        runtime_min=movie.runtime_min,
        plot=movie.plot,
        awards=movie.awards,
        box_office_omdb=movie.box_office,
        omdb_fetched_at=now,
        loaded_at=now,
    )
    persisted_movie = await dim_movie_repo.upsert(movie_dto)
    movie_id = persisted_movie.movie_id

    if movie_id is None:
        return None

    genre_dtos = [
        BridgeMovieGenreDto(movie_id=movie_id, genre_id=gid, loaded_at=now)
        for gid in genre_map.values()
    ]
    director_dtos = [
        BridgeMovieDirectorDto(movie_id=movie_id, director_id=did, loaded_at=now)
        for did in director_map.values()
    ]

    if genre_dtos:
        await bridge_genre_repo.bulk_upsert(genre_dtos)
    if director_dtos:
        await bridge_director_repo.bulk_upsert(director_dtos)

    if movie.imdb_rating is not None:
        new_rating = _decimal_or_none(movie.imdb_rating)
        current = await fact_rating_repo.get_current_rating(movie_id)
        if current is None or not _ratings_are_equal(current, new_rating, movie.imdb_votes):
            rating_dto = FactMovieRatingDto(
                rating_id=None,
                movie_id=movie_id,
                imdb_rating=new_rating,
                imdb_votes=movie.imdb_votes,
                valid_from=now,
                valid_to=None,
                is_current=True,
                loaded_at=now,
            )
            await fact_rating_repo.insert_new_rating(rating_dto)

    return movie_id


def _parse_csv_bytes(csv_bytes: bytes) -> list[RawRevenueRow]:
    """Write CSV bytes to a temporary file and parse them into row objects.

    The temporary file is deleted immediately after parsing, regardless of
    whether parsing succeeds or raises.

    Args:
        csv_bytes: Raw CSV content as bytes.

    Returns:
        List of parsed ``RawRevenueRow`` instances.

    Raises:
        FileNotFoundError: When the temporary file cannot be created.
        ValueError: When the CSV contains unparseable rows.
        OSError: On I/O failure during temporary file operations.
    """
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(csv_bytes)

    try:
        return read_revenues_csv(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to delete temporary CSV file", extra={"path": str(tmp_path)})


def _resolve_rows(
    rows: list[RawRevenueRow],
    title_map: dict[str, int],
    distributor_map: dict[str, int],
    date_map: dict[datetime.date, int],
    now: datetime.datetime,
) -> tuple[list[FactRevenueDto], list[dict[str, object]]]:
    """Resolve dimension keys and partition rows into facts and error records.

    Args:
        rows: All parsed revenue rows.
        title_map: Uppercase-keyed ``title → movie_id`` map (may include
            titles added during OMDb enrichment in the current run).
        distributor_map: ``distributor_name → distributor_id`` map.
        date_map: ``date → date_id`` built from the CSV rows.
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

        effective_distributor = (
            row.distributor if row.distributor is not None else UNKNOWN_DISTRIBUTOR_NAME
        )
        distributor_id = distributor_map.get(effective_distributor)
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


def _decimal_or_none(value: float | None) -> Decimal | None:
    """Convert a float to ``Decimal`` with one decimal place, or return ``None``.

    Args:
        value: Float value to convert, or ``None``.

    Returns:
        ``Decimal`` rounded to one decimal place, or ``None`` when the input
        is ``None`` or cannot be converted.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.1"))
    except InvalidOperation:
        return None


def _ratings_are_equal(
    current: FactMovieRatingDto,
    new_rating: Decimal | None,
    new_votes: int | None,
) -> bool:
    """Return ``True`` when rating and vote counts match the current row.

    Args:
        current: The active rating snapshot retrieved from the database.
        new_rating: Freshly fetched IMDb rating as ``Decimal``.
        new_votes: Freshly fetched IMDb vote count.

    Returns:
        ``True`` when both values are identical to the current record.
    """
    current_rating = current.imdb_rating
    if current_rating is not None:
        current_rating = current_rating.quantize(Decimal("0.1"))
    if new_rating is not None:
        new_rating = new_rating.quantize(Decimal("0.1"))
    return current_rating == new_rating and current.imdb_votes == new_votes


def _naive_utc_now() -> datetime.datetime:
    """Return the current UTC time as a naive datetime.

    PostgreSQL ``TIMESTAMP WITHOUT TIME ZONE`` columns require naive values.

    Returns:
        Current UTC time with ``tzinfo`` stripped.
    """
    return datetime.datetime.now(tz=datetime.UTC).replace(tzinfo=None)
