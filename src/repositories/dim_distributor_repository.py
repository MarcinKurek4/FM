"""Repository implementation for the distributor dimension table.

This module provides concrete persistence operations for ``dwh.dim_distributor``
using an injected ``AsyncSession``.
"""

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import DimDistributorDto
from src.models.dwh_tables import DimDistributorTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import dim_distributor_dto_to_table, dim_distributor_table_to_dto
from src.utils.timing import log_execution_time


class DimDistributorRepository:
    """Repository for distributor dimension persistence.

    Satisfies ``DimDistributorRepositoryProtocol`` structurally.

    Attributes:
        _session: Injected async database session.
    """

    __slots__ = ("_session",)

    def __init__(self: "DimDistributorRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session.
        """
        self._session = session

    @log_execution_time()
    async def get_by_id(
        self: "DimDistributorRepository",
        distributor_id: int,
    ) -> DimDistributorDto | None:
        """Retrieve a distributor by its surrogate key.

        Args:
            distributor_id: Surrogate primary key.

        Returns:
            A populated ``DimDistributorDto`` when the record exists, or
            ``None`` when no distributor with the given ID is found.
        """
        logger.debug("Fetching distributor by ID", extra={"distributor_id": distributor_id})

        result = await self._session.execute(
            select(DimDistributorTable).where(
                DimDistributorTable.distributor_id == distributor_id
            )
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Distributor not found",
                extra={"distributor_id": distributor_id},
            )
            return None

        dto = dim_distributor_table_to_dto(table)
        logger.debug(
            "Distributor fetched",
            extra={"distributor_id": distributor_id},
        )
        return dto

    @log_execution_time()
    async def get_by_natural_key(
        self: "DimDistributorRepository",
        distributor_name: str,
    ) -> DimDistributorDto | None:
        """Retrieve a distributor by its natural key.

        Args:
            distributor_name: Company name.

        Returns:
            A populated ``DimDistributorDto`` when the record exists, or
            ``None`` when no distributor with the given name is found.
        """
        logger.debug("Fetching distributor by name", extra={"distributor_name": distributor_name})

        result = await self._session.execute(
            select(DimDistributorTable).where(
                DimDistributorTable.distributor_name == distributor_name
            )
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Distributor not found",
                extra={"distributor_name": distributor_name},
            )
            return None

        dto = dim_distributor_table_to_dto(table)
        logger.debug(
            "Distributor fetched",
            extra={
                "distributor_name": distributor_name,
                "distributor_id": dto.distributor_id,
            },
        )
        return dto

    @log_execution_time()
    async def upsert(
        self: "DimDistributorRepository",
        dto: DimDistributorDto,
    ) -> DimDistributorDto:
        """Insert or update a distributor record.

        Args:
            dto: Distributor data to persist.

        Returns:
            The persisted ``DimDistributorDto`` with the ``distributor_id``
            populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        logger.debug("Upserting distributor", extra={"distributor_name": dto.distributor_name})

        existing = await self.get_by_natural_key(dto.distributor_name)

        try:
            if existing is not None:
                result = await self._session.execute(
                    select(DimDistributorTable).where(
                        DimDistributorTable.distributor_id == existing.distributor_id
                    )
                )
                table = result.scalar_one()
                table.distributor_name = dto.distributor_name
                table.loaded_at = dto.loaded_at
                await self._session.flush()
                await self._session.refresh(table)
            else:
                table = dim_distributor_dto_to_table(dto)
                table.distributor_id = None
                self._session.add(table)
                await self._session.flush()
                await self._session.refresh(table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Distributor upsert integrity violation",
                extra={"distributor_name": dto.distributor_name, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = dim_distributor_table_to_dto(table)
        logger.debug(
            "Distributor upserted",
            extra={
                "distributor_name": persisted.distributor_name,
                "distributor_id": persisted.distributor_id,
            },
        )
        return persisted
