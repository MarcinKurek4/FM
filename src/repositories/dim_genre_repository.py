"""Repository implementation for the genre dimension table.

This module provides concrete persistence operations for ``dwh.dim_genre``
using an injected ``AsyncSession``.
"""

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import DimGenreDto
from src.models.dwh_tables import DimGenreTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import dim_genre_dto_to_table, dim_genre_table_to_dto
from src.utils.timing import log_execution_time


class DimGenreRepository:
    """Repository for genre dimension persistence.

    Satisfies ``DimGenreRepositoryProtocol`` structurally.

    Attributes:
        _session: Injected async database session.
    """

    __slots__ = ("_session",)

    def __init__(self: "DimGenreRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session.
        """
        self._session = session

    @log_execution_time()
    async def get_by_id(self: "DimGenreRepository", genre_id: int) -> DimGenreDto | None:
        """Retrieve a genre by its surrogate key.

        Args:
            genre_id: Surrogate primary key.

        Returns:
            A populated ``DimGenreDto`` when the record exists, or ``None``
            when no genre with the given ID is found.
        """
        logger.debug("Fetching genre by ID", extra={"genre_id": genre_id})

        result = await self._session.execute(
            select(DimGenreTable).where(DimGenreTable.genre_id == genre_id)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Genre not found",
                extra={"genre_id": genre_id},
            )
            return None

        dto = dim_genre_table_to_dto(table)
        logger.debug(
            "Genre fetched",
            extra={"genre_id": genre_id},
        )
        return dto

    @log_execution_time()
    async def get_by_natural_key(
        self: "DimGenreRepository",
        genre_name: str,
    ) -> DimGenreDto | None:
        """Retrieve a genre by its natural key.

        Args:
            genre_name: Genre label.

        Returns:
            A populated ``DimGenreDto`` when the record exists, or ``None``
            when no genre with the given name is found.
        """
        logger.debug("Fetching genre by name", extra={"genre_name": genre_name})

        result = await self._session.execute(
            select(DimGenreTable).where(DimGenreTable.genre_name == genre_name)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Genre not found",
                extra={"genre_name": genre_name},
            )
            return None

        dto = dim_genre_table_to_dto(table)
        logger.debug(
            "Genre fetched",
            extra={"genre_name": genre_name, "genre_id": dto.genre_id},
        )
        return dto

    @log_execution_time()
    async def upsert(self: "DimGenreRepository", dto: DimGenreDto) -> DimGenreDto:
        """Insert or update a genre record.

        Args:
            dto: Genre data to persist.

        Returns:
            The persisted ``DimGenreDto`` with the ``genre_id`` populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        logger.debug("Upserting genre", extra={"genre_name": dto.genre_name})

        existing = await self.get_by_natural_key(dto.genre_name)

        try:
            if existing is not None:
                result = await self._session.execute(
                    select(DimGenreTable).where(DimGenreTable.genre_id == existing.genre_id)
                )
                table = result.scalar_one()
                table.genre_name = dto.genre_name
                table.loaded_at = dto.loaded_at
                await self._session.flush()
                await self._session.refresh(table)
            else:
                table = dim_genre_dto_to_table(dto)
                table.genre_id = None
                self._session.add(table)
                await self._session.flush()
                await self._session.refresh(table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Genre upsert integrity violation",
                extra={"genre_name": dto.genre_name, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = dim_genre_table_to_dto(table)
        logger.debug(
            "Genre upserted",
            extra={
                "genre_name": persisted.genre_name,
                "genre_id": persisted.genre_id,
            },
        )
        return persisted
