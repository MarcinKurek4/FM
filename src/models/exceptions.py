"""Domain exceptions for the FM analytics pipeline.

All application-level exception classes are defined here. Infrastructure
exceptions (database, network) live in their respective sub-packages
(``src/repositories/exceptions.py``).

Usage::

    from src.models.exceptions import OmdbApiError

    raise OmdbApiError(status_code=429, message="Daily request limit reached.")
"""


class OmdbApiError(Exception):
    """Raised when the OMDb API returns an unrecoverable HTTP error.

    This exception signals that the pipeline must be aborted because the
    OMDb API refused the request (authentication failure or rate limit
    exhaustion). The caller is responsible for translating this into an
    appropriate HTTP response.

    Attributes:
        status_code: HTTP status code returned by the OMDb API (e.g. 401, 429).
        message: Human-readable error detail from the API response body.

    Example:
        try:
            await service.run(csv_bytes)
        except OmdbApiError as exc:
            return JSONResponse(
                status_code=422,
                content={"error": "omdb_api_error", "status_code": exc.status_code},
            )
    """

    __slots__ = ("message", "status_code")

    def __init__(self: "OmdbApiError", status_code: int, message: str) -> None:
        """Initialise the exception with an HTTP status code and message.

        Args:
            status_code: HTTP status code returned by the OMDb API.
            message: Error detail from the API response body.
        """
        super().__init__(message)
        self.status_code: int = status_code
        self.message: str = message
