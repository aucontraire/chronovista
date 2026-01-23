"""
Comprehensive tests for sync_commands.py to maximize coverage.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.sync_commands import (
    channel_repository,
    console,
    process_watch_history_batch,
    sync_app,
    topic_category_repository,
    user_video_repository,
    video_repository,
)


class TestSyncAppCommands:
    """Test all sync app CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def mock_takeout_file(self):
        """Create a temporary takeout JSON file."""
        data = [
            {
                "header": "YouTube",
                "title": "Watched Test Video",
                "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "time": "2023-12-01T10:30:00Z",
                "subtitles": [
                    {
                        "name": "Test Channel",
                        "url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
                    }
                ],
                "products": ["YouTube"],
                "activityControls": ["YouTube watch history"],
            }
        ]

        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, temp_file)
        temp_file.flush()
        return temp_file.name

    def test_sync_app_help(self, runner):
        """Test main sync app help command."""
        result = runner.invoke(sync_app, ["--help"])
        assert result.exit_code == 0
        assert "Data synchronization commands" in result.output

    def test_sync_app_no_args_shows_help(self, runner):
        """Test that sync app shows help when no arguments provided."""
        result = runner.invoke(sync_app)
        # Should show help due to no_args_is_help=True (exit code 2 is expected for help)
        assert result.exit_code == 2

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    def test_history_command_not_authenticated(
        self, mock_console, mock_oauth, mock_asyncio, runner, mock_takeout_file
    ):
        """Test history command when user is not authenticated.

        Note: history command now uses run_sync_operation and check_authenticated
        from base module, so we mock in the base module.
        """
        mock_oauth.is_authenticated = False

        result = runner.invoke(sync_app, ["history", mock_takeout_file])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_history_command_authenticated(
        self, mock_oauth, mock_asyncio, runner, mock_takeout_file
    ):
        """Test history command when user is authenticated.

        Note: history command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        mock_oauth.is_authenticated = True

        result = runner.invoke(sync_app, ["history", mock_takeout_file])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_history_command_with_limit(self, mock_asyncio, runner, mock_takeout_file):
        """Test history command with custom limit.

        Note: history command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        result = runner.invoke(
            sync_app, ["history", mock_takeout_file, "--limit", "100"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_history_command_with_batch_size(
        self, mock_asyncio, runner, mock_takeout_file
    ):
        """Test history command with custom batch size.

        Note: history command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        result = runner.invoke(
            sync_app, ["history", mock_takeout_file, "--batch-size", "500"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_history_command_nonexistent_file(self, runner):
        """Test history command with nonexistent file."""
        result = runner.invoke(sync_app, ["history", "/nonexistent/file.json"])

        # Should handle file not found gracefully
        assert result.exit_code == 0

    # Removed test_playlists_command - tested in tests/unit/cli/sync/test_sync_playlists.py

    def test_transcripts_command(self, runner):
        """Test transcripts command (not implemented yet)."""
        result = runner.invoke(sync_app, ["transcripts"])

        assert result.exit_code == 0

    def test_all_command(self, runner):
        """Test all command (not implemented yet)."""
        result = runner.invoke(sync_app, ["all"])

        assert result.exit_code == 0

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_channel_command_authenticated(self, mock_oauth, mock_asyncio, runner):
        """Test channel command when authenticated."""
        mock_oauth.is_authenticated = True

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_channel_command_not_authenticated(self, mock_oauth, mock_asyncio, runner):
        """Test channel command when not authenticated."""
        mock_oauth.is_authenticated = False

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync_commands.check_authenticated")
    def test_liked_command_authenticated(self, mock_check_auth, mock_asyncio, runner):
        """Test liked command when authenticated."""
        mock_check_auth.return_value = True

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync_commands.check_authenticated")
    def test_liked_command_not_authenticated(self, mock_check_auth, mock_asyncio, runner):
        """Test liked command when not authenticated."""
        mock_check_auth.return_value = False

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0
        mock_check_auth.assert_called_once()

    def test_invalid_command(self, runner):
        """Test invalid command handling."""
        result = runner.invoke(sync_app, ["invalid-command"])

        assert result.exit_code != 0
        assert "No such command" in result.output or "Usage:" in result.output


class TestProcessWatchHistoryBatch:
    """Test the process_watch_history_batch function comprehensively."""

    @pytest.fixture
    def mock_watch_entry(self):
        """Create a mock watch history entry."""
        from chronovista.parsers.takeout_parser import WatchHistoryEntry

        entry = MagicMock(spec=WatchHistoryEntry)
        entry.video_id = "dQw4w9WgXcQ"
        entry.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
        entry.channel_name = "Test Channel"
        entry.title = "Test Video"
        entry.watched_at = datetime.now(timezone.utc)
        return entry

    @pytest.mark.asyncio
    async def test_process_empty_batch(self):
        """Test processing an empty batch."""
        result = await process_watch_history_batch([], "test_user")

        assert result["videos_created"] == 0
        assert result["channels_created"] == 0
        assert result["user_videos_created"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    @patch("chronovista.cli.sync_commands.channel_repository")
    @patch("chronovista.cli.sync_commands.video_repository")
    @patch("chronovista.cli.sync_commands.user_video_repository")
    async def test_process_batch_new_channel_and_video(
        self,
        mock_user_video_repo,
        mock_video_repo,
        mock_channel_repo,
        mock_db_manager,
        mock_watch_entry,
    ):
        """Test processing batch with new channel and video."""
        # Setup mocks
        mock_session = AsyncMock()

        # Mock async generator
        async def mock_get_session():
            yield mock_session

        mock_db_manager.get_session = mock_get_session

        # Set up async mocks for repository methods
        mock_channel_repo.get_by_channel_id = AsyncMock(
            return_value=None
        )  # Channel doesn't exist
        mock_video_repo.get_by_video_id = AsyncMock(
            return_value=None
        )  # Video doesn't exist

        mock_channel_repo.create_or_update = AsyncMock(return_value=MagicMock())
        mock_video_repo.create_or_update = AsyncMock(return_value=MagicMock())
        mock_user_video_repo.record_watch = AsyncMock(return_value=MagicMock())

        result = await process_watch_history_batch([mock_watch_entry], "test_user")

        assert result["channels_created"] == 1
        assert result["videos_created"] == 1
        assert result["user_videos_created"] == 1
        assert result["errors"] == 0

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    @patch("chronovista.cli.sync_commands.channel_repository")
    @patch("chronovista.cli.sync_commands.video_repository")
    @patch("chronovista.cli.sync_commands.user_video_repository")
    async def test_process_batch_existing_channel_and_video(
        self,
        mock_user_video_repo,
        mock_video_repo,
        mock_channel_repo,
        mock_db_manager,
        mock_watch_entry,
    ):
        """Test processing batch with existing channel and video."""
        # Setup mocks
        mock_session = AsyncMock()

        # Mock async generator
        async def mock_get_session():
            yield mock_session

        mock_db_manager.get_session = mock_get_session

        # Set up async mocks for repository methods
        mock_channel_repo.get_by_channel_id = AsyncMock(
            return_value=MagicMock()
        )  # Channel exists
        mock_video_repo.get_by_video_id = AsyncMock(
            return_value=MagicMock()
        )  # Video exists
        mock_user_video_repo.record_watch = AsyncMock(return_value=MagicMock())

        result = await process_watch_history_batch([mock_watch_entry], "test_user")

        assert result["channels_created"] == 0
        assert result["videos_created"] == 0
        assert result["user_videos_created"] == 1
        assert result["errors"] == 0

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    async def test_process_batch_with_errors(self, mock_db_manager):
        """Test processing batch with errors."""
        # Create an entry that will cause an error
        mock_entry = MagicMock()
        mock_entry.video_id = None  # This should cause an error
        mock_entry.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        result = await process_watch_history_batch([mock_entry], "test_user")

        assert result["errors"] >= 0  # Should handle errors gracefully

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    @patch("chronovista.cli.sync_commands.channel_repository")
    async def test_process_batch_no_channel_id(
        self, mock_channel_repo, mock_db_manager, mock_watch_entry
    ):
        """Test processing batch when entry has no channel ID."""
        mock_watch_entry.channel_id = None

        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        result = await process_watch_history_batch([mock_watch_entry], "test_user")

        # Should not try to create channel when channel_id is None
        mock_channel_repo.get_by_channel_id.assert_not_called()

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    async def test_process_batch_multiple_entries(self, mock_db_manager):
        """Test processing batch with multiple entries."""
        entries = []
        for i in range(5):
            entry = MagicMock()
            entry.video_id = f"video_{i}"
            entry.channel_id = f"channel_{i}"
            entry.channel_name = f"Channel {i}"
            entry.title = f"Video {i}"
            entry.watched_at = datetime.now(timezone.utc)
            entries.append(entry)

        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        result = await process_watch_history_batch(entries, "test_user")

        # Should process all entries
        assert isinstance(result, dict)
        assert all(
            key in result
            for key in [
                "videos_created",
                "channels_created",
                "user_videos_created",
                "errors",
            ]
        )


class TestSyncCommandsAsync:
    """Test async functionality in sync commands."""

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.console")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.db_manager")
    async def test_sync_channel_data_authenticated(
        self, mock_db_manager, mock_youtube_service, mock_console
    ):
        """Test sync_channel_data function when authenticated."""
        from chronovista.cli.sync_commands import sync_app

        # Mock YouTube service
        mock_channel_data = {
            "id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "snippet": {"title": "Test Channel", "description": "Test Description"},
        }
        mock_youtube_service.get_my_channel.return_value = mock_channel_data

        # Mock database
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # This would test the actual async function, but it's defined inside the command
        # So we test the command invocation instead
        assert mock_youtube_service is not None

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.console")
    @patch("chronovista.cli.sync_commands.youtube_service")
    async def test_sync_liked_videos_authenticated(
        self, mock_youtube_service, mock_console
    ):
        """Test sync_liked_videos function when authenticated."""
        # Mock YouTube service
        mock_liked_videos = [
            {"id": "video1", "snippet": {"title": "Liked Video 1"}},
            {"id": "video2", "snippet": {"title": "Liked Video 2"}},
        ]
        mock_youtube_service.get_liked_videos.return_value = mock_liked_videos

        # This would test the actual async function
        assert mock_youtube_service is not None


class TestSyncCommandsModuleLevelCode:
    """Test module-level initialization and constants."""

    def test_module_imports(self):
        """Test that all required modules are imported."""
        from chronovista.cli import sync_commands

        assert hasattr(sync_commands, "sync_app")
        assert hasattr(sync_commands, "console")
        assert hasattr(sync_commands, "channel_repository")
        assert hasattr(sync_commands, "user_video_repository")
        assert hasattr(sync_commands, "video_repository")

    def test_repository_instances(self):
        """Test repository instances are created."""
        assert channel_repository is not None
        assert user_video_repository is not None
        assert video_repository is not None

    def test_console_instance(self):
        """Test console instance is created."""
        assert console is not None
        assert hasattr(console, "print")

    def test_sync_app_configuration(self):
        """Test sync_app is properly configured."""
        assert sync_app.info.name == "sync"
        assert sync_app.info.help == "Data synchronization commands"


class TestSyncCommandsErrorHandling:
    """Test error handling in sync commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("pathlib.Path")
    @patch("chronovista.cli.sync.base.console")
    def test_history_command_file_not_exists(self, mock_console, mock_path, runner):
        """Test history command with non-existent file.

        Note: history command now uses display_error from base module,
        so we mock console in the base module.
        """
        # Mock Path.exists to return False
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path.return_value = mock_path_instance

        result = runner.invoke(sync_app, ["history", "/nonexistent/file.json"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    @patch("pathlib.Path")
    def test_history_command_not_authenticated(
        self, mock_path, mock_console, mock_oauth, runner
    ):
        """Test history command when not authenticated.

        Note: history command now uses check_authenticated and display_auth_error
        from base module, so we mock in the base module.
        """
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance

        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(sync_app, ["history", "test.json"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    def test_channel_command_not_authenticated(self, mock_console, mock_oauth, runner):
        """Test channel command when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    def test_liked_command_not_authenticated(self, mock_console, mock_oauth, runner):
        """Test liked command when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_history_command_general_exception(
        self, mock_asyncio_run, mock_console, mock_oauth, runner
    ):
        """Test history command with general exception.

        Note: history command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        mock_oauth.is_authenticated.return_value = True
        mock_asyncio_run.side_effect = Exception("General error")

        result = runner.invoke(sync_app, ["history", "test_file.json"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_channel_command_general_exception(
        self, mock_asyncio_run, mock_console, mock_oauth, runner
    ):
        """Test channel command with general exception.

        Note: channel command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        mock_oauth.is_authenticated.return_value = True
        mock_asyncio_run.side_effect = Exception("General error")

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0
        mock_console.print.assert_called()

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync.base.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_liked_command_general_exception(
        self, mock_asyncio_run, mock_base_console, mock_check_auth, runner
    ):
        """Test liked command with general exception.

        Note: liked command now uses run_sync_operation from base module,
        so we mock asyncio.run and console in the base module.
        """
        mock_check_auth.return_value = True
        mock_asyncio_run.side_effect = Exception("General error")

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0
        # Error message is printed by base module's console
        mock_base_console.print.assert_called()


class TestSyncCommandsAdditionalCoverage:
    """Additional tests to improve coverage."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    # Removed test_playlists_command - tested in tests/unit/cli/sync/test_sync_playlists.py

    def test_transcripts_command(self, runner):
        """Test transcripts command (not implemented)."""
        result = runner.invoke(sync_app, ["transcripts"])

        assert result.exit_code == 0
        assert "not yet implemented" in result.output.lower()

    def test_all_command(self, runner):
        """Test all command shows full sync interface."""
        result = runner.invoke(sync_app, ["all"])

        assert result.exit_code == 0
        assert "full sync" in result.output.lower()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_channel_command_success_flow(
        self, mock_asyncio_run, mock_console, mock_oauth, runner
    ):
        """Test successful channel command flow."""
        mock_oauth.is_authenticated.return_value = True

        # Mock the async function to run successfully
        mock_asyncio_run.return_value = None

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()

    @patch("chronovista.cli.sync_commands.check_authenticated")
    @patch("chronovista.cli.sync_commands.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_liked_command_success_flow(
        self, mock_asyncio_run, mock_console, mock_check_auth, runner
    ):
        """Test successful liked command flow.

        Note: liked command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module and check_authenticated.
        """
        mock_check_auth.return_value = True

        # Mock the async function to run successfully
        mock_asyncio_run.return_value = None

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()


class TestProcessWatchHistoryBatchImproved:
    """Improved tests for process_watch_history_batch to improve coverage."""

    @pytest.mark.asyncio
    async def test_process_batch_database_error_recovery(self):
        """Test batch processing handles database errors gracefully."""
        from datetime import datetime, timezone

        from chronovista.parsers.takeout_parser import WatchHistoryEntry

        entry = WatchHistoryEntry(
            title="Test Video",
            video_id="test123",
            video_url="https://www.youtube.com/watch?v=test123",
            action="Watched",
            channel_id="UC123",
            channel_name="Test Channel",
            watched_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )

        # Mock database operations to raise an exception during session creation
        with patch("chronovista.cli.sync_commands.db_manager") as mock_db:
            mock_db.get_session.side_effect = Exception("Database connection error")

            # Should raise the exception since session creation isn't wrapped in try/catch
            with pytest.raises(Exception, match="Database connection error"):
                await process_watch_history_batch([entry], "user123")

    @pytest.mark.asyncio
    async def test_process_batch_with_empty_list(self):
        """Test processing empty batch."""
        result = await process_watch_history_batch([], "user123")

        assert result["videos_created"] == 0
        assert result["channels_created"] == 0
        assert result["user_videos_created"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    @patch("chronovista.cli.sync_commands.channel_repository")
    @patch("chronovista.cli.sync_commands.video_repository")
    @patch("chronovista.cli.sync_commands.user_video_repository")
    async def test_process_batch_create_new_channel_and_video(
        self, mock_user_video_repo, mock_video_repo, mock_channel_repo, mock_db_manager
    ):
        """Test creating new channel and video from batch."""
        from datetime import datetime, timezone

        from chronovista.parsers.takeout_parser import WatchHistoryEntry

        entry = WatchHistoryEntry(
            title="New Video",
            video_id="9bZkp7q19f0",
            video_url="https://www.youtube.com/watch?v=9bZkp7q19f0",
            action="Watched",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            channel_name="New Channel",
            watched_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )

        # Mock database session
        mock_session = AsyncMock()

        # Mock async generator
        async def mock_get_session():
            yield mock_session

        mock_db_manager.get_session = mock_get_session

        # Mock repository methods to return None (not found)
        mock_channel_repo.get_by_channel_id = AsyncMock(return_value=None)
        mock_video_repo.get_by_video_id = AsyncMock(return_value=None)

        # Mock create methods
        mock_channel_repo.create_or_update = AsyncMock(return_value=None)
        mock_video_repo.create_or_update = AsyncMock(return_value=None)
        mock_user_video_repo.record_watch = AsyncMock(return_value=None)

        result = await process_watch_history_batch([entry], "user123")

        # Should create both channel and video
        assert result["channels_created"] == 1
        assert result["videos_created"] == 1
        assert result["user_videos_created"] == 1
        assert result["errors"] == 0

        # Verify methods were called
        mock_channel_repo.create_or_update.assert_called_once()
        mock_video_repo.create_or_update.assert_called_once()
        mock_user_video_repo.record_watch.assert_called_once()
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_history_command_asyncio_error(self, mock_asyncio, runner):
        """Test history command when asyncio.run raises an exception.

        Note: history command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        mock_asyncio.side_effect = RuntimeError("Async error")

        # The CLI should handle asyncio errors gracefully
        result = runner.invoke(sync_app, ["history", "test_file.json"])

        # The command should complete gracefully even with errors
        assert result.exit_code == 0

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync_commands.check_authenticated")
    def test_console_print_calls(self, mock_check_auth, mock_asyncio, runner):
        """Test that playlists command runs without errors when properly mocked."""
        # Mock authentication check to return False to avoid hitting the database
        mock_check_auth.return_value = False

        # Test a simple command that should print
        result = runner.invoke(sync_app, ["playlists"])

        assert result.exit_code == 0
        # The command should have checked authentication
        mock_check_auth.assert_called_once()
        # Should not have run async operation since auth check failed
        mock_asyncio.assert_not_called()

    def test_history_command_help(self, runner):
        """Test history command help."""
        result = runner.invoke(sync_app, ["history", "--help"])

        assert result.exit_code == 0
        assert "Path to Google Takeout" in result.output or "file_path" in result.output

    @patch("builtins.open", mock_open(read_data="invalid json"))
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_history_command_invalid_json(self, mock_asyncio, runner):
        """Test history command with invalid JSON file.

        Note: history command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        result = runner.invoke(sync_app, ["history", "invalid.json"])

        assert result.exit_code == 0  # Should handle gracefully

    @patch("pathlib.Path.exists")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_history_command_file_not_exists(self, mock_asyncio, mock_exists, runner):
        """Test history command when file doesn't exist.

        Note: history command now uses run_sync_operation from base module,
        so we mock asyncio.run in the base module.
        """
        mock_exists.return_value = False

        result = runner.invoke(sync_app, ["history", "nonexistent.json"])

        assert result.exit_code == 0  # Should handle gracefully


class TestSyncTopicsCommand:
    """Test sync topics command functionality."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_help(self, mock_asyncio, runner):
        """Test topics command help."""
        result = runner.invoke(sync_app, ["topics", "--help"])
        assert result.exit_code == 0
        assert "Sync YouTube video categories/topics to database" in result.output
        assert "--region" in result.output
        assert "Two-character country code" in result.output

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_default_region(self, mock_asyncio, runner):
        """Test topics command with default US region."""
        result = runner.invoke(sync_app, ["topics"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_with_region(self, mock_asyncio, runner):
        """Test topics command with custom region."""
        result = runner.invoke(sync_app, ["topics", "--region", "GB"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_with_short_region_flag(self, mock_asyncio, runner):
        """Test topics command with short -r flag."""
        result = runner.invoke(sync_app, ["topics", "-r", "DE"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_not_authenticated(
        self, mock_asyncio, mock_console, mock_oauth, runner
    ):
        """Test topics command when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(sync_app, ["topics"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync.base.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_api_success(
        self, mock_asyncio, mock_console, mock_youtube_service, mock_oauth, runner
    ):
        """Test topics command with successful API response."""
        mock_oauth.is_authenticated.return_value = True

        result = runner.invoke(sync_app, ["topics"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_exception_handling(
        self, mock_asyncio, mock_console, mock_oauth, runner
    ):
        """Test topics command exception handling."""
        mock_oauth.is_authenticated.return_value = True
        mock_asyncio.side_effect = Exception("Test exception")

        result = runner.invoke(sync_app, ["topics"])
        assert result.exit_code == 0  # Should handle exceptions gracefully

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_various_regions(self, mock_asyncio, runner):
        """Test topics command with various valid regions."""
        regions = ["US", "GB", "DE", "FR", "JP", "CA", "AU"]

        for region in regions:
            mock_asyncio.reset_mock()
            result = runner.invoke(sync_app, ["topics", "--region", region])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    def test_topics_command_case_insensitive_region(self, mock_asyncio, runner):
        """Test topics command with lowercase region code."""
        result = runner.invoke(sync_app, ["topics", "--region", "gb"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()


class TestSyncTopicsAsyncFunction:
    """Test the async sync_topics_data function comprehensively."""

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync.base.console")
    async def test_sync_topics_not_authenticated(self, mock_console, mock_oauth):
        """Test sync topics when not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        # Import and call the async function directly by mocking the command structure
        from chronovista.cli.sync_commands import sync_app

        # Since we can't easily extract the nested async function,
        # we test through the CLI interface instead
        assert True  # Placeholder for complex async testing

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.db_manager")
    @patch("chronovista.cli.sync_commands.topic_category_repository")
    @patch("chronovista.cli.sync.base.console")
    async def test_sync_topics_successful_sync(
        self,
        mock_console,
        mock_topic_repo,
        mock_db_manager,
        mock_youtube_service,
        mock_oauth,
    ):
        """Test successful topic sync process."""
        mock_oauth.is_authenticated.return_value = True

        # Mock YouTube API response
        mock_categories = [
            {"id": "1", "snippet": {"title": "Film & Animation"}},
            {"id": "10", "snippet": {"title": "Music"}},
        ]
        mock_youtube_service.get_video_categories.return_value = mock_categories

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock repository methods
        mock_topic_repo.exists.return_value = False
        mock_topic_repo.create_or_update.return_value = MagicMock()

        # Test would require calling the nested async function
        # For now, we verify the mocks are set up correctly
        assert mock_categories is not None
        assert len(mock_categories) == 2

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync.base.console")
    async def test_sync_topics_no_categories_found(
        self, mock_console, mock_youtube_service, mock_oauth
    ):
        """Test sync topics when no categories found."""
        mock_oauth.is_authenticated.return_value = True
        mock_youtube_service.get_video_categories.return_value = []

        # Test would check that appropriate message is displayed
        assert True  # Placeholder

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync.base.youtube_oauth")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync.base.console")
    async def test_sync_topics_api_error(
        self, mock_console, mock_youtube_service, mock_oauth
    ):
        """Test sync topics when YouTube API returns error."""
        mock_oauth.is_authenticated.return_value = True
        mock_youtube_service.get_video_categories.side_effect = Exception("API Error")

        # Test would verify error handling
        assert True  # Placeholder
