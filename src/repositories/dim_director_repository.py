"""Repository implementation for the director dimension table.

This module provides concrete persistence operations for ``dwh.dim_director``
using an injected ``AsyncSession``.
"""

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import DimDirectorDto
from src.models.dwh_tables import DimDirectorTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import dim_director_dto_to_table, dim_director_table_to_dto
from src.utils.timing import log_execution_time


class DimDirectorRepository:
    """Repository for director dimension persistence.

    Satisfies ``DimDirectorRepositoryProtocol`` structurally.

    Attributes:
        _session: Injected async database session.
    """

    __slots__ = ("_session",)

    def __init__(self: "DimDirectorRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session.
        """
        self._session = session

    @log_execution_time()
    async def get_by_id(self: "DimDirectorRepository", director_id: int) -> DimDirectorDto | None:
        """Retrieve a director by its surrogate key.

        Args:
            director_id: Surrogate primary key.

        Returns:
            A populated ``DimDirectorDto`` when the record exists, or
            ``None`` when no director with the given ID is found.
        """
        logger.debug("Fetching director by ID", extra={"director_id": director_id})

        result = await self._session.execute(
            select(DimDirectorTable).where(DimDirectorTable.director_id == director_id)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Director not found",
                extra={"director_id": director_id},
            )
            return None

        dto = dim_director_table_to_dto(table)
        logger.debug(
            "Director fetched",
            extra={"director_id": director_id},
        )
        return dto

    @log_execution_time()
    async def get_by_natural_key(
        self: "DimDirectorRepository",
        director_name: str,
    ) -> DimDirectorDto | None:
        """Retrieve a director by its natural key.

        Args:
            director_name: Director full name.

        Returns:
            A populated ``DimDirectorDto`` when the record exists, or
            ``None`` when no director with the given name is found.
        """
        logger.debug("Fetching director by name", extra={"director_name": director_name})

        result = await self._session.execute(
            select(DimDirectorTable).where(DimDirectorTable.director_name == director_name)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Director not found",
                extra={"director_name": director_name},
            )
            return None

        dto = dim_director_table_to_dto(table)
        logger.debug(
            "Director fetched",
            extra={
                "director_name": director_name,
                "director_id": dto.director_id,
            },
        )
        return dto

    @log_execution_time()
    async def upsert(self: "DimDirectorRepository", dto: DimDirectorDto) -> DimDirectorDto:
        """Insert or update a director record.

        Args:
            dto: Director data to persist.

        Returns:
            The persisted ``DimDirectorDto`` with the ``director_id``
            populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        logger.debug("Upserting director", extra={"director_name": dto.director_name})

        existing = await self.get_by_natural_key(dto.director_name)

        try:
            if existing is not None:
                result = await self._session.execute(
                    select(DimDirectorTable).where(
                        DimDirectorTable.director_id == existing.director_id
                    )
                )
                table = result.scalar_one()
                table.director_name = dto.director_name
                table.loaded_at = dto.loaded_at
                await self._session.flush()
                await self._session.refresh(table)
            else:
                table = dim_director_dto_to_table(dto)
                table.director_id = None
                self._session.add(table)
                await self._session.flush()
                await self._session.refresh(table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Director upsert integrity violation",
                extra={"director_name": dto.director_name, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = dim_director_table_to_dto(table)
        logger.debug(
            "Director upserted",
            extra={
                "director_name": persisted.director_name,
                "director_id": persisted.director_id,
            },
        )
        return persisted
