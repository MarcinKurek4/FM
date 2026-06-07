"""Structural interface for the movie-director bridge table repository."""

from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import BridgeMovieDirectorDto


class BridgeMovieDirectorRepositoryProtocol(Protocol):
    """Structural interface for movie-director bridge persistence.

    The composite natural key is ``(movie_id, director_id)``.
    """

    async def get_by_natural_key(
        self: "BridgeMovieDirectorRepositoryProtocol",
        movie_id: int,
        director_id: int,
    ) -> BridgeMovieDirectorDto | None:
        """Retrieve an association by composite key.

        Args:
            movie_id: Foreign key to ``dim_movie``.
            director_id: Foreign key to ``dim_director``.

        Returns:
            A populated DTO when the row exists, otherwise ``None``.
        """
        ...

    async def upsert(
        self: "BridgeMovieDirectorRepositoryProtocol",
        dto: BridgeMovieDirectorDto,
    ) -> tuple[BridgeMovieDirectorDto, bool]:
        """Insert the association when absent; return existing row otherwise.

        Args:
            dto: Bridge row to persist.

        Returns:
            A tuple of ``(persisted_dto, inserted)`` where ``inserted`` is
            ``True`` only when a new row was created.

        Raises:
            IntegrityViolationError: When a foreign key constraint is violated.
        """
        ...

    async def bulk_upsert(
        self: "BridgeMovieDirectorRepositoryProtocol",
        dtos: Sequence[BridgeMovieDirectorDto],
    ) -> tuple[list[BridgeMovieDirectorDto], int]:
        """Insert multiple associations idempotently.

        Args:
            dtos: Bridge rows to persist. May be empty.

        Returns:
            A tuple of ``(persisted_dtos, inserted_count)``.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        ...
