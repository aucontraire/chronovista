"""Fuzzy string matching utilities.

This module provides functions for fuzzy string matching using Levenshtein
distance (edit distance). It's used throughout chronovista for suggesting
similar items when users make typos or near-misses.

Use Cases:
- Language code suggestions ("enn" → "en")
- Tag autocomplete suggestions ("javascrip" → "javascript")
- Command typo corrections
"""

from collections.abc import Iterable

import Levenshtein as _levenshtein


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance between two strings.

    The Levenshtein distance is the minimum number of single-character edits
    (insertions, deletions, or substitutions) required to change one string
    into the other.

    Delegates to the C-optimised ``python-Levenshtein`` library for
    performance.

    Parameters
    ----------
    s1 : str
        First string.
    s2 : str
        Second string.

    Returns
    -------
    int
        The Levenshtein distance between the two strings.

    Examples
    --------
    >>> levenshtein_distance("en", "es")
    1
    >>> levenshtein_distance("fr", "de")
    2
    >>> levenshtein_distance("kitten", "sitting")
    3
    """
    return _levenshtein.distance(s1, s2)


def find_similar(
    query: str,
    candidates: Iterable[str],
    *,
    max_distance: int = 2,
    limit: int = 3,
    case_sensitive: bool = False,
) -> list[str]:
    """
    Find candidates within max_distance of query, sorted by distance.

    This function is useful for "Did you mean?" suggestions when a user
    enters an invalid or unrecognized value.

    Parameters
    ----------
    query : str
        The string to find similar matches for.
    candidates : Iterable[str]
        The collection of valid strings to search through.
    max_distance : int, optional
        Maximum Levenshtein distance for a match (default: 2).
        Higher values find more matches but may be less relevant.
    limit : int, optional
        Maximum number of suggestions to return (default: 3).
    case_sensitive : bool, optional
        Whether to perform case-sensitive matching (default: False).

    Returns
    -------
    List[str]
        List of similar candidates, sorted by distance (closest first),
        then alphabetically for ties. Returns original case of candidates.

    Examples
    --------
    >>> find_similar("javascrip", ["javascript", "java", "python", "typescript"])
    ['javascript']
    >>> find_similar("en", ["en", "es", "fr", "de"])
    ['en', 'es']
    >>> find_similar("xyz", ["abc", "def"], max_distance=1)
    []
    """
    normalized_query = query if case_sensitive else query.lower()
    matches: list[tuple[int, str]] = []

    for candidate in candidates:
        compare_value = candidate if case_sensitive else candidate.lower()
        distance = levenshtein_distance(normalized_query, compare_value)
        if distance <= max_distance:
            matches.append((distance, candidate))

    # Sort by distance first, then alphabetically for ties
    matches.sort(key=lambda x: (x[0], x[1].lower()))

    return [match[1] for match in matches[:limit]]
