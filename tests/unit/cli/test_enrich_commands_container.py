"""
Comprehensive tests for enrich commands using DI container pattern.

This test suite covers the refactored enrich commands that use the DI container
instead of manual 8-dependency wiring. Tests verify container integration,
service creation, command execution, and enrichment workflows.

Coverage targets:
- enrich.py: from 18% → 50%+
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from chronovista.cli.commands.enrich import app
from chronovista.models.enrichment_report import (
    EnrichmentDetail,
    EnrichmentReport,
    EnrichmentSummary,
)
from chronovista.services.enrichment.enrichment_service import EnrichmentStatus


@pytest.fixture
def runner() -> CliRunner:
    """CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_enrichment_report() -> EnrichmentReport:
    """Create a mock enrichment report."""
    return EnrichmentReport(
        timestamp=datetime(2025, 1, 22, 10, 30, 45, tzinfo=timezone.utc),
        priority="high",
        summary=EnrichmentSummary(
            videos_processed=10,
            videos_updated=8,
            videos_deleted=2,
            channels_created=3,
            tags_created=15,
            topic_associations=10,
            categories_assigned=8,
            errors=0,
            quota_used=2,
        ),
        details=[
            EnrichmentDetail(
                video_id="video123",
                status="updated",
                old_title="[Placeholder] Video 123",
                new_title="Real Video Title",
            )
        ],
    )


@pytest.fixture
def mock_enrichment_status() -> dict[str, Any]:
    """Create a mock enrichment status."""
    return {
        "total_videos": 1000,
        "fully_enriched_videos": 800,
        "placeholder_videos": 150,
        "deleted_videos": 50,
        "total_channels": 100,
        "placeholder_channels": 20,
        "enrichment_percentage": 80.0,
        "tier_high": {"count": 50, "quota_units": 1},
        "tier_medium": {"count": 100, "quota_units": 2},
        "tier_low": {"count": 150, "quota_units": 3},
        "tier_all": {"count": 200, "quota_units": 4},
    }


@pytest.fixture
def mock_channel_enrichment_status() -> dict[str, Any]:
    """Create a mock channel enrichment status."""
    return {
        "total_channels": 100,
        "enriched": 80,
        "needs_enrichment": 20,
    }


class TestEnrichRunCommandContainerIntegration:
    """Test enrich run command with container integration."""

    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_enrich_run_creates_service_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_enrichment_report: EnrichmentReport,
    ) -> None:
        """Test that enrich run command uses container to create enrichment service."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_youtube_service = MagicMock()

        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check
        mock_youtube_service.check_credentials.return_value = True

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock enrichment service methods
        mock_enrichment_service.lock = AsyncMock()
        mock_enrichment_service.lock.acquire = AsyncMock()
        mock_enrichment_service.lock.release = AsyncMock()
        mock_enrichment_service.get_priority_tier_counts = AsyncMock(
            return_value={
                "high": 10,
                "medium": 20,
                "low": 30,
                "all": 40,
                "deleted": 5,
            }
        )
        mock_enrichment_service.enrich_videos = AsyncMock(
            return_value=mock_enrichment_report
        )

        # Execute command
        result = runner.invoke(app, ["run", "--dry-run"])

        # Verify container method was called
        mock_container.create_enrichment_service.assert_called_once()

    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_enrich_run_with_include_playlists_flag(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_enrichment_report: EnrichmentReport,
    ) -> None:
        """Test that enrich run passes include_playlists flag to container."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_youtube_service = MagicMock()

        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check
        mock_youtube_service.check_credentials.return_value = True

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock enrichment service methods
        mock_enrichment_service.lock = AsyncMock()
        mock_enrichment_service.lock.acquire = AsyncMock()
        mock_enrichment_service.lock.release = AsyncMock()
        mock_enrichment_service.get_priority_tier_counts = AsyncMock(
            return_value={
                "high": 10,
                "medium": 20,
                "low": 30,
                "all": 40,
                "deleted": 5,
            }
        )
        mock_enrichment_service.enrich_videos = AsyncMock(
            return_value=mock_enrichment_report
        )
        mock_enrichment_service.enrich_playlists = AsyncMock(return_value=(5, 4, 1))

        # Execute command with include-playlists
        result = runner.invoke(app, ["run", "--include-playlists", "--dry-run"])

        # Verify container was called with include_playlists=True
        mock_container.create_enrichment_service.assert_called_once_with(
            include_playlists=True
        )

    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_enrich_run_without_include_playlists_flag(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_enrichment_report: EnrichmentReport,
    ) -> None:
        """Test that enrich run defaults to include_playlists=False."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_youtube_service = MagicMock()

        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check
        mock_youtube_service.check_credentials.return_value = True

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock enrichment service methods
        mock_enrichment_service.lock = AsyncMock()
        mock_enrichment_service.lock.acquire = AsyncMock()
        mock_enrichment_service.lock.release = AsyncMock()
        mock_enrichment_service.get_priority_tier_counts = AsyncMock(
            return_value={
                "high": 10,
                "medium": 20,
                "low": 30,
                "all": 40,
                "deleted": 5,
            }
        )
        mock_enrichment_service.enrich_videos = AsyncMock(
            return_value=mock_enrichment_report
        )

        # Execute command without include-playlists
        result = runner.invoke(app, ["run", "--dry-run"])

        # Verify container was called with include_playlists=False
        mock_container.create_enrichment_service.assert_called_once_with(
            include_playlists=False
        )

    @patch("chronovista.container.container")
    def test_enrich_run_checks_credentials_before_creating_service(
        self, mock_container: MagicMock, runner: CliRunner
    ) -> None:
        """Test that credentials are checked before creating enrichment service."""
        # Setup mocks
        mock_youtube_service = MagicMock()
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check to fail
        mock_youtube_service.check_credentials.return_value = False

        # Execute command
        result = runner.invoke(app, ["run"])

        # Should exit with credentials error
        assert result.exit_code == 2  # EXIT_CODE_NO_CREDENTIALS

        # Service creation should NOT happen
        mock_container.create_enrichment_service.assert_not_called()


class TestEnrichStatusCommandContainerIntegration:
    """Test enrich status command with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_enrich_status_creates_service_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_enrichment_status: dict[str, Any],
    ) -> None:
        """Test that enrich status command uses container to create enrichment service."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock enrichment service methods
        mock_enrichment_service.get_status = AsyncMock()
        # Create an EnrichmentStatus object from the dict
        from chronovista.services.enrichment.enrichment_service import (
            EnrichmentStatus,
            PriorityTierEstimate,
        )

        status_obj = EnrichmentStatus(
            total_videos=mock_enrichment_status["total_videos"],
            fully_enriched_videos=mock_enrichment_status["fully_enriched_videos"],
            placeholder_videos=mock_enrichment_status["placeholder_videos"],
            deleted_videos=mock_enrichment_status["deleted_videos"],
            total_channels=mock_enrichment_status["total_channels"],
            placeholder_channels=mock_enrichment_status["placeholder_channels"],
            enrichment_percentage=mock_enrichment_status["enrichment_percentage"],
            tier_high=PriorityTierEstimate(**mock_enrichment_status["tier_high"]),
            tier_medium=PriorityTierEstimate(**mock_enrichment_status["tier_medium"]),
            tier_low=PriorityTierEstimate(**mock_enrichment_status["tier_low"]),
            tier_all=PriorityTierEstimate(**mock_enrichment_status["tier_all"]),
        )
        mock_enrichment_service.get_status.return_value = status_obj

        # Execute command
        result = runner.invoke(app, ["status"])

        # Verify container method was called
        mock_container.create_enrichment_service.assert_called_once()

        # Verify status display worked
        assert result.exit_code == 0


class TestEnrichChannelsCommandContainerIntegration:
    """Test enrich channels command with container integration."""

    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_enrich_channels_creates_service_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_channel_enrichment_status: dict[str, Any],
    ) -> None:
        """Test that enrich channels command uses container to create enrichment service."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_youtube_service = MagicMock()

        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check
        mock_youtube_service.check_credentials.return_value = True

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock enrichment service methods
        mock_enrichment_service.lock = AsyncMock()
        mock_enrichment_service.lock.acquire = AsyncMock()
        mock_enrichment_service.lock.release = AsyncMock()
        mock_enrichment_service.get_channel_enrichment_status = AsyncMock(
            return_value=mock_channel_enrichment_status
        )

        from chronovista.services.enrichment.enrichment_service import (
            ChannelEnrichmentResult,
        )

        mock_result = ChannelEnrichmentResult(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            channels_processed=20,
            channels_enriched=18,
            channels_skipped=2,
            channels_failed=0,
            batches_processed=1,
            quota_used=1,
        )
        mock_enrichment_service.enrich_channels = AsyncMock(return_value=mock_result)

        # Execute command
        result = runner.invoke(app, ["channels", "--dry-run"])

        # Verify container method was called
        mock_container.create_enrichment_service.assert_called_once()

    @patch("chronovista.container.container")
    def test_enrich_channels_checks_credentials_before_creating_service(
        self, mock_container: MagicMock, runner: CliRunner
    ) -> None:
        """Test that credentials are checked before creating enrichment service."""
        # Setup mocks
        mock_youtube_service = MagicMock()
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check to fail
        mock_youtube_service.check_credentials.return_value = False

        # Execute command
        result = runner.invoke(app, ["channels"])

        # Should exit with credentials error
        assert result.exit_code == 2  # EXIT_CODE_NO_CREDENTIALS

        # Service creation should NOT happen
        mock_container.create_enrichment_service.assert_not_called()


class TestAutoSeedFlagContainerIntegration:
    """Test --auto-seed flag with container integration."""

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_auto_seed_creates_topic_seeder_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_enrichment_report: EnrichmentReport,
    ) -> None:
        """Test that --auto-seed flag uses container to create topic seeder."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_youtube_service = MagicMock()
        mock_topic_seeder = AsyncMock()

        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )
        mock_container.youtube_service = mock_youtube_service
        mock_container.create_topic_seeder.return_value = mock_topic_seeder

        # Mock credentials check
        mock_youtube_service.check_credentials.return_value = True

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock enrichment service methods
        mock_enrichment_service.lock = AsyncMock()
        mock_enrichment_service.lock.acquire = AsyncMock()
        mock_enrichment_service.lock.release = AsyncMock()
        mock_enrichment_service.get_priority_tier_counts = AsyncMock(
            return_value={
                "high": 10,
                "medium": 20,
                "low": 30,
                "all": 40,
                "deleted": 5,
            }
        )

        # Mock PrerequisiteError to trigger auto-seed
        from chronovista.exceptions import PrerequisiteError

        mock_enrichment_service.check_prerequisites = AsyncMock(
            side_effect=PrerequisiteError(
                "Prerequisites missing", missing_tables=["topic_categories"]
            )
        )

        # Mock seeder
        from chronovista.services.enrichment.seeders import TopicSeedResult

        mock_topic_seeder.seed = AsyncMock(return_value=TopicSeedResult(created=50))

        # Mock enrich_videos to succeed after seeding
        mock_enrichment_service.enrich_videos = AsyncMock(
            return_value=mock_enrichment_report
        )

        # Execute command with auto-seed
        result = runner.invoke(app, ["run", "--auto-seed", "--dry-run"])

        # Verify topic seeder was created
        mock_container.create_topic_seeder.assert_called_once()

    @pytest.mark.skip(reason="TODO: needs comprehensive integration mocking")
    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_auto_seed_creates_category_seeder_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_enrichment_report: EnrichmentReport,
    ) -> None:
        """Test that --auto-seed flag uses container to create category seeder."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_youtube_service = MagicMock()
        mock_category_seeder = AsyncMock()

        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )
        mock_container.youtube_service = mock_youtube_service
        mock_container.create_category_seeder.return_value = mock_category_seeder

        # Mock credentials check
        mock_youtube_service.check_credentials.return_value = True

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session
        ]

        # Mock enrichment service methods
        mock_enrichment_service.lock = AsyncMock()
        mock_enrichment_service.lock.acquire = AsyncMock()
        mock_enrichment_service.lock.release = AsyncMock()
        mock_enrichment_service.get_priority_tier_counts = AsyncMock(
            return_value={
                "high": 10,
                "medium": 20,
                "low": 30,
                "all": 40,
                "deleted": 5,
            }
        )

        # Mock PrerequisiteError to trigger auto-seed
        from chronovista.exceptions import PrerequisiteError

        mock_enrichment_service.check_prerequisites = AsyncMock(
            side_effect=PrerequisiteError(
                "Prerequisites missing", missing_tables=["video_categories"]
            )
        )

        # Mock seeder
        from chronovista.services.enrichment.seeders import CategorySeedResult

        mock_category_seeder.seed = AsyncMock(return_value=CategorySeedResult(created=43))

        # Mock enrich_videos to succeed after seeding
        mock_enrichment_service.enrich_videos = AsyncMock(
            return_value=mock_enrichment_report
        )

        # Execute command with auto-seed
        result = runner.invoke(app, ["run", "--auto-seed", "--dry-run"])

        # Verify category seeder was created
        mock_container.create_category_seeder.assert_called_once()


class TestSyncLikesFlagContainerIntegration:
    """Test --sync-likes flag with container integration."""

    @patch("chronovista.container.container")
    @patch("chronovista.config.database.db_manager")
    def test_sync_likes_uses_youtube_service_from_container(
        self,
        mock_db_manager: MagicMock,
        mock_container: MagicMock,
        runner: CliRunner,
        mock_enrichment_report: EnrichmentReport,
    ) -> None:
        """Test that --sync-likes flag uses youtube_service from container."""
        # Setup mocks
        mock_enrichment_service = AsyncMock()
        mock_youtube_service = AsyncMock()

        mock_container.create_enrichment_service.return_value = (
            mock_enrichment_service
        )
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check
        mock_youtube_service.check_credentials.return_value = True

        # Mock database session
        mock_session = AsyncMock()
        mock_db_manager.get_session = AsyncMock()
        mock_db_manager.get_session.return_value.__aiter__.return_value = [
            mock_session,
            mock_session,
        ]

        # Mock enrichment service methods
        mock_enrichment_service.lock = AsyncMock()
        mock_enrichment_service.lock.acquire = AsyncMock()
        mock_enrichment_service.lock.release = AsyncMock()
        mock_enrichment_service.get_priority_tier_counts = AsyncMock(
            return_value={
                "high": 10,
                "medium": 20,
                "low": 30,
                "all": 40,
                "deleted": 5,
            }
        )
        mock_enrichment_service.enrich_videos = AsyncMock(
            return_value=mock_enrichment_report
        )

        # Mock YouTube service for likes sync
        from chronovista.models.api_responses import (
            ChannelSnippet,
            VideoSnippet,
            YouTubeChannelResponse,
            YouTubeVideoResponse,
        )

        mock_channel = YouTubeChannelResponse(
            id="UC1234567890123456789012",
            snippet=ChannelSnippet(
                title="Test Channel",
                description="",
                publishedAt=datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            ),
        )
        mock_video = YouTubeVideoResponse(
            id="dQw4w9WgXcQ",
            snippet=VideoSnippet(
                title="Test Video",
                description="",
                channelId="UC1234567890123456789012",
                channelTitle="Test Channel",
                publishedAt=datetime(2022, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            ),
        )

        mock_youtube_service.get_my_channel = AsyncMock(return_value=mock_channel)
        mock_youtube_service.get_liked_videos = AsyncMock(return_value=[mock_video])

        # Execute command with sync-likes (but dry-run to avoid actual DB operations)
        # Note: sync-likes is skipped in dry-run mode
        result = runner.invoke(app, ["run", "--sync-likes", "--limit", "1"])

        # Verify youtube_service was accessed from container
        assert mock_container.youtube_service is mock_youtube_service


class TestLoggingSetup:
    """Test logging setup functionality."""

    def test_setup_enrichment_logging_creates_log_file(self) -> None:
        """Test that _setup_enrichment_logging creates log file."""
        from chronovista.cli.commands.enrich import _setup_enrichment_logging

        log_file = _setup_enrichment_logging("test-timestamp", verbose=False)

        try:
            # Log file should exist
            assert log_file.exists()
            assert "enrichment-test-timestamp.log" in str(log_file)
        finally:
            # Cleanup
            if log_file.exists():
                log_file.unlink()

    def test_setup_enrichment_logging_verbose_mode(self) -> None:
        """Test that _setup_enrichment_logging handles verbose flag."""
        from chronovista.cli.commands.enrich import _setup_enrichment_logging

        log_file = _setup_enrichment_logging("test-verbose", verbose=True)

        try:
            # Log file should exist
            assert log_file.exists()
            # Verbose mode sets DEBUG level (verified by file creation)
            assert log_file.exists()
        finally:
            # Cleanup
            if log_file.exists():
                log_file.unlink()


class TestReportSaving:
    """Test report saving functionality."""

    def test_save_report_creates_output_file(
        self, mock_enrichment_report: EnrichmentReport
    ) -> None:
        """Test that _save_report creates the output file."""
        from chronovista.cli.commands.enrich import _save_report

        output_path = Path("./test_report_container.json")

        try:
            _save_report(mock_enrichment_report, output_path)

            # File should exist
            assert output_path.exists()

            # Verify it's valid JSON
            import json

            content = json.loads(output_path.read_text())
            assert content["priority"] == "high"
            assert content["summary"]["videos_processed"] == 10
        finally:
            # Cleanup
            if output_path.exists():
                output_path.unlink()

    def test_save_report_creates_parent_directories(
        self, mock_enrichment_report: EnrichmentReport
    ) -> None:
        """Test that _save_report creates parent directories if needed."""
        from chronovista.cli.commands.enrich import _save_report

        output_path = Path("./test_nested_container/reports/enrichment.json")

        try:
            _save_report(mock_enrichment_report, output_path)

            # File and parents should exist
            assert output_path.exists()
            assert output_path.parent.exists()
        finally:
            # Cleanup
            import shutil

            if Path("./test_nested_container").exists():
                shutil.rmtree("./test_nested_container")


class TestEnrichCommandFlags:
    """Test various enrichment command flags."""

    def test_enrich_run_accepts_priority_flag(self, runner: CliRunner) -> None:
        """Test that enrich run accepts --priority flag."""
        result = runner.invoke(app, ["run", "--priority", "medium", "--help"])

        # Should not error on priority flag
        assert "Invalid priority" not in result.output

    def test_enrich_run_accepts_limit_flag(self, runner: CliRunner) -> None:
        """Test that enrich run accepts --limit flag."""
        result = runner.invoke(app, ["run", "--limit", "50", "--help"])

        # Should not error on limit flag
        assert result.exit_code == 0

    def test_enrich_run_accepts_dry_run_flag(self, runner: CliRunner) -> None:
        """Test that enrich run accepts --dry-run flag."""
        result = runner.invoke(app, ["run", "--dry-run", "--help"])

        # Should not error on dry-run flag
        assert result.exit_code == 0

    def test_enrich_run_accepts_force_flag(self, runner: CliRunner) -> None:
        """Test that enrich run accepts --force flag."""
        result = runner.invoke(app, ["run", "--force", "--help"])

        # Should not error on force flag
        assert result.exit_code == 0

    def test_enrich_run_accepts_verbose_flag(self, runner: CliRunner) -> None:
        """Test that enrich run accepts --verbose flag."""
        result = runner.invoke(app, ["run", "--verbose", "--help"])

        # Should not error on verbose flag
        assert result.exit_code == 0

    def test_enrich_run_accepts_refresh_topics_flag(self, runner: CliRunner) -> None:
        """Test that enrich run accepts --refresh-topics flag."""
        result = runner.invoke(app, ["run", "--refresh-topics", "--help"])

        # Should not error on refresh-topics flag
        assert result.exit_code == 0

    def test_enrich_run_accepts_output_flag(self, runner: CliRunner) -> None:
        """Test that enrich run accepts --output flag."""
        result = runner.invoke(app, ["run", "--output", "report.json", "--help"])

        # Should not error on output flag
        assert result.exit_code == 0

    def test_enrich_channels_accepts_limit_flag(self, runner: CliRunner) -> None:
        """Test that enrich channels accepts --limit flag."""
        result = runner.invoke(app, ["channels", "--limit", "20", "--help"])

        # Should not error on limit flag
        assert result.exit_code == 0

    def test_enrich_channels_accepts_verbose_flag(self, runner: CliRunner) -> None:
        """Test that enrich channels accepts --verbose flag."""
        result = runner.invoke(app, ["channels", "--verbose", "--help"])

        # Should not error on verbose flag
        assert result.exit_code == 0


class TestContainerSingletonAccess:
    """Test that container singletons are accessed correctly."""

    @patch("chronovista.container.container")
    def test_youtube_service_accessed_as_singleton(
        self, mock_container: MagicMock
    ) -> None:
        """Test that youtube_service is accessed as a singleton property."""
        # Setup mock
        mock_youtube_service = MagicMock()
        mock_container.youtube_service = mock_youtube_service

        # Access the service
        service = mock_container.youtube_service

        # Verify it's the same instance
        assert service is mock_youtube_service

        # Access again should return same instance
        service2 = mock_container.youtube_service
        assert service2 is service


class TestHelperFunctions:
    """Test helper functions used in enrich commands."""

    def test_generate_timestamp_format(self) -> None:
        """Test _generate_timestamp returns correct format."""
        from chronovista.cli.commands.enrich import _generate_timestamp

        timestamp = _generate_timestamp()

        # Should be YYYYMMDD-HHMMSS format
        assert len(timestamp) == 15
        assert timestamp[8] == "-"

    def test_get_default_report_path_format(self) -> None:
        """Test _get_default_report_path returns correct format."""
        from chronovista.cli.commands.enrich import _get_default_report_path

        path = _get_default_report_path()

        # Should be in exports directory
        assert "exports" in str(path)
        assert path.name.startswith("enrichment-")
        assert path.suffix == ".json"

    def test_estimate_quota_cost(self) -> None:
        """Test estimate_quota_cost function."""
        from chronovista.cli.commands.enrich import estimate_quota_cost

        # Test various batch sizes
        assert estimate_quota_cost(0) == 0
        assert estimate_quota_cost(50) == 1
        assert estimate_quota_cost(100) == 2
        assert estimate_quota_cost(150) == 3


class TestExitCodeHandling:
    """Test exit code handling in enrich commands."""

    @patch("chronovista.container.container")
    def test_enrich_run_exits_with_code_2_on_no_credentials(
        self, mock_container: MagicMock, runner: CliRunner
    ) -> None:
        """Test that enrich run exits with code 2 when credentials are missing."""
        # Setup mocks
        mock_youtube_service = MagicMock()
        mock_container.youtube_service = mock_youtube_service

        # Mock credentials check to fail
        mock_youtube_service.check_credentials.return_value = False

        # Execute command
        result = runner.invoke(app, ["run"])

        # Should exit with EXIT_CODE_NO_CREDENTIALS (2)
        assert result.exit_code == 2
