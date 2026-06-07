"""Repository implementation for the movie-genre bridge table."""

from collections.abc import Sequence

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import BridgeMovieGenreDto
from src.models.dwh_tables import BridgeMovieGenreTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import bridge_movie_genre_dto_to_table, bridge_movie_genre_table_to_dto
from src.utils.timing import log_execution_time


class BridgeMovieGenreRepository:
    """Repository for movie-genre bridge persistence.

    Satisfies ``BridgeMovieGenreRepositoryProtocol`` structurally.

    Attributes:
        _session: Injected async database session.
    """

    __slots__ = ("_session",)

    def __init__(self: "BridgeMovieGenreRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session.
        """
        self._session = session

    @log_execution_time()
    async def get_by_natural_key(
        self: "BridgeMovieGenreRepository",
        movie_id: int,
        genre_id: int,
    ) -> BridgeMovieGenreDto | None:
        """Retrieve an association by composite key.

        Args:
            movie_id: Foreign key to ``dim_movie``.
            genre_id: Foreign key to ``dim_genre``.

        Returns:
            A populated DTO when the row exists, otherwise ``None``.
        """
        logger.debug(
            "Fetching movie-genre bridge",
            extra={"movie_id": movie_id, "genre_id": genre_id},
        )

        result = await self._session.execute(
            select(BridgeMovieGenreTable).where(
                BridgeMovieGenreTable.movie_id == movie_id,
                BridgeMovieGenreTable.genre_id == genre_id,
            )
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Movie-genre bridge not found",
                extra={"movie_id": movie_id, "genre_id": genre_id},
            )
            return None

        dto = bridge_movie_genre_table_to_dto(table)
        logger.debug(
            "Movie-genre bridge fetched",
            extra={"movie_id": movie_id, "genre_id": genre_id},
        )
        return dto

    @log_execution_time()
    async def upsert(
        self: "BridgeMovieGenreRepository",
        dto: BridgeMovieGenreDto,
    ) -> tuple[BridgeMovieGenreDto, bool]:
        """Insert the association when absent; return existing row otherwise.

        Args:
            dto: Bridge row to persist.

        Returns:
            A tuple of ``(persisted_dto, inserted)`` where ``inserted`` is
            ``True`` only when a new row was created.

        Raises:
            IntegrityViolationError: When a foreign key constraint is violated.
        """
        existing = await self.get_by_natural_key(dto.movie_id, dto.genre_id)
        if existing is not None:
            logger.debug(
                "Movie-genre bridge already exists",
                extra={
                    "movie_id": dto.movie_id,
                    "genre_id": dto.genre_id,
                },
            )
            return existing, False

        try:
            table = bridge_movie_genre_dto_to_table(dto)
            self._session.add(table)
            await self._session.flush()
            await self._session.refresh(table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Movie-genre bridge insert integrity violation",
                extra={
                    "movie_id": dto.movie_id,
                    "genre_id": dto.genre_id,
                    "error": str(exc.orig),
                },
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = bridge_movie_genre_table_to_dto(table)
        logger.debug(
            "Movie-genre bridge inserted",
            extra={
                "movie_id": persisted.movie_id,
                "genre_id": persisted.genre_id,
            },
        )
        return persisted, True

    @log_execution_time()
    async def bulk_upsert(
        self: "BridgeMovieGenreRepository",
        dtos: Sequence[BridgeMovieGenreDto],
    ) -> tuple[list[BridgeMovieGenreDto], int]:
        """Insert multiple associations idempotently.

        Args:
            dtos: Bridge rows to persist. May be empty.

        Returns:
            A tuple of ``(persisted_dtos, inserted_count)``.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        count = len(dtos)
        logger.debug("Bulk upserting movie-genre bridges", extra={"count": count})

        if count == 0:
            return [], 0

        persisted: list[BridgeMovieGenreDto] = []
        inserted_count = 0
        for dto in dtos:
            result, inserted = await self.upsert(dto)
            persisted.append(result)
            if inserted:
                inserted_count += 1

        logger.debug(
            "Movie-genre bridges bulk upserted",
            extra={"count": count, "inserted_count": inserted_count},
        )
        return persisted, inserted_count
