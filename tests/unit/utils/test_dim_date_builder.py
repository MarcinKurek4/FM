"""Unit tests for dim_date builder utilities."""

import datetime

import pytest

from src.utils.dim_date_builder import (
    DIM_DATE_END,
    build_dim_date_dto,
    build_dim_date_dtos,
    compute_date_id,
    is_us_federal_holiday,
    iter_dates,
    us_federal_holidays,
)


def test_compute_date_id_formats_yyyymmdd() -> None:
    assert compute_date_id(datetime.date(2004, 9, 20)) == 20040920


def test_build_dim_date_dto_matches_dim_date_table_shape() -> None:
    dto = build_dim_date_dto(datetime.date(2004, 9, 20))

    assert dto.date_id == 20040920
    assert dto.date == datetime.date(2004, 9, 20)
    assert dto.year == 2004
    assert dto.quarter == 3
    assert dto.month == 9
    assert dto.month_name == "September"
    assert dto.day == 20
    assert dto.day_of_week == 1
    assert dto.day_of_week_name == "Monday"
    assert dto.week_number == 39
    assert dto.is_weekend is False
    assert dto.is_holiday is False


def test_build_dim_date_dto_marks_weekend() -> None:
    dto = build_dim_date_dto(datetime.date(2004, 9, 18))

    assert dto.day_of_week == 6
    assert dto.is_weekend is True


def test_us_federal_holiday_independence_day_observed_on_monday() -> None:
    observed = datetime.date(2021, 7, 5)

    assert observed in us_federal_holidays(2021)
    assert is_us_federal_holiday(observed) is True


def test_juneteenth_included_from_2021() -> None:
    assert datetime.date(2021, 6, 18) in us_federal_holidays(2021)
    assert datetime.date(2020, 6, 19) not in us_federal_holidays(2020)


def test_iter_dates_raises_when_start_after_end() -> None:
    with pytest.raises(ValueError, match="must not be after"):
        list(iter_dates(datetime.date(2020, 1, 2), datetime.date(2020, 1, 1)))


def test_build_dim_date_dtos_span_inclusive_range() -> None:
    start = datetime.date(2000, 1, 1)
    end = datetime.date(2000, 1, 3)
    dtos = build_dim_date_dtos(start, end)

    assert len(dtos) == 3
    assert dtos[0].date_id == 20000101
    assert dtos[-1].date_id == 20000103


def test_dim_date_end_constant_is_2030_12_31() -> None:
    assert DIM_DATE_END == datetime.date(2030, 12, 31)
