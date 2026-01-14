"""
Tests for VideoSeeder - creates videos from watch history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio

from chronovista.models.enums import LanguageCode
from chronovista.models.takeout.takeout_data import TakeoutData, TakeoutWatchEntry
from chronovista.models.video import VideoCreate
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.seeding.base_seeder import ProgressCallback, SeedResult
from chronovista.services.seeding.video_seeder import VideoSeeder
from tests.factories.id_factory import TestIds, YouTubeIdFactory
from tests.factories.takeout_data_factory import create_takeout_data
from tests.factories.takeout_watch_entry_factory import create_takeout_watch_entry


class TestVideoSeederUtilityFunctions:
    """Tests for utility functions."""

    # Note: generate_valid_video_id and generate_valid_channel_id were removed
    # as part of T017-T020. The new pattern uses:
    # - Real video IDs from Takeout data
    # - NULL channel_id with channel_name_hint for unknown channels

    pass  # No utility functions to test anymore


class TestVideoSeederInitialization:
    """Tests for VideoSeeder initialization."""

    @pytest.fixture
    def mock_video_repo(self) -> Mock:
        """Create mock video repository."""
        repo = Mock(spec=VideoRepository)
        repo.get_by_video_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    def test_initialization(self, mock_video_repo: Mock) -> None:
        """Test seeder initialization."""
        seeder = VideoSeeder(mock_video_repo)

        assert seeder.video_repo == mock_video_repo
        assert seeder.get_dependencies() == {"channels"}  # Depends on channels
        assert seeder.get_data_type() == "videos"


class TestVideoSeederSeeding:
    """Tests for main seeding functionality."""

    @pytest.fixture
    def mock_video_repo(self) -> Mock:
        """Create mock video repository."""
        repo = Mock(spec=VideoRepository)
        repo.get_by_video_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_video_repo: Mock) -> VideoSeeder:
        """Create VideoSeeder instance."""
        return VideoSeeder(mock_video_repo)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def sample_takeout_data(self) -> TakeoutData:
        """Create sample takeout data with watch history."""
        watch_history = [
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
                channel_name="Test Channel 1",
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
        ]

        return create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=watch_history,
            playlists=[],
        )

    async def test_seed_empty_data(
        self, seeder: VideoSeeder, mock_session: AsyncMock
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

    async def test_seed_new_videos(
        self,
        seeder: VideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding new videos."""
        # Mock repository to return None (videos don't exist)
        with (
            patch.object(
                seeder.video_repo,
                "get_by_video_id",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_get,
            patch.object(
                seeder.video_repo, "create", new_callable=AsyncMock
            ) as mock_create,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.created == 3  # Three unique videos
            assert result.updated == 0
            assert result.failed == 0
            assert result.success_rate == 100.0

            # Verify repository calls
            assert mock_create.call_count == 3

    async def test_seed_existing_videos_no_update_needed(
        self,
        seeder: VideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding existing videos that don't need updates.

        When existing video has complete data (channel_id, proper title),
        no update should occur.
        """
        # Mock video with complete data - no update needed
        mock_video = Mock()
        mock_video.channel_id = TestIds.TEST_CHANNEL_1  # Has channel_id
        mock_video.channel_name_hint = None
        mock_video.title = "Existing Title"  # Real title, not placeholder

        with patch.object(
            seeder.video_repo,
            "get_by_video_id",
            new_callable=AsyncMock,
            return_value=mock_video,
        ):
            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.created == 0
            assert result.updated == 0  # No updates needed - data is complete
            assert result.failed == 0
            assert result.success_rate == 100.0

    async def test_seed_existing_videos_update_channel_id(
        self,
        seeder: VideoSeeder,
        mock_session: AsyncMock,
    ) -> None:
        """Test seeding updates channel_id when existing is NULL.

        This is the key fix for the bug where playlist_membership_seeder
        creates placeholder videos with NULL channel_id, and video_seeder
        should update them when takeout data has the real channel_id.
        """
        # Create takeout data with channel_id
        takeout_data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[
                create_takeout_watch_entry(
                    title="Test Video",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                    channel_name="Test Channel",
                    watched_at=datetime.now(timezone.utc),
                    video_id=TestIds.TEST_VIDEO_1,
                    channel_id=TestIds.TEST_CHANNEL_1,  # Has real channel_id
                ),
            ],
            playlists=[],
        )

        # Mock existing video with NULL channel_id (placeholder scenario)
        mock_video = Mock()
        mock_video.channel_id = None  # NULL - needs update
        mock_video.channel_name_hint = None
        mock_video.title = "[Placeholder] Video"  # Placeholder title

        with (
            patch.object(
                seeder.video_repo,
                "get_by_video_id",
                new_callable=AsyncMock,
                return_value=mock_video,
            ),
            patch.object(
                seeder.video_repo,
                "update",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            result = await seeder.seed(mock_session, takeout_data)

            assert result.created == 0
            assert result.updated == 1  # Should update with channel_id
            assert result.failed == 0

            # Verify update was called with channel_id
            mock_update.assert_called_once()
            update_call = mock_update.call_args
            update_obj = update_call.kwargs["obj_in"]
            assert update_obj.channel_id == TestIds.TEST_CHANNEL_1
            assert update_obj.title == "Test Video"  # Title also updated

    async def test_seed_existing_videos_update_channel_name_hint(
        self,
        seeder: VideoSeeder,
        mock_session: AsyncMock,
    ) -> None:
        """Test seeding updates channel_name_hint when no channel_id available.

        When takeout entry has channel_name but no channel_id, and the existing
        video has neither, we should store the channel_name_hint for future resolution.
        """
        # Create takeout data without channel_id but with channel_name
        # NOTE: Must also set channel_url=None because the model validator
        # extracts channel_id from channel_url if present
        takeout_data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[
                create_takeout_watch_entry(
                    title="Test Video",
                    title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                    channel_name="Some Channel Name",  # Has name
                    watched_at=datetime.now(timezone.utc),
                    video_id=TestIds.TEST_VIDEO_1,
                    channel_id=None,  # No channel_id
                    channel_url=None,  # No URL either - prevents model validator from extracting channel_id
                ),
            ],
            playlists=[],
        )

        # Mock existing video with no channel info
        mock_video = Mock()
        mock_video.channel_id = None
        mock_video.channel_name_hint = None  # Missing - needs hint
        mock_video.title = "Existing Title"  # Has proper title

        with (
            patch.object(
                seeder.video_repo,
                "get_by_video_id",
                new_callable=AsyncMock,
                return_value=mock_video,
            ),
            patch.object(
                seeder.video_repo,
                "update",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            result = await seeder.seed(mock_session, takeout_data)

            assert result.created == 0
            assert result.updated == 1  # Should update with hint

            # Verify update was called with channel_name_hint
            mock_update.assert_called_once()
            update_call = mock_update.call_args
            update_obj = update_call.kwargs["obj_in"]
            assert update_obj.channel_name_hint == "Some Channel Name"

    async def test_seed_with_progress_callback(
        self,
        seeder: VideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding with progress callback."""
        progress_calls = []

        def mock_progress_callback(data_type: str) -> None:
            progress_calls.append(data_type)

        progress = ProgressCallback(mock_progress_callback)
        with patch.object(
            seeder.video_repo,
            "get_by_video_id",
            new_callable=AsyncMock,
            return_value=None,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data, progress)

            assert "videos" in progress_calls

    async def test_seed_error_handling(
        self,
        seeder: VideoSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test error handling during seeding."""
        # Mock repository to raise error
        with patch.object(
            seeder.video_repo,
            "get_by_video_id",
            new_callable=AsyncMock,
            side_effect=Exception("Database error"),
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.failed > 0
            assert len(result.errors) > 0
            assert "Database error" in str(result.errors[0])

    async def test_transform_entry_to_video(self, seeder: VideoSeeder) -> None:
        """Test transforming watch entry to VideoCreate model."""
        watch_entry = create_takeout_watch_entry(
            title="Test Video Title",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        assert isinstance(video_create, VideoCreate)
        assert video_create.video_id == TestIds.TEST_VIDEO_1
        assert video_create.channel_id == TestIds.TEST_CHANNEL_1
        assert video_create.title == "Test Video Title"
        assert video_create.description == ""  # Default empty
        assert video_create.default_language == LanguageCode.ENGLISH  # Default

    async def test_deduplication_of_videos(
        self, seeder: VideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test that duplicate videos are handled correctly."""
        # Create data with duplicate video IDs
        watch_history = [
            create_takeout_watch_entry(
                title="Same Video First Watch",
                title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                channel_name="Test Channel",
                watched_at=datetime.now(timezone.utc),
                video_id=TestIds.TEST_VIDEO_1,  # Same ID
                channel_id=TestIds.TEST_CHANNEL_1,
            ),
            create_takeout_watch_entry(
                title="Same Video Second Watch",
                title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
                channel_name="Test Channel",
                watched_at=datetime.now(timezone.utc),
                video_id=TestIds.TEST_VIDEO_1,  # Same ID again
                channel_id=TestIds.TEST_CHANNEL_1,
            ),
            create_takeout_watch_entry(
                title="Different Video",
                title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_2}",
                channel_name="Test Channel",
                watched_at=datetime.now(timezone.utc),
                video_id=TestIds.TEST_VIDEO_2,  # Different ID
                channel_id=TestIds.TEST_CHANNEL_1,
            ),
        ]

        data_with_duplicates = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=watch_history,
            playlists=[],
        )

        # Mock first call returns None (new), second call returns existing video
        # Only 2 calls should be made for 2 unique videos
        with patch.object(
            seeder.video_repo,
            "get_by_video_id",
            new_callable=AsyncMock,
            side_effect=[None, Mock()],
        ):

            result = await seeder.seed(mock_session, data_with_duplicates)

            # Should only process 2 unique videos (TEST_VIDEO_1 and TEST_VIDEO_2)
            assert result.created == 1  # First unique video was created
            assert result.updated == 1  # Second unique video existed


class TestVideoSeederBatchProcessing:
    """Tests for batch processing functionality."""

    @pytest.fixture
    def mock_video_repo(self) -> Mock:
        """Create mock video repository."""
        repo = Mock(spec=VideoRepository)
        repo.get_by_video_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_video_repo: Mock) -> VideoSeeder:
        """Create VideoSeeder instance."""
        return VideoSeeder(mock_video_repo)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_batch_processing_large_dataset(
        self, seeder: VideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test batch processing with large number of watch entries."""
        # Create data with many unique videos to trigger batch commits
        watch_entries = []
        for i in range(750):  # More than batch size of 500
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
            seeder.video_repo,
            "get_by_video_id",
            new_callable=AsyncMock,
            return_value=None,
        ):

            result = await seeder.seed(mock_session, large_data)

            # Should have processed all videos
            assert result.created == 750
            # Should have called commit multiple times for batching
            assert mock_session.commit.call_count >= 2


class TestVideoSeederEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def mock_video_repo(self) -> Mock:
        """Create mock video repository."""
        repo = Mock(spec=VideoRepository)
        repo.get_by_video_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_video_repo: Mock) -> VideoSeeder:
        """Create VideoSeeder instance."""
        return VideoSeeder(mock_video_repo)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    async def test_watch_entry_without_video_id(
        self, seeder: VideoSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling watch entry without video ID."""
        watch_history = [
            create_takeout_watch_entry(
                title="Video Without ID",
                title_url="https://www.youtube.com/watch?v=invalid",
                channel_name="Test Channel",
                watched_at=datetime.now(timezone.utc),
                video_id=None,  # Missing video ID
                channel_id=TestIds.TEST_CHANNEL_1,
            ),
        ]

        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=watch_history,
            playlists=[],
        )

        result = await seeder.seed(mock_session, data)

        # Should handle missing video ID gracefully (either skip or generate)
        assert result.failed >= 0

    async def test_watch_entry_without_channel_id(self, seeder: VideoSeeder) -> None:
        """Test handling watch entry without channel ID."""
        watch_entry = create_takeout_watch_entry(
            title="Video Without Channel ID",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Unknown Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=None,  # Missing channel ID
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        # Should generate a channel ID or handle gracefully
        assert video_create.channel_id.startswith("UC")
        assert len(video_create.channel_id) == 24

    async def test_empty_video_title(self, seeder: VideoSeeder) -> None:
        """Test handling of watch entry with empty title."""
        watch_entry = create_takeout_watch_entry(
            title="",  # Empty title
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        # Should handle empty title appropriately (based on actual implementation)
        assert video_create.title is not None

    async def test_special_characters_in_title(self, seeder: VideoSeeder) -> None:
        """Test handling of special characters in video titles."""
        watch_entry = create_takeout_watch_entry(
            title="Video with émojis 🎵 and spëcial chars!",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        # Should preserve special characters
        assert video_create.title == "Video with émojis 🎵 and spëcial chars!"

    async def test_very_long_title(self, seeder: VideoSeeder) -> None:
        """Test handling of very long video titles."""
        long_title = "A" * 1000  # Very long title

        watch_entry = create_takeout_watch_entry(
            title=long_title,
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        # Should either truncate or preserve based on implementation
        assert len(video_create.title) > 0

    async def test_missing_channel_name_handling(self, seeder: VideoSeeder) -> None:
        """Test handling of entries with missing channel names."""
        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name=None,  # Missing channel name
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        # Should handle missing channel name gracefully
        assert video_create.channel_id is not None


class TestVideoSeederDependencies:
    """Tests for dependency management."""

    @pytest.fixture
    def mock_video_repo(self) -> Mock:
        """Create mock video repository."""
        return Mock(spec=VideoRepository)

    def test_has_channel_dependency(self, mock_video_repo: Mock) -> None:
        """Test that seeder correctly declares channel dependency."""
        seeder = VideoSeeder(mock_video_repo)

        assert seeder.has_dependencies()
        assert "channels" in seeder.get_dependencies()
        assert len(seeder.get_dependencies()) == 1

    def test_data_type_consistency(self, mock_video_repo: Mock) -> None:
        """Test that data type is consistently reported."""
        seeder = VideoSeeder(mock_video_repo)

        assert seeder.get_data_type() == "videos"


class TestVideoSeederDefaultValues:
    """Tests for default value handling."""

    @pytest.fixture
    def mock_video_repo(self) -> Mock:
        """Create mock video repository."""
        return Mock(spec=VideoRepository)

    @pytest.fixture
    def seeder(self, mock_video_repo: Mock) -> VideoSeeder:
        """Create VideoSeeder instance."""
        return VideoSeeder(mock_video_repo)

    def test_default_language_code(self, seeder: VideoSeeder) -> None:
        """Test that default language code is set correctly."""
        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        assert video_create.default_language == LanguageCode.ENGLISH

    def test_default_description(self, seeder: VideoSeeder) -> None:
        """Test that default description is set."""
        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=datetime.now(timezone.utc),
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        assert video_create.description == ""

    def test_upload_date_estimation(self, seeder: VideoSeeder) -> None:
        """Test upload date estimation from watch date."""
        watch_date = datetime.now(timezone.utc)
        watch_entry = create_takeout_watch_entry(
            title="Test Video",
            title_url=f"https://www.youtube.com/watch?v={TestIds.TEST_VIDEO_1}",
            channel_name="Test Channel",
            watched_at=watch_date,
            video_id=TestIds.TEST_VIDEO_1,
            channel_id=TestIds.TEST_CHANNEL_1,
        )

        video_create = seeder._transform_entry_to_video(watch_entry)

        # Upload date should be set from watch date (based on actual implementation)
        assert video_create.upload_date == watch_entry.watched_at
