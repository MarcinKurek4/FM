"""ETL service for initial OMDb master-data load into the DWH.

Reads ``omdb_titles_init_result.json`` and upserts lookup dimensions,
``dim_movie``, bridge tables, and ``fact_movie_rating`` (SCD Type 2). Does
not call the OMDb API.

Usage::

    from src.services.omdb_dwh_init_load_service import OmdbDwhInitLoadService

    service = OmdbDwhInitLoadService(
        dim_rated_repo=rated_repo,
        dim_genre_repo=genre_repo,
        ...
    )
    result = await service.run()
"""

import datetime
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
from src.interfaces.dim_director_repository_protocol import DimDirectorRepositoryProtocol
from src.interfaces.dim_genre_repository_protocol import DimGenreRepositoryProtocol
from src.interfaces.dim_movie_repository_protocol import DimMovieRepositoryProtocol
from src.interfaces.dim_rated_repository_protocol import DimRatedRepositoryProtocol
from src.interfaces.fact_movie_rating_repository_protocol import (
    FactMovieRatingRepositoryProtocol,
)
from src.models.dwh import (
    BridgeMovieDirectorDto,
    BridgeMovieGenreDto,
    DimDirectorDto,
    DimGenreDto,
    DimMovieDto,
    DimRatedDto,
    FactMovieRatingDto,
)
from src.utils.omdb_json_reader import read_omdb_result_file, split_csv_field
from src.utils.timing import log_execution_time
from src.utils.rated_descriptions import get_rating_description

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_OMDB_RESULT_JSON: Path = PROJECT_ROOT / "data" / "raw" / "omdb_titles_init_result.json"


@dataclass(frozen=True, slots=True)
class OmdbDwhInitLoadResult:
    """Summary of an OMDb DWH init load run.

    Attributes:
        rated_upserted: Number of ``dim_rated`` rows upserted.
        genres_upserted: Number of ``dim_genre`` rows upserted.
        directors_upserted: Number of ``dim_director`` rows upserted.
        movies_upserted: Number of ``dim_movie`` rows upserted.
        bridges_genre_upserted: Number of new ``bridge_movie_genre`` rows.
        bridges_director_upserted: Number of new ``bridge_movie_director`` rows.
        ratings_inserted: Number of new ``fact_movie_rating`` snapshots.
        skipped_no_response: Records skipped during JSON read (no match).
        duration_ms: Wall-clock duration of the run in milliseconds.
    """

    rated_upserted: int
    genres_upserted: int
    directors_upserted: int
    movies_upserted: int
    bridges_genre_upserted: int
    bridges_director_upserted: int
    ratings_inserted: int
    skipped_no_response: int
    duration_ms: float = 0.0


class OmdbDwhInitLoadService:
    """Load OMDb init JSON into DWH master-data tables.

    Orchestrates dimension, bridge, and rating fact loads in foreign-key
    order. All persistence goes through injected repositories.

    Attributes:
        _dim_rated_repo: Rating dimension repository.
        _dim_genre_repo: Genre dimension repository.
        _dim_director_repo: Director dimension repository.
        _dim_movie_repo: Movie dimension repository.
        _bridge_genre_repo: Movie-genre bridge repository.
        _bridge_director_repo: Movie-director bridge repository.
        _fact_rating_repo: Movie rating fact repository (SCD Type 2).
        _result_json_path: Path to the init result JSON file.
    """

    __slots__ = (
        "_bridge_director_repo",
        "_bridge_genre_repo",
        "_dim_director_repo",
        "_dim_genre_repo",
        "_dim_movie_repo",
        "_dim_rated_repo",
        "_fact_rating_repo",
        "_result_json_path",
    )

    def __init__(
        self: "OmdbDwhInitLoadService",
        dim_rated_repo: DimRatedRepositoryProtocol,
        dim_genre_repo: DimGenreRepositoryProtocol,
        dim_director_repo: DimDirectorRepositoryProtocol,
        dim_movie_repo: DimMovieRepositoryProtocol,
        bridge_genre_repo: BridgeMovieGenreRepositoryProtocol,
        bridge_director_repo: BridgeMovieDirectorRepositoryProtocol,
        fact_rating_repo: FactMovieRatingRepositoryProtocol,
        result_json_path: Path | None = None,
    ) -> None:
        """Initialise the init load service.

        Args:
            dim_rated_repo: Repository for ``dim_rated``.
            dim_genre_repo: Repository for ``dim_genre``.
            dim_director_repo: Repository for ``dim_director``.
            dim_movie_repo: Repository for ``dim_movie``.
            bridge_genre_repo: Repository for ``bridge_movie_genre``.
            bridge_director_repo: Repository for ``bridge_movie_director``.
            fact_rating_repo: Repository for ``fact_movie_rating``.
            result_json_path: Init JSON path. Defaults to
                ``data/raw/omdb_titles_init_result.json``.
        """
        self._dim_rated_repo = dim_rated_repo
        self._dim_genre_repo = dim_genre_repo
        self._dim_director_repo = dim_director_repo
        self._dim_movie_repo = dim_movie_repo
        self._bridge_genre_repo = bridge_genre_repo
        self._bridge_director_repo = bridge_director_repo
        self._fact_rating_repo = fact_rating_repo
        self._result_json_path = result_json_path or DEFAULT_OMDB_RESULT_JSON

    @log_execution_time(inject_duration_ms=True)
    async def run(self: "OmdbDwhInitLoadService") -> OmdbDwhInitLoadResult:
        """Execute the full init load pipeline.

        Returns:
            Summary counts and timing for the run.

        Raises:
            FileNotFoundError: When the result JSON file is missing.
            ValueError: When the JSON structure is invalid.
        """
        logger.info(
            "Starting OMDb DWH init load",
            extra={"result_path": str(self._result_json_path)},
        )

        records, skipped_no_response = read_omdb_result_file(self._result_json_path)
        now = _to_naive_utc(datetime.datetime.now(tz=datetime.UTC))

        rated_map, rated_upserted = await self._load_rated(records, now)
        genre_map = await self._load_genres(records, now)
        director_map = await self._load_directors(records, now)
        movie_map, movies_upserted = await self._load_movies(records, rated_map, now)
        bridges_genre_upserted, bridges_director_upserted = await self._load_bridges(
            records,
            movie_map,
            genre_map,
            director_map,
            now,
        )
        ratings_inserted = await self._load_ratings(records, movie_map, now)

        result = OmdbDwhInitLoadResult(
            rated_upserted=rated_upserted,
            genres_upserted=len(genre_map),
            directors_upserted=len(director_map),
            movies_upserted=movies_upserted,
            bridges_genre_upserted=bridges_genre_upserted,
            bridges_director_upserted=bridges_director_upserted,
            ratings_inserted=ratings_inserted,
            skipped_no_response=skipped_no_response,
        )
        logger.info(
            "OMDb DWH init load finished",
            extra={
                "rated_upserted": result.rated_upserted,
                "genres_upserted": result.genres_upserted,
                "directors_upserted": result.directors_upserted,
                "movies_upserted": result.movies_upserted,
                "bridges_genre_upserted": result.bridges_genre_upserted,
                "bridges_director_upserted": result.bridges_director_upserted,
                "ratings_inserted": result.ratings_inserted,
                "skipped_no_response": result.skipped_no_response,
            },
        )
        return result

    async def _load_rated(
        self: "OmdbDwhInitLoadService",
        records: list[dict[str, object]],
        now: datetime.datetime,
    ) -> tuple[dict[str, int], int]:
        """Upsert distinct MPAA/TV rating codes and return a lookup map.

        Args:
            records: Valid OMDb init result records.
            now: Load timestamp for ``loaded_at``.

        Returns:
            A tuple of ``(rated_map, upserted_count)`` where ``rated_map``
            maps ``rating_code`` to ``rated_id``.
        """
        codes = _collect_rated_codes(records)
        rated_map: dict[str, int] = {}
        upserted = 0
        for code in sorted(codes):
            dto = DimRatedDto(
                rated_id=None,
                rating_code=code,
                rating_description=get_rating_description(code),
                loaded_at=now,
            )
            persisted = await self._dim_rated_repo.upsert(dto)
            if persisted.rated_id is not None:
                rated_map[code] = persisted.rated_id
            upserted += 1
        return rated_map, upserted

    async def _load_genres(
        self: "OmdbDwhInitLoadService",
        records: list[dict[str, object]],
        now: datetime.datetime,
    ) -> dict[str, int]:
        """Upsert genres and return a name-to-id map.

        Args:
            records: Valid OMDb init result records.
            now: Load timestamp for ``loaded_at``.

        Returns:
            Mapping from ``genre_name`` to ``genre_id``.
        """
        names = _collect_genre_names(records)
        genre_map: dict[str, int] = {}
        for name in sorted(names):
            dto = DimGenreDto(genre_id=None, genre_name=name, loaded_at=now)
            persisted = await self._dim_genre_repo.upsert(dto)
            if persisted.genre_id is not None:
                genre_map[name] = persisted.genre_id
        return genre_map

    async def _load_directors(
        self: "OmdbDwhInitLoadService",
        records: list[dict[str, object]],
        now: datetime.datetime,
    ) -> dict[str, int]:
        """Upsert directors and return a name-to-id map.

        Args:
            records: Valid OMDb init result records.
            now: Load timestamp for ``loaded_at``.

        Returns:
            Mapping from ``director_name`` to ``director_id``.
        """
        names = _collect_director_names(records)
        director_map: dict[str, int] = {}
        for name in sorted(names):
            dto = DimDirectorDto(director_id=None, director_name=name, loaded_at=now)
            persisted = await self._dim_director_repo.upsert(dto)
            if persisted.director_id is not None:
                director_map[name] = persisted.director_id
        return director_map

    async def _load_movies(
        self: "OmdbDwhInitLoadService",
        records: list[dict[str, object]],
        rated_map: dict[str, int],
        now: datetime.datetime,
    ) -> tuple[dict[str, int], int]:
        """Upsert movies and return an imdb_id-to-movie_id map.

        Args:
            records: Valid OMDb init result records.
            rated_map: Rating code to ``rated_id`` lookup.
            now: Load timestamp for ``loaded_at``.

        Returns:
            A tuple of ``(movie_map, upserted_count)``.
        """
        unique_records = _deduplicate_by_imdb_id(records)
        movie_map: dict[str, int] = {}
        upserted = 0

        for record in unique_records:
            data = record["data"]
            assert isinstance(data, dict)
            imdb_id = str(data["imdb_id"])
            rated_code = data.get("rated")
            rated_id: int | None = None
            if isinstance(rated_code, str) and rated_code.strip():
                rated_id = rated_map.get(rated_code.strip())

            dto = DimMovieDto(
                movie_id=None,
                imdb_id=imdb_id,
                title=str(data.get("title") or record.get("omdb_title") or imdb_id),
                release_year=_parse_release_year(data.get("year")),
                rated_id=rated_id,
                runtime_min=_parse_optional_int(data.get("runtime_min")),
                plot=_parse_optional_str(data.get("plot")),
                awards=_parse_optional_str(data.get("awards")),
                box_office_omdb=_parse_box_office(data.get("box_office")),
                omdb_fetched_at=_parse_fetched_at(record.get("fetched_at")),
                loaded_at=now,
            )
            persisted = await self._dim_movie_repo.upsert(dto)
            if persisted.movie_id is not None:
                movie_map[imdb_id] = persisted.movie_id
                upserted += 1

        return movie_map, upserted

    async def _load_bridges(
        self: "OmdbDwhInitLoadService",
        records: list[dict[str, object]],
        movie_map: dict[str, int],
        genre_map: dict[str, int],
        director_map: dict[str, int],
        now: datetime.datetime,
    ) -> tuple[int, int]:
        """Insert movie-genre and movie-director bridge rows.

        Args:
            records: Valid OMDb init result records.
            movie_map: ``imdb_id`` to ``movie_id`` lookup.
            genre_map: Genre name to ``genre_id`` lookup.
            director_map: Director name to ``director_id`` lookup.
            now: Load timestamp for ``loaded_at``.

        Returns:
            A tuple of ``(genre_bridge_inserted, director_bridge_inserted)``.
        """
        genre_dtos: list[BridgeMovieGenreDto] = []
        director_dtos: list[BridgeMovieDirectorDto] = []
        seen_genre_keys: set[tuple[int, int]] = set()
        seen_director_keys: set[tuple[int, int]] = set()

        for record in records:
            data = record["data"]
            assert isinstance(data, dict)
            imdb_id = str(data["imdb_id"])
            movie_id = movie_map.get(imdb_id)
            if movie_id is None:
                continue

            for genre_name in split_csv_field(data.get("genre")):
                genre_id = genre_map.get(genre_name)
                if genre_id is None:
                    continue
                key = (movie_id, genre_id)
                if key in seen_genre_keys:
                    continue
                seen_genre_keys.add(key)
                genre_dtos.append(
                    BridgeMovieGenreDto(movie_id=movie_id, genre_id=genre_id, loaded_at=now)
                )

            for director_name in split_csv_field(data.get("director")):
                director_id = director_map.get(director_name)
                if director_id is None:
                    continue
                key = (movie_id, director_id)
                if key in seen_director_keys:
                    continue
                seen_director_keys.add(key)
                director_dtos.append(
                    BridgeMovieDirectorDto(
                        movie_id=movie_id,
                        director_id=director_id,
                        loaded_at=now,
                    )
                )

        _, genre_inserted = await self._bridge_genre_repo.bulk_upsert(genre_dtos)
        _, director_inserted = await self._bridge_director_repo.bulk_upsert(director_dtos)
        return genre_inserted, director_inserted

    async def _load_ratings(
        self: "OmdbDwhInitLoadService",
        records: list[dict[str, object]],
        movie_map: dict[str, int],
        now: datetime.datetime,
    ) -> int:
        """Insert rating snapshots using SCD Type 2 when values change.

        Args:
            records: Valid OMDb init result records.
            movie_map: ``imdb_id`` to ``movie_id`` lookup.
            now: Load timestamp for ``loaded_at``.

        Returns:
            Number of new rating rows inserted.
        """
        inserted = 0
        for record in _deduplicate_by_imdb_id(records):
            data = record["data"]
            assert isinstance(data, dict)
            if data.get("imdb_rating") is None:
                continue

            imdb_id = str(data["imdb_id"])
            movie_id = movie_map.get(imdb_id)
            if movie_id is None:
                continue

            new_rating = _parse_imdb_rating(data.get("imdb_rating"))
            new_votes = _parse_optional_int(data.get("imdb_votes"))
            valid_from = _parse_fetched_at(record.get("fetched_at")) or now

            current = await self._fact_rating_repo.get_current_rating(movie_id)
            if current is not None and _ratings_are_equal(current, new_rating, new_votes):
                continue

            dto = FactMovieRatingDto(
                rating_id=None,
                movie_id=movie_id,
                imdb_rating=new_rating,
                imdb_votes=new_votes,
                valid_from=valid_from,
                valid_to=None,
                is_current=True,
                loaded_at=now,
            )
            await self._fact_rating_repo.insert_new_rating(dto)
            inserted += 1

        return inserted


def _collect_rated_codes(records: list[dict[str, object]]) -> set[str]:
    """Collect non-empty rated codes from all records."""
    codes: set[str] = set()
    for record in records:
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        rated = data.get("rated")
        if isinstance(rated, str) and rated.strip():
            codes.add(rated.strip())
    return codes


def _collect_genre_names(records: list[dict[str, object]]) -> set[str]:
    """Collect distinct genre names from all records."""
    names: set[str] = set()
    for record in records:
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        names.update(split_csv_field(data.get("genre")))
    return names


def _collect_director_names(records: list[dict[str, object]]) -> set[str]:
    """Collect distinct director names from all records."""
    names: set[str] = set()
    for record in records:
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        names.update(split_csv_field(data.get("director")))
    return names


def _deduplicate_by_imdb_id(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep the last record per ``imdb_id`` to handle duplicate titles."""
    by_imdb: dict[str, dict[str, object]] = {}
    for record in records:
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        imdb_id = data.get("imdb_id")
        if isinstance(imdb_id, str) and imdb_id.strip():
            by_imdb[imdb_id] = record
    return list(by_imdb.values())


def _to_naive_utc(value: datetime.datetime) -> datetime.datetime:
    """Convert a datetime to naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
    if value.tzinfo is None:
        return value
    return value.astimezone(datetime.UTC).replace(tzinfo=None)


def _parse_fetched_at(value: object | None) -> datetime.datetime | None:
    """Parse an ISO-8601 ``fetched_at`` string to naive UTC datetime."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(datetime.UTC).replace(tzinfo=None)


def _parse_release_year(value: object | None) -> int | None:
    """Parse a release year from JSON."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_optional_int(value: object | None) -> int | None:
    """Parse an optional integer field."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_optional_str(value: object | None) -> str | None:
    """Return a stripped string or ``None`` when blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_box_office(value: object | None) -> Decimal | None:
    """Parse box office gross to ``Decimal``."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_imdb_rating(value: object | None) -> Decimal | None:
    """Parse IMDb rating to ``Decimal`` with one decimal place."""
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
    """Return ``True`` when rating and vote counts match the current row."""
    current_rating = current.imdb_rating
    if current_rating is not None:
        current_rating = current_rating.quantize(Decimal("0.1"))
    if new_rating is not None:
        new_rating = new_rating.quantize(Decimal("0.1"))
    return current_rating == new_rating and current.imdb_votes == new_votes
