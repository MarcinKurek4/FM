"""Structural interface for the distributor dimension repository.

Consumers depend on ``DimDistributorRepositoryProtocol`` rather than the
concrete repository implementation.
"""

from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import DimDistributorDto


class DimDistributorRepositoryProtocol(Protocol):
    """Structural interface for distributor dimension persistence.

    The ETL pipeline should pre-seed an ``"Unknown"`` distributor record
    (with ``distributor_id = 0``) to handle source CSV rows where the
    distributor field contains the sentinel value ``"-"``.
    """

    async def get_by_id(
        self: "DimDistributorRepositoryProtocol",
        distributor_id: int,
    ) -> DimDistributorDto | None:
        """Retrieve a distributor by its surrogate key.

        Args:
            distributor_id: Surrogate primary key.

        Returns:
            A populated ``DimDistributorDto`` when the record exists, or
            ``None`` when no distributor with the given ID is found.
        """
        ...

    async def get_by_natural_key(
        self: "DimDistributorRepositoryProtocol",
        distributor_name: str,
    ) -> DimDistributorDto | None:
        """Retrieve a distributor by its natural key.

        Args:
            distributor_name: Company name (e.g., ``"Paramount Pictures"``).

        Returns:
            A populated ``DimDistributorDto`` when the record exists, or
            ``None`` when no distributor with the given name is found.
        """
        ...

    async def upsert(
        self: "DimDistributorRepositoryProtocol",
        dto: DimDistributorDto,
    ) -> DimDistributorDto:
        """Insert or update a distributor record.

        If a distributor with the given ``distributor_name`` already exists,
        its fields are updated. Otherwise, a new record is inserted.

        Args:
            dto: Distributor data to persist. The ``distributor_id`` field
                is ignored on insert — the database generates a new
                surrogate key.

        Returns:
            The persisted ``DimDistributorDto`` with the ``distributor_id``
            populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        ...

    async def bulk_upsert(
        self: "DimDistributorRepositoryProtocol",
        dtos: Sequence[DimDistributorDto],
    ) -> list[DimDistributorDto]:
        """Insert or update multiple distributor records in a single transaction.

        Each DTO is upserted by its ``distributor_name`` natural key.
        Existing records are updated; new records are inserted.

        Args:
            dtos: Sequence of distributor records to persist. May be empty.

        Returns:
            List of persisted ``DimDistributorDto`` instances with
            ``distributor_id`` fields populated. The order matches the
            input order.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        ...
