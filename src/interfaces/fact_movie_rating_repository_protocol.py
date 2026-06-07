"""Structural interface for the movie rating fact table repository.

Consumers depend on ``FactMovieRatingRepositoryProtocol`` rather than the
concrete repository implementation.
"""

from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import FactMovieRatingDto


class FactMovieRatingRepositoryProtocol(Protocol):
    """Structural interface for movie rating fact table persistence.

    This fact table tracks historical IMDb rating changes using Slowly
    Changing Dimension Type 2. Each movie may have multiple rating records
    (one per change), with ``is_current=True`` marking the active record.

    The repository handles SCD Type 2 logic: when a new rating is inserted,
    the previous current record is automatically closed (``valid_to`` set,
    ``is_current`` set to ``False``).
    """

    async def get_current_rating(
        self: "FactMovieRatingRepositoryProtocol",
        movie_id: int,
    ) -> FactMovieRatingDto | None:
        """Retrieve the current (active) rating for a movie.

        Args:
            movie_id: Surrogate key of the movie.

        Returns:
            The ``FactMovieRatingDto`` with ``is_current=True``, or ``None``
            when no rating exists for the given movie.
        """
        ...

    async def insert_new_rating(
        self: "FactMovieRatingRepositoryProtocol",
        dto: FactMovieRatingDto,
    ) -> FactMovieRatingDto:
        """Insert a new rating snapshot and close the previous current record.

        This method implements SCD Type 2 logic:
        1. If a current rating exists for the movie, close it (set
           ``valid_to`` and ``is_current=False``).
        2. Insert the new rating with ``is_current=True``.

        Args:
            dto: Rating data to persist. The ``rating_id`` field is ignored
                on insert — the database generates a new surrogate key.
                ``is_current`` should be ``True`` and ``valid_to`` should
                be ``None``.

        Returns:
            The persisted ``FactMovieRatingDto`` with the ``rating_id``
            populated.

        Raises:
            IntegrityViolationError: When a foreign key constraint is
                violated (e.g., ``movie_id`` references a non-existent
                movie).
        """
        ...

    async def get_rating_history(
        self: "FactMovieRatingRepositoryProtocol",
        movie_id: int,
    ) -> list[FactMovieRatingDto]:
        """Retrieve all rating snapshots for a movie, ordered by valid_from.

        Args:
            movie_id: Surrogate key of the movie.

        Returns:
            List of ``FactMovieRatingDto`` instances, ordered from oldest
            to newest. May be empty if no ratings exist for the movie.
        """
        ...

    async def bulk_insert(
        self: "FactMovieRatingRepositoryProtocol",
        dtos: Sequence[FactMovieRatingDto],
    ) -> int:
        """Insert multiple rating snapshots in a single transaction.

        Each DTO is inserted as-is without SCD Type 2 logic. This method
        is intended for initial data loading or historical backfill, not
        for incremental updates.

        Args:
            dtos: Sequence of rating records to persist. May be empty.

        Returns:
            The number of rows actually inserted.

        Raises:
            IntegrityViolationError: When a foreign key constraint is
                violated.
        """
        ...
