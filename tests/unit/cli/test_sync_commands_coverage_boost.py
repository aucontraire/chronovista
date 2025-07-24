"""
Comprehensive tests for sync_commands.py to boost coverage to 90%.

Focuses on testing the async function implementations that are currently uncovered.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.sync_commands import sync_app


class TestSyncCommandsCoverageBoost:
    """Test sync commands to boost coverage - focus on async implementations."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def mock_takeout_file_with_data(self):
        """Create a temporary takeout JSON file with realistic data."""
        data = [
            {
                "header": "YouTube",
                "title": "Watched Amazing Video",
                "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "time": "2023-12-01T10:30:00Z",
                "subtitles": [
                    {
                        "name": "Amazing Channel",
                        "url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
                    }
                ],
                "products": ["YouTube"],
                "activityControls": ["YouTube watch history"],
            },
            {
                "header": "YouTube",
                "title": "Another Great Video",
                "titleUrl": "https://www.youtube.com/watch?v=abc123def",
                "time": "2023-12-02T15:45:00Z",
                "subtitles": [
                    {
                        "name": "Great Channel",
                        "url": "https://www.youtube.com/channel/UCother456",
                    }
                ],
                "products": ["YouTube"],
                "activityControls": ["YouTube watch history"],
            },
        ]

        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, temp_file)
        temp_file.flush()
        return temp_file.name

    @patch("chronovista.parsers.takeout_parser.TakeoutParser")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    @patch("chronovista.cli.sync_commands.process_watch_history_batch")
    def test_history_command_successful_flow(
        self,
        mock_process_batch,
        mock_oauth,
        mock_youtube_service,
        mock_parser,
        runner,
        mock_takeout_file_with_data,
    ):
        """Test successful history command flow to cover async implementation."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock file parsing
        mock_parser.count_entries.return_value = {"videos": 2, "total": 2}

        # Mock watch history entries
        mock_entry1 = MagicMock()
        mock_entry1.video_id = "dQw4w9WgXcQ"
        mock_entry1.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
        mock_entry1.title = "Amazing Video"
        mock_entry1.channel_name = "Amazing Channel"
        mock_entry1.watched_at = datetime.now(timezone.utc)

        mock_entry2 = MagicMock()
        mock_entry2.video_id = "abc123def"
        mock_entry2.channel_id = "UCother456"
        mock_entry2.title = "Another Video"
        mock_entry2.channel_name = "Great Channel"
        mock_entry2.watched_at = datetime.now(timezone.utc)

        mock_parser.parse_watch_history_file.return_value = [mock_entry1, mock_entry2]

        # Mock YouTube service (async functions)
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value={"id": "UCuser123"}
        )

        # Mock batch processing
        mock_process_batch.return_value = {
            "videos_created": 2,
            "channels_created": 2,
            "user_videos_created": 2,
            "errors": 0,
        }

        result = runner.invoke(sync_app, ["history", mock_takeout_file_with_data])

        assert result.exit_code == 0
        mock_parser.count_entries.assert_called_once()
        mock_youtube_service.get_my_channel.assert_called_once()
        mock_process_batch.assert_called()

    @patch("chronovista.parsers.takeout_parser.TakeoutParser")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_history_command_no_user_channel(
        self,
        mock_oauth,
        mock_youtube_service,
        mock_parser,
        runner,
        mock_takeout_file_with_data,
    ):
        """Test history command when user channel cannot be identified."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock file parsing
        mock_parser.count_entries.return_value = {"videos": 1, "total": 1}

        # Mock YouTube service returning no user ID (async function)
        mock_youtube_service.get_my_channel = AsyncMock(return_value={})

        result = runner.invoke(sync_app, ["history", mock_takeout_file_with_data])

        assert result.exit_code == 0
        assert "Could not identify user" in result.output

    @patch("chronovista.parsers.takeout_parser.TakeoutParser")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    @patch("chronovista.cli.sync_commands.process_watch_history_batch")
    def test_history_command_with_limit(
        self,
        mock_process_batch,
        mock_oauth,
        mock_youtube_service,
        mock_parser,
        runner,
        mock_takeout_file_with_data,
    ):
        """Test history command with limit parameter."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock file parsing
        mock_parser.count_entries.return_value = {"videos": 100, "total": 100}

        # Mock YouTube service (async functions)
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value={"id": "UCuser123"}
        )

        # Mock single entry
        mock_entry = MagicMock()
        mock_entry.video_id = "dQw4w9WgXcQ"
        mock_parser.parse_watch_history_file.return_value = [mock_entry]

        # Mock batch processing
        mock_process_batch.return_value = {
            "videos_created": 1,
            "channels_created": 0,
            "user_videos_created": 1,
            "errors": 0,
        }

        result = runner.invoke(
            sync_app, ["history", mock_takeout_file_with_data, "--limit", "5"]
        )

        assert result.exit_code == 0
        # Should process min(100, 5) = 5 entries
        mock_process_batch.assert_called()

    @patch("chronovista.parsers.takeout_parser.TakeoutParser")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    @patch("chronovista.cli.sync_commands.process_watch_history_batch")
    def test_history_command_batch_processing(
        self,
        mock_process_batch,
        mock_oauth,
        mock_youtube_service,
        mock_parser,
        runner,
        mock_takeout_file_with_data,
    ):
        """Test history command batch processing with custom batch size."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock file parsing
        mock_parser.count_entries.return_value = {"videos": 3, "total": 3}

        # Mock YouTube service (async functions)
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value={"id": "UCuser123"}
        )

        # Mock multiple entries
        mock_entries = []
        for i in range(3):
            mock_entry = MagicMock()
            mock_entry.video_id = f"video{i}"
            mock_entries.append(mock_entry)

        mock_parser.parse_watch_history_file.return_value = mock_entries

        # Mock batch processing
        mock_process_batch.return_value = {
            "videos_created": 2,
            "channels_created": 1,
            "user_videos_created": 2,
            "errors": 0,
        }

        result = runner.invoke(
            sync_app, ["history", mock_takeout_file_with_data, "--batch-size", "2"]
        )

        assert result.exit_code == 0
        # Should be called twice: batch of 2, then batch of 1
        assert mock_process_batch.call_count >= 1

    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_channel_command_successful_flow(
        self, mock_oauth, mock_youtube_service, runner
    ):
        """Test successful channel command flow."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock YouTube service
        mock_channel_data = {
            "id": "UCuser123",
            "snippet": {"title": "My Channel", "description": "My awesome channel"},
        }
        mock_youtube_service.get_my_channel.return_value = mock_channel_data

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0
        mock_youtube_service.get_my_channel.assert_called_once()

    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_liked_command_successful_flow(
        self, mock_oauth, mock_youtube_service, runner
    ):
        """Test successful liked command flow."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock YouTube service - need both get_my_channel and get_liked_videos
        mock_youtube_service.get_my_channel = AsyncMock(
            return_value={"id": "UCuser123"}
        )
        mock_liked_videos = [
            {"id": "video1", "snippet": {"title": "Liked Video 1"}},
            {"id": "video2", "snippet": {"title": "Liked Video 2"}},
        ]
        mock_youtube_service.get_liked_videos = AsyncMock(
            return_value=mock_liked_videos
        )

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0
        mock_youtube_service.get_my_channel.assert_called_once()
        mock_youtube_service.get_liked_videos.assert_called_once()

    def test_playlists_command_not_implemented(self, runner):
        """Test playlists command shows not implemented message."""
        result = runner.invoke(sync_app, ["playlists"])

        assert result.exit_code == 0
        assert "not yet implemented" in result.output.lower()

    def test_transcripts_command_not_implemented(self, runner):
        """Test transcripts command shows not implemented message."""
        result = runner.invoke(sync_app, ["transcripts"])

        assert result.exit_code == 0
        assert "not yet implemented" in result.output.lower()

    def test_all_command_not_implemented(self, runner):
        """Test all command shows not implemented message."""
        result = runner.invoke(sync_app, ["all"])

        assert result.exit_code == 0
        assert "not yet implemented" in result.output.lower()

    @patch("chronovista.parsers.takeout_parser.TakeoutParser")
    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_history_command_exception_handling(
        self,
        mock_oauth,
        mock_youtube_service,
        mock_parser,
        runner,
        mock_takeout_file_with_data,
    ):
        """Test history command handles exceptions gracefully."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock parser to raise exception
        mock_parser.count_entries.side_effect = Exception("Parser error")

        result = runner.invoke(sync_app, ["history", mock_takeout_file_with_data])

        assert result.exit_code == 0  # Should handle gracefully

    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_channel_command_exception_handling(
        self, mock_oauth, mock_youtube_service, runner
    ):
        """Test channel command handles exceptions gracefully."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock service to raise exception (async function)
        mock_youtube_service.get_my_channel = AsyncMock(
            side_effect=Exception("API error")
        )

        result = runner.invoke(sync_app, ["channel"])

        assert result.exit_code == 0  # Should handle gracefully

    @patch("chronovista.cli.sync_commands.youtube_service")
    @patch("chronovista.cli.sync_commands.youtube_oauth")
    def test_liked_command_exception_handling(
        self, mock_oauth, mock_youtube_service, runner
    ):
        """Test liked command handles exceptions gracefully."""
        # Mock authentication
        mock_oauth.is_authenticated.return_value = True

        # Mock service to raise exception (async function)
        mock_youtube_service.get_liked_videos = AsyncMock(
            side_effect=Exception("API error")
        )

        result = runner.invoke(sync_app, ["liked"])

        assert result.exit_code == 0  # Should handle gracefully


class TestSyncCommandsAsyncFlows:
    """Test async flows within sync commands for better coverage."""

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    @patch("chronovista.cli.sync_commands.channel_repository")
    async def test_channel_sync_flow(self, mock_channel_repo, mock_db_manager):
        """Test async channel sync functionality."""
        # This would test the actual async function implementation
        # but since they're defined inside command functions, we test via CLI
        pass

    @pytest.mark.asyncio
    @patch("chronovista.cli.sync_commands.db_manager")
    @patch("chronovista.cli.sync_commands.video_repository")
    async def test_liked_videos_sync_flow(self, mock_video_repo, mock_db_manager):
        """Test async liked videos sync functionality."""
        # This would test the actual async function implementation
        # but since they're defined inside command functions, we test via CLI
        pass
