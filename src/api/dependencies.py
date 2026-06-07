"""FastAPI dependency functions for shared infrastructure resources.

All dependency functions use ``async def`` with ``yield`` so that FastAPI can
manage their lifecycle correctly within the request scope.

Usage::

    from src.api.dependencies import get_async_session, get_http_client

    @router.post("/upload")
    async def upload(
        session: AsyncSession = Depends(get_async_session),
        http_client: httpx.AsyncClient = Depends(get_http_client),
    ) -> None:
        ...
"""

from collections.abc import AsyncGenerator

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.factories.db_session_factory import get_db_session_factory

_HTTP_CLIENT_TIMEOUT: float = 30.0


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session from the singleton session factory.

    The session is committed on successful exit and rolled back on exception.
    The underlying connection is returned to the pool when the dependency
    scope ends.

    Yields:
        An independent ``AsyncSession`` instance bound to the current request.

    Example:
        @router.get("/items")
        async def list_items(
            session: AsyncSession = Depends(get_async_session),
        ) -> list[ItemDto]:
            ...
    """
    factory = get_db_session_factory()
    async with factory.get_session() as session:
        yield session


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Yield a shared ``httpx.AsyncClient`` for outbound HTTP calls.

    A new client is created per request. The client is properly closed when
    the dependency scope ends, releasing all underlying connections.

    Yields:
        A configured ``httpx.AsyncClient`` with a 30-second timeout.

    Example:
        @router.post("/enrich")
        async def enrich(
            http_client: httpx.AsyncClient = Depends(get_http_client),
        ) -> None:
            ...
    """
    async with httpx.AsyncClient(timeout=_HTTP_CLIENT_TIMEOUT) as client:
        yield client
