"""OMDb API response model.

Maps the raw JSON returned by ``https://www.omdbapi.com/`` to a typed,
validated Python object. All OMDb-specific quirks are handled here:

- Fields named in PascalCase or camelCase are aliased to snake_case.
- The sentinel value ``"N/A"`` is normalised to ``None`` before any
  field validator runs.
- Numeric strings with formatting (``"90,083"``, ``"$37,762,677"``,
  ``"106 min"``) are parsed to their native Python types.
- ``Year`` may be a four-digit string (``"2004"``) or a range
  (``"2004–2006"``); only the start year is retained.

Usage::

    import httpx
    from src.models.omdb import OmdbMovieResponse

    raw = httpx.get("https://www.omdbapi.com/?t=Inception&apikey=...").json()
    movie = OmdbMovieResponse.model_validate(raw)
    print(movie.imdb_rating)
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_NA_SENTINEL: str = "N/A"
OMDB_RATE_LIMIT_ERROR_REASON: str = "rate_limit_exceeded"


@dataclass(frozen=True, slots=True)
class OmdbTitleFetchOutcome:
    """Result of a single OMDb title lookup.

    Preserves the ``request_title`` sent to the API separately from the
    canonical title returned in the response body.

    Attributes:
        request_title: Title passed as the ``t`` query parameter.
        movie: Validated API response when the lookup succeeded.
        error_reason: Machine-readable failure code when ``movie`` is
            ``None``. ``None`` on success.
        error_message: Raw OMDb ``Error`` field or HTTP failure detail.

    Example:
        outcome = OmdbTitleFetchOutcome(
            request_title="Sky Captain...",
            movie=OmdbMovieResponse(...),
            error_reason=None,
        )
    """

    request_title: str
    movie: "OmdbMovieResponse | None"
    error_reason: str | None = None
    error_message: str | None = None


class OmdbMovieResponse(BaseModel):
    """Validated representation of a single OMDb movie record.

    All optional fields default to ``None`` when the OMDb API returns
    ``"N/A"`` or when the value cannot be parsed.

    Attributes:
        title: Canonical movie title.
        year: Four-digit release year, or ``None``.
        rated: MPAA rating (e.g. ``"PG-13"``), or ``None``.
        genre: Comma-separated genre list (e.g. ``"Action, Adventure"``).
        director: Director name(s), or ``None``.
        actors: Top-billed cast as a comma-separated string, or ``None``.
        plot: Full plot summary, or ``None``.
        awards: Raw awards string (e.g. ``"Won 2 Oscars…"``), or ``None``.
        imdb_rating: Numeric IMDb score (0.0–10.0), or ``None``.
        imdb_votes: Total number of IMDb votes, or ``None``.
        imdb_id: IMDb title identifier (e.g. ``"tt0346156"``).
        runtime_min: Film runtime in minutes, or ``None``.
        box_office: Domestic box office gross in USD, or ``None``.
        response: ``True`` when the API found a match, ``False`` otherwise.

    Example:
        raw = {
            "Title": "Inception",
            "Year": "2010",
            "imdbRating": "8.8",
            "imdbVotes": "2,500,000",
            "imdbID": "tt1375666",
            "Runtime": "148 min",
            "BoxOffice": "$292,576,195",
            "Response": "True",
        }
        movie = OmdbMovieResponse.model_validate(raw)
        assert movie.imdb_rating == 8.8
        assert movie.imdb_votes == 2500000
        assert movie.runtime_min == 148
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(alias="Title")
    year: int | None = Field(default=None, alias="Year")
    rated: str | None = Field(default=None, alias="Rated")
    genre: str | None = Field(default=None, alias="Genre")
    director: str | None = Field(default=None, alias="Director")
    actors: str | None = Field(default=None, alias="Actors")
    plot: str | None = Field(default=None, alias="Plot")
    awards: str | None = Field(default=None, alias="Awards")
    imdb_rating: float | None = Field(default=None, alias="imdbRating")
    imdb_votes: int | None = Field(default=None, alias="imdbVotes")
    imdb_id: str = Field(alias="imdbID")
    runtime_min: int | None = Field(default=None, alias="Runtime")
    box_office: Decimal | None = Field(default=None, alias="BoxOffice")
    response: bool = Field(alias="Response")

    @model_validator(mode="before")
    @classmethod
    def replace_na_with_none(cls, data: dict) -> dict:
        """Replace all ``"N/A"`` values with ``None`` before field validation.

        Args:
            data: Raw dictionary from the OMDb API JSON response.

        Returns:
            The same dictionary with every ``"N/A"`` string replaced by
            ``None``.
        """
        return {k: (None if v == _NA_SENTINEL else v) for k, v in data.items()}

    @field_validator("response", mode="before")
    @classmethod
    def parse_response_flag(cls, value: object) -> bool:
        """Convert the ``"True"`` / ``"False"`` response flag to a bool.

        Args:
            value: Raw value from the ``Response`` field.

        Returns:
            ``True`` when the API found a match, ``False`` otherwise.
        """
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return bool(value)

    @field_validator("year", mode="before")
    @classmethod
    def parse_year(cls, value: object) -> int | None:
        """Extract a four-digit year from strings like ``"2004"`` or ``"2004–2006"``.

        Args:
            value: Raw value from the ``Year`` field.

        Returns:
            Integer year, or ``None`` when parsing fails.
        """
        if value is None:
            return None
        match = re.search(r"\d{4}", str(value))
        return int(match.group()) if match else None

    @field_validator("imdb_votes", mode="before")
    @classmethod
    def parse_imdb_votes(cls, value: object) -> int | None:
        """Remove thousands separators and convert to int.

        Handles strings such as ``"90,083"`` → ``90083``.

        Args:
            value: Raw value from the ``imdbVotes`` field.

        Returns:
            Integer vote count, or ``None`` when the value is absent.
        """
        if value is None:
            return None
        cleaned = re.sub(r"[^\d]", "", str(value))
        return int(cleaned) if cleaned else None

    @field_validator("runtime_min", mode="before")
    @classmethod
    def parse_runtime(cls, value: object) -> int | None:
        """Extract the numeric minute count from strings like ``"106 min"``.

        Args:
            value: Raw value from the ``Runtime`` field.

        Returns:
            Integer minutes, or ``None`` when the value is absent or
            unparseable.
        """
        if value is None:
            return None
        match = re.search(r"\d+", str(value))
        return int(match.group()) if match else None

    @field_validator("box_office", mode="before")
    @classmethod
    def parse_box_office(cls, value: object) -> Decimal | None:
        """Strip currency symbols and separators from strings like ``"$37,762,677"``.

        Args:
            value: Raw value from the ``BoxOffice`` field.

        Returns:
            ``Decimal`` gross in USD, or ``None`` when the value is absent
            or unparseable.
        """
        if value is None:
            return None
        cleaned = re.sub(r"[^\d.]", "", str(value))
        try:
            return Decimal(cleaned) if cleaned else None
        except InvalidOperation:
            return None
