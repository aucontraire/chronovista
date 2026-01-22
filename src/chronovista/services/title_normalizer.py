"""
Title Normalizer Service for Playlist Resolution.

This module handles title normalization for matching Takeout playlist titles
to YouTube API titles. Google Takeout exports replace certain characters
(apostrophes, slashes) with underscores in playlist titles.

References:
- FR-030: Normalized title comparison
- FR-031: Confidence scoring for matches
- T090-T094: Title normalizer implementation tasks
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

# T090: Characters that Takeout normalizes to underscores
# Confirmed through manual investigation of actual Takeout exports
TAKEOUT_NORMALIZED_CHARS: str = "'/\\"


@dataclass(frozen=True)
class NormalizationResult:
    """
    Result of comparing two titles for normalization matching.

    Attributes
    ----------
    is_match : bool
        Whether the titles are considered a match.
    confidence : float
        Confidence score from 0.0 to 1.0.
    matching_strategy : Literal["exact", "normalized", "none"]
        The strategy that produced the match.
    source_title : str
        The original source title (from local database).
    target_title : str
        The original target title (from YouTube API).
    normalized_source : str
        The normalized version of the source title.
    normalized_target : str
        The normalized version of the target title.
    underscore_positions : list[int]
        Positions in source title where underscores occur.
    potential_original_chars : list[str]
        Characters that might have been normalized to underscores.
    """

    is_match: bool
    confidence: float
    matching_strategy: Literal["exact", "normalized", "none"]
    source_title: str
    target_title: str
    normalized_source: str
    normalized_target: str
    underscore_positions: list[int]
    potential_original_chars: list[str]


def normalize_for_comparison(title: str) -> str:
    """
    Normalize a title for comparison by replacing normalizable characters with underscores.

    This function converts a title to its "Takeout-normalized" form by:
    1. Normalizing Unicode to NFC form (composed characters)
    2. Converting to lowercase for case-insensitive comparison
    3. Replacing apostrophes and slashes with underscores
    4. Collapsing multiple consecutive underscores to single underscores

    Parameters
    ----------
    title : str
        The title to normalize.

    Returns
    -------
    str
        The normalized title ready for comparison.

    Examples
    --------
    >>> normalize_for_comparison("Conan O'Brien's Playlist")
    "conan o_brien_s playlist"

    >>> normalize_for_comparison("Music/Videos/2024")
    "music_videos_2024"

    >>> normalize_for_comparison("Already_Has_Underscores")
    "already_has_underscores"
    """
    if not title:
        return ""

    # Normalize Unicode to NFC (composed form) to handle characters like ñ
    # that may be stored as decomposed (n + combining tilde) vs composed
    normalized = unicodedata.normalize("NFC", title)

    # Convert to lowercase for case-insensitive comparison
    normalized = normalized.lower()

    # Replace Takeout-normalized characters with underscores
    for char in TAKEOUT_NORMALIZED_CHARS:
        normalized = normalized.replace(char, "_")

    # Collapse multiple consecutive underscores to single underscore
    normalized = re.sub(r"_+", "_", normalized)

    return normalized


def has_underscore_that_might_be_normalized(title: str) -> bool:
    """
    Detect if a title has underscores that might be normalized characters.

    This heuristic determines if a title likely came from Takeout export
    based on underscore patterns. Returns True if:
    - Title contains underscores that appear in word-boundary positions
    - Underscores are adjacent to letters (not just separating words)

    Parameters
    ----------
    title : str
        The title to analyze.

    Returns
    -------
    bool
        True if the title likely has normalized underscores.

    Examples
    --------
    >>> has_underscore_that_might_be_normalized("Conan O_Brien")
    True  # Underscore mid-word, likely apostrophe

    >>> has_underscore_that_might_be_normalized("my_playlist_name")
    True  # Could be intentional or normalized

    >>> has_underscore_that_might_be_normalized("MyPlaylist")
    False  # No underscores
    """
    if "_" not in title:
        return False

    # Pattern: underscore surrounded by letters (likely normalized character)
    # e.g., "O_Brien" or "Don_t"
    letter_underscore_letter = re.compile(r"[a-zA-Z]_[a-zA-Z]")
    if letter_underscore_letter.search(title):
        return True

    # Pattern: underscore at start/end of word followed/preceded by letter
    # e.g., "_Brien" or "Brien_"
    if re.search(r"\b_[a-zA-Z]|[a-zA-Z]_\b", title):
        return True

    # Pattern: title has internal playlist ID format (int_) - never normalized
    # If there are any underscores at all, treat as potentially normalized
    # This is conservative - better to check than miss
    return not title.startswith("int_")


def get_underscore_positions(title: str) -> list[int]:
    """
    Get the positions of all underscores in a title.

    Parameters
    ----------
    title : str
        The title to analyze.

    Returns
    -------
    list[int]
        List of positions (indices) where underscores occur.

    Examples
    --------
    >>> get_underscore_positions("Conan O_Brien_s Show")
    [7, 14]

    >>> get_underscore_positions("No underscores here")
    []

    References
    ----------
    FR-030: Normalized title comparison
    """
    return [i for i, char in enumerate(title) if char == "_"]


def get_potential_original_chars(
    source_title: str, target_title: str, positions: list[int]
) -> list[str]:
    """
    Determine which characters at underscore positions might have been normalized.

    This function compares underscore positions in the source title against
    the target title to identify what characters were likely replaced during
    Takeout export. Used for confidence scoring in normalized matches.

    Parameters
    ----------
    source_title : str
        The source title (with underscores from Takeout normalization).
    target_title : str
        The target title (potentially with original characters from YouTube).
    positions : list[int]
        Positions of underscores in the source title.

    Returns
    -------
    list[str]
        List of characters from target that correspond to underscores in source.
        May include apostrophes, slashes, or underscores (if intentional).

    Examples
    --------
    >>> get_potential_original_chars("O_Brien", "O'Brien", [1])
    ["'"]

    >>> get_potential_original_chars("Music_Videos", "Music/Videos", [5])
    ["/"]

    References
    ----------
    FR-031: Confidence scoring for matches
    T092: Character detection for confidence calculation
    """
    original_chars: list[str] = []

    for pos in positions:
        # Account for potential length differences due to normalization
        # Find the approximate corresponding position in target
        if pos < len(target_title):
            char = target_title[pos]
            if char in TAKEOUT_NORMALIZED_CHARS:
                original_chars.append(char)
            elif char == "_":
                original_chars.append("_")  # Intentional underscore
            else:
                # Position mismatch - try to find nearby normalizable char
                start = max(0, pos - 2)
                end = min(len(target_title), pos + 3)
                for nearby_char in target_title[start:end]:
                    if nearby_char in TAKEOUT_NORMALIZED_CHARS:
                        original_chars.append(nearby_char)
                        break

    return original_chars


def compare_titles(source_title: str, target_title: str) -> NormalizationResult:
    """
    Compare two titles with confidence scoring for normalization matching.

    This is the main entry point for title comparison. It:
    1. First tries exact match (case-insensitive)
    2. If no exact match, tries normalized comparison
    3. Calculates confidence based on match type and underscore patterns

    Confidence scoring:
    - Exact match: 1.0 (100%)
    - Normalized match with all underscores explained: 0.95 (95%)
    - Normalized match with some unexplained underscores: 0.80-0.94
    - Normalized match with many differences: 0.60-0.79
    - No match: 0.0

    Parameters
    ----------
    source_title : str
        The source title (typically from local database/Takeout).
    target_title : str
        The target title (typically from YouTube API).

    Returns
    -------
    NormalizationResult
        Detailed result including match status, confidence, and analysis.

    Examples
    --------
    >>> result = compare_titles("Conan O_Brien", "Conan O'Brien")
    >>> result.is_match
    True
    >>> result.confidence
    0.95
    >>> result.matching_strategy
    "normalized"
    """
    # Normalize both titles for comparison
    normalized_source = normalize_for_comparison(source_title)
    normalized_target = normalize_for_comparison(target_title)

    # Get underscore analysis
    underscore_positions = get_underscore_positions(source_title)
    potential_chars = get_potential_original_chars(
        source_title, target_title, underscore_positions
    )

    # Check for exact match (case-insensitive)
    if source_title.lower() == target_title.lower():
        return NormalizationResult(
            is_match=True,
            confidence=1.0,
            matching_strategy="exact",
            source_title=source_title,
            target_title=target_title,
            normalized_source=normalized_source,
            normalized_target=normalized_target,
            underscore_positions=underscore_positions,
            potential_original_chars=potential_chars,
        )

    # Check for normalized match
    if normalized_source == normalized_target:
        # Calculate confidence based on underscore explanation
        confidence = _calculate_normalized_confidence(
            source_title, target_title, underscore_positions, potential_chars
        )

        return NormalizationResult(
            is_match=True,
            confidence=confidence,
            matching_strategy="normalized",
            source_title=source_title,
            target_title=target_title,
            normalized_source=normalized_source,
            normalized_target=normalized_target,
            underscore_positions=underscore_positions,
            potential_original_chars=potential_chars,
        )

    # No match
    return NormalizationResult(
        is_match=False,
        confidence=0.0,
        matching_strategy="none",
        source_title=source_title,
        target_title=target_title,
        normalized_source=normalized_source,
        normalized_target=normalized_target,
        underscore_positions=underscore_positions,
        potential_original_chars=potential_chars,
    )


def _calculate_normalized_confidence(
    source_title: str,
    target_title: str,
    underscore_positions: list[int],
    potential_chars: list[str],
) -> float:
    """
    Calculate confidence score for a normalized match.

    Confidence is based on how many underscores in the source title can be
    explained by known Takeout-normalized characters in the target title:

    - 0.98: No underscores to explain (pure case difference)
    - 0.95: All underscores explained by normalized chars (apostrophe/slash)
    - 0.90: 75%+ underscores explained
    - 0.85: 50%+ underscores explained
    - 0.75: Some underscores explained
    - 0.70: No underscores explained (could be intentional underscores)

    Parameters
    ----------
    source_title : str
        The source title (with underscores from Takeout).
    target_title : str
        The target title (with original characters from YouTube).
    underscore_positions : list[int]
        Positions of underscores in source.
    potential_chars : list[str]
        Characters that might have been normalized.

    Returns
    -------
    float
        Confidence score between 0.0 and 1.0.

    References
    ----------
    FR-031: Confidence scoring for matches
    FR-032: User confirmation required for confidence < 0.95
    """
    if not underscore_positions:
        # No underscores to explain - pure case difference
        return 0.98

    # Count how many underscores are explainable
    explainable_count = sum(
        1 for char in potential_chars if char in TAKEOUT_NORMALIZED_CHARS
    )
    total_underscores = len(underscore_positions)

    if total_underscores == 0:
        return 0.98

    explanation_ratio = explainable_count / total_underscores

    if explanation_ratio >= 1.0:
        # All underscores fully explained by normalized chars
        return 0.95
    elif explanation_ratio >= 0.75:
        # Most underscores explained
        return 0.90
    elif explanation_ratio >= 0.5:
        # Some underscores explained
        return 0.85
    elif explanation_ratio > 0:
        # Few underscores explained
        return 0.75
    else:
        # No underscores explained - could be intentional underscores
        # Still a valid normalized match, but lower confidence
        return 0.70
