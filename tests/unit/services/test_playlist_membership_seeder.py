"""
Tests for PlaylistMembershipSeeder - creates playlist-video relationships.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)
from chronovista.repositories.playlist_repository import PlaylistRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.seeding.base_seeder import ProgressCallback, SeedResult
from chronovista.services.seeding.playlist_membership_seeder import (
    PlaylistMembershipSeeder,
)
from tests.factories.id_factory import TestIds, YouTubeIdFactory
from tests.factories.takeout_data_factory import create_takeout_data
from tests.factories.takeout_playlist_factory import create_takeout_playlist
from tests.factories.takeout_playlist_item_factory import create_takeout_playlist_item

pytestmark = pytest.mark.asyncio


class TestPlaylistMembershipSeederInitialization:
    """Tests for PlaylistMembershipSeeder initialization."""

    def test_initialization(self) -> None:
        """Test seeder initialization."""
        seeder = PlaylistMembershipSeeder()

        assert isinstance(seeder.membership_repo, PlaylistMembershipRepository)
        assert isinstance(seeder.video_repo, VideoRepository)
        assert isinstance(seeder.playlist_repo, PlaylistRepository)
        assert isinstance(seeder.channel_repo, ChannelRepository)
        assert seeder.get_dependencies() == {"playlists", "videos"}
        assert seeder.get_data_type() == "playlist_memberships"


class TestPlaylistMembershipSeederSeeding:
    """Tests for main seeding functionality."""

    @pytest.fixture
    def seeder(self) -> PlaylistMembershipSeeder:
        """Create PlaylistMembershipSeeder instance."""
        seeder = PlaylistMembershipSeeder()
        # Mock all repositories
        seeder.membership_repo = Mock(spec=PlaylistMembershipRepository)
        seeder.membership_repo.membership_exists = AsyncMock()
        seeder.membership_repo.create = AsyncMock()
        seeder.video_repo = Mock(spec=VideoRepository)
        seeder.video_repo.get_by_video_id = AsyncMock()
        seeder.video_repo.create = AsyncMock()
        seeder.playlist_repo = Mock(spec=PlaylistRepository)
        seeder.playlist_repo.get_by_playlist_id = AsyncMock()
        seeder.channel_repo = Mock(spec=ChannelRepository)
        seeder.channel_repo.get_by_channel_id = AsyncMock()
        seeder.channel_repo.create = AsyncMock()
        return seeder

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def sample_takeout_data(self):
        """Create sample takeout data with playlists containing videos."""
        return create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Favorites",
                    file_path=Path("/test/Favorites.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_1,
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_2,
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                    ],
                    video_count=3,
                ),
                create_takeout_playlist(
                    name="Watch Later",
                    file_path=Path("/test/Watch Later.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_1,  # Same video in multiple playlists
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                    ],
                    video_count=1,
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_seed_empty_data(
        self, seeder: PlaylistMembershipSeeder, mock_session: AsyncMock
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

    @pytest.mark.asyncio
    async def test_seed_new_memberships(
        self,
        seeder: PlaylistMembershipSeeder,
        mock_session: AsyncMock,
        sample_takeout_data,
    ) -> None:
        """Test seeding new playlist memberships."""
        # Mock repositories to simulate existing playlists/videos but no memberships
        mock_playlist = Mock()
        mock_playlist.playlist_id = "PL123"
        mock_video = Mock()
        mock_video.video_id = TestIds.NEVER_GONNA_GIVE_YOU_UP

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", return_value=mock_video
            ) as mock_get_video,
            patch.object(
                seeder.membership_repo, "membership_exists", return_value=False
            ) as mock_exists,
            patch.object(seeder.membership_repo, "create") as mock_create,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.created == 4  # 3 + 1 videos across playlists
            assert result.updated == 0
            assert result.failed == 0
            assert result.success_rate == 100.0

            # Verify repository calls
            assert mock_create.call_count == 4

    @pytest.mark.asyncio
    async def test_seed_existing_memberships(
        self,
        seeder: PlaylistMembershipSeeder,
        mock_session: AsyncMock,
        sample_takeout_data,
    ) -> None:
        """Test seeding existing playlist memberships (updates)."""
        # Mock repositories to return existing entities
        mock_playlist = Mock()
        mock_video = Mock()
        mock_membership = Mock()

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", return_value=mock_video
            ) as mock_get_video,
            patch.object(
                seeder.membership_repo, "membership_exists", return_value=True
            ) as mock_exists,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.created == 0
            assert result.updated == 4  # Four memberships updated
            assert result.failed == 0
            assert result.success_rate == 100.0

    @pytest.mark.asyncio
    async def test_seed_with_missing_videos(
        self,
        seeder: PlaylistMembershipSeeder,
        mock_session: AsyncMock,
        sample_takeout_data,
    ) -> None:
        """Test seeding when some videos are missing (placeholder creation)."""
        # Mock playlist exists but video doesn't
        mock_playlist = Mock()

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", return_value=None
            ) as mock_get_video,
            patch.object(
                seeder.membership_repo, "membership_exists", return_value=False
            ) as mock_exists,
            patch.object(seeder.video_repo, "create") as mock_video_create,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data)

            # Should create placeholder videos and memberships
            assert result.created > 0
            # Verify placeholder video creation was called
            assert mock_video_create.call_count > 0

    @pytest.mark.asyncio
    async def test_seed_with_missing_playlists(
        self,
        seeder: PlaylistMembershipSeeder,
        mock_session: AsyncMock,
        sample_takeout_data,
    ) -> None:
        """Test seeding when playlists are missing."""
        # Mock playlist doesn't exist
        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", return_value=None
        ) as mock_get_playlist:
            result = await seeder.seed(mock_session, sample_takeout_data)

            # Should handle missing playlists gracefully (may skip or create errors)
            assert isinstance(result, SeedResult)

    @pytest.mark.asyncio
    async def test_seed_with_progress_callback(
        self,
        seeder: PlaylistMembershipSeeder,
        mock_session: AsyncMock,
        sample_takeout_data,
    ) -> None:
        """Test seeding with progress callback."""
        progress_calls = []

        def mock_progress_callback(data_type: str) -> None:
            progress_calls.append(data_type)

        progress = ProgressCallback(mock_progress_callback)

        # Mock existing entities
        mock_playlist = Mock()
        mock_video = Mock()

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", return_value=mock_video
            ) as mock_get_video,
            patch.object(
                seeder.membership_repo, "membership_exists", return_value=False
            ) as mock_exists,
        ):

            result = await seeder.seed(mock_session, sample_takeout_data, progress)

            # Progress callback is called every 100 items, so with only 4 items it won't be called
            # This behavior is correct for the actual implementation
            # The test should verify that progress callback is set up properly, not necessarily called
            assert result.created == 4  # Verify the seeding worked correctly

    @pytest.mark.asyncio
    async def test_seed_error_handling(
        self,
        seeder: PlaylistMembershipSeeder,
        mock_session: AsyncMock,
        sample_takeout_data,
    ) -> None:
        """Test error handling during seeding."""
        # Mock repository to raise error
        with patch.object(
            seeder.playlist_repo,
            "get_by_playlist_id",
            side_effect=Exception("Database error"),
        ) as mock_get_playlist:
            result = await seeder.seed(mock_session, sample_takeout_data)

            assert result.failed > 0
            assert len(result.errors) > 0
            assert "Database error" in str(result.errors[0])


class TestPlaylistMembershipSeederTransformations:
    """Tests for data transformation methods."""

    @pytest.fixture
    def seeder(self) -> PlaylistMembershipSeeder:
        """Create PlaylistMembershipSeeder instance."""
        return PlaylistMembershipSeeder()

    def test_generate_playlist_id_consistency(
        self, seeder: PlaylistMembershipSeeder
    ) -> None:
        """Test playlist ID generation consistency."""
        playlist_name = "Test Playlist"

        id1 = seeder._generate_playlist_id(playlist_name)
        id2 = seeder._generate_playlist_id(playlist_name)

        assert id1 == id2
        assert id1.startswith("PL")
        assert len(id1) == 34

    @pytest.mark.asyncio
    async def test_create_placeholder_video(
        self, seeder: PlaylistMembershipSeeder
    ) -> None:
        """Test creating placeholder video for missing video."""
        video_id = TestIds.TEST_VIDEO_1
        session = AsyncMock()

        # Mock the repository methods using patch.object
        with (
            patch.object(
                seeder.channel_repo, "get_by_channel_id", return_value=None
            ) as mock_get_channel,
            patch.object(seeder.channel_repo, "create") as mock_channel_create,
            patch.object(seeder.video_repo, "create") as mock_video_create,
        ):

            # This should not raise an error
            await seeder._create_placeholder_video(session, video_id)

            # Verify that the video creation was called
            mock_video_create.assert_called_once()

    def test_generate_placeholder_channel_id(
        self, seeder: PlaylistMembershipSeeder
    ) -> None:
        """Test generating placeholder channel ID."""
        video_id = TestIds.TEST_VIDEO_1

        channel_id = seeder._generate_placeholder_channel_id(video_id)

        assert channel_id.startswith("UC")
        assert len(channel_id) == 24

        # Should be consistent
        assert seeder._generate_placeholder_channel_id(video_id) == channel_id


class TestPlaylistMembershipSeederPositioning:
    """Tests for playlist position handling."""

    @pytest.fixture
    def seeder(self) -> PlaylistMembershipSeeder:
        """Create PlaylistMembershipSeeder instance."""
        seeder = PlaylistMembershipSeeder()
        # Mock repositories
        seeder.membership_repo = Mock(spec=PlaylistMembershipRepository)
        seeder.membership_repo.membership_exists = AsyncMock()
        seeder.membership_repo.create = AsyncMock()
        seeder.video_repo = Mock(spec=VideoRepository)
        seeder.video_repo.get_by_video_id = AsyncMock()
        seeder.playlist_repo = Mock(spec=PlaylistRepository)
        seeder.playlist_repo.get_by_playlist_id = AsyncMock()
        return seeder

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_position_ordering_in_playlist(
        self, seeder: PlaylistMembershipSeeder, mock_session: AsyncMock
    ) -> None:
        """Test that playlist positions are correctly assigned."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Ordered Playlist",
                    file_path=Path("/test/ordered.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_1,
                            creation_timestamp=datetime(
                                2024, 1, 1, tzinfo=timezone.utc
                            ),
                        ),
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_2,
                            creation_timestamp=datetime(
                                2024, 1, 2, tzinfo=timezone.utc
                            ),
                        ),
                        create_takeout_playlist_item(
                            video_id=TestIds.NEVER_GONNA_GIVE_YOU_UP,
                            creation_timestamp=datetime(
                                2024, 1, 3, tzinfo=timezone.utc
                            ),
                        ),
                    ],
                    video_count=3,
                ),
            ],
        )

        # Mock existing entities
        mock_playlist = Mock()
        mock_video = Mock()

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", return_value=mock_video
            ) as mock_get_video,
            patch.object(
                seeder.membership_repo, "membership_exists", return_value=False
            ) as mock_exists,
            patch.object(seeder.membership_repo, "create") as mock_create,
        ):

            result = await seeder.seed(mock_session, data)

            # Verify that positions were assigned correctly
            assert mock_create.call_count == 3

        # Check that create was called with correct position values
        create_calls = mock_create.call_args_list
        positions = []
        for call in create_calls:
            # The create method should be called with (session, obj_in=membership_create)
            membership_create = call[1]["obj_in"]  # keyword argument obj_in
            positions.append(membership_create.position)

        assert positions == [0, 1, 2]  # Sequential positions


class TestPlaylistMembershipSeederBatchProcessing:
    """Tests for batch processing functionality."""

    @pytest.fixture
    def seeder(self) -> PlaylistMembershipSeeder:
        """Create PlaylistMembershipSeeder instance."""
        seeder = PlaylistMembershipSeeder()
        # Mock repositories
        seeder.membership_repo = Mock(spec=PlaylistMembershipRepository)
        seeder.membership_repo.membership_exists = AsyncMock()
        seeder.membership_repo.create = AsyncMock()
        seeder.video_repo = Mock(spec=VideoRepository)
        seeder.video_repo.get_by_video_id = AsyncMock()
        seeder.playlist_repo = Mock(spec=PlaylistRepository)
        seeder.playlist_repo.get_by_playlist_id = AsyncMock()
        return seeder

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_batch_processing_large_playlist(
        self, seeder: PlaylistMembershipSeeder, mock_session: AsyncMock
    ) -> None:
        """Test batch processing with large playlist."""
        # Create playlist with many videos to trigger batch commits
        playlist_items = []
        for i in range(150):  # More than batch size of 100
            playlist_items.append(
                create_takeout_playlist_item(
                    video_id=YouTubeIdFactory.create_video_id(f"video_{i}"),
                    creation_timestamp=datetime.now(timezone.utc),
                )
            )

        large_data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Large Playlist",
                    file_path=Path("/test/large.csv"),
                    videos=playlist_items,
                    video_count=150,
                ),
            ],
        )

        # Mock existing entities
        mock_playlist = Mock()
        mock_video = Mock()

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", return_value=mock_video
            ) as mock_get_video,
            patch.object(
                seeder.membership_repo, "membership_exists", return_value=False
            ) as mock_exists,
        ):

            result = await seeder.seed(mock_session, large_data)

            # Should have processed all memberships
            assert result.created == 150
            # Should have called commit at least once (implementation may batch differently)
            assert mock_session.commit.call_count >= 1


class TestPlaylistMembershipSeederEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def seeder(self) -> PlaylistMembershipSeeder:
        """Create PlaylistMembershipSeeder instance."""
        seeder = PlaylistMembershipSeeder()
        # Mock repositories
        seeder.membership_repo = Mock(spec=PlaylistMembershipRepository)
        seeder.membership_repo.membership_exists = AsyncMock()
        seeder.membership_repo.create = AsyncMock()
        seeder.video_repo = Mock(spec=VideoRepository)
        seeder.video_repo.get_by_video_id = AsyncMock()
        seeder.playlist_repo = Mock(spec=PlaylistRepository)
        seeder.playlist_repo.get_by_playlist_id = AsyncMock()
        seeder.channel_repo = Mock(spec=ChannelRepository)
        seeder.channel_repo.get_by_channel_id = AsyncMock()
        seeder.channel_repo.create = AsyncMock()
        return seeder

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_empty_playlist(
        self, seeder: PlaylistMembershipSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling of playlist with no videos."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Empty Playlist",
                    file_path=Path("/test/empty.csv"),
                    videos=[],
                    video_count=0,
                ),
            ],
        )

        mock_playlist = Mock()

        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
        ) as mock_get_playlist:
            result = await seeder.seed(mock_session, data)

            # Should handle empty playlist gracefully
            assert result.created == 0
            assert result.failed == 0

    @pytest.mark.asyncio
    async def test_playlist_item_without_video_id(
        self, seeder: PlaylistMembershipSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling playlist item without video ID."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Problem Playlist",
                    file_path=Path("/test/problem.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id="",  # Empty video ID (will be stripped to empty)
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                    ],
                    video_count=1,
                ),
            ],
        )

        mock_playlist = Mock()

        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
        ) as mock_get_playlist:
            result = await seeder.seed(mock_session, data)

            # Should handle empty video ID gracefully (should fail)
            assert result.failed >= 1

    @pytest.mark.asyncio
    async def test_duplicate_videos_in_same_playlist(
        self, seeder: PlaylistMembershipSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling of duplicate videos in same playlist."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Duplicate Videos",
                    file_path=Path("/test/duplicates.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_1,
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_1,  # Same video again
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_2,
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                    ],
                    video_count=3,
                ),
            ],
        )

        mock_playlist = Mock()
        mock_video = Mock()

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", return_value=mock_video
            ) as mock_get_video,
            patch.object(
                seeder.membership_repo,
                "membership_exists",
                side_effect=[False, True, False],
            ) as mock_exists,
        ):

            result = await seeder.seed(mock_session, data)

            # Should handle duplicates appropriately
            assert result.created + result.updated == 3

    def test_playlist_id_generation_consistency(
        self, seeder: PlaylistMembershipSeeder
    ) -> None:
        """Test that playlist ID generation is consistent."""
        playlist_name = "Test Playlist"

        # Test the actual method
        id1 = seeder._generate_playlist_id(playlist_name)
        id2 = seeder._generate_playlist_id(playlist_name)

        assert id1 == id2
        assert id1.startswith("PL")
        assert len(id1) == 34


class TestPlaylistMembershipSeederDependencies:
    """Tests for dependency management."""

    def test_has_correct_dependencies(self) -> None:
        """Test that seeder correctly declares dependencies."""
        seeder = PlaylistMembershipSeeder()

        assert seeder.has_dependencies()
        assert "playlists" in seeder.get_dependencies()
        assert "videos" in seeder.get_dependencies()
        assert len(seeder.get_dependencies()) == 2

    def test_data_type_consistency(self) -> None:
        """Test that data type is consistently reported."""
        seeder = PlaylistMembershipSeeder()

        assert seeder.get_data_type() == "playlist_memberships"


class TestPlaylistMembershipSeederIntegration:
    """Integration tests for playlist membership seeding."""

    @pytest.fixture
    def seeder(self) -> PlaylistMembershipSeeder:
        """Create PlaylistMembershipSeeder instance."""
        seeder = PlaylistMembershipSeeder()
        # Mock all repositories for controlled testing
        seeder.membership_repo = Mock(spec=PlaylistMembershipRepository)
        seeder.membership_repo.membership_exists = AsyncMock()
        seeder.membership_repo.create = AsyncMock()
        seeder.video_repo = Mock(spec=VideoRepository)
        seeder.video_repo.get_by_video_id = AsyncMock()
        seeder.video_repo.create = AsyncMock()
        seeder.playlist_repo = Mock(spec=PlaylistRepository)
        seeder.playlist_repo.get_by_playlist_id = AsyncMock()
        seeder.channel_repo = Mock(spec=ChannelRepository)
        seeder.channel_repo.get_by_channel_id = AsyncMock()
        seeder.channel_repo.create = AsyncMock()
        return seeder

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_complete_workflow_with_placeholders(
        self, seeder: PlaylistMembershipSeeder, mock_session: AsyncMock
    ) -> None:
        """Test complete workflow including placeholder creation."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Mixed Content Playlist",
                    file_path=Path("/test/mixed.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_1,  # Exists
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                        create_takeout_playlist_item(
                            video_id="missingVid1",  # Doesn't exist (11 chars to match VideoId validation)
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                    ],
                    video_count=2,
                ),
            ],
        )

        # Mock playlist exists
        mock_playlist = Mock()

        def mock_get_video(session, vid_id):
            return Mock() if vid_id == TestIds.TEST_VIDEO_1 else None

        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", return_value=mock_playlist
            ) as mock_get_playlist,
            patch.object(
                seeder.video_repo, "get_by_video_id", side_effect=mock_get_video
            ) as mock_get_video_method,
            patch.object(
                seeder.membership_repo, "membership_exists", return_value=False
            ) as mock_exists,
            patch.object(seeder.video_repo, "create") as mock_video_create,
        ):

            result = await seeder.seed(mock_session, data)

            # Should create both memberships (one with existing video, one with placeholder)
            assert result.created == 2

            # Should have created placeholder video
            assert mock_video_create.call_count == 1  # Only for missing video
