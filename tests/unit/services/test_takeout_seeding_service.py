"""
Tests for TakeoutSeedingService.

Comprehensive test suite covering modular seeding architecture,
dependency resolution, and orchestration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.enums import LanguageCode
from chronovista.models.takeout.takeout_data import (
    TakeoutData,
    TakeoutPlaylist,
    TakeoutPlaylistItem,
    TakeoutSubscription,
    TakeoutWatchEntry,
)
from chronovista.services.seeding.base_seeder import ProgressCallback, SeedResult
from chronovista.services.seeding.orchestrator import SeedingOrchestrator
from chronovista.services.takeout_seeding_service import TakeoutSeedingService
from tests.factories.id_factory import TestIds, YouTubeIdFactory

# Ensure async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestTakeoutSeedingService:
    """Test TakeoutSeedingService with modular architecture."""

    @pytest.fixture
    def seeding_service(self) -> TakeoutSeedingService:
        """Create TakeoutSeedingService."""
        return TakeoutSeedingService(user_id="test_user")

    @pytest.fixture
    def sample_takeout_data(self) -> TakeoutData:
        """Create sample TakeoutData for testing."""
        return TakeoutData(
            takeout_path=Path("/test/takeout"),
            watch_history=[
                TakeoutWatchEntry(
                    video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
                    title="Never Gonna Give You Up",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
                    channel_name="Rick Astley",
                    channel_id=TestIds.RICK_ASTLEY_CHANNEL,
                    watched_at=datetime.now(timezone.utc),
                ),
                TakeoutWatchEntry(
                    video_id=TestIds.TEST_VIDEO_1,
                    title="Test Video 2",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                    channel_name="Test Channel",
                    channel_id=TestIds.TEST_CHANNEL_2,
                    watched_at=datetime.now(timezone.utc),
                ),
            ],
            subscriptions=[
                TakeoutSubscription(
                    channel_id=TestIds.RICK_ASTLEY_CHANNEL,
                    channel_title="Rick Astley",
                    channel_url=f"https://www.youtube.com/channel/{TestIds.RICK_ASTLEY_CHANNEL}",
                ),
                TakeoutSubscription(
                    channel_id=TestIds.TEST_CHANNEL_2,
                    channel_title="Test Channel",
                    channel_url=f"https://www.youtube.com/channel/{TestIds.TEST_CHANNEL_2}",
                ),
            ],
            playlists=[
                TakeoutPlaylist(
                    name="My Favorites",
                    file_path=Path("/test/My Favorites.csv"),
                    videos=[
                        TakeoutPlaylistItem(
                            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
                            creation_timestamp=datetime.now(timezone.utc),
                        )
                    ],
                    video_count=1,
                ),
            ],
        )

    async def test_seeding_service_initialization(
        self, seeding_service: TakeoutSeedingService
    ) -> None:
        """Test TakeoutSeedingService initialization."""
        assert seeding_service.user_id == "test_user"
        assert isinstance(seeding_service.orchestrator, SeedingOrchestrator)

        # Verify all data types are available
        available_types = seeding_service.get_available_types()
        expected_types = {
            "channels",
            "videos",
            "user_videos",
            "playlists",
            "playlist_memberships",
        }
        assert available_types == expected_types

    async def test_get_available_types(
        self, seeding_service: TakeoutSeedingService
    ) -> None:
        """Test getting available data types."""
        available_types = seeding_service.get_available_types()
        expected_types = {
            "channels",
            "videos",
            "user_videos",
            "playlists",
            "playlist_memberships",
        }
        assert available_types == expected_types

    async def test_seed_database_complete_workflow(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test complete database seeding workflow with mocked orchestrator."""
        session = AsyncMock()

        # Mock the orchestrator's seed method
        mock_results = {
            "channels": SeedResult(
                created=2, updated=0, failed=0, duration_seconds=1.0
            ),
            "videos": SeedResult(created=2, updated=0, failed=0, duration_seconds=2.0),
            "user_videos": SeedResult(
                created=2, updated=0, failed=0, duration_seconds=1.5
            ),
            "playlists": SeedResult(
                created=1, updated=0, failed=0, duration_seconds=0.5
            ),
        }

        with patch.object(
            seeding_service.orchestrator, "seed", new_callable=AsyncMock
        ) as mock_seed:
            mock_seed.return_value = mock_results

            result = await seeding_service.seed_database(session, sample_takeout_data)

            # Verify orchestrator was called correctly
            # When data_types=None, it should pass all available types
            expected_types = {
                "channels",
                "videos",
                "user_videos",
                "playlists",
                "playlist_memberships",
            }
            mock_seed.assert_called_once_with(
                session,
                sample_takeout_data,
                expected_types,  # all available types
                None,  # progress callback
            )

            # Verify results are returned
            assert result == mock_results

    async def test_seed_database_with_specific_types(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test seeding with specific data types only."""
        session = AsyncMock()

        # Mock the orchestrator's seed method
        mock_results = {
            "channels": SeedResult(
                created=2, updated=0, failed=0, duration_seconds=1.0
            ),
            "videos": SeedResult(created=2, updated=0, failed=0, duration_seconds=2.0),
        }

        with patch.object(
            seeding_service.orchestrator, "seed", new_callable=AsyncMock
        ) as mock_seed:
            mock_seed.return_value = mock_results

            result = await seeding_service.seed_database(
                session, sample_takeout_data, data_types={"channels", "videos"}
            )

            # Verify orchestrator was called with specific types
            mock_seed.assert_called_once_with(
                session,
                sample_takeout_data,
                {"channels", "videos"},  # specific types
                None,  # progress callback
            )

            assert result == mock_results

    async def test_seed_database_with_skip_types(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test seeding with skip types."""
        session = AsyncMock()

        # Mock the orchestrator's seed method
        mock_results = {
            "channels": SeedResult(
                created=2, updated=0, failed=0, duration_seconds=1.0
            ),
            "videos": SeedResult(created=2, updated=0, failed=0, duration_seconds=2.0),
        }

        with patch.object(
            seeding_service.orchestrator, "seed", new_callable=AsyncMock
        ) as mock_seed:
            mock_seed.return_value = mock_results

            result = await seeding_service.seed_database(
                session, sample_takeout_data, skip_types={"user_videos", "playlists"}
            )

            # Should process all types except skipped ones
            expected_types = {"channels", "videos", "playlist_memberships"}

            # Verify orchestrator was called with remaining types
            mock_seed.assert_called_once()
            call_args = mock_seed.call_args
            actual_types = call_args[0][2]  # third positional argument
            assert actual_types == expected_types

            assert result == mock_results

    async def test_seed_incremental_workflow(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test incremental seeding workflow."""
        session = AsyncMock()

        # Mock the orchestrator's seed method
        mock_results = {
            "channels": SeedResult(
                created=1, updated=1, failed=0, duration_seconds=1.0
            ),
            "videos": SeedResult(created=1, updated=1, failed=0, duration_seconds=2.0),
        }

        with patch.object(
            seeding_service.orchestrator, "seed", new_callable=AsyncMock
        ) as mock_seed:
            mock_seed.return_value = mock_results

            result = await seeding_service.seed_incrementally(
                session, sample_takeout_data, data_types={"channels", "videos"}
            )

            # Incremental seeding should call the same method
            mock_seed.assert_called_once_with(
                session, sample_takeout_data, {"channels", "videos"}, None
            )

            assert result == mock_results

    async def test_progress_callback_integration(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test progress callback integration."""
        session = AsyncMock()

        # Create a mock progress callback
        progress_callback = MagicMock()

        with patch.object(
            seeding_service.orchestrator, "seed", new_callable=AsyncMock
        ) as mock_seed:
            mock_seed.return_value = {}

            await seeding_service.seed_database(
                session, sample_takeout_data, progress_callback=progress_callback
            )

            # Verify progress callback was passed to orchestrator
            expected_types = {
                "channels",
                "videos",
                "user_videos",
                "playlists",
                "playlist_memberships",
            }
            mock_seed.assert_called_once_with(
                session,
                sample_takeout_data,
                expected_types,  # all available types
                progress_callback,
            )

    async def test_seed_database_no_types_to_process(
        self, seeding_service: TakeoutSeedingService, sample_takeout_data: TakeoutData
    ) -> None:
        """Test seeding when no types are selected for processing."""
        session = AsyncMock()

        # Mock orchestrator to not be called since no types remain
        with patch.object(
            seeding_service.orchestrator, "seed", new_callable=AsyncMock
        ) as mock_seed:
            # Request all types but skip all types too
            result = await seeding_service.seed_database(
                session,
                sample_takeout_data,
                data_types={"channels", "videos"},
                skip_types={"channels", "videos"},
            )

            # No types should remain, so orchestrator shouldn't be called
            mock_seed.assert_not_called()

            # Should return empty dict
            assert result == {}

    def test_service_with_custom_user_id(
        self, sample_takeout_data: TakeoutData
    ) -> None:
        """Test service initialization with custom user ID."""
        custom_service = TakeoutSeedingService(user_id="custom_user_123")

        assert custom_service.user_id == "custom_user_123"
        assert isinstance(custom_service.orchestrator, SeedingOrchestrator)

        # Verify seeders are set up with custom user ID
        available_types = custom_service.get_available_types()
        expected_types = {
            "channels",
            "videos",
            "user_videos",
            "playlists",
            "playlist_memberships",
        }
        assert available_types == expected_types
