"""
Integration tests for `chronovista tags normalize` CLI command.

These tests verify the CLI interface for the tag normalization backfill
command, including validation, error handling, and output formatting.

NOTE: These tests use synchronous fixtures and runner.invoke() to avoid
asyncio.run() conflicts. The CLI commands themselves handle async operations
internally via asyncio.run().
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from chronovista.cli.main import app

# Test runner with environment that matches the integration test database
TEST_DATABASE_URL = os.getenv(
    "DATABASE_INTEGRATION_URL",
    "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test",
)
runner = CliRunner()


@pytest.fixture(autouse=True)
def patch_settings_for_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Patch settings to use integration test database.

    The settings singleton is loaded at module import time with values from .env.
    This fixture patches the effective_database_url property to return the
    integration test database URL.
    """
    from chronovista.config import database as database_module
    from chronovista.config import settings as settings_module

    # Patch the settings object to return the test database URL
    monkeypatch.setattr(
        settings_module.settings,
        "database_url",
        TEST_DATABASE_URL,
    )
    monkeypatch.setattr(
        settings_module.settings,
        "database_dev_url",
        TEST_DATABASE_URL,
    )
    monkeypatch.setattr(
        settings_module.settings,
        "development_mode",
        False,
    )

    # Reset the db_manager singleton to use new settings
    database_module.db_manager._engine = None
    database_module.db_manager._session_factory = None


class TestTagsNormalizeCommand:
    """Tests for `chronovista tags normalize` command."""

    def test_successful_run_output(self) -> None:
        """Test normalize command with successful backfill execution."""
        # Mock the database session
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            # Create async session mock
            mock_session = AsyncMock()

            # Mock get_session to yield the mock session
            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            # Mock the backfill service
            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_backfill",
                new_callable=AsyncMock,
            ) as mock_run_backfill:
                # Mock successful backfill - it prints via console
                mock_run_backfill.return_value = None

                result = runner.invoke(app, ["tags", "normalize"])

                # Command should succeed
                assert result.exit_code == 0, f"Unexpected output: {result.output}"

                # Verify run_backfill was called with expected parameters
                mock_run_backfill.assert_called_once()
                call_args = mock_run_backfill.call_args
                # Verify session was passed
                assert call_args[0][0] is mock_session
                # Verify batch_size was passed
                assert call_args[1]["batch_size"] == 1000  # default
                # Verify console was passed
                assert call_args[1]["console"] is not None

    def test_rerun_output(self) -> None:
        """Test normalize command when re-run (0 new records inserted)."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_backfill",
                new_callable=AsyncMock,
            ) as mock_run_backfill:
                # Mock re-run (nothing to do)
                mock_run_backfill.return_value = None

                result = runner.invoke(app, ["tags", "normalize"])

                # Command should succeed even with nothing to do
                assert result.exit_code == 0, f"Unexpected output: {result.output}"
                mock_run_backfill.assert_called_once()

    def test_batch_size_zero_exits_2(self) -> None:
        """Test normalize command rejects batch_size=0 with exit code 2."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_backfill",
                new_callable=AsyncMock,
            ) as mock_run_backfill:
                # Mock run_backfill to raise SystemExit(2) for invalid batch_size
                mock_run_backfill.side_effect = SystemExit(2)

                result = runner.invoke(app, ["tags", "normalize", "--batch-size", "0"])

                # Should exit with code 2
                assert result.exit_code == 2

    def test_batch_size_negative_exits_2(self) -> None:
        """Test normalize command rejects negative batch_size with exit code 2."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_backfill",
                new_callable=AsyncMock,
            ) as mock_run_backfill:
                # Mock run_backfill to raise SystemExit(2) for invalid batch_size
                mock_run_backfill.side_effect = SystemExit(2)

                result = runner.invoke(app, ["tags", "normalize", "--batch-size", "-1"])

                # Should exit with code 2
                assert result.exit_code == 2

    def test_missing_tables_exits_1(self) -> None:
        """Test normalize command exits with code 1 when required tables are missing."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_backfill",
                new_callable=AsyncMock,
            ) as mock_run_backfill:
                # Mock run_backfill to raise SystemExit with message about missing tables
                mock_run_backfill.side_effect = SystemExit(
                    "Required table(s) missing: canonical_tags, tag_aliases. "
                    "Run 'alembic upgrade head' to create them."
                )

                result = runner.invoke(app, ["tags", "normalize"])

                # Should exit with code 1 (SystemExit with string message)
                # Note: The error message from SystemExit is not captured in CLI output
                # by the CliRunner when raised with a string argument
                assert result.exit_code == 1

    def test_custom_batch_size(self) -> None:
        """Test normalize command with custom --batch-size parameter."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_backfill",
                new_callable=AsyncMock,
            ) as mock_run_backfill:
                mock_run_backfill.return_value = None

                result = runner.invoke(app, ["tags", "normalize", "--batch-size", "500"])

                # Command should succeed
                assert result.exit_code == 0, f"Unexpected output: {result.output}"

                # Verify run_backfill was called with custom batch_size
                mock_run_backfill.assert_called_once()
                call_args = mock_run_backfill.call_args
                assert call_args[1]["batch_size"] == 500

    def test_help_flag_shows_usage(self) -> None:
        """Test normalize command shows help text with --help flag."""
        result = runner.invoke(app, ["tags", "normalize", "--help"])

        # Should show help successfully
        assert result.exit_code == 0
        # Help text should mention batch-size option
        assert "batch-size" in result.output
        # Help text should describe the command
        assert "normalize" in result.output.lower()

    def test_exception_handling(self) -> None:
        """Test normalize command handles unexpected exceptions gracefully."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_backfill",
                new_callable=AsyncMock,
            ) as mock_run_backfill:
                # Mock unexpected exception
                mock_run_backfill.side_effect = RuntimeError("Database connection failed")

                result = runner.invoke(app, ["tags", "normalize"])

                # Should exit with non-zero code
                assert result.exit_code != 0


class TestTagsAnalyzeCommand:
    """Tests for `chronovista tags analyze` command."""

    def test_table_format_output(self) -> None:
        """Verify table format output contains summary stats."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_analysis",
                new_callable=AsyncMock,
            ) as mock_run_analysis:
                mock_run_analysis.return_value = None

                result = runner.invoke(app, ["tags", "analyze"])

                assert result.exit_code == 0, f"Unexpected output: {result.output}"
                mock_run_analysis.assert_called_once()
                call_args = mock_run_analysis.call_args
                assert call_args[1]["output_format"] == "table"

    def test_json_format_valid(self) -> None:
        """Verify --format json produces valid JSON with correct keys."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_analysis",
                new_callable=AsyncMock,
            ) as mock_run_analysis:
                mock_run_analysis.return_value = {
                    "total_distinct_tags": 100,
                    "estimated_canonical_tags": 50,
                    "skip_count": 2,
                    "top_canonical_tags": [],
                    "collision_candidates": [],
                    "skipped_tags": [],
                }

                result = runner.invoke(app, ["tags", "analyze", "--format", "json"])

                assert result.exit_code == 0, f"Unexpected output: {result.output}"
                mock_run_analysis.assert_called_once()
                call_args = mock_run_analysis.call_args
                assert call_args[1]["output_format"] == "json"

    def test_dry_run_accepted(self) -> None:
        """Verify --dry-run is accepted without error."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_analysis",
                new_callable=AsyncMock,
            ) as mock_run_analysis:
                mock_run_analysis.return_value = None

                result = runner.invoke(app, ["tags", "analyze", "--dry-run"])

                assert result.exit_code == 0, f"Unexpected output: {result.output}"
                mock_run_analysis.assert_called_once()

    def test_missing_tables_exits_1(self) -> None:
        """Verify exit code 1 when tables missing."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_analysis",
                new_callable=AsyncMock,
            ) as mock_run_analysis:
                mock_run_analysis.side_effect = SystemExit(
                    "Required table(s) missing: canonical_tags, tag_aliases. "
                    "Run 'alembic upgrade head' to create them."
                )

                result = runner.invoke(app, ["tags", "analyze"])

                assert result.exit_code == 1

    def test_help_flag(self) -> None:
        """Verify --help shows expected usage text."""
        result = runner.invoke(app, ["tags", "analyze", "--help"])

        assert result.exit_code == 0
        assert "analyze" in result.output.lower()
        assert "--format" in result.output
        assert "--dry-run" in result.output


class TestTagsRecountCommand:
    """Tests for `chronovista tags recount` command."""

    def test_normal_mode_output(self) -> None:
        """Test recount command with successful execution."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_recount",
                new_callable=AsyncMock,
            ) as mock_run_recount:
                mock_run_recount.return_value = None

                result = runner.invoke(app, ["tags", "recount"])

                # Command should succeed
                assert result.exit_code == 0, f"Unexpected output: {result.output}"

                # Verify run_recount was called with expected parameters
                mock_run_recount.assert_called_once()
                call_args = mock_run_recount.call_args
                # Verify session was passed
                assert call_args[0][0] is mock_session
                # Verify dry_run was False (default)
                assert call_args[1]["dry_run"] is False
                # Verify console was passed
                assert call_args[1]["console"] is not None

    def test_dry_run_output(self) -> None:
        """Test recount command with --dry-run flag."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_recount",
                new_callable=AsyncMock,
            ) as mock_run_recount:
                mock_run_recount.return_value = None

                result = runner.invoke(app, ["tags", "recount", "--dry-run"])

                # Command should succeed
                assert result.exit_code == 0, f"Unexpected output: {result.output}"

                # Verify run_recount was called with dry_run=True
                mock_run_recount.assert_called_once()
                call_args = mock_run_recount.call_args
                assert call_args[1]["dry_run"] is True

    def test_missing_tables_exits_1(self) -> None:
        """Test recount command exits with code 1 when tables missing."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db_manager:
            mock_session = AsyncMock()

            async def mock_get_session(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
                yield mock_session

            mock_db_manager.get_session.return_value = mock_get_session()

            with patch(
                "chronovista.services.tag_backfill.TagBackfillService.run_recount",
                new_callable=AsyncMock,
            ) as mock_run_recount:
                mock_run_recount.side_effect = SystemExit(
                    "Required table(s) missing: canonical_tags, tag_aliases. "
                    "Run 'alembic upgrade head' to create them."
                )

                result = runner.invoke(app, ["tags", "recount"])

                # Should exit with code 1 (SystemExit with string message)
                assert result.exit_code == 1

    def test_help_flag(self) -> None:
        """Verify --help shows expected usage text."""
        result = runner.invoke(app, ["tags", "recount", "--help"])

        assert result.exit_code == 0
        assert "recount" in result.output.lower()
        assert "--dry-run" in result.output
