"""Structural interface for the genre dimension repository.

Consumers depend on ``DimGenreRepositoryProtocol`` rather than the concrete
repository implementation.
"""

from typing import Protocol

from src.models.dwh import DimGenreDto


class DimGenreRepositoryProtocol(Protocol):
    """Structural interface for genre dimension persistence.

    Genres are extracted from the OMDb ``Genre`` field (a comma-separated
    string like ``"Action, Adventure, Sci-Fi"``). The service layer is
    responsible for splitting this field before calling repository methods.
    """

    async def get_by_id(
        self: "DimGenreRepositoryProtocol",
        genre_id: int,
    ) -> DimGenreDto | None:
        """Retrieve a genre by its surrogate key.

        Args:
            genre_id: Surrogate primary key.

        Returns:
            A populated ``DimGenreDto`` when the record exists, or ``None``
            when no genre with the given ID is found.
        """
        ...

    async def get_by_natural_key(
        self: "DimGenreRepositoryProtocol",
        genre_name: str,
    ) -> DimGenreDto | None:
        """Retrieve a genre by its natural key.

        Args:
            genre_name: Genre label (e.g., ``"Action"``).

        Returns:
            A populated ``DimGenreDto`` when the record exists, or ``None``
            when no genre with the given name is found.
        """
        ...

    async def upsert(
        self: "DimGenreRepositoryProtocol",
        dto: DimGenreDto,
    ) -> DimGenreDto:
        """Insert or update a genre record.

        If a genre with the given ``genre_name`` already exists, its fields
        are updated. Otherwise, a new record is inserted.

        Args:
            dto: Genre data to persist. The ``genre_id`` field is ignored
                on insert — the database generates a new surrogate key.

        Returns:
            The persisted ``DimGenreDto`` with the ``genre_id`` populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated.
        """
        ...
