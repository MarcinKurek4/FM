"""Repository implementation for the rating dimension table.

This module provides concrete persistence operations for ``dwh.dim_rated``
using an injected ``AsyncSession``.
"""

import time
from collections.abc import Sequence

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import DimRatedDto
from src.models.dwh_tables import DimRatedTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import dim_rated_dto_to_table, dim_rated_table_to_dto


class DimRatedRepository:
    """Repository for MPAA rating dimension persistence.

    Satisfies ``DimRatedRepositoryProtocol`` structurally.

    Attributes:
        _session: Injected async database session.
    """

    __slots__ = ("_session",)

    def __init__(self: "DimRatedRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session.
        """
        self._session = session

    async def get_by_id(self: "DimRatedRepository", rated_id: int) -> DimRatedDto | None:
        """Retrieve a rating by its surrogate key.

        Args:
            rated_id: Surrogate primary key.

        Returns:
            A populated ``DimRatedDto`` when the record exists, or ``None``
            when no rating with the given ID is found.
        """
        start = time.perf_counter()
        logger.debug("Fetching rating by ID", extra={"rated_id": rated_id})

        result = await self._session.execute(
            select(DimRatedTable).where(DimRatedTable.rated_id == rated_id)
        )
        table = result.scalar_one_or_none()

        duration_ms = (time.perf_counter() - start) * 1000
        if table is None:
            logger.debug(
                "Rating not found",
                extra={"rated_id": rated_id, "duration_ms": duration_ms},
            )
            return None

        dto = dim_rated_table_to_dto(table)
        logger.debug(
            "Rating fetched",
            extra={"rated_id": rated_id, "duration_ms": duration_ms},
        )
        return dto

    async def get_by_natural_key(
        self: "DimRatedRepository",
        rating_code: str,
    ) -> DimRatedDto | None:
        """Retrieve a rating by its natural key.

        Args:
            rating_code: MPAA rating code.

        Returns:
            A populated ``DimRatedDto`` when the record exists, or ``None``
            when no rating with the given code is found.
        """
        start = time.perf_counter()
        logger.debug("Fetching rating by code", extra={"rating_code": rating_code})

        result = await self._session.execute(
            select(DimRatedTable).where(DimRatedTable.rating_code == rating_code)
        )
        table = result.scalar_one_or_none()

        duration_ms = (time.perf_counter() - start) * 1000
        if table is None:
            logger.debug(
                "Rating not found",
                extra={"rating_code": rating_code, "duration_ms": duration_ms},
            )
            return None

        dto = dim_rated_table_to_dto(table)
        logger.debug(
            "Rating fetched",
            extra={
                "rating_code": rating_code,
                "rated_id": dto.rated_id,
                "duration_ms": duration_ms,
            },
        )
        return dto

    async def upsert(self: "DimRatedRepository", dto: DimRatedDto) -> DimRatedDto:
        """Insert or update a rating record.

        Args:
            dto: Rating data to persist.

        Returns:
            The persisted ``DimRatedDto`` with the ``rated_id`` populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        start = time.perf_counter()
        logger.debug("Upserting rating", extra={"rating_code": dto.rating_code})

        existing = await self.get_by_natural_key(dto.rating_code)

        try:
            if existing is not None:
                result = await self._session.execute(
                    select(DimRatedTable).where(DimRatedTable.rated_id == existing.rated_id)
                )
                table = result.scalar_one()
                table.rating_code = dto.rating_code
                table.rating_description = dto.rating_description
                table.loaded_at = dto.loaded_at
                await self._session.flush()
                await self._session.refresh(table)
            else:
                table = dim_rated_dto_to_table(dto)
                table.rated_id = None
                self._session.add(table)
                await self._session.flush()
                await self._session.refresh(table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Rating upsert integrity violation",
                extra={"rating_code": dto.rating_code, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = dim_rated_table_to_dto(table)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Rating upserted",
            extra={
                "rating_code": persisted.rating_code,
                "rated_id": persisted.rated_id,
                "duration_ms": duration_ms,
            },
        )
        return persisted

    async def bulk_upsert(
        self: "DimRatedRepository",
        dtos: Sequence[DimRatedDto],
    ) -> list[DimRatedDto]:
        """Insert or update multiple rating records in a single transaction.

        Args:
            dtos: Sequence of rating records to persist. May be empty.

        Returns:
            List of persisted ``DimRatedDto`` instances with ``rated_id``
            fields populated.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        start = time.perf_counter()
        count = len(dtos)
        logger.debug("Bulk upserting ratings", extra={"count": count})

        if count == 0:
            return []

        persisted: list[DimRatedDto] = []
        for dto in dtos:
            result = await self.upsert(dto)
            persisted.append(result)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Ratings bulk upserted",
            extra={"count": count, "duration_ms": duration_ms},
        )
        return persisted
