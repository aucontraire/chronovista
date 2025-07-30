"""
Tests for TakeoutSeedingService - comprehensive modular seeding system tests.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.chronovista.models.takeout.takeout_data import (
    TakeoutData,
    TakeoutPlaylist,
    TakeoutPlaylistItem,
    TakeoutSubscription,
    TakeoutWatchEntry,
)
from src.chronovista.services.seeding import ProgressCallback, SeedResult
from src.chronovista.services.takeout_seeding_service import TakeoutSeedingService

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestTakeoutSeedingService:
    """Test the modular TakeoutSeedingService."""

    @pytest.fixture
    def seeding_service(self):
        """Create a TakeoutSeedingService instance for testing."""
        return TakeoutSeedingService(user_id="test_user")

    @pytest.fixture
    def mock_takeout_data(self):
        """Create mock takeout data for testing."""
        return TakeoutData(
            takeout_path=Path("/test/takeout"),
            subscriptions=[
                TakeoutSubscription(
                    channel_id="UC123",
                    channel_title="Test Channel",
                    channel_url="https://youtube.com/channel/UC123",
                )
            ],
            watch_history=[
                TakeoutWatchEntry(
                    title="Test Video",
                    title_url="https://youtube.com/watch?v=abc123",
                    channel_name="Test Channel",
                    watched_at=datetime.now(),
                    video_id="abc123",
                    channel_id="UC123",
                )
            ],
            playlists=[
                TakeoutPlaylist(
                    name="Test Playlist",
                    file_path=Path("/test/takeout/playlist.csv"),
                    videos=[TakeoutPlaylistItem(video_id="abc123")],
                )
            ],
        )

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    def test_initialization(self, seeding_service):
        """Test service initialization."""
        assert seeding_service.user_id == "test_user"
        assert seeding_service.orchestrator is not None
        assert seeding_service.get_available_types() == {
            "channels",
            "videos",
            "user_videos",
            "playlists",
            "playlist_memberships",
        }

    def test_get_available_types(self, seeding_service):
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

    async def test_seed_database_all_types(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test seeding all data types."""
        # Mock the orchestrator.seed method
        mock_results = {
            "channels": SeedResult(
                created=1, updated=0, failed=0, duration_seconds=1.0
            ),
            "videos": SeedResult(created=1, updated=0, failed=0, duration_seconds=1.0),
            "user_videos": SeedResult(
                created=1, updated=0, failed=0, duration_seconds=1.0
            ),
            "playlists": SeedResult(
                created=1, updated=0, failed=0, duration_seconds=1.0
            ),
            "playlist_memberships": SeedResult(
                created=1, updated=0, failed=0, duration_seconds=1.0
            ),
        }

        with patch.object(
            seeding_service.orchestrator, "seed", return_value=mock_results
        ) as mock_seed:
            results = await seeding_service.seed_database(
                mock_session, mock_takeout_data
            )

            # Verify orchestrator was called correctly
            mock_seed.assert_called_once()
            args, kwargs = mock_seed.call_args
            assert args[0] == mock_session
            assert args[1] == mock_takeout_data
            assert args[2] == {
                "channels",
                "videos",
                "user_videos",
                "playlists",
                "playlist_memberships",
            }

            # Verify results
            assert len(results) == 5
            assert all(result.created == 1 for result in results.values())
            assert all(result.success_rate == 100.0 for result in results.values())

    async def test_seed_database_specific_types(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test seeding specific data types only."""
        mock_results = {
            "channels": SeedResult(
                created=5, updated=10, failed=0, duration_seconds=2.5
            )
        }

        with patch.object(
            seeding_service.orchestrator, "seed", return_value=mock_results
        ) as mock_seed:
            results = await seeding_service.seed_database(
                mock_session, mock_takeout_data, data_types={"channels"}
            )

            # Verify orchestrator was called with filtered types
            args, kwargs = mock_seed.call_args
            assert args[2] == {"channels"}

            # Verify results
            assert len(results) == 1
            assert "channels" in results
            assert results["channels"].created == 5
            assert results["channels"].updated == 10

    async def test_seed_database_with_skip_types(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test seeding with skip types."""
        mock_results = {
            "channels": SeedResult(
                created=1, updated=0, failed=0, duration_seconds=1.0
            ),
            "videos": SeedResult(created=1, updated=0, failed=0, duration_seconds=1.0),
            "playlist_memberships": SeedResult(
                created=1, updated=0, failed=0, duration_seconds=1.0
            ),
        }

        with patch.object(
            seeding_service.orchestrator, "seed", return_value=mock_results
        ) as mock_seed:
            results = await seeding_service.seed_database(
                mock_session, mock_takeout_data, skip_types={"user_videos", "playlists"}
            )

            # Verify orchestrator was called with correct filtered types
            args, kwargs = mock_seed.call_args
            assert args[2] == {"channels", "videos", "playlist_memberships"}

    async def test_seed_database_with_progress_callback(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test seeding with progress callback."""
        progress_calls = []

        def mock_progress_callback(data_type: str):
            progress_calls.append(data_type)

        progress = ProgressCallback(mock_progress_callback)
        mock_results = {
            "channels": SeedResult(created=1, updated=0, failed=0, duration_seconds=1.0)
        }

        with patch.object(
            seeding_service.orchestrator, "seed", return_value=mock_results
        ) as mock_seed:
            results = await seeding_service.seed_database(
                mock_session,
                mock_takeout_data,
                data_types={"channels"},
                progress_callback=progress,
            )

            # Verify progress callback was passed through
            args, kwargs = mock_seed.call_args
            assert (
                len(args) == 4
            )  # session, takeout_data, types_to_process, progress_callback
            assert args[3] == progress

    async def test_seed_incrementally(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test incremental seeding."""
        mock_results = {
            "channels": SeedResult(created=0, updated=5, failed=0, duration_seconds=1.5)
        }

        with patch.object(
            seeding_service.orchestrator, "seed", return_value=mock_results
        ) as mock_seed:
            results = await seeding_service.seed_incrementally(
                mock_session, mock_takeout_data, data_types={"channels"}
            )

            # Verify it calls the same underlying method (incremental is built into seeders)
            mock_seed.assert_called_once()
            assert results["channels"].updated == 5

    async def test_empty_data_types_handling(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test handling when no data types are selected."""
        # Test with data_types that don't intersect with available types
        results = await seeding_service.seed_database(
            mock_session, mock_takeout_data, data_types={"nonexistent_type"}
        )

        # Should return empty results
        assert results == {}

    async def test_error_handling_in_orchestrator(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test error handling when orchestrator fails."""
        with patch.object(
            seeding_service.orchestrator, "seed", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception, match="Test error"):
                await seeding_service.seed_database(mock_session, mock_takeout_data)

    def test_service_setup_creates_all_seeders(self, seeding_service):
        """Test that service setup creates all expected seeders."""
        # Verify orchestrator has all expected seeders registered
        available_types = seeding_service.get_available_types()
        assert "channels" in available_types
        assert "videos" in available_types
        assert "user_videos" in available_types
        assert "playlists" in available_types

    async def test_conflicting_data_types_and_skip_types(
        self, seeding_service, mock_takeout_data, mock_session
    ):
        """Test handling of conflicting data_types and skip_types."""
        mock_results = {
            "videos": SeedResult(created=1, updated=0, failed=0, duration_seconds=1.0)
        }

        with patch.object(
            seeding_service.orchestrator, "seed", return_value=mock_results
        ) as mock_seed:
            # Request channels and videos, but skip channels
            results = await seeding_service.seed_database(
                mock_session,
                mock_takeout_data,
                data_types={"channels", "videos"},
                skip_types={"channels"},
            )

            # Should only process videos
            args, kwargs = mock_seed.call_args
            assert args[2] == {"videos"}

    def test_user_id_propagation(self):
        """Test that user_id is properly propagated to seeders."""
        custom_user_id = "custom_test_user"
        service = TakeoutSeedingService(user_id=custom_user_id)

        assert service.user_id == custom_user_id


class TestTakeoutSeedingServiceIntegration:
    """Integration tests for TakeoutSeedingService with real components."""

    @pytest.fixture
    def integration_service(self):
        """Create a service for integration testing."""
        return TakeoutSeedingService(user_id="integration_test")

    def test_orchestrator_dependency_resolution(self, integration_service):
        """Test that dependency resolution works correctly."""
        # The orchestrator should have proper dependency resolution
        available_types = integration_service.get_available_types()

        # All expected types should be available
        assert "channels" in available_types
        assert "videos" in available_types  # depends on channels
        assert "user_videos" in available_types  # depends on videos
        assert "playlists" in available_types  # depends on channels
        assert "playlist_memberships" in available_types  # depends on playlists, videos

    async def test_real_seeder_instantiation(self, integration_service):
        """Test that real seeders are properly instantiated."""
        # This test verifies the seeders can be created without mocking
        # It tests the _setup_seeders method indirectly
        assert integration_service.orchestrator is not None

        # Should not raise any errors when getting available types
        types = integration_service.get_available_types()
        assert len(types) == 5

    async def test_with_minimal_takeout_data(self, integration_service):
        """Test with minimal takeout data structure."""
        minimal_data = TakeoutData(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        # Should handle empty data gracefully
        results = await integration_service.seed_database(
            mock_session, minimal_data, data_types={"channels"}
        )

        # Should return results even with empty data
        assert isinstance(results, dict)
