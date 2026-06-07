"""Unit tests for title encoding helpers."""

from src.utils.title_encoding import (
    contains_embedded_unicode_escape,
    decode_embedded_unicode_escapes,
)


def test_decode_embedded_unicode_escapes_replaces_known_artefacts() -> None:
    assert decode_embedded_unicode_escapes("Tu00e1r") == "Tár"
    assert decode_embedded_unicode_escapes("Les Misu00e9rables") == "Les Misérables"
    assert decode_embedded_unicode_escapes("Poku00e9mon Detective Pikachu") == (
        "Pokémon Detective Pikachu"
    )


def test_decode_embedded_unicode_escapes_leaves_plain_titles_unchanged() -> None:
    assert decode_embedded_unicode_escapes("Inception") == "Inception"
    assert decode_embedded_unicode_escapes("Avatar") == "Avatar"


def test_contains_embedded_unicode_escape_detects_artefacts() -> None:
    assert contains_embedded_unicode_escape("Quu00e9 Leu00f3n") is True
    assert contains_embedded_unicode_escape("Inception") is False
