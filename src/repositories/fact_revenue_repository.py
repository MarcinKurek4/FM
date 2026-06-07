"""Repository implementation for the revenue fact table.

This module provides concrete persistence operations for ``dwh.fact_revenue``
using an injected ``AsyncSession``.
"""

import time
import uuid
from collections.abc import Sequence

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import FactRevenueDto
from src.models.dwh_tables import FactRevenueTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import fact_revenue_dto_to_table, fact_revenue_table_to_dto


class FactRevenueRepository:
    """Repository for revenue fact table persistence.

    Satisfies ``FactRevenueRepositoryProtocol`` structurally.

    Attributes:
        _session: Injected async database session.
    """

    __slots__ = ("_session",)

    def __init__(self: "FactRevenueRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session.
        """
        self._session = session

    async def exists_by_source_row_id(
        self: "FactRevenueRepository",
        source_row_id: uuid.UUID,
    ) -> bool:
        """Check whether a fact record already exists for the given source row.

        Args:
            source_row_id: Natural key from the source CSV.

        Returns:
            ``True`` when a record with the given ``source_row_id`` exists,
            ``False`` otherwise.
        """
        start = time.perf_counter()
        logger.debug("Checking fact existence by source_row_id", extra={"source_row_id": str(source_row_id)})

        result = await self._session.execute(
            select(FactRevenueTable.revenue_id).where(
                FactRevenueTable.source_row_id == source_row_id
            )
        )
        exists = result.scalar_one_or_none() is not None

        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Fact existence checked",
            extra={"source_row_id": str(source_row_id), "exists": exists, "duration_ms": duration_ms},
        )
        return exists

    async def bulk_insert(
        self: "FactRevenueRepository",
        dtos: Sequence[FactRevenueDto],
    ) -> int:
        """Insert multiple fact records in a single transaction.

        Records with duplicate ``source_row_id`` values are silently skipped
        (idempotency). This allows the ETL pipeline to safely re-run on the
        same input without creating duplicate rows.

        Args:
            dtos: Sequence of fact records to persist. May be empty.

        Returns:
            The number of rows actually inserted (excluding duplicates).

        Raises:
            IntegrityViolationError: When a foreign key constraint is
                violated.
        """
        start = time.perf_counter()
        count = len(dtos)
        logger.debug("Bulk inserting facts", extra={"count": count})

        if count == 0:
            return 0

        inserted_count = 0
        try:
            for dto in dtos:
                if not await self.exists_by_source_row_id(dto.source_row_id):
                    table = fact_revenue_dto_to_table(dto)
                    table.revenue_id = None
                    self._session.add(table)
                    inserted_count += 1

            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Fact bulk insert integrity violation",
                extra={"count": count, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Facts bulk inserted",
            extra={
                "total_count": count,
                "inserted_count": inserted_count,
                "skipped_count": count - inserted_count,
                "duration_ms": duration_ms,
            },
        )
        return inserted_count

    async def get_by_id(
        self: "FactRevenueRepository",
        revenue_id: int,
    ) -> FactRevenueDto | None:
        """Retrieve a fact record by its surrogate key.

        Args:
            revenue_id: Surrogate primary key.

        Returns:
            A populated ``FactRevenueDto`` when the record exists, or
            ``None`` when no fact with the given ID is found.
        """
        start = time.perf_counter()
        logger.debug("Fetching fact by ID", extra={"revenue_id": revenue_id})

        result = await self._session.execute(
            select(FactRevenueTable).where(FactRevenueTable.revenue_id == revenue_id)
        )
        table = result.scalar_one_or_none()

        duration_ms = (time.perf_counter() - start) * 1000
        if table is None:
            logger.debug(
                "Fact not found",
                extra={"revenue_id": revenue_id, "duration_ms": duration_ms},
            )
            return None

        dto = fact_revenue_table_to_dto(table)
        logger.debug(
            "Fact fetched",
            extra={"revenue_id": revenue_id, "duration_ms": duration_ms},
        )
        return dto
