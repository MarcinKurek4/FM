"""Structural interface for the movie-genre bridge table repository."""

from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import BridgeMovieGenreDto


class BridgeMovieGenreRepositoryProtocol(Protocol):
    """Structural interface for movie-genre bridge persistence.

    The composite natural key is ``(movie_id, genre_id)``.
    """

    async def get_by_natural_key(
        self: "BridgeMovieGenreRepositoryProtocol",
        movie_id: int,
        genre_id: int,
    ) -> BridgeMovieGenreDto | None:
        """Retrieve an association by composite key.

        Args:
            movie_id: Foreign key to ``dim_movie``.
            genre_id: Foreign key to ``dim_genre``.

        Returns:
            A populated DTO when the row exists, otherwise ``None``.
        """
        ...

    async def upsert(
        self: "BridgeMovieGenreRepositoryProtocol",
        dto: BridgeMovieGenreDto,
    ) -> tuple[BridgeMovieGenreDto, bool]:
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
        self: "BridgeMovieGenreRepositoryProtocol",
        dtos: Sequence[BridgeMovieGenreDto],
    ) -> tuple[list[BridgeMovieGenreDto], int]:
        """Insert multiple associations idempotently.

        Args:
            dtos: Bridge rows to persist. May be empty.

        Returns:
            A tuple of ``(persisted_dtos, inserted_count)``.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        ...
