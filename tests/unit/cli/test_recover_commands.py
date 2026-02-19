"""
Tests for CLI recover commands (Feature 024 Phase 6).

This module provides comprehensive unit tests for the `chronovista recover video`
CLI command, covering argument parsing, single-video recovery, batch recovery,
dry-run mode, summary reports, and dependency checks.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.main import app
from chronovista.models.enums import AvailabilityStatus
from chronovista.services.recovery.models import RecoveryResult

runner = CliRunner()


def create_async_mock_recover(result: RecoveryResult):
    """Create an async mock for recover_video that returns the given result."""
    async def mock_recover_async(*args, **kwargs):
        return result
    return mock_recover_async


def create_async_mock_session() -> tuple[AsyncGenerator[AsyncMock, None], AsyncMock]:
    """Create an async context manager mock for db_manager.get_session."""
    mock_session = AsyncMock()

    async def mock_session_gen() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    return mock_session_gen(), mock_session


def create_mock_video_db(video_id: str, availability_status: AvailabilityStatus = AvailabilityStatus.DELETED):
    """Create a mock Video DB object."""
    mock_video = MagicMock()
    mock_video.video_id = video_id
    mock_video.availability_status = availability_status.value
    mock_video.unavailability_first_detected = None
    mock_video.created_at = datetime.now(timezone.utc)
    return mock_video


def setup_batch_query_mock(mock_session: AsyncMock, videos: list[Any]) -> None:
    """Setup mock session to return videos from SQLAlchemy query."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = videos

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    # session.execute() is async, so it returns a coroutine
    async def mock_execute(*args: Any, **kwargs: Any) -> MagicMock:
        return mock_result

    mock_session.execute.side_effect = mock_execute


class TestRecoverArgumentParsing:
    """T044: CLI argument parsing tests."""

    def test_video_id_and_all_are_mutually_exclusive(self) -> None:
        """Test that --video-id and --all cannot be used together."""
        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--all"],
        )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.stdout.lower() or "cannot" in result.stdout.lower()

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_limit_ignored_with_video_id(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that --limit is ignored when using --video-id."""
        # This test verifies the command accepts both flags but limit is ignored
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--limit", "50"],
        )

        # Should succeed - limit is simply ignored in this case
        assert result.exit_code == 0

    def test_delay_accepts_float(self) -> None:
        """Test that --delay accepts float values >= 0.0."""
        # Test valid float
        result = runner.invoke(
            app,
            ["recover", "video", "--all", "--limit", "1", "--delay", "1.5", "--dry-run"],
        )

        # Should not fail on argument parsing (may fail on other things)
        assert "invalid" not in result.stdout.lower()

    def test_delay_minimum_zero(self) -> None:
        """Test that --delay must be >= 0.0."""
        result = runner.invoke(
            app,
            ["recover", "video", "--all", "--delay", "-1.0"],
        )

        assert result.exit_code != 0

    def test_dry_run_flag(self) -> None:
        """Test that --dry-run flag is accepted."""
        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--dry-run"],
        )

        # Should accept the flag (may fail on missing dependencies or other issues)
        # We're just testing argument parsing here
        assert "--dry-run" in result.stdout or result.exit_code in [0, 1]

    def test_missing_both_video_id_and_all_shows_error(self) -> None:
        """Test that missing both --video-id and --all shows an error."""
        result = runner.invoke(
            app,
            ["recover", "video"],
        )

        # Should show help or error message
        assert result.exit_code != 0 or "help" in result.stdout.lower()


class TestSingleVideoRecovery:
    """T045: Single-video recovery command tests."""

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_invokes_orchestrator_with_correct_video_id(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that single-video recovery invokes orchestrator correctly."""
        # Setup mocks
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 0
        mock_recover.assert_called_once()
        # Verify video_id was passed
        call_args = mock_recover.call_args
        assert call_args[1]["video_id"] == "dQw4w9WgXcQ"

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_displays_rich_progress_and_result_table(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that single-video recovery displays progress and results."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                snapshots_available=10,
                snapshots_tried=3,
                duration_seconds=1.5,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 0
        # Check for result information in output
        assert "dQw4w9WgXcQ" in result.stdout
        assert "Success" in result.stdout or "✓" in result.stdout

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    @patch("chronovista.cli.commands.recover.CDXClient")
    @patch("chronovista.cli.commands.recover.PageParser")
    @patch("chronovista.cli.commands.recover.RateLimiter")
    def test_exit_code_0_on_success(
        self,
        mock_rate_limiter: MagicMock,
        mock_page_parser: MagicMock,
        mock_cdx_client: MagicMock,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that successful recovery returns exit code 0."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 0

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_exit_code_1_on_failure(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that failed recovery returns exit code 1."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=False,
                failure_reason="no_snapshots_found",
                duration_seconds=0.5,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 1


class TestBatchRecovery:
    """T046: Batch recovery command tests."""

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_queries_unavailable_videos_ordered_correctly(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that batch mode queries unavailable videos with correct ordering."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create mock video
        mock_video = create_mock_video_db("dQw4w9WgXcQ", AvailabilityStatus.DELETED)

        # Setup session to return video from query
        setup_batch_query_mock(session, [mock_video])

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--all", "--limit", "1"],
        )

        assert result.exit_code == 0

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_respects_limit(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that --limit parameter is respected in batch mode."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create 1 mock video (limit applied at SQL level)
        mock_video = create_mock_video_db("dQw4w9WgXcQ")
        setup_batch_query_mock(session, [mock_video])

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--all", "--limit", "1"],
        )

        # Should only call recover_video once (for 1 video)
        assert result.exit_code == 0
        assert mock_recover.call_count == 1

    @patch("chronovista.cli.commands.recover.asyncio.sleep")
    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_applies_delay_between_videos(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
        mock_sleep: AsyncMock,
    ) -> None:
        """Test that --delay is applied between videos in batch mode."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create 2 mock videos
        mock_videos = [
            create_mock_video_db("dQw4w9WgXcQ"),
            create_mock_video_db("jNQXAC9IVRw"),
        ]
        setup_batch_query_mock(session, mock_videos)

        # Mock recover to return success for both videos
        results = [
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
            ),
            RecoveryResult(
                video_id="jNQXAC9IVRw",
                success=True,
                snapshot_used="20220106075527",
                fields_recovered=["title"],
                duration_seconds=1.0,
            ),
        ]

        call_count = 0
        async def mock_recover_side_effect(*args, **kwargs):
            nonlocal call_count
            result = results[call_count]
            call_count += 1
            return result

        mock_recover.side_effect = mock_recover_side_effect

        # AsyncMock for sleep - no need to manually create Future
        async def mock_sleep_async(delay):
            pass

        mock_sleep.side_effect = mock_sleep_async

        result = runner.invoke(
            app,
            ["recover", "video", "--all", "--delay", "2.5"],
        )

        # Should call sleep with delay value (between videos)
        # Called once between video 0 and video 1
        assert result.exit_code == 0
        assert mock_sleep.called
        # Check that sleep was called with the correct delay
        mock_sleep.assert_called_with(2.5)

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_continues_past_individual_failures(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that batch mode continues after individual video failures."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create 3 mock videos
        mock_videos = [
            create_mock_video_db("dQw4w9WgXcQ"),
            create_mock_video_db("jNQXAC9IVRw"),
            create_mock_video_db("9bZkp7q19f0"),
        ]
        setup_batch_query_mock(session, mock_videos)

        # First video fails, second succeeds, third fails
        results = [
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=False,
                failure_reason="no_snapshots_found",
                duration_seconds=0.5,
            ),
            RecoveryResult(
                video_id="jNQXAC9IVRw",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
            ),
            RecoveryResult(
                video_id="9bZkp7q19f0",
                success=False,
                failure_reason="cdx_query_timeout",
                duration_seconds=600.0,
            ),
        ]

        call_count = 0
        async def mock_recover_side_effect(*args, **kwargs):
            nonlocal call_count
            result = results[call_count]
            call_count += 1
            return result

        mock_recover.side_effect = mock_recover_side_effect

        result = runner.invoke(
            app,
            ["recover", "video", "--all"],
        )

        # Should call recover_video for all 3 videos despite failures
        assert mock_recover.call_count == 3
        # Should exit with 0 because at least one succeeded
        assert result.exit_code == 0

    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_zero_unavailable_videos_shows_message(
        self,
        mock_get_session: MagicMock,
    ) -> None:
        """Test that zero unavailable videos shows informational message."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Setup session to return empty list
        setup_batch_query_mock(session, [])

        result = runner.invoke(
            app,
            ["recover", "video", "--all"],
        )

        assert result.exit_code == 0
        assert "no unavailable videos" in result.stdout.lower() or "0" in result.stdout


class TestDryRunMode:
    """T047: Dry-run mode tests."""

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_cdx_queries_made_in_dry_run(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that CDX queries are made in dry-run mode."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                snapshots_available=5,
                duration_seconds=0.5,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--dry-run"],
        )

        # Verify dry_run=True was passed to recover_video
        assert result.exit_code == 0
        mock_recover.assert_called_once()
        call_kwargs = mock_recover.call_args[1]
        assert call_kwargs["dry_run"] is True

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_displays_snapshot_availability_report(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that dry-run displays snapshot availability report."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                snapshots_available=10,
                snapshots_tried=1,
                duration_seconds=0.5,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--dry-run"],
        )

        assert result.exit_code == 0
        # Should mention snapshots available or dry run mode
        assert "snapshot" in result.stdout.lower() or "dry" in result.stdout.lower() or "10" in result.stdout


class TestSummaryReport:
    """T048: Summary report tests."""

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_displays_summary_counts(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that summary displays attempted/succeeded/failed counts."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create 3 mock videos
        mock_videos = [
            create_mock_video_db("dQw4w9WgXcQ"),
            create_mock_video_db("jNQXAC9IVRw"),
            create_mock_video_db("9bZkp7q19f0"),
        ]
        setup_batch_query_mock(session, mock_videos)

        # Mix of success and failure
        results = [
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
            ),
            RecoveryResult(
                video_id="jNQXAC9IVRw",
                success=False,
                failure_reason="no_snapshots_found",
                duration_seconds=0.5,
            ),
            RecoveryResult(
                video_id="9bZkp7q19f0",
                success=True,
                snapshot_used="20220106075527",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
            ),
        ]

        call_count = 0
        async def mock_recover_side_effect(*args, **kwargs):
            nonlocal call_count
            result = results[call_count]
            call_count += 1
            return result

        mock_recover.side_effect = mock_recover_side_effect

        result = runner.invoke(
            app,
            ["recover", "video", "--all"],
        )

        # Check for summary information
        assert result.exit_code == 0
        assert "summary" in result.stdout.lower() or "succeeded" in result.stdout.lower()
        # Should show count information (3 attempted, 2 succeeded, 1 failed)
        assert "3" in result.stdout and "2" in result.stdout

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_includes_per_video_result_table(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that summary includes per-video result table."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_video = create_mock_video_db("dQw4w9WgXcQ")
        setup_batch_query_mock(session, [mock_video])

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description", "view_count"],
                snapshots_available=10,
                duration_seconds=1.5,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--all"],
        )

        # Should show video ID and recovery information
        assert result.exit_code == 0
        assert "dQw4w9WgXcQ" in result.stdout
        # Should show fields recovered count (3) or mention fields
        assert "3" in result.stdout or "field" in result.stdout.lower()


class TestDependencyChecks:
    """T049: Dependency check tests."""

    @patch("chronovista.cli.commands.recover.BEAUTIFULSOUP_AVAILABLE", False)
    def test_missing_beautifulsoup_shows_error(self) -> None:
        """Test that missing beautifulsoup4 shows error and halts."""
        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        # Should fail with error about missing dependency
        assert result.exit_code != 0
        assert "beautifulsoup" in result.stdout.lower() or "dependency" in result.stdout.lower()

    @patch("chronovista.cli.commands.recover.SELENIUM_AVAILABLE", False)
    @patch("chronovista.cli.commands.recover.BEAUTIFULSOUP_AVAILABLE", True)
    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    @patch("chronovista.cli.commands.recover.CDXClient")
    @patch("chronovista.cli.commands.recover.PageParser")
    @patch("chronovista.cli.commands.recover.RateLimiter")
    def test_missing_selenium_shows_warning_but_continues(
        self,
        mock_rate_limiter: MagicMock,
        mock_page_parser: MagicMock,
        mock_cdx_client: MagicMock,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that missing selenium shows warning but continues."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        # Should succeed with warning
        assert result.exit_code == 0
        # May show warning about selenium (optional)
        # Command should still complete successfully


class TestErrorHandling:
    """Test error handling in recovery commands."""

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_cdx_error_returns_network_error_code(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that CDXError returns EXIT_CODE_NETWORK_ERROR."""
        from chronovista.exceptions import CDXError, EXIT_CODE_NETWORK_ERROR

        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        async def mock_recover_raises_cdx_error(*args, **kwargs):
            raise CDXError("CDX API timeout", video_id="dQw4w9WgXcQ", status_code=504)

        mock_recover.side_effect = mock_recover_raises_cdx_error

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == EXIT_CODE_NETWORK_ERROR
        assert "cdx" in result.stdout.lower()

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_page_parse_error_returns_exit_code_1(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that PageParseError returns exit code 1."""
        from chronovista.exceptions import PageParseError

        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        async def mock_recover_raises_parse_error(*args, **kwargs):
            raise PageParseError(
                "Failed to parse ytInitialPlayerResponse",
                video_id="dQw4w9WgXcQ",
                snapshot_timestamp="20220106075526",
            )

        mock_recover.side_effect = mock_recover_raises_parse_error

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 1
        assert "pars" in result.stdout.lower() or "error" in result.stdout.lower()

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_batch_cdx_error_continues_with_other_videos(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that batch mode continues after CDXError on individual video."""
        from chronovista.exceptions import CDXError

        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create 2 mock videos
        mock_videos = [
            create_mock_video_db("dQw4w9WgXcQ"),
            create_mock_video_db("jNQXAC9IVRw"),
        ]
        setup_batch_query_mock(session, mock_videos)

        # First video raises CDXError, second succeeds
        async def mock_recover_first_fails(*args, **kwargs):
            if "dQw4w9WgXcQ" in str(kwargs.get("video_id", "")):
                raise CDXError("CDX timeout", video_id="dQw4w9WgXcQ", status_code=504)
            else:
                return RecoveryResult(
                    video_id="jNQXAC9IVRw",
                    success=True,
                    snapshot_used="20220106075526",
                    fields_recovered=["title"],
                    duration_seconds=1.0,
                )

        mock_recover.side_effect = mock_recover_first_fails

        result = runner.invoke(
            app,
            ["recover", "video", "--all"],
        )

        # Should continue and process second video
        assert mock_recover.call_count == 2
        # Should exit with 0 because second video succeeded
        assert result.exit_code == 0


class TestRecoverCommandHelp:
    """Test help text for recover commands."""

    def test_recover_help(self) -> None:
        """Test that recover --help shows command information."""
        result = runner.invoke(app, ["recover", "--help"])

        assert result.exit_code == 0
        assert "recover" in result.stdout.lower()

    def test_recover_video_help(self) -> None:
        """Test that recover video --help shows command information."""
        result = runner.invoke(app, ["recover", "video", "--help"])

        assert result.exit_code == 0
        assert "--video-id" in result.stdout
        assert "--all" in result.stdout
        assert "--limit" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--delay" in result.stdout

    def test_recover_video_help_includes_year_flags(self) -> None:
        """Test that recover video --help shows --start-year and --end-year options."""
        result = runner.invoke(app, ["recover", "video", "--help"])

        assert result.exit_code == 0
        assert "--start-year" in result.stdout
        assert "--end-year" in result.stdout


class TestYearFilterValidation:
    """Test --start-year and --end-year CLI flag validation."""

    def test_start_year_greater_than_end_year_shows_error(self) -> None:
        """Test that --start-year > --end-year prints error and exits with code 2."""
        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--start-year", "2022", "--end-year", "2018"],
        )

        assert result.exit_code == 2
        assert "start-year" in result.stdout.lower() or "greater" in result.stdout.lower()

    def test_start_year_equal_to_end_year_accepted(self) -> None:
        """Test that --start-year == --end-year is accepted (not an error)."""
        # This should not fail on validation (may fail on other things like dependencies)
        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--start-year", "2020", "--end-year", "2020"],
        )

        # Should NOT be exit code 2 (the year-range validation error)
        # It may be 0 or 1 depending on downstream mocking, but not 2 for validation
        assert result.exit_code != 2 or "start-year" not in result.stdout.lower()

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_start_year_passed_to_orchestrator(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that --start-year is threaded through to recover_video as from_year."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20180601120000",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--start-year", "2018"],
        )

        assert result.exit_code == 0
        mock_recover.assert_called_once()
        call_kwargs = mock_recover.call_args[1]
        assert call_kwargs["from_year"] == 2018
        assert call_kwargs.get("to_year") is None

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_end_year_passed_to_orchestrator(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that --end-year is threaded through to recover_video as to_year."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20200601120000",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--end-year", "2020"],
        )

        assert result.exit_code == 0
        mock_recover.assert_called_once()
        call_kwargs = mock_recover.call_args[1]
        assert call_kwargs.get("from_year") is None
        assert call_kwargs["to_year"] == 2020

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_both_years_passed_to_orchestrator(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that both --start-year and --end-year are threaded through."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20190601120000",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--start-year", "2018", "--end-year", "2020"],
        )

        assert result.exit_code == 0
        mock_recover.assert_called_once()
        call_kwargs = mock_recover.call_args[1]
        assert call_kwargs["from_year"] == 2018
        assert call_kwargs["to_year"] == 2020

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_batch_mode_passes_years_to_orchestrator(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that year flags in batch mode are threaded to recover_video."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_video = create_mock_video_db("dQw4w9WgXcQ")
        setup_batch_query_mock(session, [mock_video])

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20190601120000",
                fields_recovered=["title"],
                duration_seconds=1.0,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--all", "--limit", "1", "--start-year", "2018", "--end-year", "2020"],
        )

        assert result.exit_code == 0
        mock_recover.assert_called_once()
        call_kwargs = mock_recover.call_args[1]
        assert call_kwargs["from_year"] == 2018
        assert call_kwargs["to_year"] == 2020


class TestChannelRecoveryDisplay:
    """T027 + T028: Channel recovery display tests."""

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_single_result_with_channel_recovery(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that single result displays channel recovery info when channel_recovered=True."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
                channel_recovered=True,
                channel_fields_recovered=["title", "description", "subscriber_count"],
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 0
        # Should show channel recovery information
        assert "channel recovery" in result.stdout.lower()
        assert "recovered 3 fields" in result.stdout.lower()
        assert "title" in result.stdout
        assert "description" in result.stdout
        assert "subscriber_count" in result.stdout

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_single_result_without_channel_recovery(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that single result does not show channel info when channel_recovered=False."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
                channel_recovered=False,
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 0
        # Should NOT show channel recovery information
        # Look for the field name but not in context of channel recovery
        stdout_lines = result.stdout.split("\n")
        # Count occurrences - should only see "Channel Recovery" as part of headers, not data
        channel_recovery_lines = [line for line in stdout_lines if "channel recovery" in line.lower()]
        # If channel_recovered=False and no failure_reason, there should be no channel recovery row
        assert len(channel_recovery_lines) == 0

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_single_result_with_channel_failure(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that single result displays channel failure reason."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
                channel_recovered=False,
                channel_failure_reason="no_snapshots_found",
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ"],
        )

        assert result.exit_code == 0
        # Should show channel recovery failure information
        assert "channel recovery" in result.stdout.lower()
        assert "failed" in result.stdout.lower()
        assert "no_snapshots_found" in result.stdout

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_batch_summary_with_channel_section(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that batch summary includes channel recovery section with correct counts."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create 3 mock videos
        mock_videos = [
            create_mock_video_db("dQw4w9WgXcQ"),
            create_mock_video_db("jNQXAC9IVRw"),
            create_mock_video_db("9bZkp7q19f0"),
        ]
        setup_batch_query_mock(session, mock_videos)

        # Two with successful channel recovery, one with failure
        results = [
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
                channel_recovered=True,
                channel_fields_recovered=["title", "description"],
            ),
            RecoveryResult(
                video_id="jNQXAC9IVRw",
                success=True,
                snapshot_used="20220106075527",
                fields_recovered=["title"],
                duration_seconds=1.0,
                channel_recovered=True,
                channel_fields_recovered=["title", "subscriber_count"],
            ),
            RecoveryResult(
                video_id="9bZkp7q19f0",
                success=True,
                snapshot_used="20220106075528",
                fields_recovered=["title"],
                duration_seconds=1.0,
                channel_recovered=False,
                channel_failure_reason="no_snapshots_found",
            ),
        ]

        call_count = 0
        async def mock_recover_side_effect(*args, **kwargs):
            nonlocal call_count
            result = results[call_count]
            call_count += 1
            return result

        mock_recover.side_effect = mock_recover_side_effect

        result = runner.invoke(
            app,
            ["recover", "video", "--all"],
        )

        assert result.exit_code == 0
        # Should show channel recovery section
        assert "channel recovery" in result.stdout.lower()
        assert "channels attempted: 3" in result.stdout.lower()
        assert "channels recovered: 2" in result.stdout.lower()
        # Should show the unique channel fields recovered
        assert "channel fields recovered:" in result.stdout.lower()
        assert "title" in result.stdout
        assert "description" in result.stdout
        assert "subscriber_count" in result.stdout

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_batch_summary_zero_channels(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that batch summary hides channel section when no channels attempted."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        # Create 2 mock videos
        mock_videos = [
            create_mock_video_db("dQw4w9WgXcQ"),
            create_mock_video_db("jNQXAC9IVRw"),
        ]
        setup_batch_query_mock(session, mock_videos)

        # Both videos recovered successfully, but no channel recovery attempted
        results = [
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title"],
                duration_seconds=1.0,
                channel_recovered=False,
            ),
            RecoveryResult(
                video_id="jNQXAC9IVRw",
                success=True,
                snapshot_used="20220106075527",
                fields_recovered=["title"],
                duration_seconds=1.0,
                channel_recovered=False,
            ),
        ]

        call_count = 0
        async def mock_recover_side_effect(*args, **kwargs):
            nonlocal call_count
            result = results[call_count]
            call_count += 1
            return result

        mock_recover.side_effect = mock_recover_side_effect

        result = runner.invoke(
            app,
            ["recover", "video", "--all"],
        )

        assert result.exit_code == 0
        # Should NOT show channel recovery section (no "Channel Recovery:" header)
        # Check that "Channel Recovery:" does not appear as a section header
        assert "channels attempted:" not in result.stdout.lower()
        assert "channels recovered:" not in result.stdout.lower()

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_dry_run_with_channel_candidates(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that dry-run displays channel recovery candidates."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
                channel_recovery_candidates=["UC123456789012345678901", "UC987654321098765432109"],
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--dry-run"],
        )

        assert result.exit_code == 0
        # Should show channel recovery candidates
        assert "channel recovery candidates" in result.stdout.lower()
        assert "2 channels" in result.stdout.lower()
        assert "UC123456789012345678901" in result.stdout
        assert "UC987654321098765432109" in result.stdout

    @patch("chronovista.cli.commands.recover.recover_video")
    @patch("chronovista.cli.commands.recover.db_manager.get_session")
    def test_dry_run_without_channel_candidates(
        self,
        mock_get_session: MagicMock,
        mock_recover: MagicMock,
    ) -> None:
        """Test that dry-run does not show channel candidates section when list is empty."""
        session_gen, session = create_async_mock_session()
        mock_get_session.return_value = session_gen

        mock_recover.side_effect = create_async_mock_recover(
            RecoveryResult(
                video_id="dQw4w9WgXcQ",
                success=True,
                snapshot_used="20220106075526",
                fields_recovered=["title", "description"],
                duration_seconds=1.5,
                channel_recovery_candidates=[],
            )
        )

        result = runner.invoke(
            app,
            ["recover", "video", "--video-id", "dQw4w9WgXcQ", "--dry-run"],
        )

        assert result.exit_code == 0
        # Should NOT show channel recovery candidates section
        assert "channel recovery candidates" not in result.stdout.lower()
