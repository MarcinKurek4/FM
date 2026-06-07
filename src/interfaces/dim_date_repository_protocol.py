"""Structural interface for the date dimension repository.

Consumers depend on ``DimDateRepositoryProtocol`` rather than the concrete
repository implementation.
"""

from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import DimDateDto


class DimDateRepositoryProtocol(Protocol):
    """Structural interface for date dimension persistence.

    The date dimension is typically pre-seeded with a wide range of dates
    before any fact data is loaded. Repositories implementing this protocol
    provide efficient bulk insert and lookup operations.
    """

    async def get_by_id(
        self: "DimDateRepositoryProtocol",
        date_id: int,
    ) -> DimDateDto | None:
        """Retrieve a date by its surrogate key.

        Args:
            date_id: Surrogate primary key in ``YYYYMMDD`` format
                (e.g., ``20040920``).

        Returns:
            A populated ``DimDateDto`` when the record exists, or ``None``
            when no date with the given ID is found.
        """
        ...

    async def get_by_natural_key(
        self: "DimDateRepositoryProtocol",
        date: str,
    ) -> DimDateDto | None:
        """Retrieve a date by its natural key.

        Args:
            date: Calendar date in ISO 8601 format (``YYYY-MM-DD``).

        Returns:
            A populated ``DimDateDto`` when the record exists, or ``None``
            when no date with the given value is found.
        """
        ...

    async def upsert(
        self: "DimDateRepositoryProtocol",
        dto: DimDateDto,
    ) -> DimDateDto:
        """Insert or update a date record.

        If a date with the given ``date_id`` already exists, its fields are
        updated. Otherwise, a new record is inserted.

        Args:
            dto: Date data to persist.

        Returns:
            The persisted ``DimDateDto`` with all fields populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        ...

    async def bulk_upsert(
        self: "DimDateRepositoryProtocol",
        dtos: Sequence[DimDateDto],
    ) -> list[DimDateDto]:
        """Insert or update multiple date records in a single transaction.

        Each DTO is upserted by its ``date`` natural key. Existing records
        are updated; new records are inserted.

        Args:
            dtos: Sequence of date records to persist. May be empty.

        Returns:
            List of persisted ``DimDateDto`` instances. The order matches
            the input order.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        ...
