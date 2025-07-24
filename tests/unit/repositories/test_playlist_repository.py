"""
Tests for PlaylistRepository functionality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from typing import List

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Playlist as PlaylistDB
from chronovista.models.playlist import (
    PlaylistAnalytics,
    PlaylistCreate,
    PlaylistSearchFilters,
    PlaylistStatistics,
    PlaylistUpdate,
)
from chronovista.repositories.playlist_repository import PlaylistRepository
from tests.factories.playlist_factory import (
    create_playlist,
    create_playlist_create,
    PlaylistTestData,
)


class TestPlaylistRepository:
    """Test PlaylistRepository functionality."""

    @pytest.fixture
    def repository(self) -> PlaylistRepository:
        """Create repository instance for testing."""
        return PlaylistRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_playlist_db(self) -> PlaylistDB:
        """Create sample database playlist object."""
        return PlaylistDB(
            playlist_id="PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR",
            title="Sample Playlist",
            description="A test playlist",
            default_language="en",
            privacy_status="public",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            video_count=10,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_playlist_create(self) -> PlaylistCreate:
        """Create sample PlaylistCreate instance."""
        return PlaylistCreate(
            playlist_id="PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR",
            title="Sample Playlist",
            description="A test playlist",
            default_language="en",
            privacy_status="public",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            video_count=10,
        )

    def test_repository_initialization(self, repository: PlaylistRepository):
        """Test repository initialization."""
        assert repository.model == PlaylistDB

    @pytest.mark.asyncio
    async def test_get_existing_playlist(
        self,
        repository: PlaylistRepository,
        mock_session: AsyncSession,
        sample_playlist_db: PlaylistDB,
    ):
        """Test getting playlist when it exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_playlist_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR")

        assert result == sample_playlist_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_playlist(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlist when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "PLnonexistent")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test exists returns True when playlist exists."""
        mock_result = MagicMock()
        mock_result.first.return_value = ("PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, "PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR")

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test exists returns False when playlist doesn't exist."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, "PLnonexistent")

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_with_channel(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlist with channel loaded."""
        mock_playlist = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_playlist
        mock_session.execute.return_value = mock_result

        result = await repository.get_with_channel(mock_session, "PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR")

        assert result == mock_playlist
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_new_playlist(
        self,
        repository: PlaylistRepository,
        mock_session: AsyncSession,
        sample_playlist_create: PlaylistCreate,
        sample_playlist_db: PlaylistDB,
    ):
        """Test create_or_update with new playlist."""
        repository.get_by_playlist_id = AsyncMock(return_value=None)
        repository.create = AsyncMock(return_value=sample_playlist_db)

        result = await repository.create_or_update(mock_session, sample_playlist_create)

        assert result == sample_playlist_db
        repository.get_by_playlist_id.assert_called_once_with(
            mock_session, sample_playlist_create.playlist_id
        )
        repository.create.assert_called_once_with(
            mock_session, obj_in=sample_playlist_create
        )

    @pytest.mark.asyncio
    async def test_create_or_update_existing_playlist(
        self,
        repository: PlaylistRepository,
        mock_session: AsyncSession,
        sample_playlist_create: PlaylistCreate,
        sample_playlist_db: PlaylistDB,
    ):
        """Test create_or_update with existing playlist."""
        repository.get_by_playlist_id = AsyncMock(return_value=sample_playlist_db)
        repository.update = AsyncMock(return_value=sample_playlist_db)

        result = await repository.create_or_update(mock_session, sample_playlist_create)

        assert result == sample_playlist_db
        repository.get_by_playlist_id.assert_called_once_with(
            mock_session, sample_playlist_create.playlist_id
        )
        repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_channel_id(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlists by channel ID."""
        mock_playlists = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_channel_id(mock_session, "UC_x5XG1OV2P6uZZ5FSM9Ttw")

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_privacy_status(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlists by privacy status."""
        mock_playlists = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_privacy_status(mock_session, "public")

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_language(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlists by language."""
        mock_playlists = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_language(mock_session, "en")

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_playlists_with_filters(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test searching playlists with comprehensive filters."""
        filters = PlaylistSearchFilters(
            playlist_ids=["PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR"],
            channel_ids=["UC_x5XG1OV2P6uZZ5FSM9Ttw"],
            title_query="music",
            description_query="playlist",
            language_codes=["en"],
            privacy_statuses=["public"],
            min_video_count=5,
            max_video_count=50,
            has_description=True,
            created_after=datetime(2023, 1, 1, tzinfo=timezone.utc),
            created_before=datetime(2023, 12, 31, tzinfo=timezone.utc),
        )

        mock_playlists = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_playlists(mock_session, filters)

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_playlists_empty_filters(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test searching playlists with empty filters."""
        filters = PlaylistSearchFilters()

        mock_playlists = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_playlists(mock_session, filters)

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_popular_playlists(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting popular playlists."""
        mock_playlists = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_popular_playlists(mock_session, limit=10)

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_recent_playlists(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting recent playlists."""
        mock_playlists = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_recent_playlists(mock_session, limit=10)

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_playlists_by_size_range(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlists by size range."""
        mock_playlists = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_playlists_by_size_range(mock_session, 10, 50)

        assert result == mock_playlists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_playlist_statistics(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlist statistics."""
        # Create properly structured mock stats object
        mock_stats = MagicMock()
        mock_stats.total_playlists = 100
        mock_stats.total_videos = 1000
        mock_stats.avg_videos_per_playlist = 10.0
        mock_stats.unique_channels = 25
        mock_stats.playlists_with_descriptions = 75
        
        # Mock first call for basic stats
        basic_stats_result = MagicMock()
        basic_stats_result.first.return_value = mock_stats
        
        # Mock different execute calls for different queries
        mock_session.execute.side_effect = [
            # Basic stats query
            basic_stats_result,
            # Privacy distribution query
            [("public", 60), ("private", 40)],
            # Language distribution query  
            [("en", 80), ("es", 20)],
            # Top channels query
            [("UC123", 15), ("UC456", 10)],
            # Size distribution queries (5 separate calls)
            MagicMock(scalar=lambda: 20),  # 0-5
            MagicMock(scalar=lambda: 30),  # 6-15
            MagicMock(scalar=lambda: 25),  # 16-50
            MagicMock(scalar=lambda: 15),  # 51-100
            MagicMock(scalar=lambda: 10),  # 100+
        ]

        result = await repository.get_playlist_statistics(mock_session)

        assert isinstance(result, PlaylistStatistics)
        assert result.total_playlists == 100
        assert result.total_videos == 1000
        assert result.avg_videos_per_playlist == 10.0
        assert result.unique_channels == 25
        assert result.playlists_with_descriptions == 75
        assert result.privacy_distribution == {"public": 60, "private": 40}
        assert "en" in result.language_distribution

    @pytest.mark.asyncio
    async def test_get_channel_playlist_count(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlist count for a channel."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_result

        result = await repository.get_channel_playlist_count(
            mock_session, "UC_x5XG1OV2P6uZZ5FSM9Ttw"
        )

        assert result == 5
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_playlists_by_multiple_channels(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlists for multiple channels."""
        mock_playlist1 = MagicMock()
        mock_playlist1.channel_id = "UC123"
        mock_playlist2 = MagicMock()
        mock_playlist2.channel_id = "UC456"
        mock_playlist3 = MagicMock()
        mock_playlist3.channel_id = "UC123"

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_playlist1, mock_playlist2, mock_playlist3]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_playlists_by_multiple_channels(
            mock_session, ["UC123", "UC456"]
        )

        assert "UC123" in result
        assert "UC456" in result
        assert len(result["UC123"]) == 2
        assert len(result["UC456"]) == 1

    @pytest.mark.asyncio
    async def test_get_playlists_by_multiple_channels_empty(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlists for empty channel list."""
        result = await repository.get_playlists_by_multiple_channels(mock_session, [])

        assert result == {}
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_create_playlists_new(
        self,
        repository: PlaylistRepository,
        mock_session: AsyncSession,
        sample_playlist_db: PlaylistDB,
    ):
        """Test bulk creating new playlists."""
        repository.get_by_playlist_id = AsyncMock(return_value=None)
        repository.create = AsyncMock(return_value=sample_playlist_db)

        playlists = [
            create_playlist_create(playlist_id="PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR"),
            create_playlist_create(playlist_id="PLfIhOa8drThIfvQR29YZ_k_hYHO-chZuF"),
            create_playlist_create(playlist_id="PL_tBM_hg5GY7p38IEq3kSKYz9JTnvIR8L"),
        ]

        result = await repository.bulk_create_playlists(mock_session, playlists)

        assert len(result) == 3
        assert repository.get_by_playlist_id.call_count == 3
        assert repository.create.call_count == 3

    @pytest.mark.asyncio
    async def test_bulk_create_playlists_mixed(
        self,
        repository: PlaylistRepository,
        mock_session: AsyncSession,
        sample_playlist_db: PlaylistDB,
    ):
        """Test bulk creating with mix of new and existing playlists."""
        # First playlist exists, second doesn't
        repository.get_by_playlist_id = AsyncMock(side_effect=[sample_playlist_db, None])
        repository.create = AsyncMock(return_value=sample_playlist_db)

        playlists = [
            create_playlist_create(playlist_id="PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR"),
            create_playlist_create(playlist_id="PLfIhOa8drThIfvQR29YZ_k_hYHO-chZuF"),
        ]

        result = await repository.bulk_create_playlists(mock_session, playlists)

        assert len(result) == 2
        assert repository.get_by_playlist_id.call_count == 2
        assert repository.create.call_count == 1  # Only one new playlist created

    @pytest.mark.asyncio
    async def test_bulk_update_video_counts(
        self,
        repository: PlaylistRepository,
        mock_session: AsyncSession,
        sample_playlist_db: PlaylistDB,
    ):
        """Test bulk updating video counts."""
        # Mock playlist with different video count
        sample_playlist_db.video_count = 5
        repository.get_by_playlist_id = AsyncMock(return_value=sample_playlist_db)
        repository.update = AsyncMock(return_value=sample_playlist_db)

        playlist_counts = {
            "PL1": 10,  # Different from current count (5)
            "PL2": 15,
        }

        result = await repository.bulk_update_video_counts(mock_session, playlist_counts)

        assert result == 2  # Both playlists updated
        assert repository.get_by_playlist_id.call_count == 2
        assert repository.update.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_by_playlist_id(
        self,
        repository: PlaylistRepository,
        mock_session: AsyncSession,
        sample_playlist_db: PlaylistDB,
    ):
        """Test deleting playlist by ID."""
        repository.get_by_playlist_id = AsyncMock(return_value=sample_playlist_db)

        result = await repository.delete_by_playlist_id(
            mock_session, "PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR"
        )

        assert result == sample_playlist_db
        mock_session.delete.assert_called_once_with(sample_playlist_db)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_channel_id(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test deleting all playlists for a channel."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        mock_session.execute.return_value = mock_count_result

        mock_playlists = [MagicMock(), MagicMock(), MagicMock()]
        repository.get_by_channel_id = AsyncMock(return_value=mock_playlists)

        result = await repository.delete_by_channel_id(mock_session, "UC123")

        assert result == 3
        assert mock_session.delete.call_count == 3
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_similar_playlists(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test finding similar playlists."""
        target_playlist = MagicMock()
        target_playlist.title = "Music Playlist"
        repository.get_by_playlist_id = AsyncMock(return_value=target_playlist)

        # Mock similar playlists
        similar_playlist = MagicMock()
        similar_playlist.title = "Music Collection"
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [similar_playlist]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_similar_playlists(mock_session, "PL1", limit=5)

        assert len(result) > 0
        assert all(len(item) == 2 for item in result)  # (playlist, similarity_score) tuples

    @pytest.mark.asyncio
    async def test_find_similar_playlists_not_found(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test finding similar playlists when target doesn't exist."""
        repository.get_by_playlist_id = AsyncMock(return_value=None)

        result = await repository.find_similar_playlists(mock_session, "PLnonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_playlist_analytics(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test getting playlist analytics."""
        # Mock different execute calls for analytics
        mock_session.execute.side_effect = [
            # Creation trends query
            [("2023-01", 10), ("2023-02", 15)],
            # Average title length query
            MagicMock(scalar=lambda: 25.5),
            # Description count query
            MagicMock(scalar=lambda: 75),
            # Average videos per playlist query
            MagicMock(scalar=lambda: 12.5),
        ]

        result = await repository.get_playlist_analytics(mock_session)

        assert isinstance(result, PlaylistAnalytics)
        assert "monthly_counts" in result.creation_trends
        assert "avg_title_length" in result.content_analysis
        assert "avg_videos_per_playlist" in result.engagement_metrics
        assert len(result.similarity_clusters) > 0


class TestPlaylistRepositoryIntegration:
    """Integration tests for PlaylistRepository with factory data."""

    @pytest.fixture
    def repository(self) -> PlaylistRepository:
        """Create repository instance."""
        return PlaylistRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_playlist_lifecycle_with_factory_data(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test complete playlist lifecycle using factory data."""
        # Create playlist using factory
        playlist_create = create_playlist_create(
            playlist_id="PLrAXtmRdnqDpVC2bT0Bz-8Q5RWmF6gBkR",
            title="Test Playlist",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw"
        )

        # Mock database playlist
        mock_playlist_db = MagicMock()
        mock_playlist_db.playlist_id = playlist_create.playlist_id
        mock_playlist_db.title = playlist_create.title
        mock_playlist_db.channel_id = playlist_create.channel_id

        # Mock repository operations
        repository.get_by_playlist_id = AsyncMock(return_value=None)  # New playlist
        repository.create = AsyncMock(return_value=mock_playlist_db)

        # Create playlist
        result = await repository.create_or_update(mock_session, playlist_create)

        assert result == mock_playlist_db
        repository.create.assert_called_once_with(mock_session, obj_in=playlist_create)

    @pytest.mark.asyncio
    async def test_search_with_test_data_patterns(
        self, repository: PlaylistRepository, mock_session: AsyncSession
    ):
        """Test search functionality with common test data patterns."""
        # Use test data patterns
        filters = PlaylistSearchFilters(
            channel_ids=PlaylistTestData.VALID_CHANNEL_IDS[:2],
            privacy_statuses=["public", "unlisted"],
            min_video_count=5,
        )

        mock_playlists = [MagicMock() for _ in range(3)]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_playlists
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_playlists(mock_session, filters)

        assert len(result) == 3
        mock_session.execute.assert_called_once()

    def test_repository_inherits_base_methods(self, repository: PlaylistRepository):
        """Test that repository inherits base methods."""
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")
        assert hasattr(repository, "model")

    def test_playlist_specific_methods(self, repository: PlaylistRepository):
        """Test that repository has playlist-specific methods."""
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "get_by_playlist_id")
        assert hasattr(repository, "get_with_channel")
        assert hasattr(repository, "create_or_update")
        assert hasattr(repository, "get_by_channel_id")
        assert hasattr(repository, "search_playlists")
        assert hasattr(repository, "get_popular_playlists")
        assert hasattr(repository, "get_playlist_statistics")
        assert hasattr(repository, "bulk_create_playlists")
        assert hasattr(repository, "find_similar_playlists")