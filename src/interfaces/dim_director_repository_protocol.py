"""Structural interface for the director dimension repository.

Consumers depend on ``DimDirectorRepositoryProtocol`` rather than the
concrete repository implementation.
"""

from typing import Protocol

from src.models.dwh import DimDirectorDto


class DimDirectorRepositoryProtocol(Protocol):
    """Structural interface for director dimension persistence.

    Directors are extracted from the OMDb ``Director`` field (a
    comma-separated string when multiple directors are credited). The
    service layer is responsible for splitting this field before calling
    repository methods.
    """

    async def get_by_id(
        self: "DimDirectorRepositoryProtocol",
        director_id: int,
    ) -> DimDirectorDto | None:
        """Retrieve a director by its surrogate key.

        Args:
            director_id: Surrogate primary key.

        Returns:
            A populated ``DimDirectorDto`` when the record exists, or
            ``None`` when no director with the given ID is found.
        """
        ...

    async def get_by_natural_key(
        self: "DimDirectorRepositoryProtocol",
        director_name: str,
    ) -> DimDirectorDto | None:
        """Retrieve a director by its natural key.

        Args:
            director_name: Director full name (e.g., ``"Christopher Nolan"``).

        Returns:
            A populated ``DimDirectorDto`` when the record exists, or
            ``None`` when no director with the given name is found.
        """
        ...

    async def upsert(
        self: "DimDirectorRepositoryProtocol",
        dto: DimDirectorDto,
    ) -> DimDirectorDto:
        """Insert or update a director record.

        If a director with the given ``director_name`` already exists, its
        fields are updated. Otherwise, a new record is inserted.

        Args:
            dto: Director data to persist. The ``director_id`` field is
                ignored on insert — the database generates a new surrogate
                key.

        Returns:
            The persisted ``DimDirectorDto`` with the ``director_id``
            populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        ...
