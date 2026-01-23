"""
Unit tests for seed CLI commands.

Tests cover:
- chronovista seed topics (--help, --dry-run, --force)
- chronovista seed categories (--help, --dry-run, --force, --regions)
- Exit codes (0 = success, 1 = failure with errors, 2 = API errors)
- Output validation
- Error handling
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.commands.seed import seed_app
from chronovista.services.enrichment.seeders import CategorySeedResult, TopicSeedResult

pytestmark = pytest.mark.asyncio

runner = CliRunner()


class TestTopicsCommandHelp:
    """Test 'chronovista seed topics --help' command."""

    def test_topics_help_displays_usage(self) -> None:
        """Test that --help displays usage information."""
        result = runner.invoke(seed_app, ["topics", "--help"])

        assert result.exit_code == 0
        assert "Seed YouTube topic categories" in result.stdout
        assert "--force" in result.stdout
        assert "--dry-run" in result.stdout

    def test_topics_help_shows_examples(self) -> None:
        """Test that help shows usage examples."""
        result = runner.invoke(seed_app, ["topics", "--help"])

        assert result.exit_code == 0
        assert "chronovista seed topics" in result.stdout


class TestTopicsCommandDryRun:
    """Test 'chronovista seed topics --dry-run' command."""

    @patch("chronovista.cli.commands.seed.TopicSeeder")
    def test_topics_dry_run_shows_preview(self, mock_seeder_class: MagicMock) -> None:
        """Test that --dry-run shows what would be seeded."""
        # Mock seeder class methods
        mock_seeder_class.get_expected_topic_count.return_value = 58
        mock_seeder_class.get_parent_count.return_value = 7
        mock_seeder_class.get_child_count.return_value = 51
        mock_seeder_class.PARENT_TOPIC_IDS = {"/m/04rlf"}  # Music only for simplicity
        mock_seeder_class.get_topic_by_id.return_value = ("Music", None, "Music")
        mock_seeder_class.get_topics_by_parent.return_value = [
            ("/m/03_d0", "Jazz")
        ]

        result = runner.invoke(seed_app, ["topics", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Would seed" in result.stdout
        assert "No changes made" in result.stdout

    @patch("chronovista.cli.commands.seed.TopicSeeder")
    def test_topics_dry_run_does_not_call_database(
        self, mock_seeder_class: MagicMock
    ) -> None:
        """Test that --dry-run does not make database changes."""
        mock_seeder_class.get_expected_topic_count.return_value = 58
        mock_seeder_class.get_parent_count.return_value = 7
        mock_seeder_class.get_child_count.return_value = 51
        mock_seeder_class.PARENT_TOPIC_IDS = set()

        mock_seeder_instance = MagicMock()
        mock_seeder_class.return_value = mock_seeder_instance

        result = runner.invoke(seed_app, ["topics", "--dry-run"])

        # Verify seed() was not called
        mock_seeder_instance.seed.assert_not_called()


class TestTopicsCommandNormalRun:
    """Test normal 'chronovista seed topics' execution."""

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_topics_normal_run_success(
        self, mock_container: MagicMock, mock_db_manager: MagicMock
    ) -> None:
        """Test successful topic seeding."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_topic_seeder.return_value = mock_seeder

        # Mock successful seeding result
        mock_seeder.seed.return_value = TopicSeedResult(
            created=58,
            skipped=0,
            deleted=0,
            failed=0,
            duration_seconds=2.5,
            errors=[]
        )

        # Mock static methods through TopicSeeder class
        with patch("chronovista.cli.commands.seed.TopicSeeder") as mock_seeder_class:
            mock_seeder_class.get_parent_count.return_value = 7
            mock_seeder_class.get_child_count.return_value = 51

            result = runner.invoke(seed_app, ["topics"])

            assert result.exit_code == 0
            assert "Topic Seeding Complete" in result.stdout
            assert "Created 58 topic categories" in result.stdout

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_topics_partial_success_with_errors(
        self, mock_container: MagicMock, mock_db_manager: MagicMock
    ) -> None:
        """Test topic seeding with some errors."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_topic_seeder.return_value = mock_seeder

        # Mock partial success
        mock_seeder.seed.return_value = TopicSeedResult(
            created=55,
            skipped=0,
            deleted=0,
            failed=3,
            duration_seconds=2.5,
            errors=["Error 1", "Error 2", "Error 3"]
        )

        # Mock static methods through TopicSeeder class
        with patch("chronovista.cli.commands.seed.TopicSeeder") as mock_seeder_class:
            mock_seeder_class.get_parent_count.return_value = 7
            mock_seeder_class.get_child_count.return_value = 51

            result = runner.invoke(seed_app, ["topics"])

            assert result.exit_code == 1
            assert "Topic seeding completed with errors" in result.stdout
            assert "Failed: 3" in result.stdout

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.TopicSeeder")
    def test_topics_database_error_handling(
        self, mock_seeder_class: MagicMock, mock_db_manager: MagicMock
    ) -> None:
        """Test handling of database errors."""
        # Mock database session error
        mock_db_manager.get_session.side_effect = Exception("Database connection failed")

        result = runner.invoke(seed_app, ["topics"])

        assert result.exit_code == 1
        assert "Topic Seeding Failed" in result.stdout
        assert "Database error" in result.stdout


class TestTopicsCommandForceFlag:
    """Test 'chronovista seed topics --force' command."""

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_topics_force_flag_deletes_and_recreates(
        self, mock_container: MagicMock, mock_db_manager: MagicMock
    ) -> None:
        """Test that --force deletes existing topics and re-seeds."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_topic_seeder.return_value = mock_seeder

        # Mock force seeding result (deleted and created)
        mock_seeder.seed.return_value = TopicSeedResult(
            created=58,
            skipped=0,
            deleted=58,
            failed=0,
            duration_seconds=3.0,
            errors=[]
        )

        # Mock static methods through TopicSeeder class
        with patch("chronovista.cli.commands.seed.TopicSeeder") as mock_seeder_class:
            mock_seeder_class.get_parent_count.return_value = 7
            mock_seeder_class.get_child_count.return_value = 51

            result = runner.invoke(seed_app, ["topics", "--force"])

            # Verify force=True was passed to seeder
            mock_seeder.seed.assert_called_once()
            call_args = mock_seeder.seed.call_args
            assert call_args.kwargs.get("force") is True

            assert result.exit_code == 0
            assert "Topics Deleted" in result.stdout or "58" in result.stdout


class TestCategoriesCommandHelp:
    """Test 'chronovista seed categories --help' command."""

    def test_categories_help_displays_usage(self) -> None:
        """Test that --help displays usage information."""
        result = runner.invoke(seed_app, ["categories", "--help"])

        assert result.exit_code == 0
        assert "Seed video categories from YouTube API" in result.stdout
        assert "--force" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--regions" in result.stdout

    def test_categories_help_shows_examples(self) -> None:
        """Test that help shows usage examples."""
        result = runner.invoke(seed_app, ["categories", "--help"])

        assert result.exit_code == 0
        assert "chronovista seed categories" in result.stdout


class TestCategoriesCommandDryRun:
    """Test 'chronovista seed categories --dry-run' command."""

    @patch("chronovista.cli.commands.seed.container")
    def test_categories_dry_run_shows_preview(
        self, mock_container: MagicMock
    ) -> None:
        """Test that --dry-run shows what would be seeded."""
        # Mock CategorySeeder static method
        with patch("chronovista.services.enrichment.seeders.CategorySeeder.get_expected_quota_cost", return_value=7):
            result = runner.invoke(seed_app, ["categories", "--dry-run"])

            assert result.exit_code == 0
            assert "DRY RUN" in result.stdout
            assert "Would fetch categories" in result.stdout
            assert "quota cost" in result.stdout.lower()
            assert "No changes made" in result.stdout

    @patch("chronovista.cli.commands.seed.container")
    def test_categories_dry_run_with_custom_regions(
        self, mock_container: MagicMock
    ) -> None:
        """Test --dry-run with custom regions."""
        # Mock CategorySeeder static method
        with patch("chronovista.services.enrichment.seeders.CategorySeeder.get_expected_quota_cost", return_value=3):
            result = runner.invoke(
                seed_app, ["categories", "--dry-run", "--regions", "US,GB,FR"]
            )

            assert result.exit_code == 0
            assert "US" in result.stdout
            assert "GB" in result.stdout
            assert "FR" in result.stdout
            assert "3 units" in result.stdout


class TestCategoriesCommandNormalRun:
    """Test normal 'chronovista seed categories' execution."""

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_categories_normal_run_success(
        self,
        mock_container: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test successful category seeding."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_category_seeder.return_value = mock_seeder

        # Mock successful seeding result
        mock_seeder.seed.return_value = CategorySeedResult(
            created=30,
            skipped=0,
            deleted=0,
            failed=0,
            duration_seconds=5.0,
            quota_used=7,
            errors=[]
        )

        result = runner.invoke(seed_app, ["categories"])

        assert result.exit_code == 0
        assert "Category Seeding Complete" in result.stdout
        assert "Created 30 unique categories" in result.stdout
        assert "Quota used: 7 units" in result.stdout

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_categories_with_custom_regions(
        self,
        mock_container: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test category seeding with custom regions."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_category_seeder.return_value = mock_seeder

        mock_seeder.seed.return_value = CategorySeedResult(
            created=25,
            skipped=0,
            deleted=0,
            failed=0,
            duration_seconds=3.0,
            quota_used=3,
            errors=[]
        )

        result = runner.invoke(
            seed_app, ["categories", "--regions", "US,GB,FR"]
        )

        # Verify regions were parsed correctly
        mock_seeder.seed.assert_called_once()
        call_args = mock_seeder.seed.call_args
        regions = call_args.kwargs.get("regions")
        assert regions == ["US", "GB", "FR"]

        assert result.exit_code == 0

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_categories_api_error_handling(
        self,
        mock_container: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test handling of API errors."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder to raise API error from container
        mock_seeder = AsyncMock()
        mock_container.create_category_seeder.return_value = mock_seeder
        mock_seeder.seed.side_effect = Exception("YouTube API quota exceeded")

        result = runner.invoke(seed_app, ["categories"])

        assert result.exit_code == 2  # Exit code 2 for API errors
        assert "Category Seeding Failed" in result.stdout
        assert "API error" in result.stdout

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_categories_partial_regional_failures(
        self,
        mock_container: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test graceful degradation with regional API failures."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_category_seeder.return_value = mock_seeder

        # Mock partial success (some regions failed)
        mock_seeder.seed.return_value = CategorySeedResult(
            created=20,
            skipped=0,
            deleted=0,
            failed=0,
            duration_seconds=4.0,
            quota_used=5,
            errors=["Region GB failed: API error", "Region JP failed: timeout"]
        )

        result = runner.invoke(seed_app, ["categories"])

        assert result.exit_code == 0  # Still succeeds despite regional failures
        assert "Warning: 2 errors occurred" in result.stdout


class TestCategoriesCommandForceFlag:
    """Test 'chronovista seed categories --force' command."""

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_categories_force_flag_deletes_and_recreates(
        self,
        mock_container: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test that --force deletes existing categories and re-seeds."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_category_seeder.return_value = mock_seeder

        # Mock force seeding result (deleted and created)
        mock_seeder.seed.return_value = CategorySeedResult(
            created=30,
            skipped=0,
            deleted=30,
            failed=0,
            duration_seconds=5.0,
            quota_used=7,
            errors=[]
        )

        result = runner.invoke(seed_app, ["categories", "--force"])

        # Verify force=True was passed to seeder
        mock_seeder.seed.assert_called_once()
        call_args = mock_seeder.seed.call_args
        assert call_args.kwargs.get("force") is True

        assert result.exit_code == 0
        assert "Categories Deleted" in result.stdout or "30" in result.stdout


class TestSeedCommandOutputFormatting:
    """Test output formatting and tables."""

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_topics_output_includes_results_table(
        self, mock_container: MagicMock, mock_db_manager: MagicMock
    ) -> None:
        """Test that topics command outputs formatted results table."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_topic_seeder.return_value = mock_seeder

        mock_seeder.seed.return_value = TopicSeedResult(
            created=58,
            skipped=0,
            deleted=0,
            failed=0,
            duration_seconds=2.5,
            errors=[]
        )

        # Mock static methods through TopicSeeder class
        with patch("chronovista.cli.commands.seed.TopicSeeder") as mock_seeder_class:
            mock_seeder_class.get_parent_count.return_value = 7
            mock_seeder_class.get_child_count.return_value = 51

            result = runner.invoke(seed_app, ["topics"])

            assert result.exit_code == 0
            assert "Topic Seeding Results" in result.stdout
            assert "Topics Created" in result.stdout
            assert "Duration" in result.stdout

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_categories_output_includes_quota_info(
        self,
        mock_container: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test that categories command outputs quota usage."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        # Mock seeder from container
        mock_seeder = AsyncMock()
        mock_container.create_category_seeder.return_value = mock_seeder

        mock_seeder.seed.return_value = CategorySeedResult(
            created=30,
            skipped=0,
            deleted=0,
            failed=0,
            duration_seconds=5.0,
            quota_used=7,
            errors=[]
        )

        result = runner.invoke(seed_app, ["categories"])

        assert result.exit_code == 0
        assert "Category Seeding Results" in result.stdout
        assert "Quota Used" in result.stdout
        assert "7 units" in result.stdout


class TestSeedCommandExitCodes:
    """Test exit code conventions."""

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_topics_success_exit_code_0(
        self, mock_container: MagicMock, mock_db_manager: MagicMock
    ) -> None:
        """Test that successful seeding exits with code 0."""
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        mock_seeder = AsyncMock()
        mock_container.create_topic_seeder.return_value = mock_seeder

        mock_seeder.seed.return_value = TopicSeedResult(
            created=58, skipped=0, deleted=0, failed=0, duration_seconds=2.5
        )

        # Mock static methods through TopicSeeder class
        with patch("chronovista.cli.commands.seed.TopicSeeder") as mock_seeder_class:
            mock_seeder_class.get_parent_count.return_value = 7
            mock_seeder_class.get_child_count.return_value = 51

            result = runner.invoke(seed_app, ["topics"])
            assert result.exit_code == 0

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_topics_failure_exit_code_1(
        self, mock_container: MagicMock, mock_db_manager: MagicMock
    ) -> None:
        """Test that seeding with errors exits with code 1."""
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        mock_seeder = AsyncMock()
        mock_container.create_topic_seeder.return_value = mock_seeder

        mock_seeder.seed.return_value = TopicSeedResult(
            created=55, skipped=0, deleted=0, failed=3, duration_seconds=2.5,
            errors=["Error 1", "Error 2", "Error 3"]
        )

        # Mock static methods through TopicSeeder class
        with patch("chronovista.cli.commands.seed.TopicSeeder") as mock_seeder_class:
            mock_seeder_class.get_parent_count.return_value = 7
            mock_seeder_class.get_child_count.return_value = 51

            result = runner.invoke(seed_app, ["topics"])
            assert result.exit_code == 1

    @patch("chronovista.cli.commands.seed.db_manager")
    @patch("chronovista.cli.commands.seed.container")
    def test_categories_api_error_exit_code_2(
        self,
        mock_container: MagicMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test that API errors exit with code 2."""
        mock_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [mock_session]

        mock_seeder = AsyncMock()
        mock_container.create_category_seeder.return_value = mock_seeder
        mock_seeder.seed.side_effect = Exception("API error")

        result = runner.invoke(seed_app, ["categories"])
        assert result.exit_code == 2
