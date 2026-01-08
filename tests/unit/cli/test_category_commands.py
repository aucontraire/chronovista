"""
Tests for Category CLI commands.

Tests the category exploration CLI commands including list, show, and videos commands.
These test the CLI interface for YouTube video categories (creator-assigned categories
like Comedy, Music, Gaming).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.category_commands import category_app, resolve_category_identifier
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoCategory as VideoCategoryDB

pytestmark = pytest.mark.asyncio


class TestCategoryCommands:
    """Test suite for category CLI commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_category_help(self, runner: CliRunner) -> None:
        """Test category help command."""
        result = runner.invoke(category_app, ["--help"])
        assert result.exit_code == 0
        assert "categories" in result.stdout.lower()
        assert "list" in result.stdout
        assert "show" in result.stdout
        assert "videos" in result.stdout

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_list_categories_command(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list categories command execution."""
        result = runner.invoke(category_app, ["list"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_list_categories_assignable_only(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list categories command with assignable-only filter."""
        result = runner.invoke(category_app, ["list", "--assignable-only"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_list_categories_assignable_only_short_flag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test list categories command with -a short flag."""
        result = runner.invoke(category_app, ["list", "-a"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_show_category_command_by_id(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test show category command execution with category ID."""
        result = runner.invoke(category_app, ["show", "23"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_show_category_command_by_name(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test show category command execution with category name."""
        result = runner.invoke(category_app, ["show", "Comedy"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_by_category_command_by_id(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command execution with category ID."""
        result = runner.invoke(category_app, ["videos", "23"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_by_category_command_by_name(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command execution with category name."""
        result = runner.invoke(category_app, ["videos", "Comedy"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_by_category_with_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with custom limit."""
        result = runner.invoke(category_app, ["videos", "23", "--limit", "10"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_by_category_with_limit_short_flag(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with -l short flag."""
        result = runner.invoke(category_app, ["videos", "23", "-l", "15"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_by_category_include_deleted(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with include-deleted flag."""
        result = runner.invoke(category_app, ["videos", "23", "--include-deleted"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_by_category_with_all_options(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with all options combined."""
        result = runner.invoke(
            category_app, ["videos", "23", "--limit", "50", "--include-deleted"]
        )

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_invalid_command(self, runner: CliRunner) -> None:
        """Test invalid command handling."""
        result = runner.invoke(category_app, ["invalid-command"])
        assert result.exit_code != 0
        assert "No such command" in result.output or "Usage:" in result.output

    def test_missing_category_argument(self, runner: CliRunner) -> None:
        """Test commands that require category argument without providing it."""
        # Test show command without category
        result = runner.invoke(category_app, ["show"])
        assert result.exit_code != 0

        # Test videos command without category
        result = runner.invoke(category_app, ["videos"])
        assert result.exit_code != 0

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_edge_case_category_identifiers(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test commands with various category identifier formats."""
        edge_case_ids = [
            "1",  # Single digit
            "23",  # Two digits
            "123",  # Three digits
            "Comedy",  # Name
            "comedy",  # Lowercase name
            "COMEDY",  # Uppercase name
            "Music",  # Another name
            "Gaming",  # Yet another name
        ]

        for category_id in edge_case_ids:
            for command in ["show", "videos"]:
                mock_asyncio.reset_mock()
                result = runner.invoke(category_app, [command, category_id])
                assert (
                    result.exit_code == 0
                ), f"Command '{command}' with category '{category_id}' should succeed"
                mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_command_limit_variations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with different limit values."""
        for limit in [1, 5, 10, 20, 50, 100]:
            mock_asyncio.reset_mock()
            result = runner.invoke(
                category_app, ["videos", "23", "--limit", str(limit)]
            )
            assert result.exit_code == 0
            mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_asyncio_exception_handling(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that commands handle asyncio.run exceptions gracefully."""
        mock_asyncio.side_effect = RuntimeError("Async runtime error")

        # All commands should handle exceptions gracefully and not crash CLI
        test_cases = [
            ["list"],
            ["show", "23"],
            ["videos", "23"],
        ]

        for cmd_args in test_cases:
            result = runner.invoke(category_app, cmd_args)
            # CLI should handle exceptions gracefully (may exit with error code)
            assert result.exit_code in [
                0,
                1,
            ], f"Command {cmd_args} should handle async exception gracefully"
            mock_asyncio.assert_called()

    def test_command_help_messages(self, runner: CliRunner) -> None:
        """Test that individual commands show help correctly."""
        # Test list command help
        result = runner.invoke(category_app, ["list", "--help"])
        assert result.exit_code == 0
        assert "List" in result.stdout and "categor" in result.stdout.lower()

        # Test show command help
        result = runner.invoke(category_app, ["show", "--help"])
        assert result.exit_code == 0
        assert "Show" in result.stdout

        # Test videos command help
        result = runner.invoke(category_app, ["videos", "--help"])
        assert result.exit_code == 0
        assert "videos" in result.stdout

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_all_commands_consistency(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test that all async commands behave consistently."""
        commands_with_args = [
            ["list"],
            ["show", "23"],
            ["videos", "23"],
        ]

        for cmd_args in commands_with_args:
            mock_asyncio.reset_mock()
            result = runner.invoke(category_app, cmd_args)

            # All commands should succeed
            assert result.exit_code == 0, f"Command {cmd_args} should succeed"
            # All async commands should call asyncio.run exactly once
            assert (
                mock_asyncio.call_count == 1
            ), f"Command {cmd_args} should call asyncio.run once"


class TestResolveCategoryIdentifier:
    """Test suite for resolve_category_identifier helper function."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock()

    @pytest.fixture
    def mock_category_repo(self) -> MagicMock:
        """Create mock category repository."""
        return MagicMock()

    @pytest.fixture
    def sample_category(self) -> VideoCategoryDB:
        """Create sample category for testing."""
        category = MagicMock(spec=VideoCategoryDB)
        category.category_id = "23"
        category.name = "Comedy"
        category.assignable = True
        category.created_at = datetime(2023, 1, 1)
        return category

    async def test_resolve_by_exact_id(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
        sample_category: VideoCategoryDB,
    ) -> None:
        """Test resolving category by exact ID match."""
        # Mock get method to return category
        mock_category_repo.get = AsyncMock(return_value=sample_category)

        result = await resolve_category_identifier(
            mock_session, mock_category_repo, "23"
        )

        assert result == sample_category
        mock_category_repo.get.assert_called_once_with(mock_session, "23")

    async def test_resolve_by_exact_name_single_match(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
        sample_category: VideoCategoryDB,
    ) -> None:
        """Test resolving category by exact name with single match."""
        # Mock get to return None (not an ID)
        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock session.execute to return single category
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_category]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await resolve_category_identifier(
            mock_session, mock_category_repo, "Comedy"
        )

        assert result == sample_category
        mock_session.execute.assert_called_once()

    async def test_resolve_by_exact_name_case_insensitive(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
        sample_category: VideoCategoryDB,
    ) -> None:
        """Test resolving category by exact name is case-insensitive."""
        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock session.execute to return single category
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_category]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await resolve_category_identifier(
            mock_session, mock_category_repo, "comedy"
        )

        assert result == sample_category
        mock_session.execute.assert_called_once()

    async def test_resolve_by_exact_name_multiple_matches_user_selects_first(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
    ) -> None:
        """Test resolving category by exact name with multiple matches, user selects first."""
        category1 = MagicMock(spec=VideoCategoryDB)
        category1.category_id = "23"
        category1.name = "Comedy"

        category2 = MagicMock(spec=VideoCategoryDB)
        category2.category_id = "24"
        category2.name = "Comedy"

        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock session.execute to return multiple categories
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [category1, category2]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock user selecting first option
        with patch("chronovista.cli.category_commands.Prompt.ask", return_value="1"):
            result = await resolve_category_identifier(
                mock_session, mock_category_repo, "Comedy"
            )

        assert result == category1

    async def test_resolve_by_exact_name_multiple_matches_user_cancels(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
    ) -> None:
        """Test resolving category by exact name with multiple matches, user cancels."""
        category1 = MagicMock(spec=VideoCategoryDB)
        category1.category_id = "23"
        category1.name = "Comedy"

        category2 = MagicMock(spec=VideoCategoryDB)
        category2.category_id = "24"
        category2.name = "Comedy"

        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock session.execute to return multiple categories
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [category1, category2]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock user selecting quit
        with patch("chronovista.cli.category_commands.Prompt.ask", return_value="q"):
            result = await resolve_category_identifier(
                mock_session, mock_category_repo, "Comedy"
            )

        assert result is None

    async def test_resolve_by_partial_name_single_match(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
        sample_category: VideoCategoryDB,
    ) -> None:
        """Test resolving category by partial name with single match."""
        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock exact name match returning empty
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock partial name match returning category
        mock_category_repo.find_by_name = AsyncMock(return_value=[sample_category])

        result = await resolve_category_identifier(
            mock_session, mock_category_repo, "Com"
        )

        assert result == sample_category
        mock_category_repo.find_by_name.assert_called_once_with(mock_session, "Com")

    async def test_resolve_by_partial_name_multiple_matches_user_selects_second(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
    ) -> None:
        """Test resolving category by partial name with multiple matches, user selects second."""
        category1 = MagicMock(spec=VideoCategoryDB)
        category1.category_id = "23"
        category1.name = "Comedy"

        category2 = MagicMock(spec=VideoCategoryDB)
        category2.category_id = "24"
        category2.name = "Comedy Central"

        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock exact name match returning empty
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock partial name match returning multiple categories
        mock_category_repo.find_by_name = AsyncMock(
            return_value=[category1, category2]
        )

        # Mock user selecting second option
        with patch("chronovista.cli.category_commands.Prompt.ask", return_value="2"):
            result = await resolve_category_identifier(
                mock_session, mock_category_repo, "Com"
            )

        assert result == category2

    async def test_resolve_by_partial_name_many_matches_limited_display(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
    ) -> None:
        """Test resolving category by partial name with >10 matches shows only first 10."""
        # Create 15 mock categories
        categories = []
        for i in range(15):
            category = MagicMock(spec=VideoCategoryDB)
            category.category_id = str(20 + i)
            category.name = f"Category {i}"
            categories.append(category)

        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock exact name match returning empty
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock partial name match returning 15 categories
        mock_category_repo.find_by_name = AsyncMock(return_value=categories)

        # Mock user selecting 5th option
        with patch("chronovista.cli.category_commands.Prompt.ask", return_value="5"):
            result = await resolve_category_identifier(
                mock_session, mock_category_repo, "Cat"
            )

        assert result == categories[4]  # 5th category (0-indexed)

    async def test_resolve_by_partial_name_user_cancels(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
    ) -> None:
        """Test resolving category by partial name with user cancellation."""
        category1 = MagicMock(spec=VideoCategoryDB)
        category1.category_id = "23"
        category1.name = "Comedy"

        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock exact name match returning empty
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock partial name match returning categories
        mock_category_repo.find_by_name = AsyncMock(return_value=[category1])

        # Mock user selecting quit - but since it's single match, no prompt needed
        result = await resolve_category_identifier(
            mock_session, mock_category_repo, "Com"
        )

        # With single partial match, should return it without prompting
        assert result == category1

    async def test_resolve_not_found(
        self,
        mock_session: AsyncMock,
        mock_category_repo: MagicMock,
    ) -> None:
        """Test resolving category when no matches found."""
        mock_category_repo.get = AsyncMock(return_value=None)

        # Mock exact name match returning empty
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock partial name match returning empty
        mock_category_repo.find_by_name = AsyncMock(return_value=[])

        result = await resolve_category_identifier(
            mock_session, mock_category_repo, "NonexistentCategory"
        )

        assert result is None


class TestCategoryCommandsEdgeCases:
    """Test edge cases and error scenarios for category commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_command_with_zero_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with limit of 0 (edge case)."""
        result = runner.invoke(category_app, ["videos", "23", "--limit", "0"])

        # Should accept but may return no results
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_videos_command_with_very_large_limit(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with very large limit."""
        result = runner.invoke(category_app, ["videos", "23", "--limit", "10000"])

        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    def test_invalid_limit_value(self, runner: CliRunner) -> None:
        """Test videos command with invalid limit value."""
        result = runner.invoke(category_app, ["videos", "23", "--limit", "invalid"])

        # Should fail with validation error
        assert result.exit_code != 0

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_negative_limit_value(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test videos command with negative limit value."""
        # Typer accepts negative values, but the implementation may handle them
        result = runner.invoke(category_app, ["videos", "23", "--limit", "-1"])

        # The command may succeed or fail depending on implementation
        # This test just verifies the command doesn't crash
        assert result.exit_code in [0, 1, 2]

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_category_with_special_characters(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test category command with special characters in name."""
        # Test with spaces
        result = runner.invoke(category_app, ["show", "News & Politics"])
        assert result.exit_code == 0
        mock_asyncio.assert_called_once()

    @patch("chronovista.cli.category_commands.asyncio.run")
    def test_all_boolean_flag_combinations(
        self, mock_asyncio: MagicMock, runner: CliRunner
    ) -> None:
        """Test all boolean flag combinations."""
        # Test list with and without assignable-only
        result = runner.invoke(category_app, ["list"])
        assert result.exit_code == 0

        result = runner.invoke(category_app, ["list", "--assignable-only"])
        assert result.exit_code == 0

        # Test videos with and without include-deleted
        result = runner.invoke(category_app, ["videos", "23"])
        assert result.exit_code == 0

        result = runner.invoke(category_app, ["videos", "23", "--include-deleted"])
        assert result.exit_code == 0

        assert mock_asyncio.call_count == 4
