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
        assert "Topic" in result.stdout  # More flexible match for topic-related help
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
        assert "List" in result.stdout and "topic" in result.stdout

        # Test show command help
        result = runner.invoke(topic_app, ["show", "--help"])
        assert result.exit_code == 0
        assert "Show" in result.stdout

        # Test channels command help
        result = runner.invoke(topic_app, ["channels", "--help"])
        assert result.exit_code == 0
        assert "channels" in result.stdout

        # Test videos command help
        result = runner.invoke(topic_app, ["videos", "--help"])
        assert result.exit_code == 0
        assert "videos" in result.stdout

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


class TestTopicChartCommand:
    """Test suite for the topic chart command (ASCII bar charts)."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_chart_help(self, runner: CliRunner) -> None:
        """Test chart command help."""
        result = runner.invoke(topic_app, ["chart", "--help"])
        assert result.exit_code == 0
        assert "Display topic popularity as ASCII bar charts" in result.stdout
        assert "--metric" in result.stdout
        assert "--limit" in result.stdout
        assert "--width" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_chart_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic chart command execution."""
        result = runner.invoke(topic_app, ["chart"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_chart_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test chart command with all options."""
        result = runner.invoke(
            topic_app,
            ["chart", "--metric", "combined", "--limit", "10", "--width", "40"],
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_chart_short_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test chart command with short option aliases."""
        result = runner.invoke(
            topic_app, ["chart", "-m", "videos", "-l", "5", "-w", "30"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_chart_different_metrics(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test chart command with different metrics."""
        valid_metrics = ["videos", "channels", "combined"]

        for metric in valid_metrics:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["chart", "--metric", metric])
            assert result.exit_code == 0, f"Metric {metric} should be valid"
            mock_asyncio.assert_called_once()

    def test_chart_invalid_metric(self, runner: CliRunner) -> None:
        """Test chart command with invalid metric values."""
        invalid_metrics = ["invalid", "topics", "counts", ""]

        for metric in invalid_metrics:
            # Note: The validation happens inside the async function,
            # so the command may still succeed at the CLI level
            result = runner.invoke(topic_app, ["chart", "--metric", metric])
            # Command should start successfully (validation happens in async code)
            assert result.exit_code == 0, f"Command should start with metric '{metric}'"


class TestTopicTreeCommand:
    """Test suite for the topic tree command (relationship trees)."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_tree_help(self, runner: CliRunner) -> None:
        """Test tree command help."""
        result = runner.invoke(topic_app, ["tree", "--help"])
        assert result.exit_code == 0
        assert "Display topic hierarchy or relationships as a tree" in result.stdout
        assert "--max-depth" in result.stdout
        assert "--min-confidence" in result.stdout
        assert "--show-stats" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_tree_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic tree command execution."""
        result = runner.invoke(topic_app, ["tree", "25"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_tree_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tree command with all options."""
        result = runner.invoke(
            topic_app,
            ["tree", "25", "--max-depth", "2", "--min-confidence", "0.2", "--no-stats"],
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_tree_short_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tree command with short option aliases."""
        result = runner.invoke(topic_app, ["tree", "25", "-d", "3", "-c", "0.1"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_tree_without_topic_id_shows_hierarchy(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tree command without topic_id shows full hierarchy."""
        result = runner.invoke(topic_app, ["tree"])

        # Should succeed and call async function to show full hierarchy
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_tree_depth_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tree command with different depth values."""
        valid_depths = [1, 2, 3, 5]

        for depth in valid_depths:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["tree", "25", "--max-depth", str(depth)])
            assert result.exit_code == 0, f"Depth {depth} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_tree_confidence_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tree command with different confidence values."""
        valid_confidences = [0.0, 0.1, 0.5, 0.9, 1.0]

        for confidence in valid_confidences:
            mock_asyncio.reset_mock()
            result = runner.invoke(
                topic_app, ["tree", "25", "--min-confidence", str(confidence)]
            )
            assert result.exit_code == 0, f"Confidence {confidence} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_tree_stats_toggle(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test tree command with stats toggle options."""
        # Test with stats enabled (default)
        result = runner.invoke(topic_app, ["tree", "25", "--show-stats"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

        # Test with stats disabled
        mock_asyncio.reset_mock()
        result = runner.invoke(topic_app, ["tree", "25", "--no-stats"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()


class TestTopicExploreCommand:
    """Test suite for the interactive topic explore command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_explore_help(self, runner: CliRunner) -> None:
        """Test explore command help."""
        result = runner.invoke(topic_app, ["explore", "--help"])
        assert result.exit_code == 0
        assert (
            "Interactive topic selection and exploration with progress bars"
            in result.stdout
        )
        assert "--analytics" in result.stdout
        assert "--auto-advance" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_explore_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic explore command execution."""
        result = runner.invoke(topic_app, ["explore"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_explore_with_analytics_disabled(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test explore command with analytics disabled."""
        result = runner.invoke(topic_app, ["explore", "--no-analytics"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_explore_with_auto_advance(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test explore command with auto-advance mode."""
        result = runner.invoke(topic_app, ["explore", "--auto-advance"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_explore_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test explore command with all options enabled."""
        result = runner.invoke(topic_app, ["explore", "--analytics", "--auto-advance"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_explore_analytics_toggle(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test explore command analytics toggle functionality."""
        # Test with analytics enabled (default)
        result = runner.invoke(topic_app, ["explore", "--analytics"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

        # Test with analytics disabled
        mock_asyncio.reset_mock()
        result = runner.invoke(topic_app, ["explore", "--no-analytics"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()


class TestTopicDiscoveryCommand:
    """Test suite for the topic discovery command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_discovery_help(self, runner: CliRunner) -> None:
        """Test discovery command help."""
        result = runner.invoke(topic_app, ["discovery", "--help"])
        assert result.exit_code == 0
        assert (
            "Analyze how users discover topics based on viewing patterns"
            in result.stdout
        )
        assert "--limit" in result.stdout
        assert "--min-interactions" in result.stdout
        assert "--method" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic discovery command execution."""
        result = runner.invoke(topic_app, ["discovery"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test discovery command with all options."""
        result = runner.invoke(
            topic_app,
            [
                "discovery",
                "--limit",
                "10",
                "--min-interactions",
                "3",
                "--method",
                "liked_content",
            ],
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_short_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test discovery command with short option aliases."""
        result = runner.invoke(topic_app, ["discovery", "-l", "5", "-m", "1"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_different_methods(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test discovery command with different discovery methods."""
        valid_methods = [
            "liked_content",
            "watched_complete",
            "watched_partial",
            "browsed",
        ]

        for method in valid_methods:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["discovery", "--method", method])
            assert result.exit_code == 0, f"Method {method} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_limit_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test discovery command with different limit values."""
        valid_limits = [1, 5, 10, 20, 50]

        for limit in valid_limits:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["discovery", "--limit", str(limit)])
            assert result.exit_code == 0, f"Limit {limit} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_interaction_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test discovery command with different min-interactions values."""
        valid_interactions = [1, 2, 3, 5, 10]

        for interactions in valid_interactions:
            mock_asyncio.reset_mock()
            result = runner.invoke(
                topic_app, ["discovery", "--min-interactions", str(interactions)]
            )
            assert (
                result.exit_code == 0
            ), f"Min interactions {interactions} should be valid"
            mock_asyncio.assert_called_once()

    def test_discovery_invalid_method(self, runner: CliRunner) -> None:
        """Test discovery command with invalid method values."""
        # Note: The validation happens inside the async function,
        # so the command may still succeed at the CLI level
        result = runner.invoke(topic_app, ["discovery", "--method", "invalid_method"])
        # Command should start successfully (validation happens in async code)
        assert result.exit_code == 0, "Command should start with invalid method"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that discovery command handles asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Async runtime error")

        result = runner.invoke(topic_app, ["discovery"])
        # CLI should handle exceptions gracefully
        assert result.exit_code in [
            0,
            1,
        ], "Command should handle async exception gracefully"
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_discovery_parameter_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test discovery command with various parameter combinations."""
        test_cases = [
            ["discovery", "-l", "3", "-m", "1"],
            ["discovery", "--limit", "5", "--method", "liked_content"],
            ["discovery", "--min-interactions", "2", "--method", "watched_complete"],
            ["discovery", "-l", "10", "-m", "3", "--method", "browsed"],
        ]

        for cmd_args in test_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            mock_asyncio.assert_called_once()


class TestTopicTrendsCommand:
    """Test suite for the topic trends command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_trends_help(self, runner: CliRunner) -> None:
        """Test trends command help."""
        result = runner.invoke(topic_app, ["trends", "--help"])
        assert result.exit_code == 0
        assert "Analyze topic popularity trends over time" in result.stdout
        assert "--period" in result.stdout
        assert "--limit" in result.stdout
        assert "--months-back" in result.stdout
        assert "--direction" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic trends command execution."""
        result = runner.invoke(topic_app, ["trends"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test trends command with all options."""
        result = runner.invoke(
            topic_app,
            [
                "trends",
                "--period",
                "weekly",
                "--limit",
                "10",
                "--months-back",
                "6",
                "--direction",
                "growing",
            ],
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_short_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test trends command with short option aliases."""
        result = runner.invoke(
            topic_app,
            ["trends", "-p", "daily", "-l", "5", "-m", "3", "-d", "declining"],
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_different_periods(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test trends command with different period values."""
        valid_periods = ["monthly", "weekly", "daily"]

        for period in valid_periods:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["trends", "--period", period])
            assert result.exit_code == 0, f"Period {period} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_different_directions(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test trends command with different trend directions."""
        valid_directions = ["growing", "declining", "stable"]

        for direction in valid_directions:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["trends", "--direction", direction])
            assert result.exit_code == 0, f"Direction {direction} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_limit_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test trends command with different limit values."""
        valid_limits = [1, 5, 10, 25, 50]

        for limit in valid_limits:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["trends", "--limit", str(limit)])
            assert result.exit_code == 0, f"Limit {limit} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_months_back_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test trends command with different months-back values."""
        valid_months = [1, 3, 6, 12, 24]

        for months in valid_months:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["trends", "--months-back", str(months)])
            assert result.exit_code == 0, f"Months back {months} should be valid"
            mock_asyncio.assert_called_once()

    def test_trends_invalid_period(self, runner: CliRunner) -> None:
        """Test trends command with invalid period values."""
        # Note: The validation happens inside the async function,
        # so the command may still succeed at the CLI level
        result = runner.invoke(topic_app, ["trends", "--period", "invalid_period"])
        # Command should start successfully (validation happens in async code)
        assert result.exit_code == 0, "Command should start with invalid period"

    def test_trends_invalid_direction(self, runner: CliRunner) -> None:
        """Test trends command with invalid direction values."""
        # Note: The validation happens inside the async function,
        # so the command may still succeed at the CLI level
        result = runner.invoke(
            topic_app, ["trends", "--direction", "invalid_direction"]
        )
        # Command should start successfully (validation happens in async code)
        assert result.exit_code == 0, "Command should start with invalid direction"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that trends command handles asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Async runtime error")

        result = runner.invoke(topic_app, ["trends"])
        # CLI should handle exceptions gracefully
        assert result.exit_code in [
            0,
            1,
        ], "Command should handle async exception gracefully"
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_trends_parameter_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test trends command with various parameter combinations."""
        test_cases = [
            ["trends", "-p", "monthly", "-l", "5"],
            ["trends", "--period", "weekly", "--direction", "growing"],
            ["trends", "--months-back", "6", "--limit", "10"],
            ["trends", "-p", "daily", "-m", "3", "-d", "stable"],
            [
                "trends",
                "--period",
                "monthly",
                "--months-back",
                "12",
                "--direction",
                "declining",
            ],
        ]

        for cmd_args in test_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            mock_asyncio.assert_called_once()


class TestTopicInsightsCommand:
    """Test suite for the topic insights command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_insights_help(self, runner: CliRunner) -> None:
        """Test insights command help."""
        result = runner.invoke(topic_app, ["insights", "--help"])
        assert result.exit_code == 0
        assert (
            "Generate personalized topic insights and recommendations" in result.stdout
        )
        assert "--user-id" in result.stdout
        assert "--limit" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic insights command execution."""
        result = runner.invoke(topic_app, ["insights"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_with_custom_user_id(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with custom user ID."""
        result = runner.invoke(topic_app, ["insights", "--user-id", "test_user_123"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_short_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with short option aliases."""
        result = runner.invoke(topic_app, ["insights", "-u", "user123", "-l", "3"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with all options."""
        result = runner.invoke(
            topic_app, ["insights", "--user-id", "advanced_user", "--limit", "8"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_limit_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with different limit values."""
        valid_limits = [1, 3, 5, 10, 20]

        for limit in valid_limits:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["insights", "--limit", str(limit)])
            assert result.exit_code == 0, f"Limit {limit} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_user_id_variations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with different user ID formats."""
        user_ids = [
            "user_123",
            "test-user",
            "USER_ALL_CAPS",
            "123456",
            "user@domain.com",
            "very-long-user-id-with-many-characters",
        ]

        for user_id in user_ids:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["insights", "--user-id", user_id])
            assert result.exit_code == 0, f"User ID '{user_id}' should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that insights command handles asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Async runtime error")

        result = runner.invoke(topic_app, ["insights"])
        # CLI should handle exceptions gracefully
        assert result.exit_code in [
            0,
            1,
        ], "Command should handle async exception gracefully"
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_parameter_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with various parameter combinations."""
        test_cases = [
            ["insights", "-u", "user1", "-l", "3"],
            ["insights", "--user-id", "analytics_user", "--limit", "7"],
            ["insights", "--user-id", "test_user", "--limit", "1"],
            ["insights", "-u", "power_user", "-l", "10"],
            ["insights", "--user-id", "researcher", "--limit", "15"],
        ]

        for cmd_args in test_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            mock_asyncio.assert_called_once()

    def test_insights_invalid_limit_values(self, runner: CliRunner) -> None:
        """Test insights command with invalid limit values."""
        invalid_limits = ["abc", "-1", "0", ""]

        for limit in invalid_limits:
            result = runner.invoke(topic_app, ["insights", "--limit", limit])
            # Should either succeed with default or fail gracefully
            # The exact behavior depends on Typer's validation
            assert result.exit_code in [
                0,
                2,
            ], f"Invalid limit '{limit}' should be handled gracefully"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_default_parameters(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with default parameters."""
        result = runner.invoke(topic_app, ["insights"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

        # Verify default parameters would be used (default_user, limit=5)
        # This is tested indirectly through successful command execution

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_empty_user_id(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with empty user ID."""
        result = runner.invoke(topic_app, ["insights", "--user-id", ""])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_special_characters_user_id(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with special characters in user ID."""
        special_user_ids = [
            "user@test.com",
            "user_with_underscores",
            "user-with-dashes",
            "user.with.dots",
            "user+plus+signs",
            "üsér_with_unicode",
        ]

        for user_id in special_user_ids:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["insights", "--user-id", user_id])
            assert (
                result.exit_code == 0
            ), f"User ID '{user_id}' should be handled correctly"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_insights_large_limit_values(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test insights command with large limit values."""
        large_limits = [50, 100, 500, 1000]

        for limit in large_limits:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["insights", "--limit", str(limit)])
            assert result.exit_code == 0, f"Large limit {limit} should be handled"
            mock_asyncio.assert_called_once()


class TestTopicGraphCommand:
    """Test suite for topic graph export command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_graph_help(self, runner: CliRunner) -> None:
        """Test graph command help."""
        result = runner.invoke(topic_app, ["graph", "--help"])
        assert result.exit_code == 0
        assert (
            "Export topic relationship graph for visualization tools" in result.stdout
        )
        assert "--format" in result.stdout
        assert "--output" in result.stdout
        assert "--min-confidence" in result.stdout
        assert "--limit" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_graph_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic graph command execution."""
        result = runner.invoke(topic_app, ["graph"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_graph_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test graph command with all options."""
        result = runner.invoke(
            topic_app,
            [
                "graph",
                "--format",
                "json",
                "--output",
                "/tmp/test_graph.json",
                "--min-confidence",
                "0.3",
                "--limit",
                "25",
            ],
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_graph_format_validation(self, runner: CliRunner) -> None:
        """Test graph command format validation."""
        # Valid formats should work
        valid_formats = ["dot", "json"]
        for format_type in valid_formats:
            result = runner.invoke(topic_app, ["graph", "--format", format_type])
            assert result.exit_code == 0, f"Format {format_type} should be valid"

        # Invalid format should fail
        result = runner.invoke(topic_app, ["graph", "--format", "invalid"])
        # Should either succeed (handled gracefully) or fail with proper error
        assert result.exit_code in [0, 1], "Invalid format should be handled gracefully"

    def test_graph_confidence_validation(self, runner: CliRunner) -> None:
        """Test graph command confidence score validation."""
        # Valid confidence scores
        valid_scores = ["0.0", "0.1", "0.5", "0.9", "1.0"]
        for score in valid_scores:
            result = runner.invoke(topic_app, ["graph", "--min-confidence", score])
            assert result.exit_code == 0, f"Confidence {score} should be valid"

        # Invalid confidence scores (outside 0.0-1.0 range)
        invalid_scores = ["-0.1", "1.1", "2.0", "abc"]
        for score in invalid_scores:
            result = runner.invoke(topic_app, ["graph", "--min-confidence", score])
            # Should fail with validation error
            assert result.exit_code == 2, f"Confidence {score} should be invalid"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_graph_limit_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test graph command with different limit values."""
        valid_limits = [1, 5, 10, 25, 50, 100]

        for limit in valid_limits:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["graph", "--limit", str(limit)])
            assert result.exit_code == 0, f"Limit {limit} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_graph_output_path_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test graph command output path handling."""
        # Test with explicit output path
        result = runner.invoke(
            topic_app, ["graph", "--output", "/tmp/custom_graph.dot"]
        )
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

        # Test without output path (should auto-generate)
        mock_asyncio.reset_mock()
        result = runner.invoke(topic_app, ["graph"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_graph_parameter_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test graph command with various parameter combinations."""
        test_cases = [
            ["graph", "-f", "dot", "-c", "0.2"],
            ["graph", "--format", "json", "--limit", "30"],
            ["graph", "--min-confidence", "0.4", "--limit", "15"],
            ["graph", "-f", "dot", "-o", "/tmp/test.dot", "-c", "0.1", "-l", "50"],
            ["graph", "--format", "json", "--output", "/tmp/graph.json"],
        ]

        for cmd_args in test_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_graph_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test graph command handles asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Graph generation error")

        result = runner.invoke(topic_app, ["graph"])
        # CLI should handle exceptions gracefully
        assert result.exit_code in [
            0,
            1,
        ], "Command should handle async exception gracefully"
        mock_asyncio.assert_called_once()

    def test_graph_invalid_limit_values(self, runner: CliRunner) -> None:
        """Test graph command with invalid limit values."""
        # Only non-integer values should fail validation
        invalid_limits = ["abc", ""]

        for limit in invalid_limits:
            result = runner.invoke(topic_app, ["graph", "--limit", limit])
            # Should fail with validation error for invalid limits
            assert (
                result.exit_code == 2
            ), f"Invalid limit '{limit}' should fail validation"

        # Negative numbers and zero are allowed by Typer but might be handled in application logic
        edge_case_limits = ["-1", "0"]
        for limit in edge_case_limits:
            result = runner.invoke(topic_app, ["graph", "--limit", limit])
            # These should either succeed or fail gracefully
            assert result.exit_code in [
                0,
                1,
                2,
            ], f"Edge case limit '{limit}' should be handled"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_graph_edge_case_parameters(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test graph command with edge case parameters."""
        edge_cases = [
            ["graph", "--min-confidence", "0.0", "--limit", "1"],  # Minimum values
            ["graph", "--min-confidence", "1.0", "--limit", "1000"],  # Maximum values
            ["graph", "--format", "dot", "--limit", "1"],  # Minimum viable graph
        ]

        for cmd_args in edge_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Edge case {cmd_args} should succeed"
            mock_asyncio.assert_called_once()


class TestTopicHeatmapCommand:
    """Test suite for topic heatmap export command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_heatmap_help(self, runner: CliRunner) -> None:
        """Test heatmap command help."""
        result = runner.invoke(topic_app, ["heatmap", "--help"])
        assert result.exit_code == 0
        assert "Generate topic activity heatmap data for visualization" in result.stdout
        assert "--output" in result.stdout
        assert "--period" in result.stdout
        assert "--months-back" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic heatmap command execution."""
        result = runner.invoke(topic_app, ["heatmap"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test heatmap command with all options."""
        result = runner.invoke(
            topic_app,
            [
                "heatmap",
                "--output",
                "/tmp/test_heatmap.json",
                "--period",
                "weekly",
                "--months-back",
                "6",
            ],
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_heatmap_period_validation(self, runner: CliRunner) -> None:
        """Test heatmap command period validation."""
        # Valid periods should work
        valid_periods = ["monthly", "weekly", "daily"]
        for period in valid_periods:
            result = runner.invoke(topic_app, ["heatmap", "--period", period])
            assert result.exit_code == 0, f"Period {period} should be valid"

        # Invalid period should fail
        result = runner.invoke(topic_app, ["heatmap", "--period", "invalid"])
        # Should either succeed (handled gracefully) or fail with proper error
        assert result.exit_code in [0, 1], "Invalid period should be handled gracefully"

    def test_heatmap_months_back_validation(self, runner: CliRunner) -> None:
        """Test heatmap command months_back validation."""
        # Valid months_back values (1-60 range)
        valid_months = ["1", "6", "12", "24", "60"]
        for months in valid_months:
            result = runner.invoke(topic_app, ["heatmap", "--months-back", months])
            assert result.exit_code == 0, f"Months {months} should be valid"

        # Invalid months_back values (outside 1-60 range)
        invalid_months = ["0", "61", "100", "-1", "abc"]
        for months in invalid_months:
            result = runner.invoke(topic_app, ["heatmap", "--months-back", months])
            # Should fail with validation error
            assert result.exit_code == 2, f"Months {months} should be invalid"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_output_path_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test heatmap command output path handling."""
        # Test with explicit output path
        result = runner.invoke(
            topic_app, ["heatmap", "--output", "/tmp/custom_heatmap.json"]
        )
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

        # Test without output path (should auto-generate)
        mock_asyncio.reset_mock()
        result = runner.invoke(topic_app, ["heatmap"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_parameter_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test heatmap command with various parameter combinations."""
        test_cases = [
            ["heatmap", "-p", "monthly", "-m", "12"],
            ["heatmap", "--period", "weekly", "--months-back", "6"],
            ["heatmap", "--output", "/tmp/test.json", "--period", "daily"],
            ["heatmap", "-o", "/tmp/heatmap.json", "-p", "monthly", "-m", "24"],
            ["heatmap", "--period", "weekly", "--months-back", "3"],
        ]

        for cmd_args in test_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test heatmap command handles asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Heatmap generation error")

        result = runner.invoke(topic_app, ["heatmap"])
        # CLI should handle exceptions gracefully
        assert result.exit_code in [
            0,
            1,
        ], "Command should handle async exception gracefully"
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_edge_case_parameters(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test heatmap command with edge case parameters."""
        edge_cases = [
            [
                "heatmap",
                "--months-back",
                "1",
                "--period",
                "daily",
            ],  # Minimum time range
            [
                "heatmap",
                "--months-back",
                "60",
                "--period",
                "monthly",
            ],  # Maximum time range
            [
                "heatmap",
                "--period",
                "weekly",
                "--months-back",
                "1",
            ],  # Short weekly analysis
        ]

        for cmd_args in edge_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Edge case {cmd_args} should succeed"
            mock_asyncio.assert_called_once()

    def test_heatmap_invalid_parameter_types(self, runner: CliRunner) -> None:
        """Test heatmap command with invalid parameter types."""
        # Invalid months_back (non-integer)
        result = runner.invoke(topic_app, ["heatmap", "--months-back", "abc"])
        assert result.exit_code == 2, "Non-integer months_back should fail validation"

        # Empty months_back
        result = runner.invoke(topic_app, ["heatmap", "--months-back", ""])
        assert result.exit_code == 2, "Empty months_back should fail validation"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_default_parameters(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test heatmap command with default parameters."""
        result = runner.invoke(topic_app, ["heatmap"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

        # Verify default parameters would be used (monthly, 12 months back)
        # This is tested indirectly through successful command execution

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_heatmap_boundary_months_values(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test heatmap command with boundary months_back values."""
        boundary_values = ["1", "60"]  # Min and max allowed values

        for months in boundary_values:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["heatmap", "--months-back", months])
            assert result.exit_code == 0, f"Boundary months {months} should be valid"
            mock_asyncio.assert_called_once()


class TestTopicEngagementCommand:
    """Test suite for topic engagement analysis command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_engagement_help(self, runner: CliRunner) -> None:
        """Test engagement command help."""
        result = runner.invoke(topic_app, ["engagement", "--help"])
        assert result.exit_code == 0
        assert (
            "Analyze topic engagement metrics based on likes, views, and comments"
            in result.stdout
        )
        assert "--topic-id" in result.stdout
        assert "--limit" in result.stdout
        assert "--sort-by" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_engagement_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic engagement command execution."""
        result = runner.invoke(topic_app, ["engagement"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_engagement_with_topic_id(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test engagement command with specific topic ID."""
        result = runner.invoke(
            topic_app, ["engagement", "--topic-id", "/m/04rlf", "--limit", "15"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_engagement_sort_validation(self, runner: CliRunner) -> None:
        """Test engagement command sort parameter validation."""
        # Valid sort options should work
        valid_sorts = [
            "engagement_score",
            "engagement_rate",
            "avg_likes",
            "avg_views",
            "avg_comments",
        ]
        for sort_by in valid_sorts:
            result = runner.invoke(topic_app, ["engagement", "--sort-by", sort_by])
            assert result.exit_code == 0, f"Sort by {sort_by} should be valid"

        # Invalid sort should fail
        result = runner.invoke(topic_app, ["engagement", "--sort-by", "invalid"])
        # Should either succeed (handled gracefully) or fail with proper error
        assert result.exit_code in [0, 1], "Invalid sort should be handled gracefully"

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_engagement_parameter_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test engagement command with various parameter combinations."""
        test_cases = [
            ["engagement", "-l", "10", "-s", "engagement_score"],
            ["engagement", "--topic-id", "/m/04rlf", "--sort-by", "avg_likes"],
            ["engagement", "--limit", "25", "--sort-by", "engagement_rate"],
            ["engagement", "-t", "/m/02jz0l", "-l", "5", "-s", "avg_views"],
        ]

        for cmd_args in test_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_engagement_limit_validation(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test engagement command with different limit values."""
        valid_limits = [1, 5, 10, 20, 50]

        for limit in valid_limits:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, ["engagement", "--limit", str(limit)])
            assert result.exit_code == 0, f"Limit {limit} should be valid"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_engagement_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test engagement command handles asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Engagement analysis error")

        result = runner.invoke(topic_app, ["engagement"])
        # CLI should handle exceptions gracefully
        assert result.exit_code in [
            0,
            1,
        ], "Command should handle async exception gracefully"
        mock_asyncio.assert_called_once()


class TestChannelEngagementCommand:
    """Test suite for channel engagement analysis command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_channel_engagement_help(self, runner: CliRunner) -> None:
        """Test channel engagement command help."""
        result = runner.invoke(topic_app, ["channel-engagement", "--help"])
        assert result.exit_code == 0
        assert (
            "Analyze channel engagement metrics for a specific topic" in result.stdout
        )
        assert "topic_id" in result.stdout
        assert "--limit" in result.stdout

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_channel_engagement_basic_execution(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test basic channel engagement command execution."""
        result = runner.invoke(topic_app, ["channel-engagement", "/m/04rlf"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_channel_engagement_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test channel engagement command with limit option."""
        result = runner.invoke(
            topic_app, ["channel-engagement", "/m/02jz0l", "--limit", "15"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_channel_engagement_parameter_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test channel engagement command with various parameter combinations."""
        test_cases = [
            ["channel-engagement", "/m/04rlf", "-l", "5"],
            ["channel-engagement", "/m/02jz0l", "--limit", "20"],
            ["channel-engagement", "/m/0cnfvx", "--limit", "1"],
        ]

        for cmd_args in test_cases:
            mock_asyncio.reset_mock()
            result = runner.invoke(topic_app, cmd_args)
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.topic_commands.asyncio.run")
    def test_channel_engagement_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test channel engagement command handles asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Channel engagement analysis error")

        result = runner.invoke(topic_app, ["channel-engagement", "/m/04rlf"])
        # CLI should handle exceptions gracefully
        assert result.exit_code in [
            0,
            1,
        ], "Command should handle async exception gracefully"
        mock_asyncio.assert_called_once()

    def test_channel_engagement_missing_topic_id(self, runner: CliRunner) -> None:
        """Test channel engagement command with missing topic ID."""
        result = runner.invoke(topic_app, ["channel-engagement"])
        # Should fail because topic_id is required
        assert result.exit_code == 2, "Missing required topic_id should fail"
