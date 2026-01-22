"""
Tests for chronovista enums.

Comprehensive test coverage for enum types used across the application,
ensuring proper value validation and serialization.
"""

from __future__ import annotations

import pytest

from chronovista.models.enums import (
    DownloadReason,
    LanguageCode,
    LanguagePreferenceType,
    PlaylistType,
    PrivacyStatus,
    TopicType,
    TrackKind,
    TranscriptType,
)


class TestLanguagePreferenceType:
    """Tests for LanguagePreferenceType enum."""

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert LanguagePreferenceType.FLUENT.value == "fluent"
        assert LanguagePreferenceType.LEARNING.value == "learning"
        assert LanguagePreferenceType.CURIOUS.value == "curious"
        assert LanguagePreferenceType.EXCLUDE.value == "exclude"

    def test_enum_string_representation(self) -> None:
        """Test that enum values serialize to expected strings."""
        assert str(LanguagePreferenceType.FLUENT.value) == "fluent"
        assert str(LanguagePreferenceType.LEARNING.value) == "learning"
        assert str(LanguagePreferenceType.CURIOUS.value) == "curious"
        assert str(LanguagePreferenceType.EXCLUDE.value) == "exclude"

    def test_enum_is_str_subclass(self) -> None:
        """Test that enum values are string instances."""
        assert isinstance(LanguagePreferenceType.FLUENT.value, str)
        assert isinstance(LanguagePreferenceType.LEARNING.value, str)
        assert isinstance(LanguagePreferenceType.CURIOUS.value, str)
        assert isinstance(LanguagePreferenceType.EXCLUDE.value, str)


class TestTranscriptType:
    """Tests for TranscriptType enum."""

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert TranscriptType.AUTO.value == "auto"
        assert TranscriptType.MANUAL.value == "manual"
        assert TranscriptType.TRANSLATED.value == "translated"

    def test_enum_string_representation(self) -> None:
        """Test that enum values serialize to expected strings."""
        assert str(TranscriptType.AUTO.value) == "auto"
        assert str(TranscriptType.MANUAL.value) == "manual"
        assert str(TranscriptType.TRANSLATED.value) == "translated"


class TestDownloadReason:
    """Tests for DownloadReason enum."""

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert DownloadReason.USER_REQUEST.value == "user_request"
        assert DownloadReason.AUTO_PREFERRED.value == "auto_preferred"
        assert DownloadReason.LEARNING_LANGUAGE.value == "learning_language"
        assert DownloadReason.API_ENRICHMENT.value == "api_enrichment"
        assert DownloadReason.SCHEMA_VALIDATION.value == "schema_validation"

    def test_enum_string_representation(self) -> None:
        """Test that enum values serialize to expected strings."""
        assert str(DownloadReason.USER_REQUEST.value) == "user_request"
        assert str(DownloadReason.AUTO_PREFERRED.value) == "auto_preferred"
        assert str(DownloadReason.LEARNING_LANGUAGE.value) == "learning_language"
        assert str(DownloadReason.API_ENRICHMENT.value) == "api_enrichment"
        assert str(DownloadReason.SCHEMA_VALIDATION.value) == "schema_validation"


class TestTrackKind:
    """Tests for TrackKind enum."""

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert TrackKind.STANDARD.value == "standard"
        assert TrackKind.ASR.value == "asr"
        assert TrackKind.FORCED.value == "forced"

    def test_enum_string_representation(self) -> None:
        """Test that enum values serialize to expected strings."""
        assert str(TrackKind.STANDARD.value) == "standard"
        assert str(TrackKind.ASR.value) == "asr"
        assert str(TrackKind.FORCED.value) == "forced"


class TestPrivacyStatus:
    """Tests for PrivacyStatus enum."""

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert PrivacyStatus.PRIVATE.value == "private"
        assert PrivacyStatus.PUBLIC.value == "public"
        assert PrivacyStatus.UNLISTED.value == "unlisted"

    def test_enum_string_representation(self) -> None:
        """Test that enum values serialize to expected strings."""
        assert str(PrivacyStatus.PRIVATE.value) == "private"
        assert str(PrivacyStatus.PUBLIC.value) == "public"
        assert str(PrivacyStatus.UNLISTED.value) == "unlisted"


class TestTopicType:
    """Tests for TopicType enum."""

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert TopicType.YOUTUBE.value == "youtube"
        assert TopicType.CUSTOM.value == "custom"

    def test_enum_string_representation(self) -> None:
        """Test that enum values serialize to expected strings."""
        assert str(TopicType.YOUTUBE.value) == "youtube"
        assert str(TopicType.CUSTOM.value) == "custom"


class TestPlaylistType:
    """
    Tests for PlaylistType enum (T079).

    PlaylistType distinguishes between regular user-created playlists and
    special system playlists with unique API behavior.
    """

    def test_enum_values_exist(self) -> None:
        """Test that all expected enum values exist."""
        assert PlaylistType.REGULAR.value == "regular"
        assert PlaylistType.LIKED.value == "liked"
        assert PlaylistType.WATCH_LATER.value == "watch_later"
        assert PlaylistType.HISTORY.value == "history"
        assert PlaylistType.FAVORITES.value == "favorites"

    def test_enum_string_representation(self) -> None:
        """Test that enum values serialize to expected strings."""
        assert str(PlaylistType.REGULAR.value) == "regular"
        assert str(PlaylistType.LIKED.value) == "liked"
        assert str(PlaylistType.WATCH_LATER.value) == "watch_later"
        assert str(PlaylistType.HISTORY.value) == "history"
        assert str(PlaylistType.FAVORITES.value) == "favorites"

    def test_enum_is_str_subclass(self) -> None:
        """Test that enum values are string instances."""
        assert isinstance(PlaylistType.REGULAR.value, str)
        assert isinstance(PlaylistType.LIKED.value, str)
        assert isinstance(PlaylistType.WATCH_LATER.value, str)
        assert isinstance(PlaylistType.HISTORY.value, str)
        assert isinstance(PlaylistType.FAVORITES.value, str)

    def test_system_playlist_types(self) -> None:
        """Test system playlist type values match API prefixes."""
        # LIKED corresponds to LL prefix
        assert PlaylistType.LIKED.value == "liked"
        # WATCH_LATER corresponds to WL prefix
        assert PlaylistType.WATCH_LATER.value == "watch_later"
        # HISTORY corresponds to HL prefix
        assert PlaylistType.HISTORY.value == "history"

    def test_regular_playlist_type(self) -> None:
        """Test regular playlist type for user-created playlists."""
        assert PlaylistType.REGULAR.value == "regular"

    def test_favorites_playlist_type(self) -> None:
        """Test favorites playlist type for legacy playlists."""
        assert PlaylistType.FAVORITES.value == "favorites"

    def test_all_values_unique(self) -> None:
        """Test that all enum values are unique."""
        values = [member.value for member in PlaylistType]
        assert len(values) == len(set(values))
        assert len(values) == 5


class TestLanguageCode:
    """Tests for LanguageCode enum."""

    def test_major_language_codes_exist(self) -> None:
        """Test that major language codes exist."""
        # English variants
        assert LanguageCode.ENGLISH.value == "en"
        assert LanguageCode.ENGLISH_US.value == "en-US"
        assert LanguageCode.ENGLISH_GB.value == "en-GB"

        # Spanish variants
        assert LanguageCode.SPANISH.value == "es"
        assert LanguageCode.SPANISH_ES.value == "es-ES"
        assert LanguageCode.SPANISH_MX.value == "es-MX"

        # Other major languages
        assert LanguageCode.FRENCH.value == "fr"
        assert LanguageCode.GERMAN.value == "de"
        assert LanguageCode.JAPANESE.value == "ja"
        assert LanguageCode.CHINESE_SIMPLIFIED.value == "zh-CN"

    def test_get_base_language(self) -> None:
        """Test get_base_language class method."""
        assert LanguageCode.get_base_language("en-US") == "en"
        assert LanguageCode.get_base_language("es-MX") == "es"
        assert LanguageCode.get_base_language("zh-CN") == "zh"
        assert LanguageCode.get_base_language("en") == "en"  # Already base

    def test_get_common_variants(self) -> None:
        """Test get_common_variants class method."""
        en_variants = LanguageCode.get_common_variants("en")
        assert "en" in en_variants
        assert "en-US" in en_variants
        assert "en-GB" in en_variants

        es_variants = LanguageCode.get_common_variants("es")
        assert "es" in es_variants
        assert "es-ES" in es_variants
        assert "es-MX" in es_variants

    def test_unknown_language_returns_base(self) -> None:
        """Test that unknown language returns base code."""
        variants = LanguageCode.get_common_variants("unknown")
        assert variants == ["unknown"]


class TestEnumComparison:
    """Tests for enum comparison and equality."""

    def test_enum_equality(self) -> None:
        """Test that enum values can be compared for equality."""
        assert PlaylistType.REGULAR == PlaylistType.REGULAR
        assert PlaylistType.LIKED != PlaylistType.WATCH_LATER  # type: ignore[comparison-overlap]
        assert PrivacyStatus.PUBLIC == PrivacyStatus.PUBLIC
        assert PrivacyStatus.PRIVATE != PrivacyStatus.UNLISTED  # type: ignore[comparison-overlap]

    def test_enum_value_equality(self) -> None:
        """Test that enum values can be compared to strings."""
        assert PlaylistType.REGULAR.value == "regular"
        assert PlaylistType.LIKED.value == "liked"
        assert PrivacyStatus.PUBLIC.value == "public"
        assert PrivacyStatus.PRIVATE.value == "private"

    def test_enum_membership(self) -> None:
        """Test that enum values can be checked for membership."""
        playlist_types = [PlaylistType.REGULAR, PlaylistType.LIKED]
        assert PlaylistType.REGULAR in playlist_types
        assert PlaylistType.WATCH_LATER not in playlist_types

        privacy_statuses = [PrivacyStatus.PUBLIC, PrivacyStatus.PRIVATE]
        assert PrivacyStatus.PUBLIC in privacy_statuses
        assert PrivacyStatus.UNLISTED not in privacy_statuses
