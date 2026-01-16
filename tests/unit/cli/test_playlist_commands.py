"""
Comprehensive tests for playlist CLI commands.

Tests the playlist management CLI commands including link, unlink, list, and show
commands with proper error handling, confirmation prompts, and exit codes.

These tests cover Tasks T038 and T039 from feature 004-playlist-id-architecture:
- T038: link/unlink commands with error handling
- T039: list/show commands with display formatting

NOTE: Due to Typer 0.16.0 limitations with Literal types, these tests focus on
testing the async implementation functions directly rather than through the CLI runner.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.cli.constants import (
    EXIT_CANCELLED,
    EXIT_SUCCESS,
    EXIT_SYSTEM_ERROR,
    EXIT_USER_ERROR,
)
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Playlist as PlaylistDB

# NOTE: We don't use pytestmark = pytest.mark.asyncio globally because:
# 1. The CLI command functions are sync functions that call asyncio.run() internally
# 2. We mark individual async tests explicitly
# 3. Helper function tests don't need asyncio mark


class TestPlaylistLinkCommandLogic:
    """Test suite for 'playlist link' command logic (T038)."""

    @pytest.fixture
    def mock_playlist_db(self) -> PlaylistDB:
        """Create mock playlist database object."""
        playlist = PlaylistDB(
            playlist_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
            youtube_id=None,
            title="My Favorite Videos",
            description="Playlist imported from Google Takeout",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            video_count=42,
            privacy_status="private",
            created_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        return playlist

    @pytest.fixture
    def mock_linked_playlist_db(self) -> PlaylistDB:
        """Create mock playlist already linked to another YouTube ID."""
        playlist = PlaylistDB(
            playlist_id="INT_abc123def456abc123def456abc123de",
            youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
            title="Another Playlist",
            description="Already linked",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            video_count=15,
            privacy_status="private",
            created_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        return playlist

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.console")
    def test_link_with_invalid_internal_id_format_returns_exit_code_1(
        self,
        mock_console: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test link with invalid internal_id format returns exit code 1."""
        mock_exit.side_effect = SystemExit(EXIT_USER_ERROR)

        # Import and invoke the link command
        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INVALID_ID",  # Invalid format
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                force=False,
                yes=False,
            )

        # Verify error message was printed
        assert mock_console.print.called
        error_output = str(mock_console.print.call_args)
        assert "Error" in error_output or "Validation" in error_output

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_USER_ERROR

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.console")
    def test_link_with_invalid_youtube_id_format_returns_exit_code_1(
        self,
        mock_console: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test link with invalid youtube_id format returns exit code 1."""
        mock_exit.side_effect = SystemExit(EXIT_USER_ERROR)

        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                youtube_id="INVALID123",  # Invalid YouTube ID format
                force=False,
                yes=False,
            )

        # Verify error message was printed
        assert mock_console.print.called
        error_output = str(mock_console.print.call_args)
        assert "Error" in error_output or "Validation" in error_output

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_USER_ERROR

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.console")
    def test_link_with_nonexistent_playlist_returns_exit_code_1(
        self,
        mock_console: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
    ) -> None:
        """Test link with non-existent playlist returns exit code 1."""
        mock_exit.side_effect = SystemExit(EXIT_USER_ERROR)

        # Mock repository to return None (playlist not found)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = None
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INT_00000000000000000000000000000000",
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                force=False,
                yes=False,
            )

        # Verify error message contains "Not Found"
        assert mock_console.print.called
        error_output = str(mock_console.print.call_args)
        assert "Error: Not Found" in error_output or "does not exist" in error_output

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_USER_ERROR

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.console")
    def test_link_with_already_linked_youtube_id_returns_exit_code_1(
        self,
        mock_console: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
        mock_playlist_db: PlaylistDB,
        mock_linked_playlist_db: PlaylistDB,
    ) -> None:
        """Test link with already-linked youtube_id returns exit code 1 (without --force)."""
        mock_exit.side_effect = SystemExit(EXIT_USER_ERROR)

        # Mock repository
        mock_repo = AsyncMock()
        mock_repo.get.return_value = mock_playlist_db
        mock_repo.get_by_youtube_id.return_value = (
            mock_linked_playlist_db  # Different playlist already linked
        )
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                force=False,
                yes=False,
            )

        # Verify error message contains "Conflict"
        assert mock_console.print.called
        error_output = str(mock_console.print.call_args)
        assert "Error: Conflict" in error_output or "already linked" in error_output

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_USER_ERROR

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.Confirm.ask")
    def test_link_with_force_overwrites_existing_link(
        self,
        mock_confirm: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
        mock_playlist_db: PlaylistDB,
        mock_linked_playlist_db: PlaylistDB,
    ) -> None:
        """Test link with --force overwrites existing link."""
        mock_exit.side_effect = SystemExit(EXIT_SUCCESS)
        mock_confirm.return_value = True  # User confirms

        # Mock repository
        mock_repo = AsyncMock()
        mock_repo.get.return_value = mock_playlist_db
        mock_repo.get_by_youtube_id.return_value = mock_linked_playlist_db
        mock_repo.link_youtube_id.return_value = None
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                force=True,
                yes=False,
            )

        # Verify link_youtube_id was called with force=True
        mock_repo.link_youtube_id.assert_called_once()
        call_args = mock_repo.link_youtube_id.call_args
        assert call_args[1]["force"] is True

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_SUCCESS

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.Confirm.ask")
    def test_link_with_user_cancellation_returns_exit_code_3(
        self,
        mock_confirm: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
        mock_playlist_db: PlaylistDB,
    ) -> None:
        """Test link with user cancellation returns exit code 3."""
        mock_exit.side_effect = SystemExit(EXIT_CANCELLED)
        mock_confirm.return_value = False  # User declines

        # Mock repository
        mock_repo = AsyncMock()
        mock_repo.get.return_value = mock_playlist_db
        mock_repo.get_by_youtube_id.return_value = None
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                force=False,
                yes=False,
            )

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_CANCELLED

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.display_success_panel")
    def test_link_success_message_format_matches_contract(
        self,
        mock_success_panel: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
        mock_playlist_db: PlaylistDB,
    ) -> None:
        """Test link success message format matches contract specification."""
        mock_exit.side_effect = SystemExit(EXIT_SUCCESS)

        # Mock repository
        mock_repo = AsyncMock()
        mock_repo.get.return_value = mock_playlist_db
        mock_repo.get_by_youtube_id.return_value = None
        mock_repo.link_youtube_id.return_value = None
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                force=False,
                yes=True,
            )

        # Verify success panel was called with correct format
        mock_success_panel.assert_called_once()
        call_args = mock_success_panel.call_args
        assert 'Linked playlist "My Favorite Videos"' in call_args[0][0]
        assert call_args[1]["title"] == "Link Complete"

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.console")
    def test_link_ctrl_c_handling_returns_exit_code_3(
        self,
        mock_console: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
    ) -> None:
        """Test Ctrl+C handling returns exit code 3 with clean message."""
        mock_exit.side_effect = SystemExit(EXIT_CANCELLED)

        # Mock repository to raise KeyboardInterrupt
        mock_repo = AsyncMock()
        mock_repo.get.side_effect = KeyboardInterrupt()
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import link

        with pytest.raises(SystemExit):
            link(
                internal_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                force=False,
                yes=False,
            )

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_CANCELLED


class TestPlaylistUnlinkCommandLogic:
    """Test suite for 'playlist unlink' command logic (T038)."""

    @pytest.fixture
    def mock_linked_playlist(self) -> PlaylistDB:
        """Create mock playlist with YouTube ID."""
        playlist = PlaylistDB(
            playlist_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
            youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
            title="My Favorite Videos",
            description="Linked playlist",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            video_count=42,
            privacy_status="private",
            created_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        return playlist

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.console")
    def test_unlink_with_nonexistent_playlist_returns_exit_code_1(
        self,
        mock_console: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
    ) -> None:
        """Test unlink with non-existent playlist returns exit code 1."""
        mock_exit.side_effect = SystemExit(EXIT_USER_ERROR)

        # Mock repository to return None (playlist not found)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = None
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import unlink

        with pytest.raises(SystemExit):
            unlink(
                playlist_id="INT_00000000000000000000000000000000",
                yes=False,
            )

        # Verify error message contains "Not Found"
        assert mock_console.print.called
        error_output = str(mock_console.print.call_args)
        assert "Error: Not Found" in error_output or "does not exist" in error_output

        # Verify exit code
        assert mock_exit.called
        assert mock_exit.call_args[0][0] == EXIT_USER_ERROR

    @patch("chronovista.cli.commands.playlist.DatabaseManager")
    @patch("chronovista.cli.commands.playlist.PlaylistRepository")
    @patch("chronovista.cli.commands.playlist.sys.exit")
    @patch("chronovista.cli.commands.playlist.display_success_panel")
    def test_unlink_success_message_format_matches_contract(
        self,
        mock_success_panel: MagicMock,
        mock_exit: MagicMock,
        mock_repo_class: MagicMock,
        mock_db_manager_class: MagicMock,
        mock_linked_playlist: PlaylistDB,
    ) -> None:
        """Test unlink success message format matches contract specification."""
        mock_exit.side_effect = SystemExit(EXIT_SUCCESS)

        # Mock repository
        mock_repo = AsyncMock()
        mock_repo.get.return_value = mock_linked_playlist
        mock_repo.unlink_youtube_id.return_value = None
        mock_repo_class.return_value = mock_repo

        # Mock database manager session
        mock_session = AsyncMock()
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]
        mock_db_manager_class.return_value = mock_db_manager

        from chronovista.cli.commands.playlist import unlink

        with pytest.raises(SystemExit):
            unlink(
                playlist_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                yes=True,
            )

        # Verify success panel was called with correct format
        mock_success_panel.assert_called_once()
        call_args = mock_success_panel.call_args
        assert 'Unlinked playlist "My Favorite Videos"' in call_args[0][0]
        assert "PLdU2X" in call_args[0][0]  # Partial YouTube ID shown


class TestPlaylistHelperFunctions:
    """Test suite for playlist command helper functions (T039)."""

    def test_truncate_id_keeps_short_ids_unchanged(self) -> None:
        """Test _truncate_id keeps short IDs unchanged."""
        from chronovista.cli.commands.playlist import _truncate_id

        short_id = "INT_abc123"
        result = _truncate_id(short_id, max_length=40)
        assert result == short_id

    def test_truncate_id_adds_ellipsis_to_long_ids(self) -> None:
        """Test _truncate_id adds ellipsis to long IDs."""
        from chronovista.cli.commands.playlist import _truncate_id

        long_id = "INT_" + "a" * 50
        result = _truncate_id(long_id, max_length=20)
        assert result.endswith("...")
        assert len(result) == 20

    def test_output_json_produces_valid_json_structure(self) -> None:
        """Test _output_json produces valid JSON structure matching contract."""
        from chronovista.cli.commands.playlist import _output_json

        # Create mock playlists
        playlists = [
            PlaylistDB(
                playlist_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
                youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
                title="Test Playlist",
                channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
                video_count=42,
                privacy_status="private",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]

        stats = {"total_playlists": 1, "linked_playlists": 1, "unlinked_playlists": 0}

        # Capture console output
        with patch("chronovista.cli.commands.playlist.console") as mock_console:
            _output_json(playlists, stats)

            # Get the JSON string that was printed
            assert mock_console.print.called
            json_str = mock_console.print.call_args[0][0]

            # Parse and verify structure
            data = json.loads(json_str)
            assert "playlists" in data
            assert "summary" in data
            assert data["summary"]["total"] == 1
            assert data["summary"]["linked"] == 1
            assert data["summary"]["unlinked"] == 0
            assert len(data["playlists"]) == 1
            assert data["playlists"][0]["playlist_id"] == "INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f"
            assert data["playlists"][0]["linked"] is True

    def test_output_csv_produces_valid_csv_header(self) -> None:
        """Test _output_csv produces valid CSV with proper header."""
        from chronovista.cli.commands.playlist import _output_csv

        playlists: List[PlaylistDB] = []
        stats = {"total_playlists": 0, "linked_playlists": 0, "unlinked_playlists": 0}

        # Capture console output
        with patch("chronovista.cli.commands.playlist.console") as mock_console:
            _output_csv(playlists, stats)

            # Verify header was printed
            calls = [str(call) for call in mock_console.print.call_args_list]
            header_call = calls[0]
            assert "playlist_id" in header_call
            assert "youtube_id" in header_call
            assert "title" in header_call
            assert "video_count" in header_call
            assert "linked" in header_call

    def test_display_playlist_details_shows_all_required_fields(self) -> None:
        """Test _display_playlist_details shows all required fields from contract."""
        from chronovista.cli.commands.playlist import _display_playlist_details

        # Create mock channel
        channel = ChannelDB(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Test Channel",
            description="Test channel",
            subscriber_count=1000,
            video_count=100,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock playlist with channel
        playlist = PlaylistDB(
            playlist_id="INT_7f37ed8c9a8e4b5d6c7f8a9b0c1d2e3f",
            youtube_id="PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
            title="My Favorite Videos",
            description="Test description",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            video_count=42,
            privacy_status="private",
            created_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        playlist.channel = channel

        # Capture console output
        with patch("chronovista.cli.commands.playlist.console") as mock_console:
            _display_playlist_details(playlist)

            # Verify all required fields were printed
            calls = [str(call) for call in mock_console.print.call_args_list]
            output_text = " ".join(calls)

            assert "Playlist Details" in output_text
            assert "Internal ID:" in output_text
            assert "YouTube ID:" in output_text
            assert "Title:" in output_text
            assert "Description:" in output_text
            assert "Videos:" in output_text
            assert "Privacy:" in output_text
            assert "Channel:" in output_text
            assert "Created:" in output_text
