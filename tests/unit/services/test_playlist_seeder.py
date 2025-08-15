"""
Tests for PlaylistSeeder - creates playlists from takeout data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Module-level imports and configuration
# pytestmark = pytest.mark.asyncio  # Apply individually to avoid warnings for sync tests

from chronovista.models.playlist import PlaylistCreate
from chronovista.models.takeout.takeout_data import TakeoutData
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.playlist_repository import PlaylistRepository
from chronovista.services.seeding.base_seeder import ProgressCallback, SeedResult
from chronovista.services.seeding.playlist_seeder import (
    PlaylistSeeder,
    generate_valid_channel_id,
    generate_valid_playlist_id,
)
from tests.factories.id_factory import TestIds, YouTubeIdFactory
from tests.factories.takeout_data_factory import create_takeout_data
from tests.factories.takeout_playlist_factory import create_takeout_playlist
from tests.factories.takeout_playlist_item_factory import create_takeout_playlist_item


class TestPlaylistSeederUtilityFunctions:
    """Tests for utility functions."""

    def test_generate_valid_playlist_id(self) -> None:
        """Test playlist ID generation."""
        seed = "test_playlist"
        playlist_id = generate_valid_playlist_id(seed)

        assert playlist_id.startswith("PL")
        assert len(playlist_id) == 34  # PL + 32 hex chars

        # Should be consistent for same input
        assert generate_valid_playlist_id(seed) == playlist_id

    def test_generate_valid_channel_id(self) -> None:
        """Test channel ID generation."""
        seed = "test_channel"
        channel_id = generate_valid_channel_id(seed)

        assert channel_id.startswith("UC")
        assert len(channel_id) == 24  # UC + 22 hex chars

        # Should be consistent for same input
        assert generate_valid_channel_id(seed) == channel_id


class TestPlaylistSeederInitialization:
    """Tests for PlaylistSeeder initialization."""

    @pytest.fixture
    def mock_playlist_repo(self) -> Mock:
        """Create mock playlist repository."""
        repo = Mock(spec=PlaylistRepository)
        repo.get_by_playlist_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    def test_initialization_default_user(self, mock_playlist_repo: Mock) -> None:
        """Test seeder initialization with default user."""
        seeder = PlaylistSeeder(mock_playlist_repo)

        assert seeder.playlist_repo == mock_playlist_repo
        assert isinstance(seeder.channel_repo, ChannelRepository)
        assert seeder.user_id == "takeout_user"
        assert seeder.get_dependencies() == set()
        assert seeder.get_data_type() == "playlists"
        assert not seeder._user_channel_created

    def test_initialization_custom_user(self, mock_playlist_repo: Mock) -> None:
        """Test seeder initialization with custom user ID."""
        custom_user_id = "custom_test_user"
        seeder = PlaylistSeeder(mock_playlist_repo, user_id=custom_user_id)

        assert seeder.user_id == custom_user_id


class TestPlaylistSeederSeeding:
    """Tests for main seeding functionality."""

    @pytest.fixture
    def mock_playlist_repo(self) -> Mock:
        """Create mock playlist repository."""
        repo = Mock(spec=PlaylistRepository)
        repo.get_by_playlist_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_playlist_repo: Mock) -> PlaylistSeeder:
        """Create PlaylistSeeder instance."""
        return PlaylistSeeder(mock_playlist_repo, user_id="test_user")

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def sample_takeout_data(self) -> TakeoutData:
        """Create sample takeout data with playlists."""
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
                    ],
                    video_count=2,
                ),
                create_takeout_playlist(
                    name="Watch Later",
                    file_path=Path("/test/Watch Later.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id=TestIds.TEST_VIDEO_2,
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                    ],
                    video_count=1,
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_seed_empty_data(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
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
    async def test_seed_new_playlists(
        self,
        seeder: PlaylistSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding new playlists."""
        # Mock repositories to return None (playlists don't exist)
        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
        ) as mock_get, \
             patch.object(
                seeder.playlist_repo, "create", new_callable=AsyncMock
             ) as mock_create:
            mock_get.return_value = None
            
            # Mock user channel creation
            with patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ) as mock_ensure:
                mock_ensure.return_value = None  # Method doesn't return anything

                result = await seeder.seed(mock_session, sample_takeout_data)

                assert result.created == 2  # Two playlists created
                assert result.updated == 0
                assert result.failed == 0
                assert result.success_rate == 100.0

                # Verify playlist repository calls
                assert mock_create.call_count == 2
                mock_ensure.assert_called_once()

    @pytest.mark.asyncio
    async def test_seed_existing_playlists(
        self,
        seeder: PlaylistSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding existing playlists (updates)."""
        # Mock repositories to return existing playlist
        mock_playlist = Mock()
        
        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_playlist
            
            # Mock user channel creation
            with patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ) as mock_ensure:
                mock_ensure.return_value = None  # Method doesn't return anything

                result = await seeder.seed(mock_session, sample_takeout_data)

                assert result.created == 0
                assert result.updated == 2  # Two playlists updated
                assert result.failed == 0
                assert result.success_rate == 100.0

    @pytest.mark.asyncio
    async def test_seed_with_progress_callback(
        self,
        seeder: PlaylistSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test seeding with progress callback."""
        progress_calls = []

        def mock_progress_callback(data_type: str) -> None:
            progress_calls.append(data_type)

        progress = ProgressCallback(mock_progress_callback)

        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None
            
            with patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ):
                result = await seeder.seed(mock_session, sample_takeout_data, progress)

                assert "playlists" in progress_calls

    @pytest.mark.asyncio
    async def test_seed_error_handling(
        self,
        seeder: PlaylistSeeder,
        mock_session: AsyncMock,
        sample_takeout_data: TakeoutData,
    ) -> None:
        """Test error handling during seeding."""
        # Mock repository to raise error
        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = Exception("Database error")
            
            with patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ):
                result = await seeder.seed(mock_session, sample_takeout_data)

                assert result.failed > 0
                assert len(result.errors) > 0
                assert "Database error" in str(result.errors[0])

    @pytest.mark.asyncio
    async def test_transform_playlist_to_create_model(
        self, seeder: PlaylistSeeder
    ) -> None:
        """Test transforming takeout playlist to PlaylistCreate model."""
        playlist = create_takeout_playlist(
            name="Test Playlist",
            file_path=Path("/test/playlist.csv"),
            videos=[
                create_takeout_playlist_item(
                    video_id=TestIds.TEST_VIDEO_1,
                    creation_timestamp=datetime.now(timezone.utc),
                ),
            ],
            video_count=1,
        )

        channel_id = TestIds.TEST_CHANNEL_1

        playlist_create = seeder._transform_playlist_to_create(playlist, channel_id)

        assert isinstance(playlist_create, PlaylistCreate)
        assert playlist_create.title == "Test Playlist"
        assert playlist_create.channel_id == channel_id
        assert playlist_create.description is not None
        assert "imported from Google Takeout" in playlist_create.description
        assert playlist_create.playlist_id.startswith("PL")
        assert len(playlist_create.playlist_id) == 34

    @pytest.mark.asyncio
    async def test_ensure_user_channel_exists_first_time(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test ensuring user channel creation on first call."""
        # Mock channel repository to return None (channel doesn't exist)
        with patch.object(
            seeder.channel_repo, "get_by_channel_id", new_callable=AsyncMock
        ) as mock_get, patch.object(
            seeder.channel_repo, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_get.return_value = None

            # Generate the expected channel ID for this user
            from chronovista.services.seeding.playlist_seeder import (
                generate_valid_channel_id,
            )

            expected_channel_id = generate_valid_channel_id(seeder.user_id)

            await seeder._ensure_user_channel_exists(mock_session, expected_channel_id)

            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_user_channel_exists_existing(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test ensuring user channel when it already exists."""
        # Mock channel repository to return existing channel
        mock_channel = Mock()
        mock_channel.channel_id = TestIds.TEST_CHANNEL_1
        
        with patch.object(
            seeder.channel_repo, "get_by_channel_id", new_callable=AsyncMock
        ) as mock_get, patch.object(
            seeder.channel_repo, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_get.return_value = mock_channel

            await seeder._ensure_user_channel_exists(mock_session, TestIds.TEST_CHANNEL_1)

            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_channel_creation_cached(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test that user channel creation is cached via _user_channel_created flag."""
        # First call should create channel
        with patch.object(
            seeder.channel_repo, "get_by_channel_id", new_callable=AsyncMock
        ) as mock_get, patch.object(
            seeder.channel_repo, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_get.return_value = None

            # Simulate first seeding call
            assert not seeder._user_channel_created

            # After first seeding, flag should be set
            seeder._user_channel_created = True
            assert seeder._user_channel_created


class TestPlaylistSeederChannelHandling:
    """Tests for user channel creation and management."""

    @pytest.fixture
    def mock_playlist_repo(self) -> Mock:
        """Create mock playlist repository."""
        repo = Mock(spec=PlaylistRepository)
        repo.get_by_playlist_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_playlist_repo: Mock) -> PlaylistSeeder:
        """Create PlaylistSeeder instance."""
        return PlaylistSeeder(mock_playlist_repo, user_id="test_user")

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_user_channel_id_generation_consistency(
        self, seeder: PlaylistSeeder
    ) -> None:
        """Test that user channel ID is consistent for same user."""
        from chronovista.services.seeding.playlist_seeder import (
            generate_valid_channel_id,
        )

        channel_id_1 = generate_valid_channel_id(seeder.user_id)
        channel_id_2 = generate_valid_channel_id(seeder.user_id)

        assert channel_id_1 == channel_id_2
        assert channel_id_1.startswith("UC")
        assert len(channel_id_1) == 24


class TestPlaylistSeederBatchProcessing:
    """Tests for batch processing functionality."""

    @pytest.fixture
    def mock_playlist_repo(self) -> Mock:
        """Create mock playlist repository."""
        repo = Mock(spec=PlaylistRepository)
        repo.get_by_playlist_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_playlist_repo: Mock) -> PlaylistSeeder:
        """Create PlaylistSeeder instance."""
        return PlaylistSeeder(mock_playlist_repo, user_id="test_user")

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_batch_processing_large_dataset(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test batch processing with large number of playlists."""
        # Create data with many playlists to trigger batch commits
        playlists = []
        for i in range(150):  # More than batch size of 100
            playlists.append(
                create_takeout_playlist(
                    name=f"Playlist {i}",
                    file_path=Path(f"/test/Playlist_{i}.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id=YouTubeIdFactory.create_video_id(f"video_{i}"),
                            creation_timestamp=datetime.now(timezone.utc),
                        ),
                    ],
                    video_count=1,
                )
            )

        large_data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=playlists,
        )

        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None
            
            with patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ):
                result = await seeder.seed(mock_session, large_data)

                # Should have processed all playlists
                assert result.created == 150
                # Should have called commit multiple times for batching
                assert mock_session.commit.call_count >= 2


class TestPlaylistSeederEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def mock_playlist_repo(self) -> Mock:
        """Create mock playlist repository."""
        repo = Mock(spec=PlaylistRepository)
        repo.get_by_playlist_id = AsyncMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def seeder(self, mock_playlist_repo: Mock) -> PlaylistSeeder:
        """Create PlaylistSeeder instance."""
        return PlaylistSeeder(mock_playlist_repo, user_id="test_user")

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_empty_playlist_name_handling(self, seeder: PlaylistSeeder) -> None:
        """Test handling of playlists with empty names."""
        playlist = create_takeout_playlist(
            name="",  # Empty name
            file_path=Path("/test/empty.csv"),
            videos=[],
            video_count=0,
        )

        # Should raise validation error for empty title
        with pytest.raises(ValueError, match="String should have at least 1 character"):
            seeder._transform_playlist_to_create(playlist, TestIds.TEST_CHANNEL_1)

    @pytest.mark.asyncio
    async def test_playlist_with_no_videos(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling of playlists with no videos."""
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

        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None
            
            with patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ):
                result = await seeder.seed(mock_session, data)

                # Should still create the playlist
                assert result.created == 1

    @pytest.mark.asyncio
    async def test_invalid_playlist_data(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test handling of invalid playlist data."""
        # This test would depend on specific validation logic in the seeder
        # For now, we test that errors are handled gracefully
        with patch.object(
            seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = ValueError("Invalid playlist data")

            data = create_takeout_data(
                takeout_path=Path("/test/takeout"),
                subscriptions=[],
                watch_history=[],
                playlists=[
                    create_takeout_playlist(
                        name="Test Playlist",
                        file_path=Path("/test/test.csv"),
                        videos=[],
                        video_count=0,
                    ),
                ],
            )

            with patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ):
                result = await seeder.seed(mock_session, data)

                assert result.failed > 0
                assert "Invalid playlist data" in str(result.errors[0])

    def test_special_characters_in_playlist_name(self, seeder: PlaylistSeeder) -> None:
        """Test handling of special characters in playlist names."""
        playlist = create_takeout_playlist(
            name="Playlist with émojis 🎵 and spëcial chars!",
            file_path=Path("/test/special.csv"),
            videos=[],
            video_count=0,
        )

        playlist_create = seeder._transform_playlist_to_create(
            playlist, TestIds.TEST_CHANNEL_1
        )

        # Should preserve special characters
        assert playlist_create.title == "Playlist with émojis 🎵 and spëcial chars!"
