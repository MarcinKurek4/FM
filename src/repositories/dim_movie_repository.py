"""Repository implementation for the movie dimension table.

This module provides concrete persistence operations for ``dwh.dim_movie``
using an injected ``AsyncSession``. All methods return DTOs; SQLModel table
instances are never exposed outside this module.
"""

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import DimMovieDto
from src.models.dwh_tables import DimMovieTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import dim_movie_dto_to_table, dim_movie_table_to_dto
from src.utils.timing import log_execution_time


class DimMovieRepository:
    """Repository for movie dimension persistence.

    Satisfies ``DimMovieRepositoryProtocol`` structurally. All methods
    accept or return ``DimMovieDto`` instances; the SQLModel table layer
    is an internal implementation detail.

    Attributes:
        _session: Injected async database session.

    Example:
        async with factory.get_session() as session:
            repo = DimMovieRepository(session)
            dto = await repo.get_by_natural_key("tt1375666")
    """

    __slots__ = ("_session",)

    def __init__(self: "DimMovieRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session. The caller is
                responsible for session lifecycle (commit, rollback, close).
        """
        self._session = session

    @log_execution_time()
    async def get_by_id(self: "DimMovieRepository", movie_id: int) -> DimMovieDto | None:
        """Retrieve a movie by its surrogate key.

        Args:
            movie_id: Surrogate primary key.

        Returns:
            A populated ``DimMovieDto`` when the record exists, or ``None``
            when no movie with the given ID is found.
        """
        logger.debug("Fetching movie by ID", extra={"movie_id": movie_id})

        result = await self._session.execute(
            select(DimMovieTable).where(DimMovieTable.movie_id == movie_id)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug("Movie not found", extra={"movie_id": movie_id})
            return None

        dto = dim_movie_table_to_dto(table)
        logger.debug(
            "Movie fetched",
            extra={"movie_id": movie_id, "imdb_id": dto.imdb_id},
        )
        return dto

    @log_execution_time()
    async def get_by_natural_key(
        self: "DimMovieRepository",
        imdb_id: str,
    ) -> DimMovieDto | None:
        """Retrieve a movie by its natural key.

        Args:
            imdb_id: IMDb title identifier (e.g., ``"tt1375666"``).

        Returns:
            A populated ``DimMovieDto`` when the record exists, or ``None``
            when no movie with the given IMDb ID is found.
        """
        logger.debug("Fetching movie by IMDb ID", extra={"imdb_id": imdb_id})

        result = await self._session.execute(
            select(DimMovieTable).where(DimMovieTable.imdb_id == imdb_id)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug("Movie not found", extra={"imdb_id": imdb_id})
            return None

        dto = dim_movie_table_to_dto(table)
        logger.debug(
            "Movie fetched",
            extra={"imdb_id": imdb_id, "movie_id": dto.movie_id},
        )
        return dto

    @log_execution_time()
    async def upsert(self: "DimMovieRepository", dto: DimMovieDto) -> DimMovieDto:
        """Insert or update a movie record.

        If a movie with the given ``imdb_id`` already exists, its fields are
        updated (SCD Type 1). Otherwise, a new record is inserted.

        Args:
            dto: Movie data to persist. The ``movie_id`` field is ignored on
                insert — the database generates a new surrogate key.

        Returns:
            The persisted ``DimMovieDto`` with the ``movie_id`` populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated
                (e.g., ``rated_id`` references a non-existent rating).
        """
        logger.debug("Upserting movie", extra={"imdb_id": dto.imdb_id})

        existing = await self.get_by_natural_key(dto.imdb_id)

        try:
            if existing is not None:
                result = await self._session.execute(
                    select(DimMovieTable).where(DimMovieTable.movie_id == existing.movie_id)
                )
                table = result.scalar_one()
                table.imdb_id = dto.imdb_id
                table.title = dto.title
                table.release_year = dto.release_year
                table.rated_id = dto.rated_id
                table.runtime_min = dto.runtime_min
                table.plot = dto.plot
                table.awards = dto.awards
                table.box_office_omdb = dto.box_office_omdb
                table.omdb_fetched_at = dto.omdb_fetched_at
                table.loaded_at = dto.loaded_at
                await self._session.flush()
                await self._session.refresh(table)
            else:
                table = dim_movie_dto_to_table(dto)
                table.movie_id = None
                self._session.add(table)
                await self._session.flush()
                await self._session.refresh(table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Movie upsert integrity violation",
                extra={"imdb_id": dto.imdb_id, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = dim_movie_table_to_dto(table)
        logger.debug(
            "Movie upserted",
            extra={
                "imdb_id": persisted.imdb_id,
                "movie_id": persisted.movie_id,
            },
        )
        return persisted

    @log_execution_time()
    async def list_all_movies(self: "DimMovieRepository") -> list[DimMovieDto]:
        """Return every movie row ordered by surrogate key.

        Returns:
            All ``DimMovieDto`` instances in ascending ``movie_id`` order.
        """
        logger.debug("Listing all movies")

        result = await self._session.execute(
            select(DimMovieTable).order_by(DimMovieTable.movie_id)
        )
        tables = result.scalars().all()
        movies = [dim_movie_table_to_dto(table) for table in tables]

        logger.debug("All movies listed", extra={"count": len(movies)})
        return movies

    @log_execution_time()
    async def bulk_load_title_map(
        self: "DimMovieRepository",
    ) -> dict[str, int]:
        """Load all movies as an uppercase-normalised title-to-ID map.

        Executes a single query to retrieve all ``(title, movie_id)`` pairs
        from ``dim_movie``. Keys are uppercased so that lookups from CSV
        titles can be performed case-insensitively via ``title.upper()``.

        Returns:
            Mapping of ``title.upper() → movie_id`` for every row currently
            in ``dim_movie``.

        Example:
            title_map = await repo.bulk_load_title_map()
            movie_id = title_map.get("INCEPTION")
        """
        logger.debug("Loading full movie title map")

        result = await self._session.execute(
            select(DimMovieTable.title, DimMovieTable.movie_id)
        )
        rows = result.all()

        title_map: dict[str, int] = {}
        for row in rows:
            title_upper = row.title.upper()
            if row.movie_id is not None:
                title_map[title_upper] = row.movie_id

        logger.debug("Movie title map loaded", extra={"count": len(title_map)})
        return title_map
