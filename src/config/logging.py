"""Centralised logging configuration for the FM pipeline.

Initialises the Loguru logger with a structured JSON sink to stdout.
Call ``setup_logging()`` exactly once during application startup (in
``app.py``). After that, every module in the project imports the
pre-configured logger with a single line::

    from loguru import logger

No per-module ``logging.getLogger(__name__)`` calls are needed.
All records automatically include ``app_version`` and the calling
module name.

Structured JSON output example::

    {
      "text": "OMDb metadata fetched\\n",
      "record": {
        "elapsed": {"repr": "0:00:01.234567", "seconds": 1.234567},
        "exception": null,
        "extra": {"app_version": "0.1.0", "title": "Inception", "imdb_id": "tt1375666"},
        "file": {"name": "omdb_client.py", "path": "..."},
        "function": "fetch_by_title",
        "level": {"icon": "✅", "name": "DEBUG", "no": 10},
        "line": 95,
        "message": "OMDb metadata fetched",
        "module": "omdb_client",
        "name": "src.services.omdb_client",
        "process": {"id": 12345, "name": "MainProcess"},
        "thread": {"id": 1, "name": "MainThread"},
        "time": {"repr": "2026-06-05 12:00:00+00:00", "timestamp": 1749081600.0}
      }
    }
"""

import sys

from loguru import logger

from src.config.settings import LogLevel


def setup_logging(app_version: str, log_level: LogLevel = "INFO") -> None:
    """Configure the global Loguru logger for the FM application.

    Removes the default Loguru handler and installs a structured JSON
    sink to stdout. Every log record is automatically annotated with
    ``app_version`` so that all downstream consumers (ELK, Datadog, etc.)
    can filter by release.

    This function must be called exactly once at application startup,
    before any module emits a log record. Subsequent calls are safe but
    redundant — the handler is replaced each time.

    Args:
        app_version: Semantic version string of the running application
            (e.g. ``"0.1.0"``). Injected into every log record as an
            ``extra`` field.
        log_level: Minimum Loguru level to emit. Sourced from
            ``Settings.log_level``; validated by Pydantic before this
            function is called.

    Example:
        from src.config.logging import setup_logging

        setup_logging(app_version="0.1.0", log_level="DEBUG")
    """
    logger.remove()

    logger.configure(extra={"app_version": app_version})

    logger.add(
        sys.stdout,
        level=log_level,
        serialize=True,
        backtrace=True,
        diagnose=False,
        enqueue=False,
    )

    logger.info(
        "Logging initialised",
        extra={"app_version": app_version, "sink": "stdout", "level": log_level},
    )
