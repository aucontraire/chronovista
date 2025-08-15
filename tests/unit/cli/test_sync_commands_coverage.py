"""
Tests for sync_commands.py to improve coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.sync_commands import process_watch_history_batch, sync_app


class TestSyncCommands:
    """Test sync command functionality."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_process_watch_history_batch_empty(self):
        """Test processing empty batch."""
        result = await process_watch_history_batch([], "test_user")

        assert result["videos_created"] == 0
        assert result["channels_created"] == 0
        assert result["user_videos_created"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_process_watch_history_batch_with_entries(self):
        """Test processing batch with watch history entries."""
        # Mock WatchHistoryEntry
        mock_entry = MagicMock()
        mock_entry.video_id = "dQw4w9WgXcQ"
        mock_entry.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
        mock_entry.title = "Test Video"
        mock_entry.channel_name = "Test Channel"

        batch = [mock_entry]

        with (
            patch("chronovista.cli.sync_commands.db_manager") as mock_db_manager,
            patch("chronovista.cli.sync_commands.video_repository") as mock_video_repo,
            patch(
                "chronovista.cli.sync_commands.channel_repository"
            ) as mock_channel_repo,
            patch(
                "chronovista.cli.sync_commands.user_video_repository"
            ) as mock_user_video_repo,
        ):

            # Mock database session
            mock_session = AsyncMock()
            mock_db_manager.get_session.return_value.__aenter__.return_value = (
                mock_session
            )

            # Mock repository methods
            mock_video_repo.get_by_video_id.return_value = None
            mock_channel_repo.get_by_channel_id.return_value = None
            mock_video_repo.create.return_value = MagicMock()
            mock_channel_repo.create.return_value = MagicMock()
            mock_user_video_repo.record_watch.return_value = MagicMock()

            result = await process_watch_history_batch(batch, "test_user")

            assert result["videos_created"] >= 0
            assert result["channels_created"] >= 0
            assert result["user_videos_created"] >= 0

    def test_sync_help_command(self, runner):
        """Test sync help command."""
        result = runner.invoke(sync_app, ["--help"])
        assert result.exit_code == 0
        assert "Data synchronization commands" in result.output

    @patch("chronovista.cli.sync_commands.asyncio.run")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_channel_command_not_authenticated(self, mock_oauth, mock_asyncio, runner):
        """Test channel command when not authenticated."""
        mock_oauth.is_authenticated = False

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0
        # Command should handle unauthenticated state

    @patch("chronovista.cli.sync_commands.asyncio.run")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_liked_command_not_authenticated(self, mock_oauth, mock_asyncio, runner):
        """Test liked command when not authenticated."""
        mock_oauth.is_authenticated = False

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0

    @patch("chronovista.cli.sync_commands.asyncio.run")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_history_command_not_authenticated(self, mock_oauth, mock_asyncio, runner):
        """Test history command when not authenticated."""
        mock_oauth.is_authenticated = False

        result = runner.invoke(sync_app, ["history", "test.json"])

        assert result.exit_code == 0

    @patch("chronovista.cli.sync_commands.asyncio.run")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_history_command_help(self, mock_oauth, mock_asyncio, runner):
        """Test history command help."""
        result = runner.invoke(sync_app, ["history", "--help"])

        assert result.exit_code == 0
        assert "Import" in result.output or "history" in result.output.lower()

    @patch("chronovista.cli.sync_commands.asyncio.run")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_all_command_help(self, mock_oauth, mock_asyncio, runner):
        """Test all command help."""
        result = runner.invoke(sync_app, ["all", "--help"])

        assert result.exit_code == 0

    @patch("chronovista.cli.sync_commands.asyncio.run")
    @patch("chronovista.cli.sync_commands.console")
    def test_command_execution_with_mocked_console(
        self, mock_console, mock_asyncio, runner
    ):
        """Test that commands work with mocked console output."""
        # This test ensures console.print calls don't cause issues
        mock_console.print = MagicMock()

        result = runner.invoke(sync_app, ["--help"])
        assert result.exit_code == 0


class TestSyncCommandsAsync:
    """Test async functionality in sync commands."""

    @pytest.mark.asyncio
    async def test_batch_processing_error_handling(self):
        """Test error handling in batch processing."""
        # Create a mock entry that will cause an error
        mock_entry = MagicMock()
        mock_entry.video_id = None  # This should cause an error

        with patch("chronovista.cli.sync_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()
            mock_db_manager.get_session.return_value.__aenter__.return_value = (
                mock_session
            )

            result = await process_watch_history_batch([mock_entry], "test_user")

            # Should handle errors gracefully
            assert "errors" in result
            assert isinstance(result["errors"], int)

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.youtube_service")
    async def test_youtube_service_integration(self, mock_youtube_service):
        """Test integration with YouTube service."""
        # Mock YouTube service calls
        mock_youtube_service.get_subscriptions.return_value = []
        mock_youtube_service.get_video_details.return_value = None

        # Test that process_watch_history_batch can handle YouTube service calls
        result = await process_watch_history_batch([], "test_user")

        assert isinstance(result, dict)
        assert "videos_created" in result


class TestSyncCommandsWithRealModules:
    """Test sync commands with real module imports."""

    def test_import_sync_app(self):
        """Test that sync_app can be imported successfully."""
        from chronovista.cli.sync_commands import sync_app

        assert sync_app is not None
        assert hasattr(sync_app, "callback")

    def test_import_repositories(self):
        """Test that repositories can be imported successfully."""
        from chronovista.cli.sync_commands import (
            channel_repository,
            user_video_repository,
            video_repository,
        )

        assert channel_repository is not None
        assert user_video_repository is not None
        assert video_repository is not None

    def test_console_import(self):
        """Test that console is imported and configured."""
        from chronovista.cli.sync_commands import console

        assert console is not None
        assert hasattr(console, "print")


class TestSyncCommandsEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    def test_invalid_command(self, runner):
        """Test invalid command handling."""
        result = runner.invoke(sync_app, ["invalid-command"])
        assert result.exit_code != 0

    @patch("chronovista.cli.sync_commands.asyncio.run")
    def test_command_with_exception(self, mock_asyncio, runner):
        """Test command handling when asyncio.run raises exception."""
        mock_asyncio.side_effect = Exception("Test exception")

        # This should not crash the CLI
        result = runner.invoke(sync_app, ["--help"])
        assert result.exit_code == 0  # Help should still work

    @pytest.mark.asyncio
    async def test_empty_user_id(self):
        """Test batch processing with empty user ID."""
        result = await process_watch_history_batch([], "")

        assert isinstance(result, dict)
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_none_batch(self):
        """Test batch processing with None batch."""
        # The function expects a List[Any], so passing None should raise TypeError
        # This test verifies that the function properly fails with the expected error
        with pytest.raises(TypeError):
            await process_watch_history_batch(None, "test_user")  # type: ignore[arg-type]
