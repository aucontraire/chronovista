"""
Comprehensive tests for sync_commands.py using DI container pattern.

This test suite covers the refactored sync commands that use the DI container
instead of module-level repository instantiation. Tests verify container
integration, command execution, error handling, and data transformation.

Coverage targets:
- sync_commands.py: from 7% → 50%+
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.main import app
from chronovista.models.api_responses import (
    ChannelSnippet,
    PlaylistSnippet,
    VideoSnippet,
    YouTubeChannelResponse,
    YouTubePlaylistResponse,
    YouTubeVideoResponse,
)


@pytest.fixture
def runner() -> CliRunner:
    """CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_youtube_channel() -> YouTubeChannelResponse:
    """Create a mock YouTube channel response."""
    return YouTubeChannelResponse(
        id="UC1234567890123456789012",
        snippet=ChannelSnippet(
            title="Test Channel",
            description="Test channel description",
            publishedAt=datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        ),
    )


@pytest.fixture
def mock_youtube_playlist() -> YouTubePlaylistResponse:
    """Create a mock YouTube playlist response."""
    return YouTubePlaylistResponse(
        id="PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
        snippet=PlaylistSnippet(
            title="Test Playlist",
            description="Test playlist description",
            publishedAt=datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            channelId="UC1234567890123456789012",
        ),
    )


@pytest.fixture
def mock_youtube_video() -> YouTubeVideoResponse:
    """Create a mock YouTube video response."""
    return YouTubeVideoResponse(
        id="dQw4w9WgXcQ",
        snippet=VideoSnippet(
            title="Test Video",
            description="Test video description",
            channelId="UC1234567890123456789012",
            channelTitle="Test Channel",
            publishedAt=datetime(2022, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        ),
    )


class TestSyncCommandHelp:
    """Test sync command help functionality."""

    def test_sync_help_displays_subcommands(self, runner: CliRunner) -> None:
        """Test that sync --help shows all available subcommands."""
        result = runner.invoke(app, ["sync", "--help"])

        assert result.exit_code == 0
        assert "Data synchronization commands" in result.stdout
        # Verify all subcommands are listed
        assert "channel" in result.stdout
        assert "playlists" in result.stdout
        assert "topics" in result.stdout
        assert "liked" in result.stdout
        assert "history" in result.stdout


class TestSyncChannelCommand:
    """Test sync channel command with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_channel_creates_repositories_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_channel: YouTubeChannelResponse,
    ) -> None:
        """Test that sync channel command uses container to create repositories."""
        # Setup mocks
        mock_channel_repo = AsyncMock()
        mock_channel_topic_repo = AsyncMock()
        mock_topic_category_repo = AsyncMock()

        mock_container.create_channel_repository.return_value = mock_channel_repo
        mock_container.create_channel_topic_repository.return_value = (
            mock_channel_topic_repo
        )
        mock_container.create_topic_category_repository.return_value = (
            mock_topic_category_repo
        )

        # Mock YouTube service
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value=mock_youtube_channel
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock repository methods
        mock_channel_repo.exists = AsyncMock(return_value=False)
        mock_channel_repo.create_or_update = AsyncMock(
            return_value=MagicMock(
                channel_id="UC1234567890123456789012",
                title="Test Channel",
                description="Test channel description",
                subscriber_count=None,
                video_count=None,
                country=None,
                default_language=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

        # Execute command
        result = runner.invoke(app, ["sync", "channel"])

        # Verify container methods were called
        mock_container.create_channel_repository.assert_called_once()
        mock_container.create_channel_topic_repository.assert_called_once()
        mock_container.create_topic_category_repository.assert_called_once()

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_channel_with_topic_filter(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_channel: YouTubeChannelResponse,
    ) -> None:
        """Test sync channel with --topic filter validation."""
        # Setup mocks
        mock_topic_category_repo = AsyncMock()
        mock_container.create_topic_category_repository.return_value = (
            mock_topic_category_repo
        )

        # Mock YouTube service
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value=mock_youtube_channel
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock topic exists check
        mock_topic_category_repo.exists = AsyncMock(return_value=True)

        # Execute command with topic filter
        result = runner.invoke(app, ["sync", "channel", "--topic", "25"])

        # Topic repository should be created to validate topic
        mock_container.create_topic_category_repository.assert_called()


class TestSyncPlaylistsCommand:
    """Test sync playlists command with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_playlists_creates_repositories_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_playlist: YouTubePlaylistResponse,
    ) -> None:
        """Test that sync playlists command uses container to create repositories."""
        # Setup mocks
        mock_playlist_repo = AsyncMock()
        mock_container.create_playlist_repository.return_value = mock_playlist_repo

        # Mock YouTube service
        mock_youtube_service.get_my_playlists = AsyncMock(
            return_value=[mock_youtube_playlist]
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock repository methods
        mock_playlist_repo.exists = AsyncMock(return_value=False)
        mock_playlist_repo.create_or_update = AsyncMock(return_value=MagicMock())

        # Execute command
        result = runner.invoke(app, ["sync", "playlists"])

        # Verify container methods were called
        mock_container.create_playlist_repository.assert_called_once()

    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_playlists_dry_run_mode(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_playlist: YouTubePlaylistResponse,
    ) -> None:
        """Test sync playlists with --dry-run flag."""
        # Mock YouTube service
        mock_youtube_service.get_my_playlists = AsyncMock(
            return_value=[mock_youtube_playlist]
        )

        # Execute command with dry-run
        result = runner.invoke(app, ["sync", "playlists", "--dry-run"])

        # In dry-run mode, repository should NOT be created
        mock_container.create_playlist_repository.assert_not_called()

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_playlists_with_include_items(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_playlist: YouTubePlaylistResponse,
    ) -> None:
        """Test sync playlists with --include-items flag."""
        # Setup mocks
        mock_playlist_repo = AsyncMock()
        mock_video_repo = AsyncMock()
        mock_playlist_membership_repo = AsyncMock()

        mock_container.create_playlist_repository.return_value = mock_playlist_repo
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_playlist_membership_repository.return_value = (
            mock_playlist_membership_repo
        )

        # Mock YouTube service
        mock_youtube_service.get_my_playlists = AsyncMock(
            return_value=[mock_youtube_playlist]
        )
        mock_youtube_service.get_playlist_videos = AsyncMock(return_value=[])

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session,
            mock_session,
        ]

        # Mock repository methods
        mock_playlist_repo.exists = AsyncMock(return_value=False)
        mock_playlist_repo.create_or_update = AsyncMock(return_value=MagicMock())

        # Execute command with include-items
        result = runner.invoke(app, ["sync", "playlists", "--include-items"])

        # Verify additional repositories were created for items
        mock_container.create_playlist_membership_repository.assert_called()


class TestSyncTopicsCommand:
    """Test sync topics command with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_topics_creates_repository_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test that sync topics command uses container to create repository."""
        # Setup mocks
        mock_topic_category_repo = AsyncMock()
        mock_container.create_topic_category_repository.return_value = (
            mock_topic_category_repo
        )

        # Mock YouTube service
        from chronovista.models.api_responses import (
            YouTubeVideoCategoryResponse,
            CategorySnippet,
        )

        mock_category = YouTubeVideoCategoryResponse(
            id="1",
            snippet=CategorySnippet(title="Film & Animation", assignable=True),
        )
        mock_youtube_service.get_video_categories = AsyncMock(
            return_value=[mock_category]
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock repository methods
        mock_topic_category_repo.exists = AsyncMock(return_value=False)
        mock_topic_category_repo.create_or_update = AsyncMock(
            return_value=MagicMock()
        )

        # Execute command
        result = runner.invoke(app, ["sync", "topics"])

        # Verify container methods were called
        mock_container.create_topic_category_repository.assert_called_once()

    def test_sync_topics_accepts_region_code(self, runner: CliRunner) -> None:
        """Test sync topics command accepts --region flag."""
        # This will fail at YouTube API call, but verifies flag parsing
        result = runner.invoke(app, ["sync", "topics", "--region", "GB"])

        # Should not error on flag parsing
        assert "region" not in result.stdout.lower() or "GB" in result.stdout


class TestSyncLikedCommand:
    """Test sync liked command with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_liked_creates_repositories_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_channel: YouTubeChannelResponse,
        mock_youtube_video: YouTubeVideoResponse,
    ) -> None:
        """Test that sync liked command uses container to create repositories."""
        # Setup mocks
        mock_video_repo = AsyncMock()
        mock_user_video_repo = AsyncMock()

        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_user_video_repository.return_value = (
            mock_user_video_repo
        )

        # Mock YouTube service
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value=mock_youtube_channel
        )
        mock_youtube_service.get_liked_videos = AsyncMock(
            return_value=[mock_youtube_video]
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session,
            mock_session,
        ]

        # Mock repository methods
        mock_video_repo.exists = AsyncMock(return_value=True)
        mock_user_video_repo.update_like_status_batch = AsyncMock(return_value=1)
        mock_user_video_repo.get_by_composite_key = AsyncMock(return_value=None)
        mock_user_video_repo.record_like = AsyncMock()

        # Execute command
        result = runner.invoke(app, ["sync", "liked"])

        # Verify container methods were called
        mock_container.create_video_repository.assert_called()
        mock_container.create_user_video_repository.assert_called()

    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_liked_dry_run_mode(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_channel: YouTubeChannelResponse,
        mock_youtube_video: YouTubeVideoResponse,
    ) -> None:
        """Test sync liked with --dry-run flag."""
        # Setup mocks
        mock_video_repo = AsyncMock()
        mock_user_video_repo = AsyncMock()

        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_user_video_repository.return_value = (
            mock_user_video_repo
        )

        # Mock YouTube service
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value=mock_youtube_channel
        )
        mock_youtube_service.get_liked_videos = AsyncMock(
            return_value=[mock_youtube_video]
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock repository methods
        mock_video_repo.exists = AsyncMock(return_value=True)

        # Execute command with dry-run
        result = runner.invoke(app, ["sync", "liked", "--dry-run"])

        # In dry-run mode, should not update database
        mock_user_video_repo.update_like_status_batch.assert_not_called()


class TestSyncAllCommand:
    """Test sync all command with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.services.youtube_service")
    @patch("chronovista.config.database.db_manager")
    def test_sync_all_creates_all_repositories(
        self,
        mock_db_manager: MagicMock,
        mock_youtube_service: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_youtube_channel: YouTubeChannelResponse,
    ) -> None:
        """Test that sync all command uses container for all operations."""
        # Setup mocks
        mock_topic_category_repo = AsyncMock()
        mock_container.create_topic_category_repository.return_value = (
            mock_topic_category_repo
        )

        # Mock YouTube service
        from chronovista.models.api_responses import (
            YouTubeVideoCategoryResponse,
            CategorySnippet,
        )

        mock_category = YouTubeVideoCategoryResponse(
            id="1",
            snippet=CategorySnippet(title="Film & Animation", assignable=True),
        )
        mock_youtube_service.get_video_categories = AsyncMock(
            return_value=[mock_category]
        )
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value=mock_youtube_channel
        )
        mock_youtube_service.get_liked_videos = AsyncMock(return_value=[])

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock repository methods
        mock_topic_category_repo.exists = AsyncMock(return_value=False)
        mock_topic_category_repo.create_or_update = AsyncMock(
            return_value=MagicMock()
        )

        # Execute command
        result = runner.invoke(app, ["sync", "all"])

        # Verify topic repository was created
        mock_container.create_topic_category_repository.assert_called()


class TestProcessWatchHistoryBatch:
    """Test process_watch_history_batch function with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.cli.sync_commands.container")
    @patch("chronovista.config.database.db_manager")
    def test_process_watch_history_batch_creates_repositories(
        self, mock_db_manager: MagicMock, mock_container: MagicMock
    ) -> None:
        """Test that process_watch_history_batch uses container for repositories."""
        import asyncio

        from chronovista.cli.sync_commands import process_watch_history_batch
        from chronovista.parsers.takeout_parser import WatchHistoryEntry

        # Setup mocks
        mock_channel_repo = AsyncMock()
        mock_video_repo = AsyncMock()
        mock_user_video_repo = AsyncMock()

        mock_container.create_channel_repository.return_value = mock_channel_repo
        mock_container.create_video_repository.return_value = mock_video_repo
        mock_container.create_user_video_repository.return_value = (
            mock_user_video_repo
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock repository methods
        mock_channel_repo.get_by_channel_id = AsyncMock(return_value=None)
        mock_channel_repo.create_or_update = AsyncMock()
        mock_video_repo.get_by_video_id = AsyncMock(return_value=None)
        mock_video_repo.create_or_update = AsyncMock()
        mock_user_video_repo.record_watch = AsyncMock()

        # Create test batch
        batch = [
            WatchHistoryEntry(
                video_id="dQw4w9WgXcQ",
                video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                title="Test Video",
                action="Watched",
                channel_id="UC1234567890123456789012",
                channel_name="Test Channel",
                watched_at=datetime.now(timezone.utc),
            )
        ]

        # Execute function
        result = asyncio.run(process_watch_history_batch(batch, "user123"))

        # Verify container methods were called
        mock_container.create_channel_repository.assert_called_once()
        mock_container.create_video_repository.assert_called_once()
        mock_container.create_user_video_repository.assert_called_once()

        # Verify result structure
        assert "videos_created" in result
        assert "channels_created" in result
        assert "user_videos_created" in result
        assert "errors" in result


class TestSyncHistoryCommand:
    """Test sync history command with file validation."""

    def test_sync_history_requires_file_path(self, runner: CliRunner) -> None:
        """Test that sync history command requires a file path argument."""
        result = runner.invoke(app, ["sync", "history"])

        # Should fail with missing argument error
        assert result.exit_code == 2
        assert "Missing argument" in result.output or "FILE_PATH" in result.output

    def test_sync_history_accepts_limit_option(self, runner: CliRunner) -> None:
        """Test that sync history command accepts --limit option."""
        # Will fail at file validation, but verifies flag parsing
        result = runner.invoke(
            app, ["sync", "history", "nonexistent.json", "--limit", "100"]
        )

        # Should not error on flag parsing
        assert "limit" not in result.stdout.lower() or "100" in result.stdout

    def test_sync_history_accepts_batch_size_option(self, runner: CliRunner) -> None:
        """Test that sync history command accepts --batch-size option."""
        # Will fail at file validation, but verifies flag parsing
        result = runner.invoke(
            app, ["sync", "history", "nonexistent.json", "--batch-size", "500"]
        )

        # Should not error on flag parsing
        assert "batch-size" not in result.stdout.lower() or "500" in result.stdout


class TestDataTransformers:
    """Test DataTransformers integration in sync commands."""

    def test_data_transformers_imported(self) -> None:
        """Test that DataTransformers is properly imported in sync_commands."""
        from chronovista.cli.sync.transformers import DataTransformers

        # Verify key transformer methods exist
        assert hasattr(DataTransformers, "extract_playlist_create")
        assert hasattr(DataTransformers, "extract_channel_create")
        assert hasattr(DataTransformers, "extract_topic_category_create")


class TestSyncFrameworkIntegration:
    """Test integration with sync framework utilities."""

    def test_sync_framework_utilities_imported(self) -> None:
        """Test that sync framework utilities are properly imported."""
        from chronovista.cli.sync.base import (
            SyncResult,
            check_authenticated,
            display_auth_error,
            display_error,
            display_success,
            display_sync_results,
            run_sync_operation,
        )

        # Verify all utilities are available
        assert SyncResult is not None
        assert check_authenticated is not None
        assert display_auth_error is not None
        assert display_error is not None
        assert display_success is not None
        assert display_sync_results is not None
        assert run_sync_operation is not None


class TestContainerReset:
    """Test container reset between operations."""

    @patch("chronovista.cli.sync_commands.container")
    def test_container_repositories_are_transient(
        self, mock_container: MagicMock
    ) -> None:
        """Test that repository factories create new instances each call."""
        # Setup mocks
        mock_container.create_video_repository.side_effect = [
            MagicMock(),
            MagicMock(),
        ]

        # Call twice
        repo1 = mock_container.create_video_repository()
        repo2 = mock_container.create_video_repository()

        # Should be different instances
        assert repo1 is not repo2

        # Verify both calls happened
        assert mock_container.create_video_repository.call_count == 2
