"""Pure helpers for building ``DimDateDto`` rows from calendar dates.

Computes surrogate keys, calendar attributes, and US federal holiday flags
for the ``dwh.dim_date`` dimension. No I/O or database access occurs here.

Usage::

    from datetime import date
    from src.utils.dim_date_builder import build_dim_date_dto

    dto = build_dim_date_dto(date(2004, 9, 20))
"""

import datetime
from collections.abc import Iterator

from src.models.dwh import DimDateDto

DIM_DATE_END_YEAR: int = 2030
DIM_DATE_END: datetime.date = datetime.date(DIM_DATE_END_YEAR, 12, 31)

_MONTH_NAMES: tuple[str, ...] = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_WEEKDAY_NAMES: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_JUNETEENTH_FIRST_YEAR: int = 2021


def compute_date_id(value: datetime.date) -> int:
    """Return the ``YYYYMMDD`` surrogate key for a calendar date.

    Args:
        value: Calendar date to encode.

    Returns:
        Integer primary key in ``YYYYMMDD`` format.

    Example:
        compute_date_id(datetime.date(2004, 9, 20)) == 20040920
    """
    return value.year * 10_000 + value.month * 100 + value.day


def _observed_holiday(value: datetime.date) -> datetime.date:
    """Return the US federal observed date for a fixed calendar holiday.

    When a holiday falls on Saturday it is observed on Friday; when it falls
    on Sunday it is observed on Monday.

    Args:
        value: Nominal holiday date.

    Returns:
        Observed holiday date.
    """
    if value.weekday() == 5:
        return value - datetime.timedelta(days=1)
    if value.weekday() == 6:
        return value + datetime.timedelta(days=1)
    return value


def _nth_weekday_of_month(
    year: int,
    month: int,
    weekday: int,
    occurrence: int,
) -> datetime.date:
    """Return the ``occurrence``-th ``weekday`` in a month.

    Args:
        year: Calendar year.
        month: Calendar month (1–12).
        weekday: ISO weekday (1=Monday, 7=Sunday).
        occurrence: One-based index (1=first, -1=last).

    Returns:
        Matching calendar date.

    Raises:
        ValueError: When ``occurrence`` is zero.
    """
    if occurrence == 0:
        raise ValueError("occurrence must be non-zero")

    if occurrence > 0:
        day = 1
        count = 0
        while day <= 31:
            try:
                candidate = datetime.date(year, month, day)
            except ValueError:
                break
            if candidate.isocalendar().weekday == weekday:
                count += 1
                if count == occurrence:
                    return candidate
            day += 1
        raise ValueError(f"No {occurrence} weekday {weekday} in {year}-{month:02d}")

    day = 31
    count = 0
    while day >= 1:
        try:
            candidate = datetime.date(year, month, day)
        except ValueError:
            day -= 1
            continue
        if candidate.isocalendar().weekday == weekday:
            count += 1
            if count == -occurrence:
                return candidate
        day -= 1
    raise ValueError(f"No last weekday {weekday} in {year}-{month:02d}")


def us_federal_holidays(year: int) -> frozenset[datetime.date]:
    """Return US federal holidays for a calendar year.

    Includes fixed and floating holidays with Saturday/Sunday observation
    rules. Juneteenth is included from 2021 onward.

    Args:
        year: Calendar year.

    Returns:
        Frozen set of observed holiday dates.
    """
    holidays: set[datetime.date] = {
        _observed_holiday(datetime.date(year, 1, 1)),
        _nth_weekday_of_month(year, 1, 1, 3),
        _nth_weekday_of_month(year, 2, 1, 3),
        _nth_weekday_of_month(year, 5, 1, -1),
        _observed_holiday(datetime.date(year, 7, 4)),
        _nth_weekday_of_month(year, 9, 1, 1),
        _nth_weekday_of_month(year, 10, 1, 2),
        _observed_holiday(datetime.date(year, 11, 11)),
        _nth_weekday_of_month(year, 11, 4, 4),
        _observed_holiday(datetime.date(year, 12, 25)),
    }
    if year >= _JUNETEENTH_FIRST_YEAR:
        holidays.add(_observed_holiday(datetime.date(year, 6, 19)))
    return frozenset(holidays)


def is_us_federal_holiday(value: datetime.date) -> bool:
    """Return whether a date is a US federal holiday.

    Args:
        value: Calendar date to evaluate.

    Returns:
        ``True`` when the date is an observed US federal holiday.
    """
    return value in us_federal_holidays(value.year)


def iter_dates(
    start: datetime.date,
    end: datetime.date,
) -> Iterator[datetime.date]:
    """Yield each calendar date from ``start`` through ``end`` inclusive.

    Args:
        start: First date in the range.
        end: Last date in the range.

    Yields:
        Consecutive ``datetime.date`` values.

    Raises:
        ValueError: When ``start`` is after ``end``.
    """
    if start > end:
        raise ValueError(f"start {start} must not be after end {end}")

    current = start
    one_day = datetime.timedelta(days=1)
    while current <= end:
        yield current
        current += one_day


def build_dim_date_dto(value: datetime.date) -> DimDateDto:
    """Build a ``DimDateDto`` for a single calendar date.

    Args:
        value: Calendar date to convert.

    Returns:
        Frozen DTO aligned with ``DimDateTable`` columns.

    Example:
        dto = build_dim_date_dto(datetime.date(2004, 9, 20))
        assert dto.date_id == 20040920
    """
    iso = value.isocalendar()
    day_of_week = iso.weekday
    return DimDateDto(
        date_id=compute_date_id(value),
        date=value,
        year=value.year,
        quarter=(value.month - 1) // 3 + 1,
        month=value.month,
        month_name=_MONTH_NAMES[value.month],
        day=value.day,
        day_of_week=day_of_week,
        day_of_week_name=_WEEKDAY_NAMES[value.weekday()],
        week_number=iso.week,
        is_weekend=day_of_week in (6, 7),
        is_holiday=is_us_federal_holiday(value),
    )


def build_dim_date_dtos(
    start: datetime.date,
    end: datetime.date,
) -> list[DimDateDto]:
    """Build ``DimDateDto`` rows for an inclusive date range.

    Args:
        start: First date in the range.
        end: Last date in the range.

    Returns:
        List of DTOs in ascending date order.
    """
    return [build_dim_date_dto(day) for day in iter_dates(start, end)]
