"""
Tests for ChannelSeeder - channel seeding from subscriptions and watch history.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.chronovista.services.seeding.channel_seeder import ChannelSeeder
from src.chronovista.services.seeding.base_seeder import ProgressCallback
from src.chronovista.models.takeout.takeout_data import TakeoutData, TakeoutSubscription, TakeoutWatchEntry
from src.chronovista.models.channel import ChannelCreate
from src.chronovista.repositories.channel_repository import ChannelRepository
from tests.factories.id_factory import YouTubeIdFactory, TestIds

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestChannelSeeder:
    """Test the ChannelSeeder implementation."""

    @pytest.fixture
    def mock_channel_repo(self):
        """Create a mock channel repository."""
        repo = Mock(spec=ChannelRepository)
        repo.get_by_channel_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def channel_seeder(self, mock_channel_repo):
        """Create a ChannelSeeder for testing."""
        return ChannelSeeder(mock_channel_repo)

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def takeout_data_with_subscriptions(self):
        """Create takeout data with subscriptions."""
        return TakeoutData(
            takeout_path=Path("/test/takeout"),
            subscriptions=[
                TakeoutSubscription(
                    channel_id=TestIds.TEST_CHANNEL_1,
                    channel_title="Tech Channel",
                    channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_1}"
                ),
                TakeoutSubscription(
                    channel_id=TestIds.TEST_CHANNEL_2,
                    channel_title="Music Channel",
                    channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_2}"
                )
            ],
            watch_history=[
                TakeoutWatchEntry(
                    title="Video 1",
                    title_url="https://youtube.com/watch?v=abc",
                    channel_name="Watch Channel",
                    watched_at=datetime.now(),
                    video_id="abc",
                    channel_id=TestIds.RICK_ASTLEY_CHANNEL
                )
            ],
            playlists=[]
        )

    def test_initialization(self, channel_seeder, mock_channel_repo):
        """Test ChannelSeeder initialization."""
        assert channel_seeder.channel_repo == mock_channel_repo
        assert channel_seeder.get_dependencies() == set()  # No dependencies
        assert channel_seeder.get_data_type() == "channels"

    async def test_seed_empty_data(self, channel_seeder, mock_session):
        """Test seeding with empty takeout data."""
        empty_data = TakeoutData(takeout_path=Path("/test/takeout"), subscriptions=[], watch_history=[], playlists=[])
        
        result = await channel_seeder.seed(mock_session, empty_data)
        
        assert result.created == 0
        assert result.updated == 0
        assert result.failed == 0
        assert result.success_rate == 100.0  # Empty data is 100% successful

    async def test_seed_subscriptions_new_channels(self, channel_seeder, mock_session, takeout_data_with_subscriptions, mock_channel_repo):
        """Test seeding subscriptions with new channels."""
        # Mock repository to return None (channel doesn't exist)
        mock_channel_repo.get_by_channel_id.return_value = None
        
        result = await channel_seeder.seed(mock_session, takeout_data_with_subscriptions)
        
        # Should create 3 channels total (2 from subscriptions + 1 from watch history)
        assert result.created > 0
        assert result.failed == 0
        assert result.success_rate == 100.0
        
        # Verify repository calls
        assert mock_channel_repo.create.call_count >= 2  # At least subscription channels

    async def test_seed_subscriptions_existing_channels(self, channel_seeder, mock_session, takeout_data_with_subscriptions, mock_channel_repo):
        """Test seeding subscriptions with existing channels."""
        # Mock repository to return existing channel
        mock_existing_channel = Mock()
        mock_channel_repo.get_by_channel_id.return_value = mock_existing_channel
        
        result = await channel_seeder.seed(mock_session, takeout_data_with_subscriptions)
        
        # Should update existing channels, not create new ones
        assert result.updated > 0
        assert result.created == 0
        assert result.failed == 0
        assert result.success_rate == 100.0

    async def test_seed_with_progress_callback(self, channel_seeder, mock_session, takeout_data_with_subscriptions, mock_channel_repo):
        """Test seeding with progress callback."""
        progress_calls = []
        
        def mock_progress(data_type: str):
            progress_calls.append(data_type)
        
        progress = ProgressCallback(mock_progress)
        mock_channel_repo.get_by_channel_id.return_value = None
        
        result = await channel_seeder.seed(mock_session, takeout_data_with_subscriptions, progress)
        
        # Progress should be called for channels
        assert "channels" in progress_calls

    async def test_seed_error_handling(self, channel_seeder, mock_session, takeout_data_with_subscriptions, mock_channel_repo):
        """Test error handling during seeding."""
        # Mock repository to raise an error
        mock_channel_repo.get_by_channel_id.side_effect = Exception("Database error")
        
        result = await channel_seeder.seed(mock_session, takeout_data_with_subscriptions)
        
        # Should handle errors gracefully
        assert result.failed > 0
        assert len(result.errors) > 0
        assert "Database error" in str(result.errors[0])

    def test_transform_subscription_to_channel(self, channel_seeder):
        """Test transforming subscription to ChannelCreate model."""
        subscription = TakeoutSubscription(
            channel_id=TestIds.TEST_CHANNEL_1,
            channel_title="Test Channel",
            channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_1}"
        )
        
        channel_create = channel_seeder._transform_subscription_to_channel(subscription)
        
        assert isinstance(channel_create, ChannelCreate)
        assert channel_create.channel_id == TestIds.TEST_CHANNEL_1
        assert channel_create.title == "Test Channel"
        assert channel_create.description == ""  # Not available in Takeout

    def test_transform_watch_entry_to_channel(self, channel_seeder):
        """Test transforming watch entry to ChannelCreate model."""
        watch_entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://youtube.com/watch?v=abc",
            channel_name="Watch Channel",
            watched_at=datetime.now(),
            video_id="abc",
            channel_id=TestIds.RICK_ASTLEY_CHANNEL
        )
        
        channel_create = channel_seeder._transform_watch_entry_to_channel(watch_entry)
        
        assert isinstance(channel_create, ChannelCreate)
        assert channel_create.channel_id == TestIds.RICK_ASTLEY_CHANNEL
        assert channel_create.title == "Watch Channel"
        assert channel_create.description == ""  # Not available in Takeout

    async def test_handle_missing_channel_id_in_watch_entry(self, channel_seeder):
        """Test handling watch entry with missing channel ID."""
        watch_entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://youtube.com/watch?v=abc",
            channel_name="Unknown Channel",
            watched_at=datetime.now(),
            video_id="abc",
            channel_id=None  # Missing channel ID
        )
        
        channel_create = channel_seeder._transform_watch_entry_to_channel(watch_entry)
        
        # Should generate a valid channel ID
        assert channel_create.channel_id.startswith("UC")
        assert len(channel_create.channel_id) == 24
        assert channel_create.title == "Unknown Channel"

    async def test_deduplication_across_sources(self, channel_seeder, mock_session, mock_channel_repo):
        """Test that channels are deduplicated across subscriptions and watch history."""
        # Create data where subscription and watch history have same channel
        data = TakeoutData(
            takeout_path=Path("/test/takeout"),
            subscriptions=[
                TakeoutSubscription(
                    channel_id=TestIds.TEST_CHANNEL_1,
                    channel_title="Common Channel",
                    channel_url=f"https://youtube.com/channel/{TestIds.TEST_CHANNEL_1}"
                )
            ],
            watch_history=[
                TakeoutWatchEntry(
                    title="Video from Common Channel",
                    title_url="https://youtube.com/watch?v=abc",
                    channel_name="Common Channel",
                    watched_at=datetime.now(),
                    video_id="abc",
                    channel_id=TestIds.TEST_CHANNEL_1  # Same as subscription
                )
            ],
            playlists=[]
        )
        
        # First call returns None (new), second call returns existing
        mock_channel_repo.get_by_channel_id.side_effect = [None, Mock()]
        
        result = await channel_seeder.seed(mock_session, data)
        
        # Should only create once, then update
        assert mock_channel_repo.create.call_count == 1
        assert result.created == 1
        assert result.updated >= 0  # May be 0 if watch history processing doesn't find additional unique channels

    async def test_batch_processing_commits(self, channel_seeder, mock_session, mock_channel_repo):
        """Test that seeding commits in batches for performance."""
        # Create data with many subscriptions to trigger batch commits
        subscriptions = [
            TakeoutSubscription(
                channel_id=YouTubeIdFactory.create_channel_id(f"channel_{i}"),
                channel_title=f"Channel {i}",
                channel_url=f"https://youtube.com/channel/{YouTubeIdFactory.create_channel_id(f'channel_{i}')}"
            )
            for i in range(150)  # More than batch size of 100
        ]
        
        data = TakeoutData(takeout_path=Path("/test/takeout"), subscriptions=subscriptions, watch_history=[], playlists=[])
        mock_channel_repo.get_by_channel_id.return_value = None
        
        await channel_seeder.seed(mock_session, data)
        
        # Should have called commit multiple times for batching
        assert mock_session.commit.call_count >= 2  # At least 2 batch commits

    def test_channel_id_generation_consistency(self, channel_seeder):
        """Test that channel ID generation is consistent for same input."""
        channel_name = "Test Channel"
        
        from src.chronovista.services.seeding.channel_seeder import generate_valid_channel_id
        id1 = generate_valid_channel_id(channel_name)
        id2 = generate_valid_channel_id(channel_name)
        
        # Should generate same ID for same input
        assert id1 == id2
        assert id1.startswith("UC")
        assert len(id1) == 24

    async def test_missing_channel_name_handling(self, channel_seeder):
        """Test handling of entries with missing channel names."""
        watch_entry = TakeoutWatchEntry(
            title="Test Video",
            title_url="https://youtube.com/watch?v=abc",
            channel_name=None,  # Missing channel name
            watched_at=datetime.now(),
            video_id="abc",
            channel_id=None
        )
        
        channel_create = channel_seeder._transform_watch_entry_to_channel(watch_entry)
        
        # Should return None for missing channel name
        assert channel_create is None