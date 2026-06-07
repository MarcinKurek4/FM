"""MPAA and TV parental-guidance rating code descriptions.

Maps OMDb ``Rated`` field values to human-readable descriptions stored in
``dwh.dim_rated.rating_description``. Codes not present in the map fall back
to the code itself.

Usage::

    from src.utils.rated_descriptions import get_rating_description

    description = get_rating_description("PG-13")
"""

RATED_DESCRIPTIONS: dict[str, str] = {
    "G": "General Audiences",
    "PG": "Parental Guidance Suggested",
    "PG-13": "Parents Strongly Cautioned",
    "R": "Restricted",
    "NC-17": "Adults Only",
    "NR": "Not Rated",
    "UR": "Unrated",
    "TV-Y": "All Children",
    "TV-Y7": "Directed to Older Children",
    "TV-G": "General Audience",
    "TV-PG": "Parental Guidance",
    "TV-14": "Parents Strongly Cautioned",
    "TV-MA": "Mature Audience Only",
}


def get_rating_description(rating_code: str) -> str:
    """Return the description for an MPAA or TV rating code.

    Args:
        rating_code: Rating label from OMDb (e.g., ``"PG-13"``).

    Returns:
        Mapped description when known; otherwise ``rating_code`` unchanged.

    Example:
        get_rating_description("R") == "Restricted"
        get_rating_description("UNRATED-X") == "UNRATED-X"
    """
    return RATED_DESCRIPTIONS.get(rating_code, rating_code)
