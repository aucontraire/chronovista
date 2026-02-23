"""
Tag Normalization Service for canonical tag resolution.

This module implements a 9-step normalization pipeline that produces a stable
canonical form for YouTube video tags.  The pipeline is pure (no I/O, no
database) and idempotent: ``normalize(normalize(x)) == normalize(x)``.

Diacritic handling is *selective* — only the eight Tier 1 combining marks
that are safe to strip are removed.  Tier 2 marks (tilde, cedilla, ogonek,
horn, dot above, ring above, caron) and all Tier 3 marks survive.

References
----------
- FR-002: Empty / whitespace-only input returns ``None``
- FR-006: ``selective_strip_diacritics`` exposed as standalone utility
- FR-007: Idempotency guarantee
- FR-008: Pure function — no I/O, no database
- T003: TagNormalizationService implementation task
"""

from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier 1 — SAFE_TO_STRIP combining marks (8 total)
# These are common Latin diacritics whose removal does *not* change the
# linguistic identity of the base character for tag-matching purposes.
# ---------------------------------------------------------------------------
SAFE_TO_STRIP: frozenset[str] = frozenset(
    {
        "\u0300",  # COMBINING GRAVE ACCENT
        "\u0301",  # COMBINING ACUTE ACCENT
        "\u0302",  # COMBINING CIRCUMFLEX ACCENT
        "\u0304",  # COMBINING MACRON
        "\u0306",  # COMBINING BREVE
        "\u0308",  # COMBINING DIAERESIS
        "\u030B",  # COMBINING DOUBLE ACUTE ACCENT
        "\u030F",  # COMBINING DOUBLE GRAVE ACCENT
    }
)

# ---------------------------------------------------------------------------
# Zero-width characters to strip (Step 5)
# ---------------------------------------------------------------------------
_ZERO_WIDTH_CHARS: frozenset[str] = frozenset(
    {
        "\u200B",  # ZERO WIDTH SPACE
        "\u200C",  # ZERO WIDTH NON-JOINER
        "\u200D",  # ZERO WIDTH JOINER
        "\uFEFF",  # ZERO WIDTH NO-BREAK SPACE / BOM
    }
)


def selective_strip_diacritics(text: str) -> str:
    """
    Strip only Tier 1 combining marks from *text*, preserving all others.

    The function decomposes to NFKD, walks each character, removes only
    the eight marks listed in ``SAFE_TO_STRIP``, and recomposes to NFC.

    Parameters
    ----------
    text : str
        The input string (arbitrary Unicode).

    Returns
    -------
    str
        The string with Tier 1 diacritics removed and NFC-recomposed.

    Examples
    --------
    >>> selective_strip_diacritics("München")
    'Munchen'

    >>> selective_strip_diacritics("año")
    'año'
    """
    decomposed = unicodedata.normalize("NFKD", text)
    filtered = "".join(ch for ch in decomposed if ch not in SAFE_TO_STRIP)
    return unicodedata.normalize("NFC", filtered)


class TagNormalizationService:
    """
    Service that normalizes raw YouTube tags into canonical form.

    The 9-step pipeline is executed in strict order:

    1. Strip leading/trailing whitespace
    2. Strip a single leading ``#`` character
    3. Replace non-breaking spaces (U+00A0) and tabs with regular space
    4. Collapse multiple spaces to a single space
    5. Strip zero-width characters (U+200B, U+200C, U+200D, U+FEFF)
    6. NFKD decompose
    7. Strip Tier 1 combining marks only (selective)
    8. NFC recompose
    9. Casefold

    The result is ``None`` when the output would be an empty string.
    """

    def normalize(self, raw_tag: str) -> str | None:
        """
        Run the full 9-step normalization pipeline on *raw_tag*.

        Parameters
        ----------
        raw_tag : str
            The raw tag value as it appears on a YouTube video.

        Returns
        -------
        str | None
            The canonical form, or ``None`` if the result is empty after
            all normalization steps.

        Examples
        --------
        >>> svc = TagNormalizationService()
        >>> svc.normalize("#MÉXICO")
        'mexico'

        >>> svc.normalize("  ")
        None
        """
        # Step 1: Strip leading/trailing whitespace
        text = raw_tag.strip()

        # Step 2: Strip SINGLE leading '#' character
        if text.startswith("#"):
            text = text[1:]

        # Step 3: Replace non-breaking spaces and tabs with regular space
        text = text.replace("\u00A0", " ").replace("\t", " ")

        # Step 4: Collapse multiple spaces to single space
        parts = text.split()
        text = " ".join(parts)

        # Step 5: Strip zero-width characters
        text = "".join(ch for ch in text if ch not in _ZERO_WIDTH_CHARS)

        # Step 6: NFKD decompose
        text = unicodedata.normalize("NFKD", text)

        # Step 7: Strip Tier 1 combining marks only
        text = "".join(ch for ch in text if ch not in SAFE_TO_STRIP)

        # Step 8: NFC recompose
        text = unicodedata.normalize("NFC", text)

        # Step 9: Casefold
        text = text.casefold()

        # Final cleanup: Collapse any multiple spaces that may have been
        # introduced during normalization (e.g., from NFKD decomposition of
        # spacing diacritics like U+00B8 SPACING CEDILLA → space + combining mark),
        # and strip any leading/trailing whitespace
        parts = text.split()
        text = " ".join(parts)

        # FR-002: Return None for empty results
        return text if text else None

    def select_canonical_form(self, forms: list[tuple[str, int]]) -> str:
        """
        Select the canonical form from a list of raw forms and their counts.

        Implements the FR-009 algorithm:
        1. Filter for title case forms (using ``str.istitle()``)
        2. If title case forms exist: pick the one with highest occurrence count
        3. If NO title case forms exist: pick the one with highest occurrence count from ALL forms
        4. If occurrence counts are tied at any step: use alphabetical ``min()`` as deterministic tiebreaker

        Parameters
        ----------
        forms : list[tuple[str, int]]
            A list of ``(raw_form, occurrence_count)`` tuples.  Must not be empty.

        Returns
        -------
        str
            The selected canonical form.

        Raises
        ------
        ValueError
            If *forms* is empty.

        Examples
        --------
        >>> svc = TagNormalizationService()
        >>> svc.select_canonical_form([("MEXICO", 203), ("Mexico", 412), ("mexico", 156)])
        'Mexico'

        >>> svc.select_canonical_form([("Mexico", 200), ("México", 200)])
        'Mexico'

        >>> svc.select_canonical_form([("MEXICO", 500), ("mexico", 300)])
        'MEXICO'
        """
        if not forms:
            raise ValueError("Cannot select canonical form from empty list")

        # Single-element case
        if len(forms) == 1:
            return forms[0][0]

        # Step 1: Filter for title case forms
        title_case_forms = [(form, count) for form, count in forms if form.istitle()]

        # Step 2: Determine the candidate pool
        if title_case_forms:
            candidates = title_case_forms
        else:
            candidates = forms

        # Step 3: Find the maximum occurrence count
        max_count = max(count for _, count in candidates)

        # Step 4: Get all forms with the maximum count
        max_forms = [form for form, count in candidates if count == max_count]

        # Step 5: Use alphabetical min as tiebreaker
        return min(max_forms)
