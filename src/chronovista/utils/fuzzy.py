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
from typing import List, Tuple


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance between two strings.

    The Levenshtein distance is the minimum number of single-character edits
    (insertions, deletions, or substitutions) required to change one string
    into the other.

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
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row: List[int] = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row: List[int] = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def find_similar(
    query: str,
    candidates: Iterable[str],
    *,
    max_distance: int = 2,
    limit: int = 3,
    case_sensitive: bool = False,
) -> List[str]:
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
    matches: List[Tuple[int, str]] = []

    for candidate in candidates:
        compare_value = candidate if case_sensitive else candidate.lower()
        distance = levenshtein_distance(normalized_query, compare_value)
        if distance <= max_distance:
            matches.append((distance, candidate))

    # Sort by distance first, then alphabetically for ties
    matches.sort(key=lambda x: (x[0], x[1].lower()))

    return [match[1] for match in matches[:limit]]
