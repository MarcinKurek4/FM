"""FastAPI application factory for the FM box office analytics pipeline.

This module is the entry point of the application. It:

1. Reads the application version from the installed package metadata.
2. Initialises the global Loguru logger via ``setup_logging()``.
3. Creates and returns the ``FastAPI`` instance.

The logger is fully configured by the time any request handler or
background task runs. All other modules import the pre-configured
logger with::

    from loguru import logger

Start the application::

    poetry run uvicorn src.app:app --reload
"""

import importlib.metadata

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from loguru import logger

from src.api.v1.ratings import router as ratings_router
from src.api.v1.revenue_upload import router as revenue_upload_router
from src.config.logging import setup_logging
from src.config.settings import get_settings


def _get_version() -> str:
    """Read the package version from installed metadata.

    Returns:
        Semantic version string (e.g. ``"0.1.0"``), or ``"unknown"`` when
        the package metadata is not available (e.g. during bare script
        execution without ``poetry install``).
    """
    try:
        return importlib.metadata.version("fm")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


APP_VERSION: str = _get_version()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the application lifecycle.

    Emits a startup log and a shutdown log around the yield point.

    Args:
        application: The FastAPI application instance.

    Yields:
        Control to the ASGI server while the application is running.
    """
    logger.info(
        "Application starting",
        extra={"app_version": APP_VERSION, "docs_url": application.docs_url},
    )
    yield
    logger.info("Application shutting down", extra={"app_version": APP_VERSION})


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    Validates all settings before logging is initialised so that a
    misconfigured environment is reported immediately at startup.
    The call order is intentional:

    1. ``get_settings()`` — validates all environment variables via Pydantic.
       Raises ``ValidationError`` with a full field report if anything is
       missing or malformed. This happens before the logger is configured.
    2. ``setup_logging()`` — configures Loguru with the validated
       ``log_level`` and ``app_version``.
    3. ``FastAPI(...)`` — creates the application instance.

    Returns:
        A fully configured ``FastAPI`` instance ready for use with an
        ASGI server.

    Example:
        from src.app import create_app

        app = create_app()
    """
    settings = get_settings()
    setup_logging(app_version=APP_VERSION, log_level=settings.log_level)

    application = FastAPI(
        title="FM — Box Office Analytics",
        version=APP_VERSION,
        description="Movie box office analytics pipeline with OMDb enrichment.",
        lifespan=lifespan,
    )

    application.include_router(revenue_upload_router)
    application.include_router(ratings_router)

    return application


app: FastAPI = create_app()
