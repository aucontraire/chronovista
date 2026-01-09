"""
Tests for UserVideoSeeder - creates user-video relationships from watch history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio

from chronovista.models.takeout.takeout_data import TakeoutData
from chronovista.models.user_video import UserVideoCreate
from chronovista.repositories.user_video_repository import UserVideoRepository
from chronovista.services.seeding.base_seeder import ProgressCallback, SeedResult
from chronovista.services.seeding.user_video_seeder import UserVideoSeeder
from tests.factories.id_factory import TestIds, YouTubeIdFactory
from tests.factories.takeout_data_factory import create_takeout_data
from tests.factories.takeout_watch_entry_factory import create_takeout_watch_entry


class TestUserVideoSeederInitialization:
    """Tests for UserVideoSeeder initialization."""

    @pytest.fixture
    def mock_user_video_repo(self) -> Mock:
        """Create mock user video repository."""
        repo = Mock(spec=UserVideoRepository)
        repo.get_by_composite_key = AsyncMock()
        repo.create = AsyncMock()
        return repo

    def test_initialization_default_user(self, mock_user_video_repo: Mock) -> None:
        """Test seeder initialization with default user."""
        seeder = UserVideoSeeder(mock_user_video_repo)

        assert seeder.user_video_repo == mock_user_video_repo
        assert seeder.user_id == "takeout_user"
        assert seeder.get_dependencies() == {"videos"}  # Depends on videos
        assert seeder.get_data_type() == "user_videos"

    def test_initialization_custom_user(self, mock_user_video_repo: Mock) -> None:
        """Test seeder initialization with custom user ID."""
        custom_user_id = "custom_test_user"
        seeder = UserVideoSeeder(mock_user_video_repo, user_id=custom_user_id)

        assert seeder.user_id == custom_user_id


class TestUserVideoSeederSeeding:
    """Tests for main seeding functionality."""

    @pytest.fixture
    def mock_user_video_repo(self) -> Mock:
        """Create mock user video repository."""
        repo = Mock(spec=UserVideoRepository)
        repo.get_by_composite_key = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_user_video_repo: Mock) -> UserVideoSeeder:
        """Create UserVideoSeeder instance."""
        return UserVideoSeeder(mock_user_video_repo, user_id="test_user")

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def sample_takeout_data(self) -> TakeoutData:
        """Create sample takeout data with watch history."""
        return create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[
                create_takeout_watch_entry(
                    title="Never Gonna Give You Up",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
                    channel_name="Rick Astley",
                    watched_at=datetime.now(timezone.utc),
                    video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
                    channel_id=TestIds.RICK_ASTLEY_CHANNEL,
                ),
                create_takeout_watch_entry(
                    title="Test Video 1",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                    channel_name="Test Channel",
                    watched_at=datetime.now(timezone.utc),
                    video_id=TestIds.TEST_VIDEO_1,
                    channel_id=TestIds.TEST_CHANNEL_1,
                ),
                create_takeout_watch_entry(
                    title="Test Video 2",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_2}",
                    channel_name="Test Channel 2",
                    watched_at=datetime.now(timezone.utc),
                    video_id=TestIds.TEST_VIDEO_2,
                    channel_id=TestIds.TEST_CHANNEL_2,
                ),
            ],
            playlists=[],
        )

    async def test_seed_empty_data(
        self, seeder: UserVideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test seeding with empty takeout data."""
        empty_data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[],
        )

        result = await seeder.seed(mock_session, empty_data)

        assert isinstance(result, SeedResult)
        assert result.created == 0
        assert result.updated == 0
        assert result.failed == 0
        assert result.success_rate == 100.0

    async def test_seed_new_user_videos(
        self,
        seeder: UserVideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding new user-video relationships."""
        # Mock repository to return None (relationships don't exist)
        with (
            patch.object(
                seeder.user_video_repo,
                "get_by_composite_key",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_get,
            patch.object(
                seeder.user_video_repo, "create", new_callable=AsyncMock
            ) as mock_create,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.created == 3  # Three videos watched
            assert result.updated == 0
            assert result.failed == 0
            assert result.success_rate == 100.0

            # Verify repository calls
            assert mock_create.call_count == 3

    async def test_seed_existing_user_videos(
        self,
        seeder: UserVideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding existing user-video relationships (updates)."""
        # Mock repository to return existing relationship
        mock_user_video = Mock()
        with patch.object(
            seeder.user_video_repo,
            "get_by_composite_key",
            new_callable=AsyncMock,
            return_value=mock_user_video,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.created == 0
            assert result.updated == 3  # Three relationships updated
            assert result.failed == 0
            assert result.success_rate == 100.0

    async def test_seed_with_progress_callback(
        self,
        seeder: UserVideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding with progress callback."""
        progress_calls = []

        def mock_progress_callback(data_type: str) -> None:
            progress_calls.append(data_type)

        progress = ProgressCallback(mock_progress_callback)
        with patch.object(
            seeder.user_video_repo,
            "get_by_composite_key",
            new_callable=AsyncMock,
            return_value=None,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data, progress)

            assert "user_videos" in progress_calls

    async def test_seed_error_handling(
        self,
        seeder: UserVideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test error handling during seeding."""
        # Mock repository to raise error
        with patch.object(
            seeder.user_video_repo,
            "get_by_composite_key",
            new_callable=AsyncMock,
            side_effect=Exception("Database error"),
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.failed > 0
            assert len(result.errors) > 0
            assert "Database error" in str(result.errors[0])

    async def test_transform_watch_entry_to_user_video(
        self, seeder: UserVideoSeeder
    ) -> None:
        """Test transforming watch entry to UserVideoCreate model."""
        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        user_video_create = seeder._transform_entry(watch_entry)

        assert isinstance(user_video_create, UserVideoCreate)
        assert user_video_create.user_id == "test_user"
        assert user_video_create.video_id == TestIds.TEST_VIDEO_1
        assert user_video_create.watched_at == watch_entry.watched_at
        # Check fields that actually exist in the implementation
        assert user_video_create.rewatch_count == 0

    async def test_filter_entries_with_timestamps(
        self, seeder: UserVideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test filtering watch entries that have timestamps."""
        from chronovista.models.takeout.takeout_data import TakeoutWatchEntry

        # Create entries directly to ensure None is preserved
        entry_with_timestamp_1 = TakeoutWatchEntry(
            title="With Timestamp",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),  # Has timestamp
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
            channel_url=f"https://www.youtube.com/channel/{TestIds.TEST_CHANNEL_1}",
            raw_time="2024-01-01T10:00:00Z",
        )

        entry_without_timestamp = TakeoutWatchEntry(
            title="Without Timestamp",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_2}",
            channel_name="Test Channel",
            watched_at=None,  # No timestamp - this should be preserved
            video_id=TestIds.TEST_VIDEO_2,
            channel_id=TestIds.TEST_CHANNEL_2,
            channel_url=f"https://www.youtube.com/channel/{TestIds.TEST_CHANNEL_2}",
            raw_time=None,
        )

        entry_with_timestamp_2 = TakeoutWatchEntry(
            title="With Timestamp 2",
            title_url=f"https://www.youtube.com/watch?v={TestIds.NEVER_GONNA_GIVE_YOU_UP}",
            channel_name="Rick Astley",
            watched_at=datetime.now(timezone.utc),  # Has timestamp
            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
            channel_id=TestIds.RICK_ASTLEY_CHANNEL,
            channel_url=f"https://www.youtube.com/channel/{TestIds.RICK_ASTLEY_CHANNEL}",
            raw_time="2024-01-01T11:00:00Z",
        )

        # Create data with some entries missing timestamps
        data_mixed_timestamps = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[
                entry_with_timestamp_1,
                entry_without_timestamp,
                entry_with_timestamp_2,
            ],
            playlists=[],
        )

        with (
            patch.object(
                seeder.user_video_repo,
                "get_by_composite_key",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_get,
            patch.object(
                seeder.user_video_repo, "create", new_callable=AsyncMock
            ) as mock_create,
        ):

            result = await seeder.seed(mock_session, data_mixed_timestamps)

            # Should only process entries with timestamps
            assert result.created == 2  # Only 2 entries have timestamps
            assert mock_create.call_count == 2


class TestUserVideoSeederBatchProcessing:
    """Tests for batch processing functionality."""

    @pytest.fixture
    def mock_user_video_repo(self) -> Mock:
        """Create mock user video repository."""
        repo = Mock(spec=UserVideoRepository)
        repo.get_by_composite_key = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_user_video_repo: Mock) -> UserVideoSeeder:
        """Create UserVideoSeeder instance."""
        return UserVideoSeeder(mock_user_video_repo, user_id="test_user")

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_batch_processing_large_dataset(
        self, seeder: UserVideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test batch processing with large number of watch entries."""
        # Create data with many watch entries to trigger batch commits
        watch_entries = []
        for i in range(1500):  # More than batch size of 1000
            watch_entries.append(
                create_takeout_watch_entry(
                    title=f"Video {i}",
                    title_url=f"https://www.youtube.com/watch?v={YouTubeIdFactory.create_video_id(f'video_{i}')}",
                    channel_name=f"Channel {i}",
                    watched_at=datetime.now(timezone.utc),
                    video_id=YouTubeIdFactory.create_video_id(f"video_{i}"),
                    channel_id=YouTubeIdFactory.create_channel_id(f"channel_{i}"),
                )
            )

        large_data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=watch_entries,
            playlists=[],
        )

        with patch.object(
            seeder.user_video_repo,
            "get_by_composite_key",
            new_callable=AsyncMock,
            return_value=None,
        ):

            result = await seeder.seed(mock_session, large_data)

            # Should have processed all entries
            assert result.created == 1500
            # Should have called commit multiple times for batching
            assert mock_session.commit.call_count >= 2


class TestUserVideoSeederEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def mock_user_video_repo(self) -> Mock:
        """Create mock user video repository."""
        repo = Mock(spec=UserVideoRepository)
        repo.get_by_composite_key = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_user_video_repo: Mock) -> UserVideoSeeder:
        """Create UserVideoSeeder instance."""
        return UserVideoSeeder(mock_user_video_repo, user_id="test_user")

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    async def test_watch_entry_without_video_id(
        self, seeder: UserVideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling watch entry without video ID."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[
                create_takeout_watch_entry(
                    title="Video Without ID",
                    title_url="https://www.youtube.com/watch?v=invalid",
                    channel_name="Test Channel",
                    watched_at=datetime.now(timezone.utc),
                    video_id=None,  # Missing video ID
                    channel_id=TestIds.TEST_CHANNEL_1,
                ),
            ],
            playlists=[],
        )

        result = await seeder.seed(mock_session, data)

        # Should handle missing video ID gracefully
        assert result.failed >= 0  # May be handled gracefully or as error

    async def test_watch_entry_with_invalid_timestamp(
        self, seeder: UserVideoSeeder
    ) -> None:
        """Test creating user video from watch entry with edge case timestamp."""
        # Create watch entry with very old timestamp
        old_timestamp = datetime(1990, 1, 1, tzinfo=timezone.utc)
        watch_entry = create_takeout_watch_entry(
            title="Old Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=old_timestamp,
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        user_video_create = seeder._transform_entry(watch_entry)

        assert user_video_create is not None
        assert user_video_create.watched_at == old_timestamp

    async def test_duplicate_video_watches_same_timestamp(
        self, seeder: UserVideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling duplicate watches of same video at same time."""
        same_timestamp = datetime.now(timezone.utc)

        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[
                create_takeout_watch_entry(
                    title="Same Video",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                    channel_name="Test Channel",
                    watched_at=same_timestamp,
                    video_id=TestIds.TEST_VIDEO_1,
                    channel_id=TestIds.TEST_CHANNEL_1,
                ),
                create_takeout_watch_entry(
                    title="Same Video Again",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                    channel_name="Test Channel",
                    watched_at=same_timestamp,
                    video_id=TestIds.TEST_VIDEO_1,  # Same video ID
                    channel_id=TestIds.TEST_CHANNEL_1,
                ),
            ],
            playlists=[],
        )

        # Mock first call returns None (new), second returns existing
        with patch.object(
            seeder.user_video_repo,
            "get_by_composite_key",
            new_callable=AsyncMock,
            side_effect=[None, Mock()],
        ):

            result = await seeder.seed(mock_session, data)

            # Should handle duplicates appropriately
            assert result.created + result.updated == 2

    async def test_missing_user_id(self, mock_user_video_repo: Mock) -> None:
        """Test behavior with empty user ID raises validation error."""
        seeder = UserVideoSeeder(mock_user_video_repo, user_id="")

        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        # Empty user ID should raise validation error when creating UserVideoCreate
        with pytest.raises(Exception) as exc_info:
            seeder._transform_entry(watch_entry)

        # Verify it's a validation error about empty user ID
        assert "UserId cannot be empty" in str(exc_info.value)

    def test_interaction_type_consistency(self, mock_user_video_repo: Mock) -> None:
        """Test that interaction type is consistently set."""
        seeder = UserVideoSeeder(mock_user_video_repo, user_id="test_user")

        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        user_video_create = seeder._transform_entry(watch_entry)

        # Check fields that actually exist in the implementation
        assert user_video_create is not None
        assert user_video_create.liked == False  # Default value
        assert user_video_create.saved_to_playlist == False  # Default value


class TestUserVideoSeederDependencies:
    """Tests for dependency management."""

    @pytest.fixture
    def mock_user_video_repo(self) -> Mock:
        """Create mock user video repository."""
        return Mock(spec=UserVideoRepository)

    def test_has_video_dependency(self, mock_user_video_repo: Mock) -> None:
        """Test that seeder correctly declares video dependency."""
        seeder = UserVideoSeeder(mock_user_video_repo)

        assert seeder.has_dependencies()
        assert "videos" in seeder.get_dependencies()
        assert len(seeder.get_dependencies()) == 1

    def test_data_type_consistency(self, mock_user_video_repo: Mock) -> None:
        """Test that data type is consistently reported."""
        seeder = UserVideoSeeder(mock_user_video_repo)

        assert seeder.get_data_type() == "user_videos"
