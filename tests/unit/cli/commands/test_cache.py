"""
Unit tests for cache CLI commands.

Comprehensive test coverage for the `chronovista cache warm` command
including dry-run mode, type filtering, quality selection, limit/delay
parameters, exit codes, and error handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from chronovista.cli.commands import cache as cache_module
from chronovista.models.enums import ImageQuality
from chronovista.services.image_cache import CacheStats, WarmResult

# Create test apps that wrap each command
test_warm_app = typer.Typer()
test_warm_app.command(name="warm")(cache_module.warm)

test_status_app = typer.Typer()
test_status_app.command(name="status")(cache_module.status)

test_purge_app = typer.Typer()
test_purge_app.command(name="purge")(cache_module.purge)

runner = CliRunner()


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_image_cache_service():
    """Create a mock ImageCacheService."""
    service = MagicMock()

    # Mock warm_channels method
    async def mock_warm_channels(*args, **kwargs):
        return WarmResult(
            downloaded=10,
            skipped=5,
            failed=0,
            no_url=2,
            total=17,
        )

    service.warm_channels = AsyncMock(side_effect=mock_warm_channels)

    # Mock warm_videos method
    async def mock_warm_videos(*args, **kwargs):
        return WarmResult(
            downloaded=50,
            skipped=25,
            failed=0,
            no_url=0,
            total=75,
        )

    service.warm_videos = AsyncMock(side_effect=mock_warm_videos)

    return service


# ═══════════════════════════════════════════════════════════════════════════
# T021: CLI Warm Command Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCacheWarmCommand:
    """Unit tests for the `cache warm` CLI command."""

    def test_warm_dry_run_shows_counts_without_downloading(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm --dry-run` shows counts without downloading."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, ["--dry-run"])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout
        assert "Dry run" in output or "dry" in output.lower()

        # Verify service methods were called with dry_run=True
        mock_image_cache_service.warm_channels.assert_called_once()
        call_kwargs = mock_image_cache_service.warm_channels.call_args.kwargs
        assert call_kwargs["dry_run"] is True

        mock_image_cache_service.warm_videos.assert_called_once()
        call_kwargs = mock_image_cache_service.warm_videos.call_args.kwargs
        assert call_kwargs["dry_run"] is True

    def test_warm_type_channels_only_warms_channels(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm --type channels` only warms channels."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [ "--type", "channels"])

        assert result.exit_code == 0

        # Verify only channels were warmed
        mock_image_cache_service.warm_channels.assert_called_once()
        mock_image_cache_service.warm_videos.assert_not_called()

    def test_warm_type_videos_only_warms_videos(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm --type videos` only warms videos."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [ "--type", "videos"])

        assert result.exit_code == 0

        # Verify only videos were warmed
        mock_image_cache_service.warm_videos.assert_called_once()
        mock_image_cache_service.warm_channels.assert_not_called()

    def test_warm_type_all_warms_both(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm --type all` warms both channels and videos."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [ "--type", "all"])

        assert result.exit_code == 0

        # Verify both channels and videos were warmed
        mock_image_cache_service.warm_channels.assert_called_once()
        mock_image_cache_service.warm_videos.assert_called_once()

    def test_warm_limit_passes_limit_to_service(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm --limit 5` passes limit to service."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [ "--limit", "5"])

        assert result.exit_code == 0

        # Verify limit was passed to both service methods
        call_kwargs = mock_image_cache_service.warm_channels.call_args.kwargs
        assert call_kwargs["limit"] == 5

        call_kwargs = mock_image_cache_service.warm_videos.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_warm_delay_passes_delay_to_service(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm --delay 1.0` passes delay to service."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [ "--delay", "1.0"])

        assert result.exit_code == 0

        # Verify delay was passed to both service methods
        call_kwargs = mock_image_cache_service.warm_channels.call_args.kwargs
        assert call_kwargs["delay"] == 1.0

        call_kwargs = mock_image_cache_service.warm_videos.call_args.kwargs
        assert call_kwargs["delay"] == 1.0

    def test_warm_type_invalid_exits_with_code_2(self):
        """Test `warm --type invalid` exits with code 2."""
        result = runner.invoke(test_warm_app, [ "--type", "invalid"])

        assert result.exit_code == 2
        # Rich console output goes to output, not stdout
        output = result.output if result.output else result.stdout
        assert "Invalid --type" in output or "invalid" in output.lower()

    def test_warm_quality_invalid_exits_with_code_2(self):
        """Test `warm --quality invalid` exits with code 2."""
        result = runner.invoke(test_warm_app, [ "--quality", "invalid"])

        assert result.exit_code == 2
        # Rich console output goes to output, not stdout
        output = result.output if result.output else result.stdout
        assert "Invalid --quality" in output or "invalid" in output.lower()

    def test_warm_with_failed_downloads_exits_with_code_1(
        self, mock_db_session
    ):
        """Test `warm` with failed downloads exits with code 1."""

        # Create service that reports failures
        service_with_failures = MagicMock()

        async def mock_warm_channels_with_failures(*args, **kwargs):
            return WarmResult(
                downloaded=5,
                skipped=3,
                failed=2,  # Some failures
                no_url=1,
                total=11,
            )

        service_with_failures.warm_channels = AsyncMock(
            side_effect=mock_warm_channels_with_failures
        )

        async def mock_warm_videos_with_failures(*args, **kwargs):
            return WarmResult(
                downloaded=10,
                skipped=5,
                failed=3,  # Some failures
                no_url=0,
                total=18,
            )

        service_with_failures.warm_videos = AsyncMock(
            side_effect=mock_warm_videos_with_failures
        )

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service_with_failures,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [])

        assert result.exit_code == 1

    def test_warm_with_all_successes_exits_with_code_0(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm` with all successes exits with code 0."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [])

        assert result.exit_code == 0

    def test_warm_null_thumbnail_url_reported_as_no_url(
        self, mock_db_session
    ):
        """Test NULL thumbnail_url channels reported as no_url in summary."""

        # Create service that reports no_url entries
        service_with_no_urls = MagicMock()

        async def mock_warm_channels_with_no_urls(*args, **kwargs):
            return WarmResult(
                downloaded=5,
                skipped=3,
                failed=0,
                no_url=10,  # Some channels have no URL
                total=18,
            )

        service_with_no_urls.warm_channels = AsyncMock(
            side_effect=mock_warm_channels_with_no_urls
        )

        async def mock_warm_videos_no_op(*args, **kwargs):
            return WarmResult(
                downloaded=0,
                skipped=0,
                failed=0,
                no_url=0,
                total=0,
            )

        service_with_no_urls.warm_videos = AsyncMock(
            side_effect=mock_warm_videos_no_op
        )

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service_with_no_urls,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [ "--type", "channels"])

        assert result.exit_code == 0
        # The summary table should include the No URL column with value 10
        output = result.output if result.output else result.stdout
        assert "10" in output  # The no_url count should appear in output

    def test_warm_default_quality_is_mqdefault(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test default quality for video thumbnails is mqdefault."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [ "--type", "videos"])

        assert result.exit_code == 0

        # Verify quality passed to service is mqdefault
        call_kwargs = mock_image_cache_service.warm_videos.call_args.kwargs
        assert call_kwargs["quality"] == "mqdefault"

    def test_warm_quality_hqdefault(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test `warm --quality hqdefault` passes correct quality to service."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(
                    test_warm_app, ["--type", "videos", "--quality", "hqdefault"]
                )

        assert result.exit_code == 0

        # Verify quality passed to service is hqdefault
        call_kwargs = mock_image_cache_service.warm_videos.call_args.kwargs
        assert call_kwargs["quality"] == "hqdefault"

    def test_warm_default_type_is_all(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test default --type is 'all' (both channels and videos)."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [])

        assert result.exit_code == 0

        # Verify both channels and videos were warmed (default is "all")
        mock_image_cache_service.warm_channels.assert_called_once()
        mock_image_cache_service.warm_videos.assert_called_once()

    def test_warm_default_delay_is_0_5(
        self, mock_db_session, mock_image_cache_service
    ):
        """Test default --delay is 0.5 seconds."""

        async def mock_get_session(*args, **kwargs):
            yield mock_db_session

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=mock_image_cache_service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_warm_app, [])

        assert result.exit_code == 0

        # Verify delay passed to service is 0.5
        call_kwargs = mock_image_cache_service.warm_channels.call_args.kwargs
        assert call_kwargs["delay"] == 0.5

        call_kwargs = mock_image_cache_service.warm_videos.call_args.kwargs
        assert call_kwargs["delay"] == 0.5


# ═══════════════════════════════════════════════════════════════════════════
# T024: CLI Status Command Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCacheStatusCommand:
    """Unit tests for the `cache status` CLI command."""

    def test_status_displays_cache_stats(self):
        """Test `status` displays cache statistics in table format."""
        # Create mock service with realistic stats
        service = MagicMock()

        async def mock_get_stats():
            return CacheStats(
                channel_count=150,
                channel_missing_count=5,
                video_count=2500,
                video_missing_count=12,
                total_size_bytes=500_000_000,  # 500 MB
                oldest_file=datetime(2023, 1, 15, tzinfo=timezone.utc),
                newest_file=datetime(2024, 12, 20, tzinfo=timezone.utc),
            )

        service.get_stats = AsyncMock(side_effect=mock_get_stats)

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            result = runner.invoke(test_status_app, [])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify cache stats appear in output
        assert "150" in output  # channel_count
        assert "2,500" in output or "2500" in output  # video_count (may have comma)
        assert "476" in output or "500" in output  # size in MB (approx)

    def test_status_displays_missing_markers_count(self):
        """Test `status` displays missing marker counts in table."""
        service = MagicMock()

        async def mock_get_stats():
            return CacheStats(
                channel_count=100,
                channel_missing_count=8,
                video_count=1000,
                video_missing_count=25,
                total_size_bytes=100_000_000,
                oldest_file=datetime(2023, 6, 1, tzinfo=timezone.utc),
                newest_file=datetime(2024, 11, 30, tzinfo=timezone.utc),
            )

        service.get_stats = AsyncMock(side_effect=mock_get_stats)

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            result = runner.invoke(test_status_app, [])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify missing counts appear
        assert "8" in output  # channel_missing_count
        assert "25" in output  # video_missing_count

    def test_status_displays_cache_directory_path(self):
        """Test `status` displays cache directory path."""
        service = MagicMock()

        async def mock_get_stats():
            return CacheStats(
                channel_count=50,
                channel_missing_count=2,
                video_count=500,
                video_missing_count=3,
                total_size_bytes=50_000_000,
                oldest_file=datetime(2023, 3, 10, tzinfo=timezone.utc),
                newest_file=datetime(2024, 10, 15, tzinfo=timezone.utc),
            )

        service.get_stats = AsyncMock(side_effect=mock_get_stats)

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            result = runner.invoke(test_status_app, [])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify cache directory is shown
        assert "Cache directory:" in output or "cache" in output.lower()

    def test_status_displays_file_dates(self):
        """Test `status` displays oldest and newest file dates."""
        service = MagicMock()

        async def mock_get_stats():
            return CacheStats(
                channel_count=75,
                channel_missing_count=1,
                video_count=800,
                video_missing_count=5,
                total_size_bytes=75_000_000,
                oldest_file=datetime(2023, 1, 1, tzinfo=timezone.utc),
                newest_file=datetime(2024, 12, 31, tzinfo=timezone.utc),
            )

        service.get_stats = AsyncMock(side_effect=mock_get_stats)

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            result = runner.invoke(test_status_app, [])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify file dates appear
        assert "2023-01-01" in output  # oldest_file
        assert "2024-12-31" in output  # newest_file

    def test_status_exits_with_code_0(self):
        """Test `status` exits with code 0 on success."""
        service = MagicMock()

        async def mock_get_stats():
            return CacheStats(
                channel_count=10,
                channel_missing_count=0,
                video_count=100,
                video_missing_count=0,
                total_size_bytes=10_000_000,
                oldest_file=datetime(2024, 1, 1, tzinfo=timezone.utc),
                newest_file=datetime(2024, 12, 1, tzinfo=timezone.utc),
            )

        service.get_stats = AsyncMock(side_effect=mock_get_stats)

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            result = runner.invoke(test_status_app, [])

        assert result.exit_code == 0

    def test_status_empty_cache_displays_zero_counts(self):
        """Test `status` with empty cache shows all zero counts."""
        service = MagicMock()

        async def mock_get_stats():
            return CacheStats(
                channel_count=0,
                channel_missing_count=0,
                video_count=0,
                video_missing_count=0,
                total_size_bytes=0,
                oldest_file=None,
                newest_file=None,
            )

        service.get_stats = AsyncMock(side_effect=mock_get_stats)

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            result = runner.invoke(test_status_app, [])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify zeros appear (multiple times for different columns)
        # Count occurrences to ensure we're seeing the table data
        zero_count = output.count("0")
        assert zero_count >= 4  # At least 4 zeros for cached + missing columns


# ═══════════════════════════════════════════════════════════════════════════
# T025: CLI Purge Command Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCachePurgeCommand:
    """Unit tests for the `cache purge` CLI command."""

    def test_purge_with_force_skips_confirmation(self):
        """Test `purge --force` bypasses confirmation prompt."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 50_000_000  # 50 MB freed

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_purge_app, ["--force"])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify no confirmation prompt appeared
        assert "Are you sure" not in output
        # Verify purge was called
        service.purge.assert_called_once()

    def test_purge_default_type_is_all(self):
        """Test default purge type is 'all'."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 100_000_000  # 100 MB freed

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_purge_app, ["--force"])

        assert result.exit_code == 0

        # Verify purge was called with type_="all"
        call_kwargs = service.purge.call_args.kwargs
        assert call_kwargs["type_"] == "all"

    def test_purge_type_channels_only(self):
        """Test `purge --type channels` only purges channels."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 25_000_000  # 25 MB freed

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(
                    test_purge_app, ["--type", "channels", "--force"]
                )

        assert result.exit_code == 0

        # Verify purge was called with type_="channels"
        call_kwargs = service.purge.call_args.kwargs
        assert call_kwargs["type_"] == "channels"

    def test_purge_type_videos_only(self):
        """Test `purge --type videos` only purges videos."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 10_000_000  # 10 MB freed

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_purge_app, ["--type", "videos", "--force"])

        assert result.exit_code == 0

        # Verify purge was called with type_="videos"
        call_kwargs = service.purge.call_args.kwargs
        assert call_kwargs["type_"] == "videos"

    def test_purge_type_invalid_exits_2(self):
        """Test `purge --type invalid` exits with code 2."""
        result = runner.invoke(test_purge_app, ["--type", "invalid", "--force"])

        assert result.exit_code == 2
        output = result.output if result.output else result.stdout
        assert "Invalid --type" in output or "invalid" in output.lower()

    def test_purge_reports_bytes_freed(self):
        """Test `purge` reports freed bytes in human-readable format."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 150_000_000  # 150 MB freed

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_purge_app, ["--force"])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify freed size is shown (should be ~143 MB)
        assert "MB" in output or "freed" in output.lower()

    def test_purge_confirmation_prompt_y(self):
        """Test purge proceeds when user confirms with 'y'."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 50_000_000  # 50 MB freed

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                # Simulate user typing "y" at the confirmation prompt
                result = runner.invoke(test_purge_app, [], input="y\n")

        assert result.exit_code == 0
        # Verify purge was actually called
        service.purge.assert_called_once()

    def test_purge_confirmation_prompt_n_exits_1(self):
        """Test purge cancels with exit code 1 when user responds 'n'."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 50_000_000

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                # Simulate user typing "n" at the confirmation prompt
                result = runner.invoke(test_purge_app, [], input="n\n")

        assert result.exit_code == 1
        output = result.output if result.output else result.stdout
        assert "cancelled" in output.lower() or "canceled" in output.lower()
        # Verify purge was NOT called
        service.purge.assert_not_called()

    def test_purge_unavailable_content_warning(self):
        """Test purge displays warning about unavailable content."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 15  # 15 cached images from unavailable content

        async def mock_purge(*args, **kwargs):
            return 50_000_000

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_purge_app, ["--force"])

        assert result.exit_code == 0
        output = result.output if result.output else result.stdout

        # Verify warning about unavailable content
        assert "15" in output  # count of unavailable images
        assert "Warning" in output or "warning" in output.lower()
        assert (
            "unavailable" in output.lower() or "CANNOT be re-downloaded" in output
        )

    def test_purge_exits_0_on_success(self):
        """Test `purge` exits with code 0 on successful completion."""
        service = MagicMock()

        async def mock_count_unavailable(*args, **kwargs):
            return 0

        async def mock_purge(*args, **kwargs):
            return 75_000_000  # 75 MB freed

        service.count_unavailable_cached = AsyncMock(
            side_effect=mock_count_unavailable
        )
        service.purge = AsyncMock(side_effect=mock_purge)

        async def mock_get_session(*args, **kwargs):
            yield AsyncMock()

        with patch(
            "chronovista.cli.commands.cache._build_cache_service",
            return_value=service,
        ):
            with patch(
                "chronovista.cli.commands.cache.db_manager.get_session",
                side_effect=mock_get_session,
            ):
                result = runner.invoke(test_purge_app, ["--force"])

        assert result.exit_code == 0
