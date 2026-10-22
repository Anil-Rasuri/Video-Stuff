"""Tiny helpers for telling Telugu / Devanagari / Latin text apart."""

from __future__ import annotations

import unicodedata


def script_of(text: str) -> str:
    """Return 'telugu', 'devanagari' or 'latin' for a word.

    Any Telugu letter wins, then any Devanagari letter, otherwise Latin
    (which also covers digits and punctuation).
    """
    has_devanagari = False
    for ch in text:
        o = ord(ch)
        if 0x0C00 <= o <= 0x0C7F:
            return "telugu"
        if 0x0900 <= o <= 0x097F or 0xA8E0 <= o <= 0xA8FF:
            has_devanagari = True
    return "devanagari" if has_devanagari else "latin"


def grapheme_len(text: str) -> int:
    """Approximate visible length: combining marks (vowel signs, viramas) don't count."""
    return sum(1 for ch in text if not unicodedata.category(ch).startswith("M"))
