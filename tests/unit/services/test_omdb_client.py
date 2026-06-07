"""Unit tests for the OMDb HTTP client."""

import json

import httpx
import pytest

from src.models.omdb import OMDB_RATE_LIMIT_ERROR_REASON
from src.services.omdb_client import OmdbClient


@pytest.mark.asyncio
async def test_fetch_by_title_detailed_detects_rate_limit_in_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"Response": "False", "Error": "Request limit reached!"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OmdbClient(api_key="test-key", http_client=http_client)
        outcome = await client.fetch_by_title_detailed("Inception")

    assert outcome.movie is None
    assert outcome.error_reason == OMDB_RATE_LIMIT_ERROR_REASON
    assert outcome.error_message == "Request limit reached!"


@pytest.mark.asyncio
async def test_fetch_by_title_detailed_detects_rate_limit_on_http_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=401,
            content=json.dumps({"Response": "False", "Error": "Request limit reached!"}),
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OmdbClient(api_key="test-key", http_client=http_client)
        outcome = await client.fetch_by_title_detailed("Inception")

    assert outcome.error_reason == OMDB_RATE_LIMIT_ERROR_REASON
