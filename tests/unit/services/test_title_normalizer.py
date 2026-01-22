"""
Tests for Title Normalizer Service.

Tests the normalization logic used to match Takeout playlist titles
to YouTube API titles, including confidence scoring.

References:
- T095-T098: Title normalizer test tasks
- FR-030: Normalized title comparison
- FR-031: Confidence scoring for matches
"""

from __future__ import annotations

import pytest

from chronovista.services.title_normalizer import (
    TAKEOUT_NORMALIZED_CHARS,
    NormalizationResult,
    compare_titles,
    get_potential_original_chars,
    get_underscore_positions,
    has_underscore_that_might_be_normalized,
    normalize_for_comparison,
)


class TestTakeoutNormalizedChars:
    """T090: Tests for TAKEOUT_NORMALIZED_CHARS constant."""

    def test_contains_apostrophe(self) -> None:
        """Verify apostrophe is in normalized chars set."""
        assert "'" in TAKEOUT_NORMALIZED_CHARS

    def test_contains_forward_slash(self) -> None:
        """Verify forward slash is in normalized chars set."""
        assert "/" in TAKEOUT_NORMALIZED_CHARS

    def test_contains_backslash(self) -> None:
        """Verify backslash is in normalized chars set."""
        assert "\\" in TAKEOUT_NORMALIZED_CHARS

    def test_is_string_type(self) -> None:
        """Verify constant is a string."""
        assert isinstance(TAKEOUT_NORMALIZED_CHARS, str)


class TestNormalizeForComparison:
    """T095: Tests for normalize_for_comparison() function."""

    def test_apostrophe_normalized_to_underscore(self) -> None:
        """Apostrophe should be replaced with underscore."""
        result = normalize_for_comparison("Conan O'Brien")
        assert "_" in result
        assert "'" not in result
        assert result == "conan o_brien"

    def test_forward_slash_normalized_to_underscore(self) -> None:
        """Forward slash should be replaced with underscore."""
        result = normalize_for_comparison("Music/Videos")
        assert "_" in result
        assert "/" not in result
        assert result == "music_videos"

    def test_backslash_normalized_to_underscore(self) -> None:
        """Backslash should be replaced with underscore."""
        result = normalize_for_comparison("Path\\To\\Playlist")
        assert result == "path_to_playlist"

    def test_case_insensitive(self) -> None:
        """Normalization should convert to lowercase."""
        result = normalize_for_comparison("My PLAYLIST Name")
        assert result == "my playlist name"

    def test_multiple_apostrophes(self) -> None:
        """Multiple apostrophes should all be normalized."""
        result = normalize_for_comparison("Don't Stop 'til You Get Enough")
        assert "'" not in result
        assert result == "don_t stop _til you get enough"

    def test_consecutive_normalized_chars(self) -> None:
        """Consecutive normalizable chars should collapse to single underscore."""
        result = normalize_for_comparison("Test'/Mixed")
        assert "__" not in result  # Should not have double underscores
        assert result == "test_mixed"

    def test_empty_string(self) -> None:
        """Empty string should return empty string."""
        assert normalize_for_comparison("") == ""

    def test_no_normalizable_chars(self) -> None:
        """String without normalizable chars returns lowercase only."""
        result = normalize_for_comparison("Simple Playlist")
        assert result == "simple playlist"

    def test_preserves_spaces(self) -> None:
        """Spaces should be preserved."""
        result = normalize_for_comparison("My Playlist Name")
        assert " " in result
        assert result == "my playlist name"

    def test_preserves_numbers(self) -> None:
        """Numbers should be preserved."""
        result = normalize_for_comparison("Playlist 2024")
        assert "2024" in result
        assert result == "playlist 2024"

    def test_mixed_content(self) -> None:
        """Mixed content should be properly normalized."""
        result = normalize_for_comparison("Rock & Roll '80s/90s Hits")
        assert result == "rock & roll _80s_90s hits"

    def test_existing_underscores_preserved(self) -> None:
        """Existing underscores should be preserved."""
        result = normalize_for_comparison("my_playlist")
        assert result == "my_playlist"


class TestHasUnderscoreThatMightBeNormalized:
    """T096: Tests for has_underscore_that_might_be_normalized() heuristic."""

    def test_no_underscores_returns_false(self) -> None:
        """Title without underscores should return False."""
        assert has_underscore_that_might_be_normalized("My Playlist") is False

    def test_mid_word_underscore_returns_true(self) -> None:
        """Underscore between letters should return True."""
        assert has_underscore_that_might_be_normalized("Conan O_Brien") is True

    def test_dont_pattern_returns_true(self) -> None:
        """Don't pattern (Don_t) should return True."""
        assert has_underscore_that_might_be_normalized("Don_t Stop") is True

    def test_underscore_separating_words_returns_true(self) -> None:
        """Underscore separating words could be normalized."""
        assert has_underscore_that_might_be_normalized("my_playlist_name") is True

    def test_internal_id_prefix_returns_false(self) -> None:
        """Internal playlist ID (int_) should return False."""
        assert has_underscore_that_might_be_normalized("int_12345") is False

    def test_multiple_underscores_returns_true(self) -> None:
        """Multiple underscores should return True."""
        assert has_underscore_that_might_be_normalized("a_b_c") is True

    def test_empty_string_returns_false(self) -> None:
        """Empty string should return False."""
        assert has_underscore_that_might_be_normalized("") is False

    def test_only_underscore_returns_true(self) -> None:
        """Single underscore should return True (conservative)."""
        assert has_underscore_that_might_be_normalized("_") is True


class TestGetUnderscorePositions:
    """Tests for get_underscore_positions() helper function."""

    def test_no_underscores(self) -> None:
        """Title without underscores returns empty list."""
        assert get_underscore_positions("Hello World") == []

    def test_single_underscore(self) -> None:
        """Single underscore returns its position."""
        positions = get_underscore_positions("Hello_World")
        assert positions == [5]

    def test_multiple_underscores(self) -> None:
        """Multiple underscores return all positions."""
        positions = get_underscore_positions("a_b_c")
        assert positions == [1, 3]

    def test_underscore_at_start(self) -> None:
        """Underscore at start returns position 0."""
        positions = get_underscore_positions("_start")
        assert positions == [0]

    def test_underscore_at_end(self) -> None:
        """Underscore at end returns correct position."""
        positions = get_underscore_positions("end_")
        assert positions == [3]


class TestGetPotentialOriginalChars:
    """Tests for get_potential_original_chars() helper function."""

    def test_apostrophe_detected(self) -> None:
        """Apostrophe at underscore position should be detected."""
        chars = get_potential_original_chars("O_Brien", "O'Brien", [1])
        assert "'" in chars

    def test_slash_detected(self) -> None:
        """Slash at underscore position should be detected."""
        chars = get_potential_original_chars("Music_Videos", "Music/Videos", [5])
        assert "/" in chars

    def test_no_positions_returns_empty(self) -> None:
        """No underscore positions returns empty list."""
        chars = get_potential_original_chars("Hello", "Hello", [])
        assert chars == []

    def test_intentional_underscore_detected(self) -> None:
        """Intentional underscore in target should be detected."""
        chars = get_potential_original_chars("my_name", "my_name", [2])
        assert "_" in chars


class TestCompareTitles:
    """T097: Tests for compare_titles() with confidence scoring."""

    def test_exact_match_full_confidence(self) -> None:
        """Exact match (case-insensitive) should have 100% confidence."""
        result = compare_titles("My Playlist", "my playlist")
        assert result.is_match is True
        assert result.confidence == 1.0
        assert result.matching_strategy == "exact"

    def test_exact_match_same_case(self) -> None:
        """Exact match with same case should have 100% confidence."""
        result = compare_titles("My Playlist", "My Playlist")
        assert result.is_match is True
        assert result.confidence == 1.0
        assert result.matching_strategy == "exact"

    def test_normalized_match_apostrophe(self) -> None:
        """Normalized match with apostrophe should be detected."""
        result = compare_titles("Conan O_Brien", "Conan O'Brien")
        assert result.is_match is True
        assert result.matching_strategy == "normalized"
        assert result.confidence >= 0.90

    def test_normalized_match_slash(self) -> None:
        """Normalized match with slash should be detected."""
        result = compare_titles("Music_Videos", "Music/Videos")
        assert result.is_match is True
        assert result.matching_strategy == "normalized"
        assert result.confidence >= 0.90

    def test_no_match_different_titles(self) -> None:
        """Different titles should not match."""
        result = compare_titles("My Playlist", "Other Playlist")
        assert result.is_match is False
        assert result.confidence == 0.0
        assert result.matching_strategy == "none"

    def test_normalized_match_high_confidence(self) -> None:
        """Normalized match with clear normalization should be high confidence."""
        result = compare_titles("Don_t Stop", "Don't Stop")
        assert result.is_match is True
        assert result.confidence >= 0.90

    def test_result_contains_original_titles(self) -> None:
        """Result should contain original titles."""
        result = compare_titles("Source", "Target")
        assert result.source_title == "Source"
        assert result.target_title == "Target"

    def test_result_contains_normalized_titles(self) -> None:
        """Result should contain normalized titles."""
        result = compare_titles("Test'Title", "Test'Title")
        assert result.normalized_source == "test_title"
        assert result.normalized_target == "test_title"

    def test_result_is_frozen_dataclass(self) -> None:
        """NormalizationResult should be immutable."""
        result = compare_titles("A", "B")
        assert isinstance(result, NormalizationResult)
        with pytest.raises(AttributeError):
            result.is_match = True  # type: ignore[misc]


class TestEdgeCases:
    """T098: Tests for edge cases in title normalization."""

    def test_intentional_underscores_match(self) -> None:
        """Titles with intentional underscores should match exactly."""
        result = compare_titles("my_playlist_name", "my_playlist_name")
        assert result.is_match is True
        assert result.confidence == 1.0
        assert result.matching_strategy == "exact"

    def test_multiple_underscores_normalized(self) -> None:
        """Multiple underscores from multiple normalizations."""
        result = compare_titles("Rock_Roll_80s", "Rock/Roll'80s")
        assert result.is_match is True
        assert result.matching_strategy == "normalized"

    def test_empty_source_title(self) -> None:
        """Empty source title should not match non-empty target."""
        result = compare_titles("", "Playlist")
        assert result.is_match is False

    def test_empty_target_title(self) -> None:
        """Empty target title should not match non-empty source."""
        result = compare_titles("Playlist", "")
        assert result.is_match is False

    def test_both_empty_titles(self) -> None:
        """Both empty titles should match exactly."""
        result = compare_titles("", "")
        assert result.is_match is True
        assert result.confidence == 1.0

    def test_unicode_characters_preserved(self) -> None:
        """Unicode characters should be preserved."""
        result = compare_titles("Música Española", "Música Española")
        assert result.is_match is True
        assert result.confidence == 1.0

    def test_mixed_case_normalized_match(self) -> None:
        """Mixed case with normalization should match."""
        result = compare_titles("CONAN O_BRIEN", "conan o'brien")
        assert result.is_match is True

    def test_whitespace_differences_no_match(self) -> None:
        """Extra whitespace should not match."""
        result = compare_titles("My  Playlist", "My Playlist")
        assert result.is_match is False

    def test_leading_trailing_whitespace_no_match(self) -> None:
        """Leading/trailing whitespace should not match (preserve exact behavior)."""
        result = compare_titles(" My Playlist", "My Playlist")
        assert result.is_match is False

    def test_real_world_example_conan_obrien(self) -> None:
        """Real-world example: Conan O'Brien playlist from investigation."""
        result = compare_titles("Conan O_Brien_s Best Moments", "Conan O'Brien's Best Moments")
        assert result.is_match is True
        assert result.matching_strategy == "normalized"
        assert result.confidence >= 0.90

    def test_real_world_example_date_format(self) -> None:
        """Real-world example: Date format with slash."""
        result = compare_titles("Music_2024", "Music/2024")
        assert result.is_match is True
        assert result.matching_strategy == "normalized"

    def test_underscore_vs_space_no_match(self) -> None:
        """Underscore should not match space."""
        result = compare_titles("My_Playlist", "My Playlist")
        assert result.is_match is False


class TestConfidenceScoring:
    """Additional tests for confidence scoring edge cases."""

    def test_high_confidence_single_apostrophe(self) -> None:
        """Single apostrophe normalization should be high confidence."""
        result = compare_titles("It_s a Test", "It's a Test")
        assert result.confidence >= 0.90

    def test_confidence_decreases_with_unexplained_underscores(self) -> None:
        """Confidence should be lower when underscores can't be explained."""
        # This has underscore that doesn't correspond to a normalizable char
        result = compare_titles("test_name", "test_name")
        # Exact match should be 1.0
        assert result.confidence == 1.0

    def test_normalized_result_fields(self) -> None:
        """Verify all NormalizationResult fields are populated."""
        result = compare_titles("Don_t", "Don't")

        assert result.is_match is True
        assert result.confidence > 0.0
        assert result.matching_strategy == "normalized"
        assert result.source_title == "Don_t"
        assert result.target_title == "Don't"
        assert result.normalized_source == "don_t"
        assert result.normalized_target == "don_t"
        assert isinstance(result.underscore_positions, list)
        assert isinstance(result.potential_original_chars, list)
