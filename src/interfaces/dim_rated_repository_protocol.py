"""Structural interface for the rating dimension repository.

Consumers depend on ``DimRatedRepositoryProtocol`` rather than the concrete
repository implementation.
"""

from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import DimRatedDto


class DimRatedRepositoryProtocol(Protocol):
    """Structural interface for MPAA rating dimension persistence.

    This mini-dimension normalises the ``rated`` field from OMDb into a
    separate lookup table. The dimension should be pre-seeded with standard
    MPAA ratings (G, PG, PG-13, R, NC-17, etc.) before fact data is loaded.
    """

    async def get_by_id(
        self: "DimRatedRepositoryProtocol",
        rated_id: int,
    ) -> DimRatedDto | None:
        """Retrieve a rating by its surrogate key.

        Args:
            rated_id: Surrogate primary key.

        Returns:
            A populated ``DimRatedDto`` when the record exists, or ``None``
            when no rating with the given ID is found.
        """
        ...

    async def get_by_natural_key(
        self: "DimRatedRepositoryProtocol",
        rating_code: str,
    ) -> DimRatedDto | None:
        """Retrieve a rating by its natural key.

        Args:
            rating_code: MPAA rating code (e.g., ``"PG-13"``, ``"R"``).

        Returns:
            A populated ``DimRatedDto`` when the record exists, or ``None``
            when no rating with the given code is found.
        """
        ...

    async def upsert(
        self: "DimRatedRepositoryProtocol",
        dto: DimRatedDto,
    ) -> DimRatedDto:
        """Insert or update a rating record.

        If a rating with the given ``rating_code`` already exists, its
        fields are updated. Otherwise, a new record is inserted.

        Args:
            dto: Rating data to persist. The ``rated_id`` field is ignored
                on insert — the database generates a new surrogate key.

        Returns:
            The persisted ``DimRatedDto`` with the ``rated_id`` populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        ...

    async def bulk_upsert(
        self: "DimRatedRepositoryProtocol",
        dtos: Sequence[DimRatedDto],
    ) -> list[DimRatedDto]:
        """Insert or update multiple rating records in a single transaction.

        Each DTO is upserted by its ``rating_code`` natural key. Existing
        records are updated; new records are inserted.

        Args:
            dtos: Sequence of rating records to persist. May be empty.

        Returns:
            List of persisted ``DimRatedDto`` instances with ``rated_id``
            fields populated. The order matches the input order.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        ...
