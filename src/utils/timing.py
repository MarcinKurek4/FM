"""Wall-clock timing utilities for async and sync callables.

Provides a decorator that logs execution duration at DEBUG in a dedicated
record, separate from business-level log messages.
"""

import dataclasses
import functools
import inspect
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, overload

from loguru import logger

P = ParamSpec("P")
R = TypeVar("R")

_DURATION_MS_FIELD = "duration_ms"
_TIMING_LOG_MESSAGE = "Operation timing"


def _elapsed_ms(start: float) -> float:
    """Return milliseconds elapsed since ``start``.

    Args:
        start: Value from ``time.perf_counter()`` at operation start.

    Returns:
        Elapsed wall-clock time in milliseconds, rounded to three decimals.
    """
    return round((time.perf_counter() - start) * 1000, 3)


def _log_timing(operation: str, duration_ms: float) -> None:
    """Emit a DEBUG timing record for a completed operation.

    Args:
        operation: Qualified name of the timed callable.
        duration_ms: Elapsed wall-clock time in milliseconds.
    """
    logger.debug(
        _TIMING_LOG_MESSAGE,
        extra={"operation": operation, "duration_ms": duration_ms},
    )


def _inject_duration_ms(result: R, duration_ms: float) -> R:
    """Set ``duration_ms`` on a dataclass result when the field is declared.

    Args:
        result: Value returned by the wrapped callable.
        duration_ms: Measured elapsed time in milliseconds.

    Returns:
        ``result`` unchanged, or a copy with ``duration_ms`` replaced.
    """
    if not dataclasses.is_dataclass(result):
        return result
    fields = getattr(result, "__dataclass_fields__", {})
    if _DURATION_MS_FIELD not in fields:
        return result
    return dataclasses.replace(result, duration_ms=duration_ms)


def _wrap_async(
    func: Callable[P, Any],
    operation_name: str,
    inject_duration_ms: bool,
) -> Callable[P, Any]:
    """Build an async wrapper that times ``func``.

    Args:
        func: Async callable to wrap.
        operation_name: Name used in the DEBUG timing record.
        inject_duration_ms: Whether to populate ``duration_ms`` on dataclass
            return values.

    Returns:
        Async wrapper with identical call signature to ``func``.
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
        except Exception:
            _log_timing(operation_name, _elapsed_ms(start))
            raise
        duration_ms = _elapsed_ms(start)
        _log_timing(operation_name, duration_ms)
        if inject_duration_ms:
            return _inject_duration_ms(result, duration_ms)
        return result

    return wrapper


def _wrap_sync(
    func: Callable[P, Any],
    operation_name: str,
    inject_duration_ms: bool,
) -> Callable[P, Any]:
    """Build a sync wrapper that times ``func``.

    Args:
        func: Synchronous callable to wrap.
        operation_name: Name used in the DEBUG timing record.
        inject_duration_ms: Whether to populate ``duration_ms`` on dataclass
            return values.

    Returns:
        Sync wrapper with identical call signature to ``func``.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception:
            _log_timing(operation_name, _elapsed_ms(start))
            raise
        duration_ms = _elapsed_ms(start)
        _log_timing(operation_name, duration_ms)
        if inject_duration_ms:
            return _inject_duration_ms(result, duration_ms)
        return result

    return wrapper


@overload
def log_execution_time(
    func: Callable[P, R],
    /,
    *,
    operation_name: str | None = None,
    inject_duration_ms: bool = False,
) -> Callable[P, R]: ...


@overload
def log_execution_time(
    func: None = None,
    /,
    *,
    operation_name: str | None = None,
    inject_duration_ms: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def log_execution_time(
    func: Callable[P, R] | None = None,
    /,
    *,
    operation_name: str | None = None,
    inject_duration_ms: bool = False,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a callable to log wall-clock duration at DEBUG on completion.

    Supports both synchronous and ``async`` functions. Timing is always
    logged in a separate DEBUG record with fields ``operation`` and
    ``duration_ms``.

    When ``inject_duration_ms`` is ``True`` and the return value is a
    dataclass declaring ``duration_ms``, that field is populated with the
    measured duration before the value is returned to the caller.

    Args:
        func: Callable to wrap when used as ``@log_execution_time`` without
            parentheses.
        operation_name: Override for the ``operation`` log field. Defaults to
            ``func.__qualname__``.
        inject_duration_ms: Populate ``duration_ms`` on dataclass results.

    Returns:
        The wrapped callable, or a decorator when ``func`` is ``None``.

    Example:
        @log_execution_time()
        async def get_by_id(self, movie_id: int) -> DimMovieDto | None:
            ...

        @log_execution_time(inject_duration_ms=True)
        async def run(self) -> RevenueInitLoadResult:
            ...
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        op_name = operation_name or fn.__qualname__
        if inspect.iscoroutinefunction(fn):
            return _wrap_async(fn, op_name, inject_duration_ms)  # type: ignore[return-value]
        return _wrap_sync(fn, op_name, inject_duration_ms)  # type: ignore[return-value]

    if func is not None:
        return decorator(func)
    return decorator
