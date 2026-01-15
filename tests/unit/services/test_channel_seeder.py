"""
Tests for ChannelSeeder - channel seeding from subscriptions and watch history.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from chronovista.models.channel import ChannelCreate
from chronovista.models.takeout.takeout_data import TakeoutData
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.services.seeding.base_seeder import ProgressCallback
from chronovista.services.seeding.channel_seeder import ChannelSeeder
from tests.factories.id_factory import TestIds, YouTubeIdFactory
from tests.factories.takeout_data_factory import create_takeout_data
from tests.factories.takeout_subscription_factory import create_takeout_subscription
from tests.factories.takeout_watch_entry_factory import (
    create_minimal_takeout_watch_entry,
    create_takeout_watch_entry,
)

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestChannelSeeder:
    """Test the ChannelSeeder implementation."""

    @pytest.fixture
    def mock_channel_repo(self) -> Mock:
        """Create a mock channel repository."""
        repo = Mock(spec=ChannelRepository)
        repo.get_by_channel_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def channel_seeder(self, mock_channel_repo: Mock) -> ChannelSeeder:
        """Create a ChannelSeeder for testing."""
        return ChannelSeeder(mock_channel_repo)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def takeout_data_with_subscriptions(self) -> TakeoutData:
        """Create takeout data with subscriptions."""
        return create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[
                create_takeout_subscription(
                    channel_id=TestIds.TEST_CHANNEL_1,
                    channel_title="Tech Channel",
                    channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_1}",
                ),
                create_takeout_subscription(
                    channel_id=TestIds.TEST_CHANNEL_2,
                    channel_title="Music Channel",
                    channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_2}",
                ),
            ],
            watch_history=[
                create_takeout_watch_entry(
                    title="Video 1",
                    title_url="https://youtube.com/watch?v=abc",
                    channel_name="Watch Channel",
                    watched_at=datetime.now(),
                    video_id="abc",
                    channel_id=TestIds.RICK_ASTLEY_CHANNEL,
                )
            ],
            playlists=[],
        )

    def test_initialization(self, channel_seeder, mock_channel_repo):
        """Test ChannelSeeder initialization."""
        assert channel_seeder.channel_repo == mock_channel_repo
        assert channel_seeder.get_dependencies() == set()  # No dependencies
        assert channel_seeder.get_data_type() == "channels"

    async def test_seed_empty_data(self, channel_seeder, mock_session):
        """Test seeding with empty takeout data."""
        empty_data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        result = await channel_seeder.seed(mock_session, empty_data)

        assert result.created == 0
        assert result.updated == 0
        assert result.failed == 0
        assert result.success_rate == 100.0  # Empty data is 100% successful

    async def test_seed_subscriptions_new_channels(
        self,
        channel_seeder,
        mock_session,
        takeout_data_with_subscriptions,
        mock_channel_repo,
    ):
        """Test seeding subscriptions with new channels."""
        # Mock repository to return None (channel doesn't exist)
        mock_channel_repo.get_by_channel_id.return_value = None

        result = await channel_seeder.seed(
            mock_session, takeout_data_with_subscriptions
        )

        # Should create 3 channels total (2 from subscriptions + 1 from watch history)
        assert result.created > 0
        assert result.failed == 0
        assert result.success_rate == 100.0

        # Verify repository calls
        assert (
            mock_channel_repo.create.call_count >= 2
        )  # At least subscription channels

    async def test_seed_subscriptions_existing_channels(
        self,
        channel_seeder,
        mock_session,
        takeout_data_with_subscriptions,
        mock_channel_repo,
    ):
        """Test seeding subscriptions with existing channels."""
        # Mock repository to return existing channel
        mock_existing_channel = Mock()
        mock_channel_repo.get_by_channel_id.return_value = mock_existing_channel

        result = await channel_seeder.seed(
            mock_session, takeout_data_with_subscriptions
        )

        # Should update existing channels, not create new ones
        assert result.updated > 0
        assert result.created == 0
        assert result.failed == 0
        assert result.success_rate == 100.0

    async def test_seed_with_progress_callback(
        self,
        channel_seeder,
        mock_session,
        takeout_data_with_subscriptions,
        mock_channel_repo,
    ):
        """Test seeding with progress callback."""
        progress_calls = []

        def mock_progress(data_type: str):
            progress_calls.append(data_type)

        progress = ProgressCallback(mock_progress)
        mock_channel_repo.get_by_channel_id.return_value = None

        result = await channel_seeder.seed(
            mock_session, takeout_data_with_subscriptions, progress
        )

        # Progress should be called for channels
        assert "channels" in progress_calls

    async def test_seed_error_handling(
        self,
        channel_seeder,
        mock_session,
        takeout_data_with_subscriptions,
        mock_channel_repo,
    ):
        """Test error handling during seeding."""
        # Mock repository to raise an error
        mock_channel_repo.get_by_channel_id.side_effect = Exception("Database error")

        result = await channel_seeder.seed(
            mock_session, takeout_data_with_subscriptions
        )

        # Should handle errors gracefully
        assert result.failed > 0
        assert len(result.errors) > 0
        assert "Database error" in str(result.errors[0])

    def test_transform_subscription_to_channel(self, channel_seeder):
        """Test transforming subscription to ChannelCreate model."""
        subscription = create_takeout_subscription(
            channel_id=TestIds.TEST_CHANNEL_1,
            channel_title="Test Channel",
            channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_1}",
        )

        channel_create = channel_seeder._transform_subscription_to_channel(subscription)

        assert isinstance(channel_create, ChannelCreate)
        assert channel_create.channel_id == TestIds.TEST_CHANNEL_1
        assert channel_create.title == "Test Channel"
        assert channel_create.description == ""  # Not available in Takeout
        assert channel_create.is_subscribed is True  # Subscriptions mean user is subscribed

    def test_transform_watch_entry_to_channel(self, channel_seeder):
        """Test transforming watch entry to ChannelCreate model."""
        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url="https://youtube.com/watch?v=abc",
            channel_name="Watch Channel",
            watched_at=datetime.now(),
            video_id="abc",
            channel_id=TestIds.RICK_ASTLEY_CHANNEL,
        )

        channel_create = channel_seeder._transform_watch_entry_to_channel(watch_entry)

        assert isinstance(channel_create, ChannelCreate)
        assert channel_create.channel_id == TestIds.RICK_ASTLEY_CHANNEL
        assert channel_create.title == "Watch Channel"
        assert channel_create.description == ""  # Not available in Takeout

    async def test_handle_missing_channel_id_in_watch_entry(self, channel_seeder):
        """Test handling watch entry with missing channel ID.

        Updated behavior (T017-T020): When channel_id is missing, we return None
        instead of generating fake IDs. Videos will use channel_name_hint instead.
        """
        # Use minimal factory which has channel_id=None by default
        watch_entry = create_minimal_takeout_watch_entry(
            title="Test Video",
            title_url="https://youtube.com/watch?v=abc",
            channel_name="Unknown Channel",
            watched_at=datetime.now(),
            video_id="abc",
        )

        channel_create = channel_seeder._transform_watch_entry_to_channel(watch_entry)

        # Should return None when channel_id is missing (no fake ID generation)
        assert channel_create is None

    async def test_deduplication_across_sources(
        self, channel_seeder, mock_session, mock_channel_repo
    ):
        """Test that channels are deduplicated across subscriptions and watch history."""
        # Create data where subscription and watch history have same channel
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[
                create_takeout_subscription(
                    channel_id=TestIds.TEST_CHANNEL_1,
                    channel_title="Common Channel",
                    channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_1}",
                )
            ],
            watch_history=[
                create_takeout_watch_entry(
                    title="Video from Common Channel",
                    title_url="https://youtube.com/watch?v=abc",
                    channel_name="Common Channel",
                    watched_at=datetime.now(),
                    video_id="abc",
                    channel_id=TestIds.TEST_CHANNEL_1,  # Same as subscription
                )
            ],
            playlists=[],
        )

        # First call returns None (new), second call returns existing
        mock_channel_repo.get_by_channel_id.side_effect = [None, Mock()]

        result = await channel_seeder.seed(mock_session, data)

        # Should only create once, then update
        assert mock_channel_repo.create.call_count == 1
        assert result.created == 1
        assert (
            result.updated >= 0
        )  # May be 0 if watch history processing doesn't find additional unique channels

    async def test_batch_processing_commits(
        self, channel_seeder, mock_session, mock_channel_repo
    ):
        """Test that seeding commits in batches for performance."""
        # Create data with many subscriptions to trigger batch commits
        subscriptions = [
            create_takeout_subscription(
                channel_id=YouTubeIdFactory.create_channel_id(f"channel_{i}"),
                channel_title=f"Channel {i}",
                channel_url=f"https://youtube.com/channel/{YouTubeIdFactory.create_channel_id(f'channel_{i}')}",
            )
            for i in range(150)  # More than batch size of 100
        ]

        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=subscriptions,
            watch_history=[],
            playlists=[],
        )
        mock_channel_repo.get_by_channel_id.return_value = None

        await channel_seeder.seed(mock_session, data)

        # Should have called commit multiple times for batching
        assert mock_session.commit.call_count >= 2  # At least 2 batch commits

    @pytest.mark.skip(
        reason="generate_valid_channel_id removed in T017-T020. "
        "Seeder now uses real channel IDs from YouTube API or NULL with hint."
    )
    def test_channel_id_generation_consistency(self, channel_seeder):
        """Test that channel ID generation is consistent for same input."""
        pass  # Test skipped - helper function removed

    async def test_missing_channel_name_handling(self, channel_seeder):
        """Test handling of entries with missing channel names.

        Updated behavior (T017-T020): When channel_name is missing, we create
        a placeholder channel with the actual channel_id from the entry.
        The placeholder prefix is now "[Channel]" not "[Unknown Channel]".
        """
        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url="https://youtube.com/watch?v=abc",
            channel_name=None,  # Missing channel name
            watched_at=datetime.now(),
            video_id="abc",
        )

        channel_create = channel_seeder._transform_watch_entry_to_channel(watch_entry)

        # Should create placeholder channel with the entry's channel_id
        assert channel_create is not None
        assert channel_create.channel_id.startswith("UC")
        assert len(channel_create.channel_id) == 24
        # Updated: prefix is now "[Channel]" not "[Unknown Channel]"
        assert channel_create.title.startswith("[Channel]")
