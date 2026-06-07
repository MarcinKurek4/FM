"""Reader for OMDb enrichment init result JSON files.

Loads ``omdb_titles_init_result.json`` produced by
``OmdbEnrichmentEtlService`` and returns only records with a successful OMDb
response and a non-empty ``imdb_id``.

Usage::

    from pathlib import Path
    from src.utils.omdb_json_reader import read_omdb_result_file

    records, skipped = read_omdb_result_file(Path("data/raw/omdb_titles_init_result.json"))
"""

import json
from pathlib import Path

from loguru import logger


def read_omdb_result_file(path: Path) -> tuple[list[dict[str, object]], int]:
    """Load and filter OMDb init result records from a JSON array file.

    Each element must contain a ``data`` object. Records are retained when
    ``data.response`` is truthy and ``data.imdb_id`` is a non-empty string.
    All other records are skipped.

    Args:
        path: Path to the init result JSON file.

    Returns:
        A tuple of ``(valid_records, skipped_count)``. ``valid_records`` is
        the list of raw dicts as stored in the file (including envelope
        fields ``request_title``, ``fetched_at``, ``omdb_title``, ``data``).

    Raises:
        FileNotFoundError: When ``path`` does not exist.
        ValueError: When the file root is not a JSON array.

    Example:
        records, skipped = read_omdb_result_file(Path("data/raw/omdb_titles_init_result.json"))
    """
    if not path.is_file():
        raise FileNotFoundError(f"OMDb result file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array at root of {path}")

    valid_records: list[dict[str, object]] = []
    skipped_count = 0

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            skipped_count += 1
            logger.warning(
                "Skipping non-object OMDb result entry",
                extra={"index": index, "path": str(path)},
            )
            continue

        data = item.get("data")
        if not isinstance(data, dict):
            skipped_count += 1
            continue

        response = data.get("response")
        if response is not True and response != "true" and response != "True":
            skipped_count += 1
            continue

        imdb_id = data.get("imdb_id")
        if not isinstance(imdb_id, str) or not imdb_id.strip():
            skipped_count += 1
            continue

        valid_records.append(item)

    logger.info(
        "OMDb result file read",
        extra={
            "path": str(path),
            "total_entries": len(raw),
            "valid_count": len(valid_records),
            "skipped_count": skipped_count,
        },
    )
    return valid_records, skipped_count


def split_csv_field(value: object | None) -> list[str]:
    """Split a comma-separated OMDb field into trimmed non-empty tokens.

    Args:
        value: Raw field value (typically ``genre`` or ``director``).

    Returns:
        List of trimmed strings. Empty when ``value`` is ``None`` or blank.

    Example:
        split_csv_field("Action, Crime, Drama") == ["Action", "Crime", "Drama"]
    """
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]
