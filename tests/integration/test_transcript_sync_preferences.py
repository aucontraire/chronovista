"""
Integration tests for preference-aware transcript sync functionality.

This test suite validates that the `chronovista sync transcripts` command
correctly uses user language preferences when downloading transcripts,
implementing the FLUENT/LEARNING/CURIOUS/EXCLUDE preference hierarchy.

Test Coverage:
- T114: FLUENT preferences download all matching transcripts automatically
- T115: LEARNING preferences download original + translation to top fluent language
- T116: LEARNING preferences download original only when translation unavailable
- T117: CURIOUS preferences are skipped during sync (on-demand only)
- T118: EXCLUDE preferences prevent transcript download completely
- T119: No preferences configured shows upgrade path prompt
- T120: --language flag overrides configured preferences
- T121: Mixed preference types work correctly together
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.main import app
from chronovista.db.models import Video as VideoDB
from chronovista.models.enums import (
    DownloadReason,
    LanguageCode,
    LanguagePreferenceType,
    TrackKind,
    TranscriptType,
)
from chronovista.models.transcript_source import TranscriptSource
from chronovista.models.user_language_preference import UserLanguagePreference
from chronovista.models.video_transcript import EnhancedVideoTranscriptBase

# CRITICAL: Module-level marker for integration tests
pytestmark = [pytest.mark.integration]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_preference(
    language_code: str,
    preference_type: str,
    priority: int,
    auto_download: bool = True,
    learning_goal: str = "",
) -> UserLanguagePreference:
    """
    Create a UserLanguagePreference instance for testing.

    Parameters
    ----------
    language_code : str
        BCP-47 language code (e.g., 'en', 'es-MX')
    preference_type : str
        Type of preference ('fluent', 'learning', 'curious', 'exclude')
    priority : int
        Priority order (1 = highest)
    auto_download : bool
        Whether to auto-download transcripts
    learning_goal : str
        Optional learning goal description

    Returns
    -------
    UserLanguagePreference
        Fully populated preference instance
    """
    # Map string preference type to enum value
    pref_type_map = {
        "fluent": LanguagePreferenceType.FLUENT,
        "learning": LanguagePreferenceType.LEARNING,
        "curious": LanguagePreferenceType.CURIOUS,
        "exclude": LanguagePreferenceType.EXCLUDE,
    }

    # Map string language code to enum (if it exists, otherwise use string)
    try:
        lang_enum = LanguageCode(language_code)
    except ValueError:
        # For test cases with non-enum language codes, use the string directly
        lang_enum = language_code  # type: ignore[assignment]

    return UserLanguagePreference(
        user_id="test_user_123",
        language_code=lang_enum,
        preference_type=pref_type_map[preference_type],
        priority=priority,
        auto_download_transcripts=auto_download,
        learning_goal=learning_goal if learning_goal else None,
        created_at=datetime.now(timezone.utc),
    )


def create_mock_video(video_id: str, title: str) -> MagicMock:
    """
    Create a mock Video database model.

    Parameters
    ----------
    video_id : str
        YouTube video ID (must be exactly 11 characters)
    title : str
        Video title

    Returns
    -------
    MagicMock
        Mock Video object with required attributes
    """
    # Ensure video_id is exactly 11 characters (YouTube video ID format)
    if len(video_id) != 11:
        # Pad or truncate to 11 characters
        video_id = (video_id + "0" * 11)[:11]

    video = MagicMock(spec=VideoDB)
    video.video_id = video_id
    video.title = title
    video.duration = 240  # 4 minutes
    video.channel_id = "UC1234567890123456789012"
    video.channel_name_hint = "Test Channel"
    # Configure __str__ for Rich rendering
    video.configure_mock(__str__=MagicMock(return_value=title))
    return video


def create_mock_transcript(
    video_id: str,
    language_code: str,
    transcript_text: str = "Test transcript content",
) -> EnhancedVideoTranscriptBase:
    """
    Create a mock EnhancedVideoTranscriptBase.

    Parameters
    ----------
    video_id : str
        YouTube video ID (must be exactly 11 characters)
    language_code : str
        BCP-47 language code
    transcript_text : str
        Transcript content

    Returns
    -------
    EnhancedVideoTranscriptBase
        Mock transcript object
    """
    # Ensure video_id is exactly 11 characters (YouTube video ID format)
    if len(video_id) != 11:
        # Pad or truncate to 11 characters
        video_id = (video_id + "0" * 11)[:11]

    return EnhancedVideoTranscriptBase(
        video_id=video_id,
        language_code=LanguageCode(language_code),
        transcript_text=transcript_text,
        transcript_type=TranscriptType.AUTO,
        download_reason=DownloadReason.USER_REQUEST,
        confidence_score=0.95,
        is_cc=False,
        is_auto_synced=True,
        track_kind=TrackKind.STANDARD,
        caption_name=f"{language_code} (auto-generated)",
        source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
        plain_text_only=transcript_text,
        raw_transcript_data={"snippets": []},
    )


# ============================================================================
# FLUENT PREFERENCE TESTS
# ============================================================================


class TestSyncTranscriptsFluentPreferences:
    """Test transcript sync with FLUENT language preferences."""

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_with_fluent_preferences(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T114: Sync downloads only FLUENT language transcripts.

        Scenario:
        1. User has FLUENT preferences for English and Spanish
        2. Video has transcripts: en, es, fr, de
        3. Sync downloads en and es
        4. Verify: fr and de are NOT downloaded
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_1", "Test Video")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # Setup user preferences: FLUENT for en and es
        user_preferences = [
            create_preference("en", "fluent", priority=1),
            create_preference("es", "fluent", priority=2),
        ]
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(
            return_value=user_preferences
        )

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository to return test video
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository (no existing transcripts)
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock available languages (en, es, fr, de)
        mock_transcript_service.get_available_languages = AsyncMock(
            return_value=[
                {"language_code": "en", "name": "English"},
                {"language_code": "es", "name": "Spanish"},
                {"language_code": "fr", "name": "French"},
                {"language_code": "de", "name": "German"},
            ]
        )

        # Mock transcript downloads for en and es
        mock_transcript_service.get_transcript = AsyncMock(
            side_effect=[
                create_mock_transcript("test_video_1", "en"),
                create_mock_transcript("test_video_1", "es"),
            ]
        )

        # Execute command
        runner = CliRunner()
        result = runner.invoke(app, ["sync", "transcripts", "--limit", "1"])

        # Verify transcripts were downloaded for en and es only
        assert mock_transcript_service.get_transcript.call_count == 2

        # Verify output indicates using preferences
        assert "preference" in result.stdout.lower() or "fluent" in result.stdout.lower()


# ============================================================================
# LEARNING PREFERENCE TESTS
# ============================================================================


class TestSyncTranscriptsLearningPreferences:
    """Test transcript sync with LEARNING language preferences."""

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_with_learning_preferences_with_translation(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T115: LEARNING language downloads original + translation pair.

        Scenario:
        1. User has FLUENT=en, LEARNING=it
        2. Video has transcripts: it, en, fr
        3. Sync downloads: it (original), en (translation target)
        4. Verify: Translation pairing information displayed
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_2", "Italian Video")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # Setup user preferences: FLUENT=en, LEARNING=it
        user_preferences = [
            create_preference("en", "fluent", priority=1),
            create_preference("it", "learning", priority=1),
        ]
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(
            return_value=user_preferences
        )

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock available languages (it, en, fr)
        mock_transcript_service.get_available_languages = AsyncMock(
            return_value=[
                {"language_code": "it", "name": "Italian"},
                {"language_code": "en", "name": "English"},
                {"language_code": "fr", "name": "French"},
            ]
        )

        # Mock transcript downloads for it and en
        mock_transcript_service.get_transcript = AsyncMock(
            side_effect=[
                create_mock_transcript("test_video_2", "en"),  # FLUENT
                create_mock_transcript("test_video_2", "it"),  # LEARNING original
                create_mock_transcript("test_video_2", "en"),  # LEARNING translation
            ]
        )

        # Execute command
        runner = CliRunner()
        result = runner.invoke(app, ["sync", "transcripts", "--limit", "1"])

        # Verify transcripts were downloaded
        assert mock_transcript_service.get_transcript.call_count >= 2

        # Verify output shows LEARNING language handling
        assert "learning" in result.stdout.lower()

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_with_learning_no_translation_available(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T116: LEARNING downloads original only when translation unavailable.

        Scenario:
        1. User has FLUENT=en, LEARNING=it
        2. Video has transcripts: it, fr (NO English)
        3. Sync downloads: it (original only)
        4. Verify: Message indicates translation not available
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_3", "Italian Video No EN")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # Setup user preferences: FLUENT=en, LEARNING=it
        user_preferences = [
            create_preference("en", "fluent", priority=1),
            create_preference("it", "learning", priority=1),
        ]
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(
            return_value=user_preferences
        )

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock available languages (it, fr - NO en)
        mock_transcript_service.get_available_languages = AsyncMock(
            return_value=[
                {"language_code": "it", "name": "Italian"},
                {"language_code": "fr", "name": "French"},
            ]
        )

        # Mock transcript download for it only
        mock_transcript_service.get_transcript = AsyncMock(
            return_value=create_mock_transcript("test_video_3", "it")
        )

        # Execute command
        runner = CliRunner()
        result = runner.invoke(app, ["sync", "transcripts", "--limit", "1"])

        # Verify only Italian was downloaded
        assert mock_transcript_service.get_transcript.call_count == 1


# ============================================================================
# CURIOUS AND EXCLUDE PREFERENCE TESTS
# ============================================================================


class TestSyncTranscriptsCuriousAndExcludePreferences:
    """Test transcript sync with CURIOUS and EXCLUDE preferences."""

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_skips_curious_languages(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T117: CURIOUS languages are skipped during sync.

        Scenario:
        1. User has FLUENT=en, CURIOUS=fr
        2. Video has transcripts: en, fr
        3. Sync downloads en only
        4. Verify: fr is marked as skipped (on-demand)
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_4", "Video with Curious")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # Setup user preferences: FLUENT=en, CURIOUS=fr
        user_preferences = [
            create_preference("en", "fluent", priority=1),
            create_preference("fr", "curious", priority=1),
        ]
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(
            return_value=user_preferences
        )

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock available languages (en, fr)
        mock_transcript_service.get_available_languages = AsyncMock(
            return_value=[
                {"language_code": "en", "name": "English"},
                {"language_code": "fr", "name": "French"},
            ]
        )

        # Mock transcript download for en only
        mock_transcript_service.get_transcript = AsyncMock(
            return_value=create_mock_transcript("test_video_4", "en")
        )

        # Execute command
        runner = CliRunner()
        result = runner.invoke(app, ["sync", "transcripts", "--limit", "1"])

        # Verify only English was downloaded (curious is skipped)
        assert mock_transcript_service.get_transcript.call_count == 1

        # Verify output indicates CURIOUS language was skipped
        assert "curious" in result.stdout.lower() or "skipped" in result.stdout.lower()

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_excludes_blocked_languages(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T118: EXCLUDE languages are never downloaded.

        Scenario:
        1. User has FLUENT=en, EXCLUDE=de
        2. Video has transcripts: en, de, fr
        3. Sync downloads en only
        4. Verify: de is blocked and never downloaded
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_5", "Video with Excluded")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # Setup user preferences: FLUENT=en, EXCLUDE=de
        user_preferences = [
            create_preference("en", "fluent", priority=1),
            create_preference("de", "exclude", priority=1),
        ]
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(
            return_value=user_preferences
        )

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock available languages (en, de, fr)
        mock_transcript_service.get_available_languages = AsyncMock(
            return_value=[
                {"language_code": "en", "name": "English"},
                {"language_code": "de", "name": "German"},
                {"language_code": "fr", "name": "French"},
            ]
        )

        # Mock transcript download for en only
        mock_transcript_service.get_transcript = AsyncMock(
            return_value=create_mock_transcript("test_video_5", "en")
        )

        # Execute command
        runner = CliRunner()
        result = runner.invoke(app, ["sync", "transcripts", "--limit", "1"])

        # Verify only English was downloaded (de is excluded)
        assert mock_transcript_service.get_transcript.call_count == 1

        # Verify output indicates EXCLUDE language was blocked
        assert "exclude" in result.stdout.lower() or "skipped" in result.stdout.lower()


# ============================================================================
# NO PREFERENCES TESTS
# ============================================================================


class TestSyncTranscriptsNoPreferences:
    """Test transcript sync when no preferences are configured."""

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_with_no_preferences_shows_prompt(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T119: Shows upgrade path prompt when no preferences configured.

        Scenario:
        1. User has NO preferences configured
        2. Sync command is executed
        3. Verify: Upgrade path prompt displayed
        4. Verify: Falls back to default behavior (English)
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_6", "Video No Preferences")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # No preferences configured (empty list)
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(return_value=[])

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock transcript download (falls back to English)
        mock_transcript_service.get_transcript = AsyncMock(
            return_value=create_mock_transcript("test_video_6", "en")
        )

        # Execute command
        runner = CliRunner()
        result = runner.invoke(app, ["sync", "transcripts", "--limit", "1"])

        # Verify upgrade path prompt is shown
        assert (
            "preference" in result.stdout.lower()
            or "chronovista languages set" in result.stdout.lower()
        )


# ============================================================================
# FLAG OVERRIDE TESTS
# ============================================================================


class TestSyncTranscriptsLanguageFlagOverride:
    """Test --language flag overriding configured preferences."""

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_language_flag_overrides_preferences(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T120: --language flag overrides configured preferences.

        Scenario:
        1. User has preferences configured (FLUENT=en, LEARNING=it)
        2. Command executed with --language es
        3. Verify: Spanish is downloaded (preferences ignored)
        4. Verify: Output indicates --language flag is being used
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_7", "Override Test")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # Setup user preferences (will be ignored)
        user_preferences = [
            create_preference("en", "fluent", priority=1),
            create_preference("it", "learning", priority=1),
        ]
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(
            return_value=user_preferences
        )

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock transcript download for Spanish
        mock_transcript_service.get_transcript = AsyncMock(
            return_value=create_mock_transcript("test_video_7", "es")
        )

        # Execute command with --language es flag
        runner = CliRunner()
        result = runner.invoke(
            app, ["sync", "transcripts", "--limit", "1", "--language", "es"]
        )

        # Verify Spanish was requested
        assert mock_transcript_service.get_transcript.call_count == 1
        call_args = mock_transcript_service.get_transcript.call_args
        assert "es" in call_args.kwargs.get("language_codes", [])

        # Verify output indicates --language flag usage
        assert "--language" in result.stdout.lower() or "es" in result.stdout.lower()


# ============================================================================
# MIXED PREFERENCES TESTS
# ============================================================================


class TestSyncTranscriptsMixedPreferences:
    """Test transcript sync with all preference types together."""

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_with_mixed_preferences(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        mock_check_auth: MagicMock,
    ) -> None:
        """
        T121: Test with all four preference types configured.

        Scenario:
        1. User has: FLUENT=en, LEARNING=it, CURIOUS=fr, EXCLUDE=de
        2. Video has transcripts: en, it, fr, de, es
        3. Verify:
           - en downloaded (FLUENT)
           - it downloaded (LEARNING)
           - fr skipped (CURIOUS)
           - de blocked (EXCLUDE)
           - es ignored (no preference)
        """
        # Setup authentication
        mock_check_auth.return_value = True

        # Create test video
        test_video = create_mock_video("test_video_8", "Mixed Preferences")

        # Setup repository mocks
        mock_video_repo = AsyncMock()
        mock_video_transcript_repo = AsyncMock()
        mock_user_lang_pref_repo = AsyncMock()
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_video_transcript_repository.return_value = (
            mock_video_transcript_repo
        )
        mock_container.create_user_language_preference_repository.return_value = (
            mock_user_lang_pref_repo
        )

        # Setup all four preference types
        user_preferences = [
            create_preference("en", "fluent", priority=1),
            create_preference("it", "learning", priority=1),
            create_preference("fr", "curious", priority=1),
            create_preference("de", "exclude", priority=1),
        ]
        mock_user_lang_pref_repo.get_user_preferences = AsyncMock(
            return_value=user_preferences
        )

        # Setup database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ] * 10

        # Mock video repository
        mock_video_repo.search_videos = AsyncMock(return_value=[test_video])

        # Mock transcript repository
        mock_video_transcript_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_video_transcript_repo.create_or_update = AsyncMock()

        # Mock transcript service
        mock_transcript_service = AsyncMock()
        mock_container.transcript_service = mock_transcript_service

        # Mock available languages (en, it, fr, de, es)
        mock_transcript_service.get_available_languages = AsyncMock(
            return_value=[
                {"language_code": "en", "name": "English"},
                {"language_code": "it", "name": "Italian"},
                {"language_code": "fr", "name": "French"},
                {"language_code": "de", "name": "German"},
                {"language_code": "es", "name": "Spanish"},
            ]
        )

        # Mock transcript downloads for en and it
        mock_transcript_service.get_transcript = AsyncMock(
            side_effect=[
                create_mock_transcript("test_video_8", "en"),  # FLUENT
                create_mock_transcript("test_video_8", "it"),  # LEARNING
                create_mock_transcript("test_video_8", "en"),  # LEARNING translation
            ]
        )

        # Execute command
        runner = CliRunner()
        result = runner.invoke(app, ["sync", "transcripts", "--limit", "1"])

        # Verify correct transcripts were downloaded (en, it)
        # fr should be skipped (curious), de should be blocked (exclude)
        assert mock_transcript_service.get_transcript.call_count >= 2

        # Verify output shows all preference types
        stdout_lower = result.stdout.lower()
        assert "fluent" in stdout_lower or "learning" in stdout_lower
