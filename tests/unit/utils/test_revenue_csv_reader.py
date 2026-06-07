"""Unit tests for revenue CSV parsing utilities."""

import datetime
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from src.utils.revenue_csv_reader import read_revenues_csv


def test_read_revenues_csv_accepts_null_theaters_and_distributor(tmp_path: Path) -> None:
    """Parse rows when theaters and distributor CSV fields are empty."""
    row_id = uuid.UUID("6e46c77c-1069-3ba8-b45f-ade734dea946")
    csv_path = tmp_path / "revenues.csv"
    csv_path.write_text(
        "id,date,title,revenue,theaters,distributor\n"
        f"{row_id},2022-12-05,2nd Chance,424,,Bleecker Street Media\n",
        encoding="utf-8",
    )

    rows = read_revenues_csv(csv_path)

    assert len(rows) == 1
    assert rows[0].row_id == row_id
    assert rows[0].theaters is None
    assert rows[0].distributor == "Bleecker Street Media"
    assert rows[0].revenue == Decimal("424")


def test_read_revenues_csv_maps_distributor_sentinel_to_none(tmp_path: Path) -> None:
    """Map the distributor sentinel value to None."""
    row_id = uuid.uuid4()
    csv_path = tmp_path / "revenues.csv"
    csv_path.write_text(
        "id,date,title,revenue,theaters,distributor\n"
        f"{row_id},2022-12-05,Example Film,1000,10,-\n",
        encoding="utf-8",
    )

    rows = read_revenues_csv(csv_path)

    assert len(rows) == 1
    assert rows[0].distributor is None
    assert rows[0].theaters == 10


def test_read_revenues_csv_raises_when_file_missing(tmp_path: Path) -> None:
    """Raise FileNotFoundError when the CSV path does not exist."""
    with pytest.raises(FileNotFoundError):
        read_revenues_csv(tmp_path / "missing.csv")
