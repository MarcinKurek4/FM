"""OMDb API client implementation.

Wraps ``httpx.AsyncClient`` to provide typed, validated access to the
OMDb REST API. The client is stateless and relies on an externally managed
``AsyncClient`` instance for connection pooling and lifecycle control.

Usage::

    import httpx
    from src.services.omdb_client import OmdbClient

    async with httpx.AsyncClient() as http:
        client = OmdbClient(api_key="your_key", http_client=http)
        movie = await client.fetch_by_title("Inception")
        if movie:
            print(movie.imdb_rating)
"""

import httpx
from loguru import logger
from pydantic import ValidationError

from src.models.omdb import (
    OMDB_RATE_LIMIT_ERROR_REASON,
    OmdbMovieResponse,
    OmdbTitleFetchOutcome,
)
from src.utils.omdb_errors import is_omdb_rate_limit_response

_TITLE_PARAM: str = "t"
_IMDB_ID_PARAM: str = "i"
_PLOT_PARAM: str = "plot"
_PLOT_VALUE: str = "full"
_APIKEY_PARAM: str = "apikey"


class OmdbClient:
    """HTTP client for the OMDb REST API.

    Satisfies ``OmdbClientProtocol`` structurally — no inheritance required.

    The ``http_client`` is injected rather than created internally so that:

    - A single ``AsyncClient`` instance (with its connection pool) is reused
      across all requests made during a pipeline run.
    - Tests can pass an ``httpx.Client`` built with ``MockTransport`` without
      any monkey-patching.

    Attributes:
        _api_key: OMDb API key appended to every request.
        _base_url: Base URL of the OMDb API endpoint.
        _http_client: Shared async HTTP client.

    Example:
        import httpx
        from src.services.omdb_client import OmdbClient

        async with httpx.AsyncClient() as http:
            client = OmdbClient(api_key="abc123", http_client=http)
            movie = await client.fetch_by_title("The Matrix")
    """

    __slots__ = ("_api_key", "_base_url", "_http_client")

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        base_url: str = "https://www.omdbapi.com/",
    ) -> None:
        """Initialise the OMDb client.

        Args:
            api_key: OMDb API key for authentication.
            http_client: Shared ``httpx.AsyncClient`` instance. The caller
                is responsible for its lifecycle (open/close).
            base_url: Base URL of the OMDb API. Defaults to the public
                production endpoint.
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/") + "/"
        self._http_client = http_client

    async def fetch_by_title(
        self,
        title: str,
    ) -> OmdbMovieResponse | None:
        """Fetch metadata for a movie title from the OMDb API.

        Performs a title search using the ``?t=`` parameter with
        ``plot=full``. Returns ``None`` when the API signals no match
        (``Response: "False"``) or when an HTTP or validation error occurs.

        Args:
            title: Movie title to look up. Sent verbatim as the ``t``
                query parameter; URL encoding is handled by ``httpx``.

        Returns:
            A validated ``OmdbMovieResponse`` on success, or ``None`` when
            the title is not found or the request fails.

        Raises:
            httpx.TimeoutException: When the API does not respond within
                the ``AsyncClient`` timeout configured by the caller.
        """
        outcome = await self.fetch_by_title_detailed(title)
        return outcome.movie

    async def fetch_by_title_detailed(
        self,
        title: str,
    ) -> OmdbTitleFetchOutcome:
        """Fetch metadata and return structured success or failure details.

        Args:
            title: Movie title to look up.

        Returns:
            ``OmdbTitleFetchOutcome`` with the original request title,
            validated movie data on success, or an ``error_reason`` code.

        Raises:
            httpx.TimeoutException: When the API does not respond within
                the ``AsyncClient`` timeout configured by the caller.
        """
        params = {
            _TITLE_PARAM: title,
            _PLOT_PARAM: _PLOT_VALUE,
            _APIKEY_PARAM: self._api_key,
        }
        return await self._fetch_detailed(request_label=title, params=params)

    async def fetch_by_imdb_id(
        self,
        imdb_id: str,
    ) -> OmdbMovieResponse | None:
        """Fetch metadata for an IMDb title identifier from the OMDb API.

        Args:
            imdb_id: IMDb ID (e.g. ``"tt1375666"``).

        Returns:
            A validated ``OmdbMovieResponse`` on success, or ``None`` on failure.

        Raises:
            httpx.TimeoutException: When the API does not respond in time.
        """
        outcome = await self.fetch_by_imdb_id_detailed(imdb_id)
        return outcome.movie

    async def fetch_by_imdb_id_detailed(
        self,
        imdb_id: str,
    ) -> OmdbTitleFetchOutcome:
        """Fetch metadata by IMDb ID and return structured outcome details.

        Args:
            imdb_id: IMDb ID sent as the ``i`` query parameter.

        Returns:
            ``OmdbTitleFetchOutcome`` with ``request_title`` set to ``imdb_id``.

        Raises:
            httpx.TimeoutException: When the API does not respond in time.
        """
        params = {
            _IMDB_ID_PARAM: imdb_id,
            _PLOT_PARAM: _PLOT_VALUE,
            _APIKEY_PARAM: self._api_key,
        }
        return await self._fetch_detailed(request_label=imdb_id, params=params)

    async def _fetch_detailed(
        self,
        request_label: str,
        params: dict[str, str],
    ) -> OmdbTitleFetchOutcome:
        """Execute an OMDb GET request and map the response to an outcome.

        Args:
            request_label: Title or IMDb ID used for logging.
            params: Query parameters including ``apikey``.

        Returns:
            Structured success or failure outcome.
        """
        logger.debug("Fetching OMDb metadata", extra={"request_label": request_label})

        try:
            response = await self._http_client.get(self._base_url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_message = _extract_error_message(exc.response)
            status_code = exc.response.status_code
            if is_omdb_rate_limit_response(
                status_code=status_code,
                error_message=error_message,
            ):
                logger.error(
                    "OMDb rate limit exceeded",
                    extra={
                        "request_label": request_label,
                        "status_code": status_code,
                        "error_message": error_message,
                    },
                )
                return OmdbTitleFetchOutcome(
                    request_title=request_label,
                    movie=None,
                    error_reason=OMDB_RATE_LIMIT_ERROR_REASON,
                    error_message=error_message,
                )
            logger.warning(
                "OMDb HTTP error",
                extra={"request_label": request_label, "status_code": status_code},
            )
            return OmdbTitleFetchOutcome(
                request_title=request_label,
                movie=None,
                error_reason="http_error",
                error_message=error_message,
            )
        except httpx.RequestError as exc:
            logger.error(
                "OMDb request failed",
                extra={"request_label": request_label, "error": str(exc)},
            )
            return OmdbTitleFetchOutcome(
                request_title=request_label,
                movie=None,
                error_reason="request_error",
            )

        payload: dict = response.json()

        if not payload.get("Response", "False").lower() == "true":
            error_message = _string_or_none(payload.get("Error"))
            if is_omdb_rate_limit_response(error_message=error_message):
                logger.error(
                    "OMDb rate limit exceeded",
                    extra={"request_label": request_label, "error_message": error_message},
                )
                return OmdbTitleFetchOutcome(
                    request_title=request_label,
                    movie=None,
                    error_reason=OMDB_RATE_LIMIT_ERROR_REASON,
                    error_message=error_message,
                )
            logger.debug(
                "OMDb lookup not found",
                extra={"request_label": request_label, "error_message": error_message},
            )
            return OmdbTitleFetchOutcome(
                request_title=request_label,
                movie=None,
                error_reason="not_found",
                error_message=error_message,
            )

        try:
            movie = OmdbMovieResponse.model_validate(payload)
        except ValidationError as exc:
            logger.error(
                "OMDb response validation failed",
                extra={"request_label": request_label, "error": str(exc)},
            )
            return OmdbTitleFetchOutcome(
                request_title=request_label,
                movie=None,
                error_reason="validation_error",
            )

        logger.debug(
            "OMDb metadata fetched",
            extra={"request_label": request_label, "imdb_id": movie.imdb_id},
        )
        return OmdbTitleFetchOutcome(request_title=request_label, movie=movie)


def _extract_error_message(response: httpx.Response) -> str | None:
    """Read the OMDb ``Error`` field from an HTTP error response body.

    Args:
        response: HTTP response returned by the OMDb API.

    Returns:
        Error message string when present, otherwise ``None``.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        return _string_or_none(payload.get("Error"))
    return None


def _string_or_none(value: object) -> str | None:
    """Convert a value to string when it is a non-empty string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
