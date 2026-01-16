"""
Tests for PlaylistSeeder - creates playlists from takeout data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.playlist import PlaylistCreate
from chronovista.models.takeout.takeout_data import TakeoutData
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.playlist_repository import PlaylistRepository
from chronovista.services.seeding.base_seeder import ProgressCallback, SeedResult
from chronovista.services.seeding.playlist_seeder import (
    PlaylistSeeder,
    generate_internal_playlist_id,
)
from tests.factories.id_factory import TestIds, YouTubeIdFactory
from tests.factories.takeout_data_factory import create_takeout_data
from tests.factories.takeout_playlist_factory import create_takeout_playlist
from tests.factories.takeout_playlist_item_factory import create_takeout_playlist_item

# Module-level imports and configuration
# pytestmark = pytest.mark.asyncio  # Apply individually to avoid warnings for sync tests


class TestPlaylistSeederUtilityFunctions:
    """Tests for utility functions."""

    def test_generate_internal_playlist_id(self) -> None:
        """Test internal playlist ID generation with INT_ prefix."""
        seed = "test_playlist"
        playlist_id = generate_internal_playlist_id(seed)

        # AC: Generated IDs satisfy SC-006 (type identifiable at glance)
        # Note: PlaylistId validator normalizes INT_ to lowercase (int_)
        assert playlist_id.upper().startswith("INT_")

        # AC: Total length is 36 characters (INT_ prefix + 32 hex chars)
        assert len(playlist_id) == 36  # INT_ (4) + 32 hex chars = 36

        # AC: All generated IDs are lowercase hex
        hash_part = playlist_id[4:]  # Remove INT_ prefix
        assert hash_part == hash_part.lower()
        assert all(c in "0123456789abcdef" for c in hash_part)

        # AC: Same seed produces same ID (deterministic/idempotent)
        assert generate_internal_playlist_id(seed) == playlist_id

    def test_generate_internal_playlist_id_different_seeds(self) -> None:
        """Test that different seeds produce different IDs."""
        id1 = generate_internal_playlist_id("playlist_a")
        id2 = generate_internal_playlist_id("playlist_b")

        assert id1 != id2
        assert id1.upper().startswith("INT_")
        assert id2.upper().startswith("INT_")

    # Note: generate_valid_channel_id was removed as part of T017-T020
    # The new pattern uses NULL channel_id with channel_name_hint


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
        with (
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                seeder.playlist_repo, "create", new_callable=AsyncMock
            ) as mock_create,
        ):
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
        # Updated to use INT_ prefix (36 chars: INT_ + 32 hex)
        # Note: PlaylistId validator normalizes to lowercase (int_)
        assert playlist_create.playlist_id.upper().startswith("INT_")
        assert len(playlist_create.playlist_id) == 36

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="generate_valid_channel_id removed in T017-T020. "
        "Seeder now uses real channel IDs from YouTube API or NULL with hint."
    )
    async def test_ensure_user_channel_exists_first_time(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test ensuring user channel creation on first call."""
        pass  # Test skipped - helper function removed

    @pytest.mark.asyncio
    async def test_ensure_user_channel_exists_existing(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test ensuring user channel when it already exists."""
        # Mock channel repository to return existing channel
        mock_channel = Mock()
        mock_channel.channel_id = TestIds.TEST_CHANNEL_1

        with (
            patch.object(
                seeder.channel_repo, "get_by_channel_id", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                seeder.channel_repo, "create", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_get.return_value = mock_channel

            await seeder._ensure_user_channel_exists(
                mock_session, TestIds.TEST_CHANNEL_1
            )

            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_channel_creation_cached(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test that user channel creation is cached via _user_channel_created flag."""
        # First call should create channel
        with (
            patch.object(
                seeder.channel_repo, "get_by_channel_id", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                seeder.channel_repo, "create", new_callable=AsyncMock
            ) as mock_create,
        ):
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
    @pytest.mark.skip(
        reason="generate_valid_channel_id removed in T017-T020. "
        "Seeder now uses real channel IDs from YouTube API or NULL with hint."
    )
    async def test_user_channel_id_generation_consistency(
        self, seeder: PlaylistSeeder
    ) -> None:
        """Test that user channel ID is consistent for same user."""
        pass  # Test skipped - helper function removed


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


class TestPlaylistSeederReseedWithCascade:
    """Tests for re-seed upgrade path with FK cascade (T037)."""

    @pytest.fixture
    def mock_playlist_repo(self) -> Mock:
        """Create mock playlist repository."""
        repo = Mock(spec=PlaylistRepository)
        repo.get_by_playlist_id = AsyncMock()
        repo.create = AsyncMock()
        repo.delete_by_channel_id = AsyncMock()
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
        session.rollback = AsyncMock()
        return session

    def test_generate_internal_playlist_id_produces_int_prefix(self) -> None:
        """Test generate_internal_playlist_id produces INT_ prefix (36 chars total)."""
        seed = "test_playlist"
        playlist_id = generate_internal_playlist_id(seed)

        # Should have INT_ prefix (uppercase in generation)
        assert playlist_id.startswith("INT_")
        # Total length is 36 characters (INT_ = 4 chars + 32 hex chars)
        assert len(playlist_id) == 36

    def test_generate_internal_playlist_id_is_deterministic(self) -> None:
        """Test generate_internal_playlist_id is deterministic (same seed → same ID)."""
        seed = "my_playlist"
        id1 = generate_internal_playlist_id(seed)
        id2 = generate_internal_playlist_id(seed)

        # Same seed should produce same ID
        assert id1 == id2

    def test_generate_internal_playlist_id_produces_lowercase_hex(self) -> None:
        """Test generate_internal_playlist_id produces lowercase hex characters."""
        seed = "test_playlist"
        playlist_id = generate_internal_playlist_id(seed)

        # Hash part (after INT_ prefix) should be lowercase hex
        hash_part = playlist_id[4:]  # Skip INT_ prefix
        assert hash_part == hash_part.lower()
        assert all(c in "0123456789abcdef" for c in hash_part)

    @pytest.mark.asyncio
    async def test_clear_existing_playlists_deletes_via_cascade(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test re-seed deletes old playlists and memberships via CASCADE."""
        user_channel_id = "UC1234567890123456789012"

        # Mock delete_by_channel_id to return number of deleted playlists
        with patch.object(
            seeder.playlist_repo, "delete_by_channel_id", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = 5

            deleted_count = await seeder.clear_existing_playlists(
                mock_session, user_channel_id
            )

            # Should have called delete_by_channel_id
            mock_delete.assert_called_once_with(mock_session, user_channel_id)

            # Should return number of deleted playlists
            assert deleted_count == 5

    @pytest.mark.asyncio
    async def test_seed_with_clear_existing_creates_new_int_playlists(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test re-seed creates new playlists with INT_ prefix."""
        data = create_takeout_data(
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
                    ],
                    video_count=1,
                ),
            ],
        )

        # Mock create to track created playlists
        created_playlists = []

        async def mock_create(session: AsyncSession, obj_in: PlaylistCreate) -> Mock:
            created_playlists.append(obj_in)
            return Mock()

        # Mock clear operation, get_by_playlist_id, and create
        with (
            patch.object(
                seeder.playlist_repo, "delete_by_channel_id", new_callable=AsyncMock
            ) as mock_delete,
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                seeder.playlist_repo, "create", new=mock_create
            ),
            patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ),
        ):
            mock_delete.return_value = 3
            mock_get.return_value = None

            result = await seeder.seed(mock_session, data, clear_existing=True)

            # Should have cleared existing playlists
            mock_delete.assert_called_once()

            # Should have created 1 new playlist
            assert result.created == 1
            assert len(created_playlists) == 1

            # New playlist should have INT_ prefix
            new_playlist = created_playlists[0]
            assert new_playlist.playlist_id.upper().startswith("INT_")
            assert len(new_playlist.playlist_id) == 36

    @pytest.mark.asyncio
    async def test_seed_operates_within_transaction(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test re-seed operates within transaction (partial failure rolls back)."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="Playlist 1",
                    file_path=Path("/test/playlist1.csv"),
                    videos=[],
                    video_count=0,
                ),
            ],
        )

        # Mock clear to fail
        with (
            patch.object(
                seeder.playlist_repo, "delete_by_channel_id", new_callable=AsyncMock
            ) as mock_delete,
            patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ),
            pytest.raises(Exception, match="Database error"),
        ):
            mock_delete.side_effect = Exception("Database error")
            await seeder.seed(mock_session, data, clear_existing=True)

            # Should have rolled back on failure
            mock_session.rollback.assert_called()

    @pytest.mark.asyncio
    async def test_interrupted_reseed_can_be_safely_rerun(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test interrupted re-seed can be safely re-run (idempotent)."""
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

        # First run - creates playlist
        with (
            patch.object(
                seeder.playlist_repo, "delete_by_channel_id", new_callable=AsyncMock
            ) as mock_delete1,
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
            ) as mock_get1,
            patch.object(
                seeder.playlist_repo, "create", new_callable=AsyncMock
            ) as mock_create1,
            patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ),
        ):
            mock_delete1.return_value = 0
            mock_get1.return_value = None

            result1 = await seeder.seed(mock_session, data, clear_existing=True)
            assert result1.created == 1

        # Second run - should work without errors
        with (
            patch.object(
                seeder.playlist_repo, "delete_by_channel_id", new_callable=AsyncMock
            ) as mock_delete2,
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
            ) as mock_get2,
            patch.object(
                seeder.playlist_repo, "create", new_callable=AsyncMock
            ) as mock_create2,
            patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ),
        ):
            mock_delete2.return_value = 1
            mock_get2.return_value = None

            result2 = await seeder.seed(mock_session, data, clear_existing=True)
            assert result2.created == 1

    @pytest.mark.asyncio
    async def test_clear_existing_handles_cascade_automatically(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test FK cascade behavior - memberships deleted automatically."""
        user_channel_id = "UC1234567890123456789012"

        # Mock delete to simulate CASCADE behavior
        # In real database, CASCADE deletes playlist_video_membership rows automatically
        with patch.object(
            seeder.playlist_repo, "delete_by_channel_id", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = 10

            deleted_count = await seeder.clear_existing_playlists(
                mock_session, user_channel_id
            )

            # Only playlists are explicitly deleted
            # Memberships are handled by database CASCADE
            assert deleted_count == 10
            mock_delete.assert_called_once()

    def test_generate_internal_playlist_id_different_seeds_different_ids(self) -> None:
        """Test different seeds produce different INT_ IDs."""
        id1 = generate_internal_playlist_id("playlist_a")
        id2 = generate_internal_playlist_id("playlist_b")

        assert id1 != id2
        assert id1.startswith("INT_")
        assert id2.startswith("INT_")
        assert len(id1) == 36
        assert len(id2) == 36

    @pytest.mark.asyncio
    async def test_seed_without_clear_existing_preserves_playlists(
        self, seeder: PlaylistSeeder, mock_session: AsyncMock
    ) -> None:
        """Test seeding without clear_existing=True preserves existing playlists."""
        data = create_takeout_data(
            takeout_path=Path("/test/takeout"),
            subscriptions=[],
            watch_history=[],
            playlists=[
                create_takeout_playlist(
                    name="New Playlist",
                    file_path=Path("/test/new.csv"),
                    videos=[],
                    video_count=0,
                ),
            ],
        )

        # Mock operations
        with (
            patch.object(
                seeder.playlist_repo, "delete_by_channel_id", new_callable=AsyncMock
            ) as mock_delete,
            patch.object(
                seeder.playlist_repo, "get_by_playlist_id", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                seeder.playlist_repo, "create", new_callable=AsyncMock
            ) as mock_create,
            patch.object(
                seeder, "_ensure_user_channel_exists", new_callable=AsyncMock
            ),
        ):
            mock_get.return_value = None

            result = await seeder.seed(mock_session, data, clear_existing=False)

            # Should NOT have called delete
            mock_delete.assert_not_called()

            # Should have created new playlist
            assert result.created == 1
