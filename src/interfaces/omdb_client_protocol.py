"""Structural interface for the OMDb API client.

Consumers depend on ``OmdbClientProtocol`` rather than the concrete
``OmdbClient`` implementation. This keeps the service layer decoupled
from the HTTP transport and makes the client trivial to stub in tests.
"""

from typing import Protocol

from src.models.omdb import OmdbMovieResponse, OmdbTitleFetchOutcome


class OmdbClientProtocol(Protocol):
    """Structural interface for fetching movie metadata from OMDb.

    Any class that implements ``fetch_by_title`` with the correct signature
    satisfies this protocol — no inheritance required.

    Example:
        class FakeOmdbClient:
            async def fetch_by_title(
                self, title: str
            ) -> OmdbMovieResponse | None:
                return None

        client: OmdbClientProtocol = FakeOmdbClient()
    """

    async def fetch_by_title(
        self: "OmdbClientProtocol",
        title: str,
    ) -> OmdbMovieResponse | None:
        """Fetch metadata for a single movie title from the OMDb API.

        Args:
            title: Movie title to search for. Passed as the ``t`` query
                parameter to the OMDb API.

        Returns:
            A populated ``OmdbMovieResponse`` when the API finds a match,
            or ``None`` when the title is not found or the API returns an
            error response.
        """
        ...

    async def fetch_by_title_detailed(
        self: "OmdbClientProtocol",
        title: str,
    ) -> OmdbTitleFetchOutcome:
        """Fetch metadata and preserve the request title on failure.

        Args:
            title: Movie title to search for.

        Returns:
            Structured outcome with ``request_title``, optional ``movie``,
            and ``error_reason`` when the lookup fails.
        """
        ...

    async def fetch_by_imdb_id_detailed(
        self: "OmdbClientProtocol",
        imdb_id: str,
    ) -> OmdbTitleFetchOutcome:
        """Fetch metadata by IMDb title identifier.

        Args:
            imdb_id: IMDb ID (e.g. ``"tt1375666"``), sent as the ``i``
                query parameter.

        Returns:
            Structured outcome with ``request_title`` set to ``imdb_id``,
            optional ``movie``, and ``error_reason`` when the lookup fails.
        """
        ...
