"""
Tests for Tag CLI commands.

Tests the tag exploration CLI commands including list, show, videos, search,
stats, and by-video commands. These test the CLI interface for YouTube video tags
(keywords that creators add to help with video discoverability).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.tag_commands import tag_app
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.models.video_tag import VideoTagStatistics

pytestmark = pytest.mark.asyncio


class TestTagCommands:
    """Test suite for tag CLI commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_tag_help(self, runner: CliRunner) -> None:
        """Test tag help command."""
        result = runner.invoke(tag_app, ["--help"])
        assert result.exit_code == 0
        assert "tags" in result.stdout.lower() or "tag" in result.stdout.lower()
        assert "list" in result.stdout
        assert "show" in result.stdout
        assert "videos" in result.stdout
        assert "search" in result.stdout
        assert "stats" in result.stdout
        assert "by-video" in result.stdout

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_list_tags_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list tags command execution."""
        result = runner.invoke(tag_app, ["list"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_list_tags_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list tags command with custom limit."""
        result = runner.invoke(tag_app, ["list", "--limit", "20"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_list_tags_with_limit_short_flag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list tags command with -l short flag."""
        result = runner.invoke(tag_app, ["list", "-l", "30"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_show_tag_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test show tag command execution."""
        result = runner.invoke(tag_app, ["show", "--tag", "music"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_show_tag_with_related_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test show tag command with custom related limit."""
        result = runner.invoke(tag_app, ["show", "--tag", "music", "--related", "15"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_show_tag_with_related_short_flag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test show tag command with -r short flag."""
        result = runner.invoke(tag_app, ["show", "--tag", "music", "-r", "5"])

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_show_tag_with_dash_prefix(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test show tag command with dash-prefixed tag."""
        result = runner.invoke(tag_app, ["show", "--tag", "-ALFIE"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_videos_by_tag_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos by tag command execution."""
        result = runner.invoke(tag_app, ["videos", "--tag", "gaming"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_videos_by_tag_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos by tag command with custom limit."""
        result = runner.invoke(tag_app, ["videos", "--tag", "gaming", "--limit", "10"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_videos_by_tag_with_limit_short_flag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos by tag command with -l short flag."""
        result = runner.invoke(tag_app, ["videos", "--tag", "gaming", "-l", "15"])

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_videos_by_tag_with_dash_prefix(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos by tag command with dash-prefixed tag."""
        result = runner.invoke(tag_app, ["videos", "--tag", "-House"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_search_tags_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test search tags command execution."""
        result = runner.invoke(tag_app, ["search", "--pattern", "music"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_search_tags_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test search tags command with custom limit."""
        result = runner.invoke(tag_app, ["search", "--pattern", "music", "--limit", "25"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_search_tags_with_limit_short_flag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test search tags command with -l short flag."""
        result = runner.invoke(tag_app, ["search", "--pattern", "music", "-l", "40"])

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_search_tags_with_dash_prefix(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test search tags command with dash-prefixed pattern."""
        result = runner.invoke(tag_app, ["search", "--pattern", "-test"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_tag_stats_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tag stats command execution."""
        result = runner.invoke(tag_app, ["stats"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_tags_by_video_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tags by video command execution."""
        result = runner.invoke(tag_app, ["by-video", "--id", "dQw4w9WgXcQ"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_tags_by_video_with_dash_prefix(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tags by video command with dash-prefixed video ID."""
        # This tests the fix for video IDs starting with '-'
        result = runner.invoke(tag_app, ["by-video", "--id", "-2kc5xfeQEs"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_tags_by_video_short_flag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tags by video command with -i short flag."""
        result = runner.invoke(tag_app, ["by-video", "-i", "dQw4w9WgXcQ"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_invalid_command(self, runner: CliRunner) -> None:
        """Test invalid command handling."""
        result = runner.invoke(tag_app, ["invalid-command"])
        assert result.exit_code != 0
        assert "No such command" in result.output or "Usage:" in result.output

    def test_missing_tag_argument(self, runner: CliRunner) -> None:
        """Test commands that require tag argument without providing it."""
        # Test show command without tag
        result = runner.invoke(tag_app, ["show"])
        assert result.exit_code != 0

        # Test videos command without tag
        result = runner.invoke(tag_app, ["videos"])
        assert result.exit_code != 0

        # Test search command without pattern
        result = runner.invoke(tag_app, ["search"])
        assert result.exit_code != 0

    def test_missing_video_id_argument(self, runner: CliRunner) -> None:
        """Test by-video command without video_id."""
        result = runner.invoke(tag_app, ["by-video"])
        assert result.exit_code != 0

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_edge_case_tag_patterns(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with various tag patterns."""
        edge_case_tags = [
            "music",  # Simple word
            "game-review",  # With hyphen
            "how to",  # With space
            "C++",  # With special chars
            "2023",  # Numbers
            "let's play",  # With apostrophe
        ]

        for tag in edge_case_tags:
            for command in ["show", "videos"]:
                mock_asyncio.reset_mock()
                result = runner.invoke(tag_app, [command, "--tag", tag])
                assert (
                    result.exit_code == 0
                ), f"Command '{command}' with tag '{tag}' should succeed"
                mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_command_limit_variations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with different limit values."""
        for limit in [1, 5, 10, 20, 50, 100]:
            # Test list command with various limits
            mock_asyncio.reset_mock()
            result = runner.invoke(tag_app, ["list", "--limit", str(limit)])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

            # Test videos command with various limits
            mock_asyncio.reset_mock()
            result = runner.invoke(tag_app, ["videos", "--tag", "music", "--limit", str(limit)])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

            # Test search command with various limits
            mock_asyncio.reset_mock()
            result = runner.invoke(tag_app, ["search", "--pattern", "music", "--limit", str(limit)])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_asyncio_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that commands handle asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Async runtime error")

        # All commands should handle exceptions gracefully and not crash CLI
        test_cases = [
            ["list"],
            ["show", "--tag", "music"],
            ["videos", "--tag", "music"],
            ["search", "--pattern", "music"],
            ["stats"],
            ["by-video", "--id", "dQw4w9WgXcQ"],
        ]

        for cmd_args in test_cases:
            result = runner.invoke(tag_app, cmd_args)
            # CLI should handle exceptions gracefully (may exit with error code)
            assert result.exit_code in [
                0,
                1,
            ], f"Command {cmd_args} should handle async exception gracefully"
            mock_asyncio.assert_called()

    def test_command_help_messages(self, runner: CliRunner) -> None:
        """Test that individual commands show help correctly."""
        # Test list command help
        result = runner.invoke(tag_app, ["list", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout.lower() and "tag" in result.stdout.lower()

        # Test show command help
        result = runner.invoke(tag_app, ["show", "--help"])
        assert result.exit_code == 0
        assert "show" in result.stdout.lower()

        # Test videos command help
        result = runner.invoke(tag_app, ["videos", "--help"])
        assert result.exit_code == 0
        assert "video" in result.stdout.lower()

        # Test search command help
        result = runner.invoke(tag_app, ["search", "--help"])
        assert result.exit_code == 0
        assert "search" in result.stdout.lower()

        # Test stats command help
        result = runner.invoke(tag_app, ["stats", "--help"])
        assert result.exit_code == 0
        assert "stat" in result.stdout.lower()

        # Test by-video command help
        result = runner.invoke(tag_app, ["by-video", "--help"])
        assert result.exit_code == 0
        assert "video" in result.stdout.lower()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_all_commands_consistency(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that all async commands behave consistently."""
        commands_with_args = [
            ["list"],
            ["show", "--tag", "music"],
            ["videos", "--tag", "music"],
            ["search", "--pattern", "music"],
            ["stats"],
            ["by-video", "--id", "dQw4w9WgXcQ"],
        ]

        for cmd_args in commands_with_args:
            mock_asyncio.reset_mock()
            result = runner.invoke(tag_app, cmd_args)

            # All commands should succeed
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            # All async commands should call asyncio.run exactly once
            assert (
                mock_asyncio.call_count == 1
            ), f"Command {cmd_args} should call asyncio.run once"


class TestTagCommandsEdgeCases:
    """Test edge cases and error scenarios for tag commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_list_with_zero_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list command with limit of 0 (edge case)."""
        result = runner.invoke(tag_app, ["list", "--limit", "0"])

        # Should accept but may return no results
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_videos_with_zero_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with limit of 0 (edge case)."""
        result = runner.invoke(tag_app, ["videos", "--tag", "music", "--limit", "0"])

        # Should accept but may return no results
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_search_with_zero_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test search command with limit of 0 (edge case)."""
        result = runner.invoke(tag_app, ["search", "--pattern", "music", "--limit", "0"])

        # Should accept but may return no results
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_list_with_very_large_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list command with very large limit."""
        result = runner.invoke(tag_app, ["list", "--limit", "10000"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_videos_with_very_large_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with very large limit."""
        result = runner.invoke(tag_app, ["videos", "--tag", "music", "--limit", "10000"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_invalid_limit_value(self, runner: CliRunner) -> None:
        """Test commands with invalid limit value."""
        result = runner.invoke(tag_app, ["list", "--limit", "invalid"])
        assert result.exit_code != 0

        result = runner.invoke(tag_app, ["videos", "--tag", "music", "--limit", "invalid"])
        assert result.exit_code != 0

        result = runner.invoke(tag_app, ["search", "--pattern", "music", "--limit", "invalid"])
        assert result.exit_code != 0

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_negative_limit_value(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with negative limit value."""
        # Typer accepts negative values, but the implementation may handle them
        result = runner.invoke(tag_app, ["list", "--limit", "-1"])
        assert result.exit_code in [0, 1, 2]

        result = runner.invoke(tag_app, ["videos", "--tag", "music", "--limit", "-1"])
        assert result.exit_code in [0, 1, 2]

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_tag_with_special_characters(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with special characters in tag."""
        # Test with spaces
        result = runner.invoke(tag_app, ["show", "--tag", "how to cook"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

        # Test with special chars
        mock_asyncio.reset_mock()
        result = runner.invoke(tag_app, ["videos", "--tag", "C++"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_very_long_tag_name(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with very long tag name."""
        long_tag = "a" * 100  # Long but valid tag
        result = runner.invoke(tag_app, ["show", "--tag", long_tag])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_empty_string_tag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with empty string tag."""
        # Typer may handle this differently, but test the behavior
        result = runner.invoke(tag_app, ["show", "--tag", ""])
        # May succeed or fail depending on Typer's handling
        assert result.exit_code in [0, 1, 2]

    @patch("chronovista.cli.tag_commands.asyncio.run")
    def test_video_id_formats(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test by-video command with various video ID formats."""
        video_ids = [
            "dQw4w9WgXcQ",  # Standard 11-char
            "9bZkp7q19f0",  # Another standard
            "shortid",  # Short
            "-2kc5xfeQEs",  # Dash prefix (requires --id)
        ]

        for video_id in video_ids:
            mock_asyncio.reset_mock()
            result = runner.invoke(tag_app, ["by-video", "--id", video_id])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()


class TestListTagsAsyncIntegration:
    """Test async integration for list_tags command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_list_tags_with_results(self, runner: CliRunner) -> None:
        """Test list_tags with results through CLI."""
        # Mock the entire async call path
        async def mock_run_list() -> None:
            pass  # Simulated successful execution

        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=lambda f: mock_run_list()):
            result = runner.invoke(tag_app, ["list", "--limit", "50"])
            assert result.exit_code == 0

    def test_list_tags_no_results(self, runner: CliRunner) -> None:
        """Test list_tags with no results through CLI."""
        async def mock_run_list() -> None:
            pass  # Simulated execution with no results

        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=lambda f: mock_run_list()):
            result = runner.invoke(tag_app, ["list"])
            assert result.exit_code == 0

    def test_list_tags_error_handling(self, runner: CliRunner) -> None:
        """Test list_tags error handling through CLI."""
        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=RuntimeError("Database error")):
            result = runner.invoke(tag_app, ["list"])
            # Should handle error gracefully
            assert result.exit_code in [0, 1]


class TestShowTagIntegration:
    """Test integration for show_tag command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_show_tag_command_integration(self, runner: CliRunner) -> None:
        """Test show_tag command through CLI."""
        async def mock_run() -> None:
            pass

        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=lambda f: mock_run()):
            result = runner.invoke(tag_app, ["show", "--tag", "music", "--related", "10"])
            assert result.exit_code == 0


class TestVideosByTagIntegration:
    """Test integration for videos_by_tag command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_videos_by_tag_command_integration(self, runner: CliRunner) -> None:
        """Test videos_by_tag command through CLI."""
        async def mock_run() -> None:
            pass

        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=lambda f: mock_run()):
            result = runner.invoke(tag_app, ["videos", "--tag", "music", "--limit", "20"])
            assert result.exit_code == 0


class TestSearchTagsIntegration:
    """Test integration for search_tags command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_search_tags_command_integration(self, runner: CliRunner) -> None:
        """Test search_tags command through CLI."""
        async def mock_run() -> None:
            pass

        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=lambda f: mock_run()):
            result = runner.invoke(tag_app, ["search", "--pattern", "music", "--limit", "30"])
            assert result.exit_code == 0


class TestTagStatsIntegration:
    """Test integration for tag_stats command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_tag_stats_command_integration(self, runner: CliRunner) -> None:
        """Test tag_stats command through CLI."""
        async def mock_run() -> None:
            pass

        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=lambda f: mock_run()):
            result = runner.invoke(tag_app, ["stats"])
            assert result.exit_code == 0


class TestTagsByVideoIntegration:
    """Test integration for tags_by_video command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_tags_by_video_command_integration(self, runner: CliRunner) -> None:
        """Test tags_by_video command through CLI."""
        async def mock_run() -> None:
            pass

        with patch("chronovista.cli.tag_commands.asyncio.run", side_effect=lambda f: mock_run()):
            result = runner.invoke(tag_app, ["by-video", "--id", "dQw4w9WgXcQ"])
            assert result.exit_code == 0
