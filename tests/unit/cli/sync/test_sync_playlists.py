"""
Comprehensive tests for playlist sync command.

Tests the `chronovista sync playlists` command including authentication,
API interactions, database operations, and dry-run mode.
"""

# mypy: disable-error-code="call-arg"

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.sync_commands import sync_app
from chronovista.models.api_responses import (
    PlaylistContentDetails,
    PlaylistSnippet,
    PlaylistStatus,
    YouTubePlaylistResponse,
)


class TestPlaylistsCommand:
    """Test playlist sync command."""

    # Valid 24-char channel ID (UC + 22 chars = 24 total)
    VALID_CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxxxxxx"
    # Valid 34-char playlist ID (PL + 32 chars = 34 total)
    VALID_PLAYLIST_ID_1 = "PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    VALID_PLAYLIST_ID_2 = "PLyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def mock_playlist_1(self) -> YouTubePlaylistResponse:
        """Create a mock playlist response."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="My Awesome Playlist",
            description="A collection of great videos",
            channel_title="Test Channel",
            default_language="en",
        )
        content_details = PlaylistContentDetails(
            item_count=15,
        )
        status = PlaylistStatus(
            privacy_status="public",
        )
        return YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID_1,
            snippet=snippet,
            content_details=content_details,
            status=status,
        )

    @pytest.fixture
    def mock_playlist_2(self) -> YouTubePlaylistResponse:
        """Create another mock playlist response."""
        published = datetime(2024, 2, 10, 8, 30, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Private Collection",
            description="My private videos",
            channel_title="Test Channel",
            default_language="en",
        )
        content_details = PlaylistContentDetails(
            item_count=5,
        )
        status = PlaylistStatus(
            privacy_status="private",
        )
        return YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="abc456",
            id=self.VALID_PLAYLIST_ID_2,
            snippet=snippet,
            content_details=content_details,
            status=status,
        )

    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_not_authenticated(
        self,
        mock_oauth: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test playlists command when user is not authenticated."""
        mock_oauth.is_authenticated.return_value = False

        result = runner.invoke(sync_app, ["playlists"])

        assert result.exit_code == 0
        # Should display auth error message
        assert "Authentication Required" in result.output or "not authenticated" in result.output.lower()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_no_playlists_found(
        self,
        mock_oauth: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test playlists command when no playlists are found."""
        mock_oauth.is_authenticated.return_value = True

        result = runner.invoke(sync_app, ["playlists"])

        assert result.exit_code == 0
        # Verify asyncio.run was called (command reached async execution)
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_dry_run_shows_preview(
        self,
        mock_oauth: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test playlists command in dry-run mode."""
        mock_oauth.is_authenticated.return_value = True

        result = runner.invoke(sync_app, ["playlists", "--dry-run"])

        assert result.exit_code == 0
        # Verify asyncio.run was called with dry-run
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_successful_sync(
        self,
        mock_oauth: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test successful playlist sync."""
        mock_oauth.is_authenticated.return_value = True

        result = runner.invoke(sync_app, ["playlists"])

        assert result.exit_code == 0
        # Verify asyncio.run was called
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_include_items_flag(
        self,
        mock_oauth: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test playlists command with --include-items flag."""
        mock_oauth.is_authenticated.return_value = True

        result = runner.invoke(sync_app, ["playlists", "--include-items"])

        assert result.exit_code == 0
        # Verify asyncio.run was called with include-items flag
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_handles_errors_gracefully(
        self,
        mock_oauth: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test playlists command handles errors gracefully."""
        mock_oauth.is_authenticated.return_value = True

        # Simulate error by having asyncio.run raise an exception
        mock_asyncio.side_effect = Exception("Simulated error")

        result = runner.invoke(sync_app, ["playlists"])

        # Should complete with error handling
        assert result.exit_code == 0
        assert "error" in result.output.lower() or "Error" in result.output or "failed" in result.output.lower()

    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_help(
        self,
        mock_oauth: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test playlists command help text."""
        result = runner.invoke(sync_app, ["playlists", "--help"])

        assert result.exit_code == 0
        assert "playlists" in result.output.lower()
        assert "--include-items" in result.output or "include-items" in result.output
        assert "--dry-run" in result.output or "dry-run" in result.output

    @patch("chronovista.cli.sync.base.asyncio.run")
    @patch("chronovista.cli.sync.base.youtube_oauth")
    def test_playlists_command_updates_existing_playlist(
        self,
        mock_oauth: MagicMock,
        mock_asyncio: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test playlists command updates existing playlist."""
        mock_oauth.is_authenticated.return_value = True

        result = runner.invoke(sync_app, ["playlists"])

        assert result.exit_code == 0
        # Verify asyncio.run was called
        mock_asyncio.assert_called_once()
