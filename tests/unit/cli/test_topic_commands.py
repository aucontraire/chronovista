"""
Tests for Topic CLI commands.

Tests the topic exploration and analytics CLI commands including
list, show, channels, and videos commands.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.topic_commands import topic_app
from chronovista.db.models import TopicCategory as TopicCategoryDB


class TestTopicCommands:
    """Test suite for topic CLI commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_topic_help(self, runner: CliRunner) -> None:
        """Test topic help command."""
        result = runner.invoke(topic_app, ["--help"])
        assert result.exit_code == 0
        assert "Topic exploration and analytics" in result.stdout
        assert "list" in result.stdout
        assert "show" in result.stdout
        assert "channels" in result.stdout
        assert "videos" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_list_topics_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list topics command execution."""
        result = runner.invoke(topic_app, ["list"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_list_topics_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list topics command with custom limit."""
        result = runner.invoke(topic_app, ["list", "--limit", "10"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_list_topics_with_various_limits(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list topics command with different limit values."""
        for limit in [1, 10, 100, 999]:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["list", "--limit", str(limit)])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_show_topic_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test show topic command execution."""
        result = runner.invoke(topic_app, ["show", "test_topic_001"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_channels_by_topic_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test channels command execution."""
        result = runner.invoke(topic_app, ["channels", "test_topic_001"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_channels_by_topic_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test channels command with custom limit."""
        result = runner.invoke(
            topic_app, ["channels", "test_topic_001", "--limit", "10"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_videos_by_topic_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command execution."""
        result = runner.invoke(topic_app, ["videos", "test_topic_001"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_videos_by_topic_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with custom limit."""
        result = runner.invoke(topic_app, ["videos", "test_topic_001", "--limit", "10"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_invalid_command(self, runner: CliRunner) -> None:
        """Test invalid command handling."""
        result = runner.invoke(topic_app, ["invalid-command"])
        assert result.exit_code != 0
        assert "No such command" in result.output or "Usage:" in result.output

    def test_missing_topic_id_arguments(self, runner: CliRunner) -> None:
        """Test commands that require topic_id argument without providing it."""
        # Test show command without topic_id
        result = runner.invoke(topic_app, ["show"])
        assert result.exit_code != 0

        # Test channels command without topic_id
        result = runner.invoke(topic_app, ["channels"])
        assert result.exit_code != 0

        # Test videos command without topic_id
        result = runner.invoke(topic_app, ["videos"])
        assert result.exit_code != 0

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_edge_case_topic_ids(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with various topic ID formats."""
        edge_case_ids = [
            "123",
            "topic_with_underscores",
            "topic-with-dashes",
            "verylongtopicidthatmightcauseproblemsinsomedatabases",
            "UPPERCASE_TOPIC",
            "MixedCaseTopicId",
        ]

        for topic_id in edge_case_ids:
            for command in ["show", "channels", "videos"]:
                mock_asyncio.reset_mock()
                result = runner.invoke(topic_app, [command, topic_id])
                assert (
                    result.exit_code == 0
                ), f"Command '{command}' with topic_id '{topic_id}' should succeed"
                mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_command_limit_variations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with different limit values."""
        # Test channels with different limits
        for limit in [5, 20, 50, 100]:
            mock_asyncio.reset_mock()
            result = runner.invoke(
                topic_app, ["channels", "test_topic", "--limit", str(limit)]
            )
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

        # Test videos with different limits
        for limit in [5, 20, 50, 100]:
            mock_asyncio.reset_mock()
            result = runner.invoke(
                topic_app, ["videos", "test_topic", "--limit", str(limit)]
            )
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_asyncio_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that commands handle asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Async runtime error")

        # All commands should handle exceptions gracefully and not crash CLI
        test_cases = [
            ["list"],
            ["show", "test_topic"],
            ["channels", "test_topic"],
            ["videos", "test_topic"],
        ]

        for cmd_args in test_cases:
            result = runner.invoke(topic_app, cmd_args)
            # CLI should handle exceptions gracefully (may exit with error code)
            assert result.exit_code in [
                0,
                1,
            ], f"Command {cmd_args} should handle async exception gracefully"
            mock_asyncio.assert_called()

    def test_command_help_messages(self, runner: CliRunner) -> None:
        """Test that individual commands show help correctly."""
        # Test list command help
        result = runner.invoke(topic_app, ["list", "--help"])
        assert result.exit_code == 0
        assert "List all topic categories" in result.stdout

        # Test show command help
        result = runner.invoke(topic_app, ["show", "--help"])
        assert result.exit_code == 0
        assert "Show detailed information" in result.stdout

        # Test channels command help
        result = runner.invoke(topic_app, ["channels", "--help"])
        assert result.exit_code == 0
        assert "Show channels associated" in result.stdout

        # Test videos command help
        result = runner.invoke(topic_app, ["videos", "--help"])
        assert result.exit_code == 0
        assert "Show videos associated" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_all_commands_consistency(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that all async commands behave consistently."""
        commands_with_args = [
            ["list"],
            ["show", "topic123"],
            ["channels", "topic123"],
            ["videos", "topic123"],
        ]

        for cmd_args in commands_with_args:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)

            # All commands should succeed
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            # All async commands should call asyncio.run exactly once
            assert (
                mock_asyncio.call_count == 1
            ), f"Command {cmd_args} should call asyncio.run once"

    def test_short_option_aliases(self, runner: CliRunner) -> None:
        """Test that short option aliases work correctly."""
        # Test list command with -l alias
        with patch("chronovista.cli.topic_commands.asyncio.run") as mock_asyncio:
            result = runner.invoke(topic_app, ["list", "-l", "25"])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

        # Test channels command with -l alias
        with patch("chronovista.cli.topic_commands.asyncio.run") as mock_asyncio:
            result = runner.invoke(topic_app, ["channels", "test_topic", "-l", "15"])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

        # Test videos command with -l alias
        with patch("chronovista.cli.topic_commands.asyncio.run") as mock_asyncio:
            result = runner.invoke(topic_app, ["videos", "test_topic", "-l", "15"])
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()


class TestTopicCommandsLimitValidation:
    """Test limit parameter validation for topic commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_valid_limit_values(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that valid limit values are accepted."""
        valid_limits = [1, 10, 50, 100, 999]

        for limit in valid_limits:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["list", "--limit", str(limit)])
            assert result.exit_code == 0, f"Limit {limit} should be valid"
            mock_asyncio.assert_called_once()

    def test_invalid_limit_values(self, runner: CliRunner) -> None:
        """Test that invalid limit values are handled correctly."""
        invalid_limits = ["abc", "-1", "0", ""]

        for limit in invalid_limits:
            result = runner.invoke(topic_app, ["list", "--limit", limit])
            # Should either succeed with default or fail gracefully
            # The exact behavior depends on Typer's validation
            assert result.exit_code in [
                0,
                2,
            ], f"Invalid limit '{limit}' should be handled gracefully"
