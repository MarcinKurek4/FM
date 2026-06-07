"""Unit tests for execution timing decorator."""

import dataclasses
import datetime

import pytest

from src.utils.timing import log_execution_time


@dataclasses.dataclass(frozen=True, slots=True)
class _TimedResult:
    value: int
    duration_ms: float = 0.0


@pytest.mark.asyncio
async def test_log_execution_time_async_does_not_change_return_value() -> None:
    @log_execution_time()
    async def compute() -> int:
        return 42

    assert await compute() == 42


@pytest.mark.asyncio
async def test_log_execution_time_injects_duration_ms_on_dataclass() -> None:
    @log_execution_time(inject_duration_ms=True)
    async def run_pipeline() -> _TimedResult:
        return _TimedResult(value=7)

    result = await run_pipeline()

    assert result.value == 7
    assert result.duration_ms >= 0.0


def test_log_execution_time_sync_injects_duration_ms_on_dataclass() -> None:
    @log_execution_time(inject_duration_ms=True)
    def run_pipeline() -> _TimedResult:
        return _TimedResult(value=3)

    result = run_pipeline()

    assert result.value == 3
    assert result.duration_ms >= 0.0


@pytest.mark.asyncio
async def test_log_execution_time_logs_on_exception() -> None:
    @log_execution_time()
    async def failing() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await failing()


@pytest.mark.asyncio
async def test_log_execution_time_custom_operation_name() -> None:
    @log_execution_time(operation_name="custom.run")
    async def compute() -> datetime.date:
        return datetime.date(2026, 6, 7)

    assert await compute() == datetime.date(2026, 6, 7)
