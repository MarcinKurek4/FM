"""Repository implementation for the movie rating fact table with SCD Type 2.

This module provides concrete persistence operations for
``dwh.fact_movie_rating`` using an injected ``AsyncSession``. It implements
Slowly Changing Dimension Type 2 logic for tracking historical rating changes.
"""

import time
from collections.abc import Sequence

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.dwh import FactMovieRatingDto
from src.models.dwh_tables import FactMovieRatingTable
from src.repositories.exceptions import IntegrityViolationError
from src.utils.dwh_mappers import fact_movie_rating_dto_to_table, fact_movie_rating_table_to_dto


class FactMovieRatingRepository:
    """Repository for movie rating fact table persistence with SCD Type 2.

    Satisfies ``FactMovieRatingRepositoryProtocol`` structurally. Implements
    SCD Type 2 logic: when a new rating is inserted, the previous current
    record is automatically closed.

    Attributes:
        _session: Injected async database session.

    Example:
        async with factory.get_session() as session:
            repo = FactMovieRatingRepository(session)
            current = await repo.get_current_rating(movie_id=1)
    """

    __slots__ = ("_session",)

    def __init__(self: "FactMovieRatingRepository", session: AsyncSession) -> None:
        """Initialise the repository with an async session.

        Args:
            session: Active async database session. The caller is
                responsible for session lifecycle (commit, rollback, close).
        """
        self._session = session

    async def get_current_rating(
        self: "FactMovieRatingRepository",
        movie_id: int,
    ) -> FactMovieRatingDto | None:
        """Retrieve the current (active) rating for a movie.

        Args:
            movie_id: Surrogate key of the movie.

        Returns:
            The ``FactMovieRatingDto`` with ``is_current=True``, or ``None``
            when no rating exists for the given movie.
        """
        start = time.perf_counter()
        logger.debug("Fetching current rating", extra={"movie_id": movie_id})

        result = await self._session.execute(
            select(FactMovieRatingTable).where(
                FactMovieRatingTable.movie_id == movie_id,
                FactMovieRatingTable.is_current == True,  # noqa: E712
            )
        )
        table = result.scalar_one_or_none()

        duration_ms = (time.perf_counter() - start) * 1000
        if table is None:
            logger.debug(
                "Current rating not found",
                extra={"movie_id": movie_id, "duration_ms": duration_ms},
            )
            return None

        dto = fact_movie_rating_table_to_dto(table)
        logger.debug(
            "Current rating fetched",
            extra={
                "movie_id": movie_id,
                "rating_id": dto.rating_id,
                "imdb_rating": str(dto.imdb_rating) if dto.imdb_rating else None,
                "duration_ms": duration_ms,
            },
        )
        return dto

    async def insert_new_rating(
        self: "FactMovieRatingRepository",
        dto: FactMovieRatingDto,
    ) -> FactMovieRatingDto:
        """Insert a new rating snapshot and close the previous current record.

        This method implements SCD Type 2 logic:
        1. If a current rating exists for the movie, close it.
        2. Insert the new rating with ``is_current=True``.

        Args:
            dto: Rating data to persist.

        Returns:
            The persisted ``FactMovieRatingDto`` with the ``rating_id``
            populated.

        Raises:
            IntegrityViolationError: When a foreign key constraint is
                violated.
        """
        start = time.perf_counter()
        logger.debug("Inserting new rating (SCD Type 2)", extra={"movie_id": dto.movie_id})

        try:
            existing_current = await self.get_current_rating(dto.movie_id)

            if existing_current is not None:
                existing_table = fact_movie_rating_dto_to_table(existing_current)
                existing_table.is_current = False
                existing_table.valid_to = dto.valid_from
                self._session.add(existing_table)
                await self._session.flush()
                logger.debug(
                    "Closed previous rating record",
                    extra={
                        "movie_id": dto.movie_id,
                        "rating_id": existing_current.rating_id,
                        "valid_to": dto.valid_from.isoformat(),
                    },
                )

            new_table = fact_movie_rating_dto_to_table(dto)
            new_table.rating_id = None
            new_table.is_current = True
            new_table.valid_to = None
            self._session.add(new_table)
            await self._session.flush()
            await self._session.refresh(new_table)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Rating insert integrity violation",
                extra={"movie_id": dto.movie_id, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        persisted = fact_movie_rating_table_to_dto(new_table)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "New rating inserted",
            extra={
                "movie_id": persisted.movie_id,
                "rating_id": persisted.rating_id,
                "imdb_rating": str(persisted.imdb_rating) if persisted.imdb_rating else None,
                "duration_ms": duration_ms,
            },
        )
        return persisted

    async def get_rating_history(
        self: "FactMovieRatingRepository",
        movie_id: int,
    ) -> list[FactMovieRatingDto]:
        """Retrieve all rating snapshots for a movie, ordered by valid_from.

        Args:
            movie_id: Surrogate key of the movie.

        Returns:
            List of ``FactMovieRatingDto`` instances, ordered from oldest
            to newest. May be empty if no ratings exist for the movie.
        """
        start = time.perf_counter()
        logger.debug("Fetching rating history", extra={"movie_id": movie_id})

        result = await self._session.execute(
            select(FactMovieRatingTable)
            .where(FactMovieRatingTable.movie_id == movie_id)
            .order_by(FactMovieRatingTable.valid_from)
        )
        tables = result.scalars().all()

        dtos = [fact_movie_rating_table_to_dto(table) for table in tables]
        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Rating history fetched",
            extra={"movie_id": movie_id, "count": len(dtos), "duration_ms": duration_ms},
        )
        return dtos

    async def bulk_insert(
        self: "FactMovieRatingRepository",
        dtos: Sequence[FactMovieRatingDto],
    ) -> int:
        """Insert multiple rating snapshots in a single transaction.

        Args:
            dtos: Sequence of rating records to persist. May be empty.

        Returns:
            The number of rows actually inserted.

        Raises:
            IntegrityViolationError: When a foreign key constraint is
                violated.
        """
        start = time.perf_counter()
        count = len(dtos)
        logger.debug("Bulk inserting ratings", extra={"count": count})

        if count == 0:
            return 0

        try:
            for dto in dtos:
                table = fact_movie_rating_dto_to_table(dto)
                table.rating_id = None
                self._session.add(table)

            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            logger.error(
                "Rating bulk insert integrity violation",
                extra={"count": count, "error": str(exc.orig)},
            )
            raise IntegrityViolationError(
                constraint_name=getattr(exc.orig, "constraint_name", None),
                detail=str(exc.orig),
            ) from exc

        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Ratings bulk inserted",
            extra={"count": count, "duration_ms": duration_ms},
        )
        return count
