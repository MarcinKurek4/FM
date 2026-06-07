"""Repository implementation for the date dimension table.

This module provides concrete persistence operations for ``dwh.dim_date``
using an injected ``AsyncSession``.
"""

import datetime
from collections.abc import Sequence

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import DimDateDto
from src.models.dwh_tables import DimDateTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import dim_date_dto_to_table, dim_date_table_to_dto
from src.utils.timing import log_execution_time

_UPSERT_UPDATE_COLUMNS: tuple[str, ...] = (
    "date",
    "year",
    "quarter",
    "month",
    "month_name",
    "day",
    "day_of_week",
    "day_of_week_name",
    "week_number",
    "is_weekend",
    "is_holiday",
)


class DimDateRepository:
    """Repository for date dimension persistence.

    Satisfies ``DimDateRepositoryProtocol`` structurally.

    Attributes:
        _session: Injected async database session.
    """

    __slots__ = ("_session",)

    def __init__(self: "DimDateRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session.
        """
        self._session = session

    @log_execution_time()
    async def get_by_id(self: "DimDateRepository", date_id: int) -> DimDateDto | None:
        """Retrieve a date by its surrogate key.

        Args:
            date_id: Surrogate primary key in ``YYYYMMDD`` format.

        Returns:
            A populated ``DimDateDto`` when the record exists, or ``None``
            when no date with the given ID is found.
        """
        logger.debug("Fetching date by ID", extra={"date_id": date_id})

        result = await self._session.execute(
            select(DimDateTable).where(DimDateTable.date_id == date_id)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Date not found",
                extra={"date_id": date_id},
            )
            return None

        dto = dim_date_table_to_dto(table)
        logger.debug(
            "Date fetched",
            extra={"date_id": date_id},
        )
        return dto

    @log_execution_time()
    async def get_by_natural_key(
        self: "DimDateRepository",
        date: str,
    ) -> DimDateDto | None:
        """Retrieve a date by its natural key.

        Args:
            date: Calendar date in ISO 8601 format (``YYYY-MM-DD``).

        Returns:
            A populated ``DimDateDto`` when the record exists, or ``None``
            when no date with the given value is found.
        """
        logger.debug("Fetching date by natural key", extra={"date": date})

        parsed_date = datetime.date.fromisoformat(date)
        result = await self._session.execute(
            select(DimDateTable).where(DimDateTable.date == parsed_date)
        )
        table = result.scalar_one_or_none()

        if table is None:
            logger.debug(
                "Date not found",
                extra={"date": date},
            )
            return None

        dto = dim_date_table_to_dto(table)
        logger.debug(
            "Date fetched",
            extra={"date": date, "date_id": dto.date_id},
        )
        return dto

    @log_execution_time()
    async def upsert(self: "DimDateRepository", dto: DimDateDto) -> DimDateDto:
        """Insert or update a date record.

        Args:
            dto: Date data to persist.

        Returns:
            The persisted ``DimDateDto`` with all fields populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        logger.debug("Upserting date", extra={"date_id": dto.date_id})

        try:
            existing_table = await self._session.get(DimDateTable, dto.date_id)
            if existing_table is not None:
                existing_table.date = dto.date
                existing_table.year = dto.year
                existing_table.quarter = dto.quarter
                existing_table.month = dto.month
                existing_table.month_name = dto.month_name
                existing_table.day = dto.day
                existing_table.day_of_week = dto.day_of_week
                existing_table.day_of_week_name = dto.day_of_week_name
                existing_table.week_number = dto.week_number
                existing_table.is_weekend = dto.is_weekend
                existing_table.is_holiday = dto.is_holiday
                table = existing_table
            else:
                table = dim_date_dto_to_table(dto)
                self._session.add(table)
            await self._session.flush()
            await self._session.refresh(table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Date upsert integrity violation",
                extra={"date_id": dto.date_id, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = dim_date_table_to_dto(table)
        logger.debug(
            "Date upserted",
            extra={"date_id": persisted.date_id},
        )
        return persisted

    @log_execution_time()
    async def bulk_upsert(
        self: "DimDateRepository",
        dtos: Sequence[DimDateDto],
    ) -> list[DimDateDto]:
        """Insert or update multiple date records in a single transaction.

        Args:
            dtos: Sequence of date records to persist. May be empty.

        Returns:
            List of persisted ``DimDateDto`` instances.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        count = len(dtos)
        logger.debug("Bulk upserting dates", extra={"count": count})

        if count == 0:
            return []

        values = [_dim_date_dto_to_insert_values(dto) for dto in dtos]
        table = DimDateTable.__table__
        insert_stmt = pg_insert(table).values(values)
        update_map = {
            column: insert_stmt.excluded[column]
            for column in _UPSERT_UPDATE_COLUMNS
        }
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["date_id"],
            set_=update_map,
        )

        try:
            await self._session.execute(upsert_stmt)
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Date bulk upsert integrity violation",
                extra={"count": count, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        logger.debug(
            "Dates bulk upserted",
            extra={"count": count},
        )
        return list(dtos)


def _dim_date_dto_to_insert_values(dto: DimDateDto) -> dict[str, object]:
    """Convert a DTO to a PostgreSQL insert value mapping."""
    return {
        "date_id": dto.date_id,
        "date": dto.date,
        "year": dto.year,
        "quarter": dto.quarter,
        "month": dto.month,
        "month_name": dto.month_name,
        "day": dto.day,
        "day_of_week": dto.day_of_week,
        "day_of_week_name": dto.day_of_week_name,
        "week_number": dto.week_number,
        "is_weekend": dto.is_weekend,
        "is_holiday": dto.is_holiday,
    }
