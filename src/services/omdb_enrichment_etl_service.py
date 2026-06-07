"""ETL service for bulk OMDb enrichment of unique movie titles.

Reads movie titles from the revenue-by-title master CSV (highest revenue
first), fetches metadata from the OMDb API, and writes:

- ``data/raw/omdb_titles_init_result.json`` — successful lookups
- ``data/raw/omdb_titles_init_errorlog.json`` — titles with no match or
  request failure (created only when at least one title fails)

With ``resume=True``, titles already present in the result JSON are skipped,
new lookups are merged into the existing files, and previously failed titles
are retried.

Usage::

    from src.services.omdb_enrichment_etl_service import OmdbEnrichmentEtlService

    service = OmdbEnrichmentEtlService(omdb_client=client)
    result = await service.run(resume=True)
"""

import asyncio
import datetime
import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from loguru import logger

from src.interfaces.omdb_client_protocol import OmdbClientProtocol
from src.models.omdb import OMDB_RATE_LIMIT_ERROR_REASON, OmdbTitleFetchOutcome
from src.utils.title_encoding import decode_embedded_unicode_escapes

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR: Path = PROJECT_ROOT / "data" / "raw"
DEFAULT_MASTER_DIR: Path = PROJECT_ROOT / "data" / "master"
DEFAULT_REVENUE_BY_TITLE_CSV: Path = DEFAULT_MASTER_DIR / "revenue_by_title.csv"
DEFAULT_OMDB_RESULT_JSON: Path = DEFAULT_RAW_DIR / "omdb_titles_init_result.json"
DEFAULT_OMDB_ERRORLOG_JSON: Path = DEFAULT_RAW_DIR / "omdb_titles_init_errorlog.json"

_MASTER_CSV_SCHEMA: dict[str, pl.DataType] = {
    "title": pl.String,
    "total_revenue": pl.Int64,
}

_HTTP_TIMEOUT_SECONDS: float = 30.0
_REQUEST_DELAY_SECONDS: float = 0.1


@dataclass(frozen=True, slots=True)
class OmdbEnrichmentEtlResult:
    """Summary of an OMDb enrichment ETL run.

    Attributes:
        result_path: Path to the successful-results JSON file.
        errorlog_path: Path to the error log when failures occurred, else
            ``None``.
        total_titles: Number of unique titles in the source file.
        processed_count: Number of titles attempted in this run.
        skipped_count: Number of source titles skipped because they already
            exist in the result JSON (resume mode only).
        success_count: Number of successful API lookups in this run.
        error_count: Number of failed lookups in this run.
        stopped_due_to_rate_limit: ``True`` when the run halted after an
            OMDb quota error.
    """

    result_path: Path
    errorlog_path: Path | None
    total_titles: int
    processed_count: int
    skipped_count: int
    success_count: int
    error_count: int
    stopped_due_to_rate_limit: bool


class OmdbEnrichmentEtlService:
    """Fetch OMDb metadata for titles ranked by total box office revenue.

    Each successful record stores the ``request_title`` alongside the
    validated API payload so downstream loaders can reconcile titles that
    differ from OMDb's canonical spelling.

    Attributes:
        _omdb_client: Injected OMDb HTTP client.
        _revenue_by_title_csv_path: Master CSV listing titles by revenue.
        _result_json_path: Output path for successful lookups.
        _errorlog_json_path: Output path for failed lookups.
        _request_delay_seconds: Pause between consecutive API calls.
    """

    __slots__ = (
        "_errorlog_json_path",
        "_omdb_client",
        "_request_delay_seconds",
        "_result_json_path",
        "_revenue_by_title_csv_path",
    )

    def __init__(
        self: "OmdbEnrichmentEtlService",
        omdb_client: OmdbClientProtocol,
        revenue_by_title_csv_path: Path | None = None,
        result_json_path: Path | None = None,
        errorlog_json_path: Path | None = None,
        request_delay_seconds: float = _REQUEST_DELAY_SECONDS,
    ) -> None:
        """Initialise the ETL service.

        Args:
            omdb_client: Client used for OMDb title lookups.
            revenue_by_title_csv_path: Master CSV path with ``title`` and
                ``total_revenue`` columns. Defaults to
                ``data/master/revenue_by_title.csv``.
            result_json_path: Successful results JSON path.
            errorlog_json_path: Failed lookups JSON path.
            request_delay_seconds: Delay between API calls to reduce rate-
                limit pressure on the OMDb free tier.
        """
        self._omdb_client = omdb_client
        self._revenue_by_title_csv_path = (
            revenue_by_title_csv_path or DEFAULT_REVENUE_BY_TITLE_CSV
        )
        self._result_json_path = result_json_path or DEFAULT_OMDB_RESULT_JSON
        self._errorlog_json_path = errorlog_json_path or DEFAULT_OMDB_ERRORLOG_JSON
        self._request_delay_seconds = request_delay_seconds

    def extract_titles_by_revenue(self: "OmdbEnrichmentEtlService") -> list[str]:
        """Return movie titles ordered by descending total revenue.

        Returns:
            Title strings sorted from highest to lowest ``total_revenue``.

        Raises:
            FileNotFoundError: When the master CSV does not exist.
            ValueError: When the file contains no titles.
        """
        if not self._revenue_by_title_csv_path.is_file():
            raise FileNotFoundError(
                f"Revenue-by-title master CSV not found: {self._revenue_by_title_csv_path}"
            )

        titles = (
            pl.scan_csv(self._revenue_by_title_csv_path, schema_overrides=_MASTER_CSV_SCHEMA)
            .sort("total_revenue", descending=True)
            .select("title")
            .collect()
            .get_column("title")
            .to_list()
        )
        if not titles:
            raise ValueError(f"No titles found in {self._revenue_by_title_csv_path}")

        return [str(title) for title in titles]

    async def run(
        self: "OmdbEnrichmentEtlService",
        *,
        resume: bool = False,
    ) -> OmdbEnrichmentEtlResult:
        """Process titles from the master CSV and write JSON output files.

        Args:
            resume: When ``True``, load existing result and error JSON files,
                skip titles already present in the result file, merge new
                records into those files instead of overwriting them, and
                retry titles that previously failed.

        Returns:
            Summary of the ETL run including output paths and counts.

        Raises:
            FileNotFoundError: When the master CSV is missing.
            ValueError: When no titles are found in the source file or when
                an existing JSON output file has an invalid root type.
        """
        all_titles = self.extract_titles_by_revenue()
        existing_successes = _load_record_list(self._result_json_path) if resume else []
        existing_errors = _load_record_list(self._errorlog_json_path) if resume else []

        if resume:
            successful_titles = _collect_normalized_request_titles(existing_successes)
            titles = [
                title
                for title in all_titles
                if _normalize_title_for_match(title) not in successful_titles
            ]
            skipped_count = len(all_titles) - len(titles)
        else:
            titles = all_titles
            skipped_count = 0

        logger.info(
            "Starting OMDb enrichment ETL",
            extra={
                "title_count": len(all_titles),
                "pending_count": len(titles),
                "skipped_count": skipped_count,
                "resume": resume,
                "source": str(self._revenue_by_title_csv_path),
            },
        )

        new_successes: list[dict[str, object]] = []
        new_errors: list[dict[str, object]] = []
        stopped_due_to_rate_limit = False
        processed_count = 0

        for index, title in enumerate(titles, start=1):
            outcome = await self._fetch_title(title)
            fetched_at = datetime.datetime.now(tz=datetime.UTC).isoformat()
            processed_count = index

            if outcome.movie is not None:
                new_successes.append(_success_record(outcome, fetched_at))
            else:
                new_errors.append(_error_record(outcome, fetched_at))
                if outcome.error_reason == OMDB_RATE_LIMIT_ERROR_REASON:
                    stopped_due_to_rate_limit = True
                    logger.error(
                        "OMDb rate limit reached, stopping enrichment ETL",
                        extra={
                            "request_title": outcome.request_title,
                            "processed_count": processed_count,
                            "total_titles": len(titles),
                            "error_message": outcome.error_message,
                        },
                    )
                    break

            if not stopped_due_to_rate_limit and index < len(titles):
                if self._request_delay_seconds > 0:
                    await asyncio.sleep(self._request_delay_seconds)

            if not stopped_due_to_rate_limit and index % 100 == 0:
                logger.info(
                    "OMDb enrichment progress",
                    extra={
                        "processed": index,
                        "total": len(titles),
                        "success_count": len(new_successes),
                        "error_count": len(new_errors),
                    },
                )

        if resume:
            merged_successes = _merge_success_records(existing_successes, new_successes)
            successful_titles = _collect_normalized_request_titles(merged_successes)
            merged_errors = _merge_error_records(
                existing_errors,
                new_errors,
                successful_titles,
                normalize_keys=True,
            )
        else:
            merged_successes = new_successes
            merged_errors = new_errors

        errorlog_path = self._persist_outputs(merged_successes, merged_errors)

        result = OmdbEnrichmentEtlResult(
            result_path=self._result_json_path,
            errorlog_path=errorlog_path,
            total_titles=len(all_titles),
            processed_count=processed_count,
            skipped_count=skipped_count,
            success_count=len(new_successes),
            error_count=len(new_errors),
            stopped_due_to_rate_limit=stopped_due_to_rate_limit,
        )
        log_method = logger.warning if stopped_due_to_rate_limit else logger.info
        log_method(
            "OMDb enrichment ETL finished",
            extra={
                "result_path": str(result.result_path),
                "errorlog_path": str(result.errorlog_path) if result.errorlog_path else None,
                "total_titles": result.total_titles,
                "processed_count": result.processed_count,
                "skipped_count": result.skipped_count,
                "success_count": result.success_count,
                "error_count": result.error_count,
                "stopped_due_to_rate_limit": result.stopped_due_to_rate_limit,
            },
        )
        return result

    def _persist_outputs(
        self: "OmdbEnrichmentEtlService",
        successes: list[dict[str, object]],
        errors: list[dict[str, object]],
    ) -> Path | None:
        """Write result and error JSON files.

        Args:
            successes: Successful lookup records.
            errors: Failed lookup records.

        Returns:
            Error log path when failures were written, otherwise ``None``.
        """
        self._result_json_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(self._result_json_path, successes)

        if not errors:
            if self._errorlog_json_path.is_file():
                self._errorlog_json_path.unlink()
            return None

        self._write_json(self._errorlog_json_path, errors)
        return self._errorlog_json_path

    async def _fetch_title(
        self: "OmdbEnrichmentEtlService",
        title: str,
    ) -> OmdbTitleFetchOutcome:
        """Fetch a single title, delegating to the injected client.

        Args:
            title: Movie title to look up.

        Returns:
            ``OmdbTitleFetchOutcome`` with success or failure details.
        """
        return await self._omdb_client.fetch_by_title_detailed(title)

    @staticmethod
    def _write_json(path: Path, records: list[dict[str, object]]) -> None:
        """Serialize records to a UTF-8 JSON file.

        Args:
            path: Destination file path.
            records: JSON-serialisable record list.
        """
        path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _load_record_list(path: Path) -> list[dict[str, object]]:
    """Load a JSON array file of enrichment records.

    Args:
        path: Path to the result or error log JSON file.

    Returns:
        List of record dicts. Returns an empty list when the file does not
        exist.

    Raises:
        ValueError: When the file root is not a JSON array.
    """
    if not path.is_file():
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array at root of {path}")

    records: list[dict[str, object]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            records.append(item)
        else:
            logger.warning(
                "Skipping non-object entry in enrichment JSON",
                extra={"path": str(path), "index": index},
            )
    return records


def _normalize_title_for_match(title: str) -> str:
    """Normalise a title for resume matching across encoding variants.

    Args:
        title: Raw or decoded title string.

    Returns:
        Title with embedded ``uXXXX`` escape sequences decoded.
    """
    return decode_embedded_unicode_escapes(title)


def _collect_request_titles(records: list[dict[str, object]]) -> set[str]:
    """Collect raw ``request_title`` values from enrichment JSON records.

    Args:
        records: Result or error records loaded from disk.

    Returns:
        Set of non-empty request title strings.
    """
    titles: set[str] = set()
    for record in records:
        title = record.get("request_title")
        if isinstance(title, str) and title:
            titles.add(title)
    return titles


def _collect_normalized_request_titles(records: list[dict[str, object]]) -> set[str]:
    """Collect normalised ``request_title`` values for resume comparisons.

    Args:
        records: Result or error records loaded from disk.

    Returns:
        Set of normalised request title strings.
    """
    return {_normalize_title_for_match(title) for title in _collect_request_titles(records)}


def _merge_success_records(
    existing: list[dict[str, object]],
    new_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Append new successful lookups to existing result records.

    Args:
        existing: Records already stored in the result JSON file.
        new_records: Successful lookups from the current run.

    Returns:
        Combined list preserving existing order and appending new records.
    """
    return existing + new_records


def _merge_error_records(
    existing: list[dict[str, object]],
    new_records: list[dict[str, object]],
    successful_titles: set[str],
    *,
    normalize_keys: bool = False,
) -> list[dict[str, object]]:
    """Merge error records and drop titles that now have a success entry.

    When a title is retried successfully, its previous error row is removed.
    For duplicate error rows, the record from the current run wins.

    Args:
        existing: Records already stored in the error log JSON file.
        new_records: Failed lookups from the current run.
        successful_titles: Titles present in the merged success file. When
            ``normalize_keys`` is ``True``, values are normalised titles.
        normalize_keys: Compare and key records using normalised titles.

    Returns:
        De-duplicated error records sorted by ``request_title``.
    """
    by_title: dict[str, dict[str, object]] = {}

    def _match_key(title: str) -> str:
        return _normalize_title_for_match(title) if normalize_keys else title

    def _is_successful(title: str) -> bool:
        key = _match_key(title)
        return key in successful_titles

    for record in existing:
        title = record.get("request_title")
        if isinstance(title, str) and title and not _is_successful(title):
            by_title[_match_key(title)] = record

    for record in new_records:
        title = record.get("request_title")
        if isinstance(title, str) and title and not _is_successful(title):
            by_title[_match_key(title)] = record

    return [
        by_title[key]
        for key in sorted(
            by_title,
            key=lambda normalized: str(by_title[normalized].get("request_title", normalized)),
        )
    ]


def _success_record(
    outcome: OmdbTitleFetchOutcome,
    fetched_at: str,
) -> dict[str, object]:
    """Build a JSON record for a successful OMDb lookup."""
    assert outcome.movie is not None
    return {
        "request_title": outcome.request_title,
        "fetched_at": fetched_at,
        "omdb_title": outcome.movie.title,
        "data": outcome.movie.model_dump(mode="json", by_alias=False),
    }


def _error_record(
    outcome: OmdbTitleFetchOutcome,
    fetched_at: str,
) -> dict[str, object]:
    """Build a JSON record for a failed OMDb lookup."""
    record: dict[str, object] = {
        "request_title": outcome.request_title,
        "fetched_at": fetched_at,
        "error_reason": outcome.error_reason or "no_match_or_error",
    }
    if outcome.error_message is not None:
        record["error_message"] = outcome.error_message
    return record

