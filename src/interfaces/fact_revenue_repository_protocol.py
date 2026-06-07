"""Structural interface for the revenue fact table repository.

Consumers depend on ``FactRevenueRepositoryProtocol`` rather than the
concrete repository implementation.
"""

import uuid
from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import FactRevenueDto


class FactRevenueRepositoryProtocol(Protocol):
    """Structural interface for revenue fact table persistence.

    The fact table stores one row per movie per day, with revenue and
    theater count as additive measures. The natural key ``source_row_id``
    (from the source CSV) ensures idempotency when re-running the ETL
    pipeline.
    """

    async def exists_by_source_row_id(
        self: "FactRevenueRepositoryProtocol",
        source_row_id: uuid.UUID,
    ) -> bool:
        """Check whether a fact record already exists for the given source row.

        Args:
            source_row_id: Natural key from the source CSV.

        Returns:
            ``True`` when a record with the given ``source_row_id`` exists,
            ``False`` otherwise.
        """
        ...

    async def bulk_insert(
        self: "FactRevenueRepositoryProtocol",
        dtos: Sequence[FactRevenueDto],
    ) -> int:
        """Insert multiple fact records in a single transaction.

        Records with duplicate ``source_row_id`` values are silently skipped
        (idempotency via ``ON CONFLICT DO NOTHING``). This allows the ETL
        pipeline to safely re-run on the same input without creating
        duplicate rows.

        Args:
            dtos: Sequence of fact records to persist. May be empty.

        Returns:
            The number of rows actually inserted (excluding duplicates).

        Raises:
            IntegrityViolationError: When a foreign key constraint is
                violated (e.g., ``movie_id`` references a non-existent
                movie).
        """
        ...

    async def get_by_id(
        self: "FactRevenueRepositoryProtocol",
        revenue_id: int,
    ) -> FactRevenueDto | None:
        """Retrieve a fact record by its surrogate key.

        Args:
            revenue_id: Surrogate primary key.

        Returns:
            A populated ``FactRevenueDto`` when the record exists, or
            ``None`` when no fact with the given ID is found.
        """
        ...
