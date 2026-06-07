"""Raw source model for the revenues_per_day CSV file.

This module defines a single dataclass that mirrors the CSV schema exactly.
It is the entry point of the pipeline — all downstream transformations start
from a sequence of ``RawRevenueRow`` instances produced by the ingestion layer.

No business logic or transformation lives here. Cleaning and enrichment
happen in the service layer.

CSV schema::

    id,date,title,revenue,theaters,distributor
    8b19ad43-...,2004-09-20,Sky Captain...,925482,3170,Paramount Pictures
"""

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal


MISSING_DISTRIBUTOR_SENTINEL: str = "-"


@dataclass(frozen=True, slots=True)
class RawRevenueRow:
    """One row from the ``revenues_per_day.csv`` source file.

    The field names and types map directly to the CSV columns. The only
    normalisation applied at parse time is:

    - ``date`` is parsed from ``YYYY-MM-DD`` string to ``datetime.date``.
    - ``revenue`` and ``theaters`` are cast to ``int``.
    - ``distributor`` is set to ``None`` when the source value equals the
      sentinel string ``"-"``.

    Attributes:
        row_id: Parsed UUID from the ``id`` column.
        date: Calendar date on which the revenue was recorded.
        title: Movie title as it appears in the source file. May contain
            encoding artefacts (e.g. ``Tu00e1r`` for ``Tár``); cleaning
            is deferred to the transformation layer.
        revenue: Box office revenue in USD for the given date. Stored as
            ``Decimal`` to preserve exactness for both integer and
            fractional monetary values present in the source.
        theaters: Number of theater screens showing the film on that date,
            or ``None`` when the CSV field is empty.
        distributor: Distribution company name, or ``None`` when the source
            file contains the sentinel value ``"-"`` or an empty field.

    Example:
        row = RawRevenueRow(
            row_id=uuid.UUID("8b19ad43-3a7e-b14b-49e9-1f7a0eb1568e"),
            date=datetime.date(2004, 9, 20),
            title="Sky Captain and the World of Tomorrow",
            revenue=Decimal("925482"),
            theaters=3170,
            distributor="Paramount Pictures",
        )
    """

    row_id: uuid.UUID
    date: datetime.date
    title: str
    revenue: Decimal
    theaters: int | None
    distributor: str | None
