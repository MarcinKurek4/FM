"""Structural interface for the movie dimension repository.

Consumers depend on ``DimMovieRepositoryProtocol`` rather than the concrete
repository implementation. This keeps the service layer decoupled from the
persistence layer and makes repositories trivial to stub in tests.
"""

from collections.abc import Sequence
from typing import Protocol

from src.models.dwh import DimMovieDto


class DimMovieRepositoryProtocol(Protocol):
    """Structural interface for movie dimension persistence.

    Any class that implements the methods below with matching signatures
    satisfies this protocol — no inheritance required.

    Example:
        class FakeDimMovieRepository:
            async def get_by_id(self, movie_id: int) -> DimMovieDto | None:
                return None

        repo: DimMovieRepositoryProtocol = FakeDimMovieRepository()
    """

    async def get_by_id(
        self: "DimMovieRepositoryProtocol",
        movie_id: int,
    ) -> DimMovieDto | None:
        """Retrieve a movie by its surrogate key.

        Args:
            movie_id: Surrogate primary key.

        Returns:
            A populated ``DimMovieDto`` when the record exists, or ``None``
            when no movie with the given ID is found.
        """
        ...

    async def get_by_natural_key(
        self: "DimMovieRepositoryProtocol",
        imdb_id: str,
    ) -> DimMovieDto | None:
        """Retrieve a movie by its natural key.

        Args:
            imdb_id: IMDb title identifier (e.g., ``"tt1375666"``).

        Returns:
            A populated ``DimMovieDto`` when the record exists, or ``None``
            when no movie with the given IMDb ID is found.
        """
        ...

    async def upsert(
        self: "DimMovieRepositoryProtocol",
        dto: DimMovieDto,
    ) -> DimMovieDto:
        """Insert or update a movie record.

        If a movie with the given ``imdb_id`` already exists, its fields are
        updated (SCD Type 1). Otherwise, a new record is inserted.

        Args:
            dto: Movie data to persist. The ``movie_id`` field is ignored on
                insert — the database generates a new surrogate key.

        Returns:
            The persisted ``DimMovieDto`` with the ``movie_id`` populated.

        Raises:
            IntegrityViolationError: When a database constraint is violated
                (e.g., ``rated_id`` references a non-existent rating).
        """
        ...

    async def list_all_movies(
        self: "DimMovieRepositoryProtocol",
    ) -> list[DimMovieDto]:
        """Return every movie in ``dim_movie`` ordered by ``movie_id``.

        Returns:
            All persisted ``DimMovieDto`` rows, sorted ascending by
            ``movie_id``. May be empty when the dimension has no rows.

        Example:
            movies = await repo.list_all_movies()
        """
        ...

    async def bulk_load_title_map(
        self: "DimMovieRepositoryProtocol",
    ) -> dict[str, int]:
        """Load all movies as an uppercase-normalised title-to-ID map.

        Returns:
            Mapping of ``title.upper() → movie_id`` for every row currently
            in ``dim_movie``.

        Example:
            title_map = await repo.bulk_load_title_map()
            movie_id = title_map.get("INCEPTION")
        """
        ...

    async def bulk_upsert(
        self: "DimMovieRepositoryProtocol",
        dtos: Sequence[DimMovieDto],
    ) -> list[DimMovieDto]:
        """Insert or update multiple movie records in a single transaction.

        Each DTO is upserted by its ``imdb_id`` natural key. Existing records
        are updated; new records are inserted.

        Args:
            dtos: Sequence of movie records to persist. May be empty.

        Returns:
            List of persisted ``DimMovieDto`` instances with ``movie_id``
            fields populated. The order matches the input order.

        Raises:
            IntegrityViolationError: When any constraint is violated.
        """
        ...
