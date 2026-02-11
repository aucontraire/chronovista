"""
Tests for fuzzy string matching utilities.

This module provides comprehensive test coverage for the fuzzy matching
utilities used throughout chronovista for "Did you mean?" suggestions.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from chronovista.utils.fuzzy import find_similar, levenshtein_distance


# -------------------------------------------------------------------------
# Test: levenshtein_distance
# -------------------------------------------------------------------------


class TestLevenshteinDistance:
    """Tests for levenshtein_distance() function."""

    def test_identical_strings(self) -> None:
        """Test distance of identical strings is 0."""
        assert levenshtein_distance("en", "en") == 0
        assert levenshtein_distance("hello", "hello") == 0
        assert levenshtein_distance("", "") == 0

    def test_single_substitution(self) -> None:
        """Test single character substitution."""
        assert levenshtein_distance("en", "es") == 1
        assert levenshtein_distance("cat", "bat") == 1
        assert levenshtein_distance("book", "look") == 1

    def test_single_insertion(self) -> None:
        """Test single character insertion."""
        assert levenshtein_distance("en", "enn") == 1
        assert levenshtein_distance("cat", "cats") == 1
        assert levenshtein_distance("helo", "hello") == 1

    def test_single_deletion(self) -> None:
        """Test single character deletion."""
        assert levenshtein_distance("en", "e") == 1
        assert levenshtein_distance("cats", "cat") == 1
        assert levenshtein_distance("hello", "helo") == 1

    def test_empty_string(self) -> None:
        """Test distance to empty string is length of other string."""
        assert levenshtein_distance("en", "") == 2
        assert levenshtein_distance("", "en") == 2
        assert levenshtein_distance("hello", "") == 5
        assert levenshtein_distance("", "hello") == 5

    def test_completely_different(self) -> None:
        """Test distance of completely different strings."""
        assert levenshtein_distance("abc", "xyz") == 3
        assert levenshtein_distance("cat", "dog") == 3

    def test_classic_example(self) -> None:
        """Test classic kitten/sitting example (distance = 3)."""
        # kitten → sitten (s for k) → sittin (i for e) → sitting (g added)
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_symmetry(self) -> None:
        """Test that distance is symmetric: d(a,b) == d(b,a)."""
        assert levenshtein_distance("abc", "def") == levenshtein_distance("def", "abc")
        assert levenshtein_distance("en", "es") == levenshtein_distance("es", "en")

    def test_case_sensitive(self) -> None:
        """Test that comparison is case-sensitive."""
        assert levenshtein_distance("ABC", "abc") == 3
        assert levenshtein_distance("Hello", "hello") == 1


# -------------------------------------------------------------------------
# Test: find_similar
# -------------------------------------------------------------------------


class TestFindSimilar:
    """Tests for find_similar() function."""

    def test_exact_match(self) -> None:
        """Test exact match is returned first."""
        candidates = ["javascript", "java", "python", "typescript"]
        result = find_similar("javascript", candidates)
        assert result == ["javascript"]

    def test_close_match(self) -> None:
        """Test close matches are found."""
        candidates = ["javascript", "java", "python", "typescript"]
        result = find_similar("javascrip", candidates)
        assert result == ["javascript"]

    def test_multiple_matches_sorted_by_distance(self) -> None:
        """Test multiple matches are sorted by distance."""
        candidates = ["en", "es", "fr", "de"]
        result = find_similar("en", candidates, max_distance=2)
        # "en" has distance 0, "es" has distance 1
        assert result[0] == "en"
        assert "es" in result

    def test_no_matches(self) -> None:
        """Test empty result when no matches within distance."""
        candidates = ["javascript", "python", "typescript"]
        result = find_similar("rust", candidates, max_distance=2)
        assert result == []

    def test_limit_results(self) -> None:
        """Test limit parameter restricts results."""
        candidates = ["en", "es", "et", "el", "eo"]
        result = find_similar("e", candidates, max_distance=2, limit=2)
        assert len(result) <= 2

    def test_case_insensitive_default(self) -> None:
        """Test case-insensitive matching by default."""
        candidates = ["JavaScript", "Python", "TypeScript"]
        result = find_similar("javascript", candidates)
        assert result == ["JavaScript"]

    def test_case_sensitive_option(self) -> None:
        """Test case-sensitive matching when specified."""
        candidates = ["JavaScript", "javascript", "JAVASCRIPT"]
        # With case_sensitive=True, "JavaScript" has distance 1 (J→j),
        # "JAVASCRIPT" has distance 10 (all chars different case)
        result = find_similar("javascript", candidates, case_sensitive=True)
        assert result[0] == "javascript"  # Exact match first
        assert "JavaScript" in result  # Distance 1, within default max_distance=2

        # Use max_distance=0 for exact matches only
        result = find_similar("javascript", candidates, case_sensitive=True, max_distance=0)
        assert result == ["javascript"]

    def test_empty_query(self) -> None:
        """Test empty query matches short candidates."""
        candidates = ["a", "ab", "abc", "abcd"]
        result = find_similar("", candidates, max_distance=2)
        # Empty string has distance equal to candidate length
        assert "a" in result
        assert "ab" in result
        assert "abc" not in result  # distance 3 > max_distance 2

    def test_empty_candidates(self) -> None:
        """Test empty candidates list returns empty result."""
        result = find_similar("test", [])
        assert result == []

    def test_alphabetical_tiebreaker(self) -> None:
        """Test alphabetical sorting for same distance."""
        candidates = ["cat", "bat", "rat"]
        result = find_similar("mat", candidates, max_distance=1)
        # All have distance 1, should be sorted alphabetically
        assert result == ["bat", "cat", "rat"]

    def test_preserves_original_case(self) -> None:
        """Test that original candidate case is preserved in results."""
        candidates = ["JavaScript", "TypeScript", "CoffeeScript"]
        result = find_similar("javascript", candidates)
        assert result == ["JavaScript"]
        assert result[0] == "JavaScript"  # Original case preserved

    def test_max_distance_zero(self) -> None:
        """Test max_distance=0 only returns exact matches."""
        candidates = ["en", "es", "fr"]
        result = find_similar("en", candidates, max_distance=0)
        assert result == ["en"]
        result = find_similar("enn", candidates, max_distance=0)
        assert result == []

    def test_generator_input(self) -> None:
        """Test that generator input works."""
        def candidate_gen() -> Generator[str, None, None]:
            yield from ["en", "es", "fr"]

        result = find_similar("en", candidate_gen())
        assert "en" in result

    def test_real_world_language_codes(self) -> None:
        """Test with realistic language code scenario."""
        lang_codes = ["en", "en-US", "en-GB", "es", "es-MX", "fr", "de", "it", "pt"]

        # User types "enn" instead of "en"
        result = find_similar("enn", lang_codes, max_distance=2, limit=3)
        assert "en" in result

        # User types "es-us" instead of "en-US"
        result = find_similar("es-us", lang_codes, max_distance=2, limit=3)
        assert "en-US" in result or "es" in result

    def test_real_world_tag_suggestions(self) -> None:
        """Test with realistic tag suggestion scenario."""
        tags = ["javascript", "java", "python", "typescript", "react", "angular"]

        # User types "javascrip" (missing 't')
        result = find_similar("javascrip", tags, max_distance=2, limit=3)
        assert "javascript" in result

        # User types "pyhton" (typo)
        result = find_similar("pyhton", tags, max_distance=2, limit=3)
        assert "python" in result
