"""Helpers for interpreting OMDb API error responses.

The OMDb API often returns HTTP 200 with ``Response: "False"`` and an
``Error`` message. Rate-limit failures may also appear as HTTP 401 or 429.
"""

_RATE_LIMIT_MARKERS: tuple[str, ...] = (
    "request limit reached",
    "daily request limit",
    "limit reached",
)


def is_omdb_rate_limit_response(
    *,
    status_code: int | None = None,
    error_message: str | None = None,
) -> bool:
    """Return whether an OMDb response indicates a rate-limit violation.

    Args:
        status_code: HTTP status code from the API response.
        error_message: Value of the JSON ``Error`` field when present.

    Returns:
        ``True`` when the response signals that the daily request quota
        has been exhausted.

    Example:
        is_omdb_rate_limit_response(error_message="Request limit reached!")
    """
    if status_code == 429:
        return True

    if not error_message:
        return False

    normalized = error_message.strip().lower()
    return any(marker in normalized for marker in _RATE_LIMIT_MARKERS)
