"""
Tests for Recovery Models.

Unit tests for Pydantic models in src/chronovista/models/takeout/recovery.py
Covers HistoricalTakeout, RecoveredVideoMetadata, RecoveredChannelMetadata,
RecoveryCandidate, VideoRecoveryAction, ChannelRecoveryAction, RecoveryResult,
RecoveryOptions, and helper functions.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from chronovista.models.takeout.recovery import (
    CHANNEL_PLACEHOLDER_PREFIX,
    UNKNOWN_CHANNEL_PREFIX,
    VIDEO_PLACEHOLDER_PREFIX,
    ChannelRecoveryAction,
    HistoricalTakeout,
    RecoveredChannelMetadata,
    RecoveredVideoMetadata,
    RecoveryCandidate,
    RecoveryOptions,
    RecoveryResult,
    VideoRecoveryAction,
    extract_video_id_from_placeholder,
    is_placeholder_channel_name,
    is_placeholder_video_title,
)


class TestHistoricalTakeout:
    """Tests for HistoricalTakeout model."""

    def test_create_basic_takeout(self) -> None:
        """Test creating a basic HistoricalTakeout."""
        takeout = HistoricalTakeout(
            path=Path("/takeouts/2024-01-15"),
            export_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        assert takeout.path == Path("/takeouts/2024-01-15")
        assert takeout.export_date.year == 2024
        assert takeout.has_watch_history is False
        assert takeout.has_playlists is False
        assert takeout.has_subscriptions is False

    def test_create_takeout_with_all_features(self) -> None:
        """Test creating a HistoricalTakeout with all data types available."""
        takeout = HistoricalTakeout(
            path=Path("/takeouts/full-export"),
            export_date=datetime(2023, 6, 1, tzinfo=timezone.utc),
            has_watch_history=True,
            has_playlists=True,
            has_subscriptions=True,
        )
        assert takeout.has_watch_history is True
        assert takeout.has_playlists is True
        assert takeout.has_subscriptions is True

    def test_takeout_with_partial_data(self) -> None:
        """Test creating a HistoricalTakeout with only watch history."""
        takeout = HistoricalTakeout(
            path=Path("/takeouts/partial"),
            export_date=datetime(2022, 12, 25, tzinfo=timezone.utc),
            has_watch_history=True,
            has_playlists=False,
            has_subscriptions=False,
        )
        assert takeout.has_watch_history is True
        assert takeout.has_playlists is False


class TestRecoveredVideoMetadata:
    """Tests for RecoveredVideoMetadata model."""

    def test_create_video_metadata(self) -> None:
        """Test creating RecoveredVideoMetadata."""
        metadata = RecoveredVideoMetadata(
            video_id="dQw4w9WgXcQ",
            title="Never Gonna Give You Up",
            channel_name="RickAstleyVEVO",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            channel_url="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            watched_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            source_takeout=Path("/takeouts/2024-01-15"),
            source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        assert metadata.video_id == "dQw4w9WgXcQ"
        assert metadata.title == "Never Gonna Give You Up"
        assert metadata.channel_name == "RickAstleyVEVO"

    def test_video_metadata_minimal(self) -> None:
        """Test creating RecoveredVideoMetadata with minimal data."""
        metadata = RecoveredVideoMetadata(
            video_id="abc123XYZ_-",
            title="Some Video Title",
            source_takeout=Path("/takeouts/2023-06-01"),
            source_date=datetime(2023, 6, 1, tzinfo=timezone.utc),
        )
        assert metadata.video_id == "abc123XYZ_-"
        assert metadata.channel_name is None
        assert metadata.channel_id is None
        assert metadata.watched_at is None


class TestRecoveredChannelMetadata:
    """Tests for RecoveredChannelMetadata model."""

    def test_create_channel_metadata(self) -> None:
        """Test creating RecoveredChannelMetadata."""
        metadata = RecoveredChannelMetadata(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            channel_name="RickAstleyVEVO",
            channel_url="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            source_takeout=Path("/takeouts/2024-01-15"),
            source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            video_count=42,
        )
        assert metadata.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert metadata.channel_name == "RickAstleyVEVO"
        assert metadata.video_count == 42

    def test_channel_metadata_default_video_count(self) -> None:
        """Test that video_count defaults to 0."""
        metadata = RecoveredChannelMetadata(
            channel_id="UCtest123",
            channel_name="Test Channel",
            source_takeout=Path("/takeouts/test"),
            source_date=datetime.now(timezone.utc),
        )
        assert metadata.video_count == 0


class TestRecoveryCandidate:
    """Tests for RecoveryCandidate model."""

    def test_create_placeholder_candidate(self) -> None:
        """Test creating a recovery candidate for a placeholder video."""
        candidate = RecoveryCandidate(
            video_id="dQw4w9WgXcQ",
            current_title="[Placeholder] Video dQw4w9WgXcQ",
            is_placeholder=True,
            channel_id="UCtest123",
            channel_is_placeholder=False,
        )
        assert candidate.is_placeholder is True
        assert candidate.channel_is_placeholder is False

    def test_create_non_placeholder_candidate(self) -> None:
        """Test creating a recovery candidate for a real video."""
        candidate = RecoveryCandidate(
            video_id="xyz789ABC",
            current_title="Real Video Title",
            is_placeholder=False,
        )
        assert candidate.is_placeholder is False
        assert candidate.channel_id is None


class TestVideoRecoveryAction:
    """Tests for VideoRecoveryAction model."""

    def test_create_title_update_action(self) -> None:
        """Test creating a title update action."""
        action = VideoRecoveryAction(
            video_id="dQw4w9WgXcQ",
            old_title="[Placeholder] Video dQw4w9WgXcQ",
            new_title="Never Gonna Give You Up",
            source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            action_type="update_title",
        )
        assert action.action_type == "update_title"
        assert action.old_channel_id is None
        assert action.new_channel_id is None

    def test_create_both_update_action(self) -> None:
        """Test creating an action that updates both title and channel."""
        action = VideoRecoveryAction(
            video_id="dQw4w9WgXcQ",
            old_title="[Placeholder] Video dQw4w9WgXcQ",
            new_title="Never Gonna Give You Up",
            old_channel_id="UCplaceholder",
            new_channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            channel_name="RickAstleyVEVO",
            source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            action_type="both",
        )
        assert action.action_type == "both"
        assert action.old_channel_id == "UCplaceholder"
        assert action.new_channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"


class TestChannelRecoveryAction:
    """Tests for ChannelRecoveryAction model."""

    def test_create_channel_action(self) -> None:
        """Test creating a channel create action."""
        action = ChannelRecoveryAction(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            channel_name="RickAstleyVEVO",
            channel_url="https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            action_type="create",
            source_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        assert action.action_type == "create"

    def test_create_channel_update_action(self) -> None:
        """Test creating a channel update action."""
        action = ChannelRecoveryAction(
            channel_id="UCtest123",
            channel_name="Updated Channel Name",
            action_type="update_name",
            source_date=datetime.now(timezone.utc),
        )
        assert action.action_type == "update_name"


class TestRecoveryResult:
    """Tests for RecoveryResult model."""

    def test_create_empty_result(self) -> None:
        """Test creating an empty recovery result."""
        result = RecoveryResult()
        assert result.videos_recovered == 0
        assert result.videos_still_missing == 0
        assert result.channels_created == 0
        assert result.channels_updated == 0
        assert result.takeouts_scanned == 0
        assert result.dry_run is False
        assert len(result.video_actions) == 0
        assert len(result.channel_actions) == 0
        assert len(result.errors) == 0

    def test_create_dry_run_result(self) -> None:
        """Test creating a dry run result."""
        result = RecoveryResult(dry_run=True)
        assert result.dry_run is True

    def test_mark_complete(self) -> None:
        """Test marking a result as complete."""
        result = RecoveryResult()
        assert result.completed_at is None
        result.mark_complete()
        assert result.completed_at is not None

    def test_add_error(self) -> None:
        """Test adding errors to result."""
        result = RecoveryResult()
        result.add_error("First error")
        result.add_error("Second error")
        assert len(result.errors) == 2
        assert "First error" in result.errors
        assert "Second error" in result.errors

    def test_result_with_actions(self) -> None:
        """Test result with video and channel actions."""
        video_action = VideoRecoveryAction(
            video_id="dQw4w9WgXcQ",
            old_title="[Placeholder] Video dQw4w9WgXcQ",
            new_title="Never Gonna Give You Up",
            source_date=datetime.now(timezone.utc),
        )
        channel_action = ChannelRecoveryAction(
            channel_id="UCtest123",
            channel_name="Test Channel",
            source_date=datetime.now(timezone.utc),
        )
        result = RecoveryResult(
            videos_recovered=1,
            channels_created=1,
            video_actions=[video_action],
            channel_actions=[channel_action],
        )
        assert len(result.video_actions) == 1
        assert len(result.channel_actions) == 1


class TestRecoveryOptions:
    """Tests for RecoveryOptions model."""

    def test_default_options(self) -> None:
        """Test default recovery options."""
        options = RecoveryOptions()
        assert options.dry_run is False
        assert options.verbose is False
        assert options.process_oldest_first is False
        assert options.update_channels is True
        assert options.batch_size == 100

    def test_custom_options(self) -> None:
        """Test custom recovery options."""
        options = RecoveryOptions(
            dry_run=True,
            verbose=True,
            process_oldest_first=True,
            update_channels=False,
            batch_size=50,
        )
        assert options.dry_run is True
        assert options.verbose is True
        assert options.process_oldest_first is True
        assert options.update_channels is False
        assert options.batch_size == 50


class TestPlaceholderDetection:
    """Tests for placeholder detection helper functions."""

    def test_is_placeholder_video_title_true(self) -> None:
        """Test detecting placeholder video titles."""
        assert is_placeholder_video_title("[Placeholder] Video dQw4w9WgXcQ") is True
        assert is_placeholder_video_title("[Placeholder] Video abc123XYZ_-") is True

    def test_is_placeholder_video_title_false(self) -> None:
        """Test detecting non-placeholder video titles."""
        assert is_placeholder_video_title("Never Gonna Give You Up") is False
        assert is_placeholder_video_title("Some Random Video Title") is False
        assert is_placeholder_video_title("[Other] Video Title") is False

    def test_is_placeholder_video_title_edge_cases(self) -> None:
        """Test edge cases for video placeholder detection."""
        assert is_placeholder_video_title("") is False
        assert is_placeholder_video_title("[Placeholder]") is False  # No " Video " prefix
        assert is_placeholder_video_title("Placeholder Video abc") is False  # Missing brackets

    def test_is_placeholder_channel_name_true(self) -> None:
        """Test detecting placeholder channel names."""
        assert is_placeholder_channel_name("[Placeholder] Unknown Channel") is True
        assert is_placeholder_channel_name("[Unknown Channel] UCtest123") is True
        assert is_placeholder_channel_name("[Placeholder] Channel Name") is True

    def test_is_placeholder_channel_name_false(self) -> None:
        """Test detecting non-placeholder channel names."""
        assert is_placeholder_channel_name("RickAstleyVEVO") is False
        assert is_placeholder_channel_name("My Cool Channel") is False
        assert is_placeholder_channel_name("") is False

    def test_extract_video_id_from_placeholder(self) -> None:
        """Test extracting video ID from placeholder title."""
        assert extract_video_id_from_placeholder("[Placeholder] Video dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert extract_video_id_from_placeholder("[Placeholder] Video abc123XYZ_-") == "abc123XYZ_-"

    def test_extract_video_id_not_placeholder(self) -> None:
        """Test that extract returns None for non-placeholder titles."""
        assert extract_video_id_from_placeholder("Never Gonna Give You Up") is None
        assert extract_video_id_from_placeholder("") is None
        assert extract_video_id_from_placeholder("[Other] Video abc") is None


class TestConstants:
    """Tests for module constants."""

    def test_video_placeholder_prefix(self) -> None:
        """Test VIDEO_PLACEHOLDER_PREFIX constant."""
        assert VIDEO_PLACEHOLDER_PREFIX == "[Placeholder] Video "

    def test_channel_placeholder_prefix(self) -> None:
        """Test CHANNEL_PLACEHOLDER_PREFIX constant."""
        assert CHANNEL_PLACEHOLDER_PREFIX == "[Placeholder]"

    def test_unknown_channel_prefix(self) -> None:
        """Test UNKNOWN_CHANNEL_PREFIX constant."""
        assert UNKNOWN_CHANNEL_PREFIX == "[Unknown"
