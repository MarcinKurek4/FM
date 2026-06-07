"""Unit tests for the OMDb enrichment ETL service."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.models.omdb import (
    OMDB_RATE_LIMIT_ERROR_REASON,
    OmdbMovieResponse,
    OmdbTitleFetchOutcome,
)
from src.services.omdb_enrichment_etl_service import OmdbEnrichmentEtlService


class _FakeOmdbClient:
    """Stub OMDb client for ETL unit tests."""

    __slots__ = ("_fetch_order", "_responses")

    def __init__(
        self,
        responses: dict[str, OmdbTitleFetchOutcome],
        fetch_order: list[str] | None = None,
    ) -> None:
        self._responses = responses
        self._fetch_order = fetch_order

    async def fetch_by_title(self, title: str) -> OmdbMovieResponse | None:
        outcome = await self.fetch_by_title_detailed(title)
        return outcome.movie

    async def fetch_by_title_detailed(self, title: str) -> OmdbTitleFetchOutcome:
        if self._fetch_order is not None:
            self._fetch_order.append(title)
        return self._responses[title]


@pytest.fixture
def revenue_by_title_csv_for_omdb_etl(tmp_path: Path) -> Path:
    """Write a minimal revenue-by-title master CSV."""
    csv_path = tmp_path / "revenue_by_title.csv"
    csv_path.write_text(
        "title,total_revenue\n"
        "Alpha,300\n"
        "Beta,200\n",
        encoding="utf-8",
    )
    return csv_path


def _movie(title: str, imdb_id: str) -> OmdbMovieResponse:
    return OmdbMovieResponse.model_validate(
        {
            "Title": title,
            "Year": "2004",
            "imdbID": imdb_id,
            "Response": "True",
        }
    )


@pytest.mark.asyncio
async def test_extract_titles_by_revenue_returns_descending_order(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "revenue_by_title.csv"
    csv_path.write_text(
        "title,total_revenue\n"
        "Alpha,100\n"
        "Beta,300\n"
        "Gamma,200\n",
        encoding="utf-8",
    )
    service = OmdbEnrichmentEtlService(
        omdb_client=_FakeOmdbClient({}),
        revenue_by_title_csv_path=csv_path,
        request_delay_seconds=0,
    )

    titles = service.extract_titles_by_revenue()

    assert titles == ["Beta", "Gamma", "Alpha"]


@pytest.mark.asyncio
async def test_run_writes_result_and_errorlog_with_request_title(
    revenue_by_title_csv_for_omdb_etl: Path,
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "omdb_titles_init_result.json"
    errorlog_path = tmp_path / "omdb_titles_init_errorlog.json"
    client = _FakeOmdbClient(
        {
            "Alpha": OmdbTitleFetchOutcome(
                request_title="Alpha",
                movie=_movie("Alpha Movie", "tt0000001"),
            ),
            "Beta": OmdbTitleFetchOutcome(
                request_title="Beta",
                movie=None,
                error_reason="not_found",
            ),
        }
    )
    service = OmdbEnrichmentEtlService(
        omdb_client=client,
        revenue_by_title_csv_path=revenue_by_title_csv_for_omdb_etl,
        result_json_path=result_path,
        errorlog_json_path=errorlog_path,
        request_delay_seconds=0,
    )

    result = await service.run()

    assert result.total_titles == 2
    assert result.success_count == 1
    assert result.error_count == 1
    assert result.errorlog_path == errorlog_path

    successes = json.loads(result_path.read_text(encoding="utf-8"))
    assert successes[0]["request_title"] == "Alpha"
    assert successes[0]["omdb_title"] == "Alpha Movie"
    assert successes[0]["data"]["imdb_id"] == "tt0000001"

    errors = json.loads(errorlog_path.read_text(encoding="utf-8"))
    assert errors[0]["request_title"] == "Beta"
    assert errors[0]["error_reason"] == "not_found"


@pytest.mark.asyncio
async def test_run_processes_highest_revenue_title_first(tmp_path: Path) -> None:
    csv_path = tmp_path / "revenue_by_title.csv"
    csv_path.write_text(
        "title,total_revenue\n"
        "Alpha,100\n"
        "Beta,300\n"
        "Gamma,200\n",
        encoding="utf-8",
    )
    result_path = tmp_path / "omdb_titles_init_result.json"
    errorlog_path = tmp_path / "omdb_titles_init_errorlog.json"
    fetch_order: list[str] = []
    client = _FakeOmdbClient(
        {
            "Beta": OmdbTitleFetchOutcome(
                request_title="Beta",
                movie=_movie("Beta Movie", "tt0000002"),
            ),
            "Gamma": OmdbTitleFetchOutcome(
                request_title="Gamma",
                movie=_movie("Gamma Movie", "tt0000003"),
            ),
            "Alpha": OmdbTitleFetchOutcome(
                request_title="Alpha",
                movie=_movie("Alpha Movie", "tt0000001"),
            ),
        },
        fetch_order=fetch_order,
    )
    service = OmdbEnrichmentEtlService(
        omdb_client=client,
        revenue_by_title_csv_path=csv_path,
        result_json_path=result_path,
        errorlog_json_path=errorlog_path,
        request_delay_seconds=0,
    )

    await service.run()

    assert fetch_order == ["Beta", "Gamma", "Alpha"]


@pytest.mark.asyncio
async def test_run_skips_errorlog_when_all_titles_succeed(
    revenue_by_title_csv_for_omdb_etl: Path,
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "omdb_titles_init_result.json"
    errorlog_path = tmp_path / "omdb_titles_init_errorlog.json"
    client = _FakeOmdbClient(
        {
            "Alpha": OmdbTitleFetchOutcome(
                request_title="Alpha",
                movie=_movie("Alpha Movie", "tt0000001"),
            ),
            "Beta": OmdbTitleFetchOutcome(
                request_title="Beta",
                movie=_movie("Beta Movie", "tt0000002"),
            ),
        }
    )
    service = OmdbEnrichmentEtlService(
        omdb_client=client,
        revenue_by_title_csv_path=revenue_by_title_csv_for_omdb_etl,
        result_json_path=result_path,
        errorlog_json_path=errorlog_path,
        request_delay_seconds=0,
    )

    result = await service.run()

    assert result.errorlog_path is None
    assert not errorlog_path.exists()
    assert len(json.loads(result_path.read_text(encoding="utf-8"))) == 2


@pytest.mark.asyncio
async def test_run_stops_when_rate_limit_is_reached(tmp_path: Path) -> None:
    csv_path = tmp_path / "revenue_by_title.csv"
    csv_path.write_text(
        "title,total_revenue\n"
        "Alpha,100\n"
        "Beta,200\n"
        "Gamma,300\n",
        encoding="utf-8",
    )
    result_path = tmp_path / "omdb_titles_init_result.json"
    errorlog_path = tmp_path / "omdb_titles_init_errorlog.json"
    client = _FakeOmdbClient(
        {
            "Gamma": OmdbTitleFetchOutcome(
                request_title="Gamma",
                movie=None,
                error_reason=OMDB_RATE_LIMIT_ERROR_REASON,
                error_message="Request limit reached!",
            ),
            "Beta": OmdbTitleFetchOutcome(
                request_title="Beta",
                movie=_movie("Beta Movie", "tt0000002"),
            ),
            "Alpha": OmdbTitleFetchOutcome(
                request_title="Alpha",
                movie=_movie("Alpha Movie", "tt0000001"),
            ),
        }
    )
    service = OmdbEnrichmentEtlService(
        omdb_client=client,
        revenue_by_title_csv_path=csv_path,
        result_json_path=result_path,
        errorlog_json_path=errorlog_path,
        request_delay_seconds=0,
    )

    result = await service.run()

    assert result.processed_count == 1
    assert result.success_count == 0
    assert result.error_count == 1
    assert result.stopped_due_to_rate_limit is True
    assert json.loads(result_path.read_text(encoding="utf-8")) == []
    errors = json.loads(errorlog_path.read_text(encoding="utf-8"))
    assert len(errors) == 1
    assert errors[0]["request_title"] == "Gamma"
    assert errors[0]["error_reason"] == OMDB_RATE_LIMIT_ERROR_REASON


@pytest.mark.asyncio
async def test_run_resume_skips_existing_successes_and_merges_files(
    revenue_by_title_csv_for_omdb_etl: Path,
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "omdb_titles_init_result.json"
    errorlog_path = tmp_path / "omdb_titles_init_errorlog.json"
    result_path.write_text(
        json.dumps(
            [
                {
                    "request_title": "Alpha",
                    "fetched_at": "2026-06-05T10:00:00+00:00",
                    "omdb_title": "Alpha Movie",
                    "data": {
                        "title": "Alpha Movie",
                        "imdb_id": "tt0000001",
                        "response": True,
                    },
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    errorlog_path.write_text(
        json.dumps(
            [
                {
                    "request_title": "Beta",
                    "fetched_at": "2026-06-05T10:00:00+00:00",
                    "error_reason": "http_error",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    client = _FakeOmdbClient(
        {
            "Beta": OmdbTitleFetchOutcome(
                request_title="Beta",
                movie=_movie("Beta Movie", "tt0000002"),
            ),
        }
    )
    service = OmdbEnrichmentEtlService(
        omdb_client=client,
        revenue_by_title_csv_path=revenue_by_title_csv_for_omdb_etl,
        result_json_path=result_path,
        errorlog_json_path=errorlog_path,
        request_delay_seconds=0,
    )

    result = await service.run(resume=True)

    assert result.total_titles == 2
    assert result.skipped_count == 1
    assert result.processed_count == 1
    assert result.success_count == 1
    assert result.error_count == 0

    successes = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(successes) == 2
    assert successes[0]["request_title"] == "Alpha"
    assert successes[1]["request_title"] == "Beta"
    assert not errorlog_path.exists()


@pytest.mark.asyncio
async def test_run_resume_skips_titles_with_legacy_unicode_escape_in_result(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "revenue_by_title.csv"
    csv_path.write_text(
        "title,total_revenue\n"
        "Tár,1000\n",
        encoding="utf-8",
    )
    result_path = tmp_path / "omdb_titles_init_result.json"
    errorlog_path = tmp_path / "omdb_titles_init_errorlog.json"
    result_path.write_text(
        json.dumps(
            [
                {
                    "request_title": "Tu00e1r",
                    "fetched_at": "2026-06-05T10:00:00+00:00",
                    "omdb_title": "Tár",
                    "data": {
                        "title": "Tár",
                        "imdb_id": "tt0000001",
                        "response": True,
                    },
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    client = AsyncMock()
    service = OmdbEnrichmentEtlService(
        omdb_client=client,
        revenue_by_title_csv_path=csv_path,
        result_json_path=result_path,
        errorlog_json_path=errorlog_path,
        request_delay_seconds=0,
    )

    result = await service.run(resume=True)

    assert result.skipped_count == 1
    assert result.processed_count == 0
    client.fetch_by_title_detailed.assert_not_called()


@pytest.mark.asyncio
async def test_run_resume_makes_no_api_calls_when_all_titles_succeeded(
    revenue_by_title_csv_for_omdb_etl: Path,
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "omdb_titles_init_result.json"
    errorlog_path = tmp_path / "omdb_titles_init_errorlog.json"
    result_path.write_text(
        json.dumps(
            [
                {
                    "request_title": "Alpha",
                    "fetched_at": "2026-06-05T10:00:00+00:00",
                    "omdb_title": "Alpha Movie",
                    "data": {"title": "Alpha Movie", "imdb_id": "tt0000001", "response": True},
                },
                {
                    "request_title": "Beta",
                    "fetched_at": "2026-06-05T10:00:01+00:00",
                    "omdb_title": "Beta Movie",
                    "data": {"title": "Beta Movie", "imdb_id": "tt0000002", "response": True},
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    client = _FakeOmdbClient({})
    service = OmdbEnrichmentEtlService(
        omdb_client=client,
        revenue_by_title_csv_path=revenue_by_title_csv_for_omdb_etl,
        result_json_path=result_path,
        errorlog_json_path=errorlog_path,
        request_delay_seconds=0,
    )

    result = await service.run(resume=True)

    assert result.skipped_count == 2
    assert result.processed_count == 0
    assert result.success_count == 0
    assert len(json.loads(result_path.read_text(encoding="utf-8"))) == 2
