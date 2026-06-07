"""Helpers for normalising movie title strings from the revenues CSV.

The source file stores some Unicode characters as literal ``uXXXX`` sequences
(for example ``Tu00e1r`` instead of ``Tár``). These helpers decode those
artefacts before aggregation or OMDb lookups.

Usage::

    from src.utils.title_encoding import decode_embedded_unicode_escapes

    title = decode_embedded_unicode_escapes("Les Misu00e9rables")
"""

import re

_EMBEDDED_UNICODE_ESCAPE: re.Pattern[str] = re.compile(r"u([0-9a-fA-F]{4})")


def decode_embedded_unicode_escapes(value: str) -> str:
    """Decode literal ``uXXXX`` Unicode escape sequences in a title string.

    The revenues source CSV does not use UTF-8 mojibake; instead, selected
    code points appear as the five-character pattern ``u`` followed by four
    hexadecimal digits (for example ``u00e9`` for ``é``).

    Args:
        value: Raw title string from the CSV.

    Returns:
        Title with embedded escape sequences replaced by Unicode characters.
        Unchanged when no escape pattern is present.

    Example:
        decode_embedded_unicode_escapes("Tu00e1r") == "Tár"
        decode_embedded_unicode_escapes("Inception") == "Inception"
    """
    return _EMBEDDED_UNICODE_ESCAPE.sub(
        lambda match: chr(int(match.group(1), 16)),
        value,
    )


def contains_embedded_unicode_escape(value: str) -> bool:
    """Return whether a title contains at least one ``uXXXX`` escape sequence.

    Args:
        value: Raw title string from the CSV.

    Returns:
        ``True`` when ``decode_embedded_unicode_escapes`` would modify ``value``.

    Example:
        contains_embedded_unicode_escape("Poku00e9mon") is True
        contains_embedded_unicode_escape("Inception") is False
    """
    return _EMBEDDED_UNICODE_ESCAPE.search(value) is not None
