"""Unit tests for OMDb error helpers."""

from src.utils.omdb_errors import is_omdb_rate_limit_response


def test_is_omdb_rate_limit_response_matches_request_limit_message() -> None:
    assert is_omdb_rate_limit_response(error_message="Request limit reached!") is True


def test_is_omdb_rate_limit_response_matches_daily_limit_message() -> None:
    assert is_omdb_rate_limit_response(error_message="Daily request limit reached!") is True


def test_is_omdb_rate_limit_response_matches_http_429() -> None:
    assert is_omdb_rate_limit_response(status_code=429) is True


def test_is_omdb_rate_limit_response_rejects_not_found_message() -> None:
    assert is_omdb_rate_limit_response(error_message="Movie not found!") is False
