"""Text processing utilities for correction and analysis pipelines.

Provides helper functions for normalising text tokens extracted from
word-level diffs and cross-segment candidates.
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width and other invisible formatting characters that are not whitespace
# (so ``\s`` never matches them) but should be removed: zero-width space,
# zero-width non-joiner, zero-width joiner, byte-order mark / zero-width
# no-break space, and the soft hyphen.
_INVISIBLE_CHARS = "".join(chr(c) for c in (0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD))
_INVISIBLE_RE = re.compile(f"[{_INVISIBLE_CHARS}]")

# One run of any whitespace (including newlines, tabs, and Unicode spaces such
# as the non-breaking space U+00A0, which ``\s`` matches in ``str`` mode).
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def normalize_segment_text(text: str) -> str:
    """Normalize whitespace and invisible characters in transcript segment text.

    Collapses every run of whitespace (newlines, tabs, non-breaking and other
    Unicode spaces) to a single regular space; removes zero-width characters and
    the soft hyphen; applies Unicode NFC composition; and trims. Textual content
    — letters, accents/diacritics, currency symbols, non-Latin scripts, and
    ordinary punctuation — is never altered; only whitespace is collapsed and
    known-invisible formatting characters removed.

    Intended for transcript segment text. Because it strips the zero-width
    joiner (U+200D), it is NOT emoji-safe: it would split an emoji ZWJ sequence
    (e.g. a family or flag emoji) into its component glyphs. Captions do not
    contain such sequences, so this does not affect transcripts; do not reuse
    this on emoji-bearing content where ZWJ sequences must be preserved.

    This is the single source of truth for the stored-text fold, applied where
    segment text is derived at ingest and by the whitespace-normalization
    backfill. It is idempotent: ``normalize_segment_text(normalize_segment_text(x))``
    equals ``normalize_segment_text(x)``.

    Parameters
    ----------
    text : str
        The raw segment text (possibly containing line breaks, non-breaking or
        zero-width characters).

    Returns
    -------
    str
        The normalized text.

    Examples
    --------
    >>> normalize_segment_text("foo\\nbar")
    'foo bar'
    >>> normalize_segment_text("a\\u00a0b")
    'a b'
    >>> normalize_segment_text("  x\\u200b y  ")
    'x y'
    """
    # NFC is applied LAST: stripping invisibles first removes any zero-width
    # character sitting between a base letter and its combining mark, so NFC can
    # then compose them. Applying NFC first would leave such a pair decomposed
    # (the separator blocks composition, then the strip removes it), which both
    # violates the NFC-output guarantee and breaks idempotency — a second pass
    # would compose it, changing the result (and re-writing the row in the
    # backfill).
    normalized = _INVISIBLE_RE.sub("", text)
    normalized = _WHITESPACE_RUN_RE.sub(" ", normalized)
    normalized = unicodedata.normalize("NFC", normalized)
    return normalized.strip()


# Characters to strip from the boundaries of tokens.  Internal punctuation
# (hyphens in "Teapot-Dome", apostrophes in "Khashoggi's") is preserved.
_BOUNDARY_PUNCT_RE = re.compile(
    r"^[.,;:!?\"'`()\[\]{}<>…—–\-/\\|@#$%^&*~]+|"
    r"[.,;:!?\"'`()\[\]{}<>…—–\-/\\|@#$%^&*~]+$"
)


def strip_boundary_punctuation(text: str) -> str:
    """Strip leading and trailing punctuation from text, preserving internal punctuation.

    Characters such as ``.``, ``,``, ``;``, ``:``, ``!``, ``?``, ``"``,
    ``'``, ``(``, ``)`` and similar are removed from the boundaries only.
    Internal punctuation (e.g., hyphens in "Teapot-Dome" or apostrophes
    in "Khashoggi's") is preserved.

    Parameters
    ----------
    text : str
        The input text to clean.

    Returns
    -------
    str
        The text with boundary punctuation removed.

    Examples
    --------
    >>> strip_boundary_punctuation('"Johnson"')
    'Johnson'
    >>> strip_boundary_punctuation("Teapot-Dome")
    'Teapot-Dome'
    >>> strip_boundary_punctuation("Khashoggi's")
    "Khashoggi's"
    >>> strip_boundary_punctuation("...hello...")
    'hello'
    """
    return _BOUNDARY_PUNCT_RE.sub("", text)
