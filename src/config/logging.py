"""Centralised logging configuration for the FM pipeline.

Initialises the Loguru logger with a human-readable text sink to stdout.
Call ``setup_logging()`` exactly once during application startup (in
``app.py``). After that, every module in the project imports the
pre-configured logger with a single line::

    from loguru import logger

No per-module ``logging.getLogger(__name__)`` calls are needed.
All records automatically include ``app_version`` and the calling
module name.

Human-readable output example::

    2026-06-06 14:30:00.123 | INFO     | src.services.omdb_client:fetch_by_title:187 | OMDb metadata fetched | app_version=0.1.0 imdb_id=tt1375666 title=Inception
"""

import sys

from loguru import logger

from src.config.settings import LogLevel

_COLORED_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
    "{extra[context]}"
    "{exception}\n"
)

_PLAIN_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} | {message}"
    "{extra[context]}"
    "{exception}\n"
)


def _flatten_extra_fields(extra: dict[str, object]) -> dict[str, object]:
    """Normalise Loguru extra fields for display.

    Call sites in this project pass structured data via the standard
    ``extra={...}`` keyword. Loguru stores that mapping under a nested
    ``extra`` key instead of merging it at the top level.

    Args:
        extra: Raw ``record["extra"]`` mapping from Loguru.

    Returns:
        Flat mapping of displayable key/value pairs.
    """
    flattened: dict[str, object] = {}
    for key, value in extra.items():
        if key == "context":
            continue
        if key == "extra" and isinstance(value, dict):
            flattened.update(value)
            continue
        flattened[key] = value
    return flattened


def _record_patcher(record: dict) -> None:
    """Attach a human-readable rendering of structured extra fields.

    Args:
        record: Mutable Loguru record dictionary updated in place.
    """
    fields = _flatten_extra_fields(record["extra"])
    parts = [f"{key}={value}" for key, value in sorted(fields.items())]
    record["extra"]["context"] = f" | {' '.join(parts)}" if parts else ""


def setup_logging(app_version: str, log_level: LogLevel = "INFO") -> None:
    """Configure the global Loguru logger for the FM application.

    Removes the default Loguru handler and installs a human-readable text
    sink to stdout. Every log record is automatically annotated with
    ``app_version`` so that log lines can be filtered by release.

    Colour highlighting is enabled only when stdout is an interactive
    terminal. In Docker and CI the output is plain text without ANSI codes.

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

    logger.configure(extra={"app_version": app_version}, patcher=_record_patcher)

    use_color = sys.stdout.isatty()
    log_format = _COLORED_LOG_FORMAT if use_color else _PLAIN_LOG_FORMAT

    logger.add(
        sys.stdout,
        level=log_level,
        format=log_format,
        colorize=use_color,
        backtrace=True,
        diagnose=False,
        enqueue=False,
    )

    logger.info(
        "Logging initialised",
        extra={"sink": "stdout", "level": log_level},
    )
