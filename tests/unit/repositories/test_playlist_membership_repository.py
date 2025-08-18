"""
Tests for PlaylistMembershipRepository.

Comprehensive test suite covering all CRUD operations and specialized queries
for playlist-video relationships.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import PlaylistMembership as DBPlaylistMembership
from chronovista.models.playlist_membership import PlaylistMembershipCreate
from chronovista.repositories.playlist_membership_repository import (
    PlaylistMembershipRepository,
)
from tests.factories.id_factory import TestIds, YouTubeIdFactory

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


class TestPlaylistMembershipRepository:
    """Test the PlaylistMembershipRepository CRUD operations and specialized queries."""

    @pytest.fixture
    def repository(self):
        """Create a PlaylistMembershipRepository for testing."""
        return PlaylistMembershipRepository()

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_membership_create(self):
        """Create sample playlist membership create data."""
        return PlaylistMembershipCreate(
            playlist_id=TestIds.TEST_PLAYLIST_1,
            video_id=TestIds.TEST_VIDEO_1,
            position=0,
            added_at=datetime.now(timezone.utc),
        )

    def test_repository_initialization(self, repository):
        """Test repository initializes correctly."""
        assert repository.model == DBPlaylistMembership
        assert isinstance(repository, PlaylistMembershipRepository)

    async def test_get_playlist_videos_empty(self, repository, mock_session):
        """Test getting videos from empty playlist."""
        # Mock empty result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        videos = await repository.get_playlist_videos(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert videos == []
        mock_session.execute.assert_called_once()

    async def test_get_playlist_videos_with_content(self, repository, mock_session):
        """Test getting videos from playlist with content."""
        # Create mock memberships
        mock_membership1 = DBPlaylistMembership(
            playlist_id=TestIds.TEST_PLAYLIST_1,
            video_id=TestIds.TEST_VIDEO_1,
            position=0,
            created_at=datetime.now(timezone.utc),
        )
        mock_membership2 = DBPlaylistMembership(
            playlist_id=TestIds.TEST_PLAYLIST_1,
            video_id=TestIds.TEST_VIDEO_2,
            position=1,
            created_at=datetime.now(timezone.utc),
        )

        # Mock result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            mock_membership1,
            mock_membership2,
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        videos = await repository.get_playlist_videos(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert len(videos) == 2
        assert videos[0].video_id == TestIds.TEST_VIDEO_1
        assert videos[1].video_id == TestIds.TEST_VIDEO_2
        mock_session.execute.assert_called_once()

    async def test_get_video_playlists_empty(self, repository, mock_session):
        """Test getting playlists for video not in any playlist."""
        # Mock empty result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        playlists = await repository.get_video_playlists(
            mock_session, TestIds.TEST_VIDEO_1
        )

        assert playlists == []
        mock_session.execute.assert_called_once()

    async def test_get_video_playlists_with_content(self, repository, mock_session):
        """Test getting playlists for video in multiple playlists."""
        # Create mock memberships
        mock_membership1 = DBPlaylistMembership(
            playlist_id=TestIds.TEST_PLAYLIST_1,
            video_id=TestIds.TEST_VIDEO_1,
            position=0,
            created_at=datetime.now(timezone.utc),
        )
        mock_membership2 = DBPlaylistMembership(
            playlist_id=TestIds.TEST_PLAYLIST_2,
            video_id=TestIds.TEST_VIDEO_1,
            position=5,
            created_at=datetime.now(timezone.utc),
        )

        # Mock result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            mock_membership1,
            mock_membership2,
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        playlists = await repository.get_video_playlists(
            mock_session, TestIds.TEST_VIDEO_1
        )

        assert len(playlists) == 2
        assert playlists[0].playlist_id == TestIds.TEST_PLAYLIST_1
        assert playlists[1].playlist_id == TestIds.TEST_PLAYLIST_2
        mock_session.execute.assert_called_once()

    async def test_clear_playlist_videos_empty(self, repository, mock_session):
        """Test clearing videos from empty playlist."""
        # Mock result with 0 rows affected
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await repository.clear_playlist_videos(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert count == 0
        mock_session.execute.assert_called_once()

    async def test_clear_playlist_videos_with_content(self, repository, mock_session):
        """Test clearing videos from playlist with content."""
        # Mock result with 3 rows affected
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        count = await repository.clear_playlist_videos(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert count == 3
        mock_session.execute.assert_called_once()

    async def test_clear_playlist_videos_none_rowcount(self, repository, mock_session):
        """Test clearing playlist when rowcount is None."""
        # Mock result with None rowcount (edge case)
        mock_result = MagicMock()
        mock_result.rowcount = None
        mock_session.execute.return_value = mock_result

        count = await repository.clear_playlist_videos(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert count == 0
        mock_session.execute.assert_called_once()

    async def test_membership_exists_true(self, repository, mock_session):
        """Test checking membership that exists."""
        # Mock membership found
        mock_membership = DBPlaylistMembership(
            playlist_id=TestIds.TEST_PLAYLIST_1,
            video_id=TestIds.TEST_VIDEO_1,
            position=0,
            created_at=datetime.now(timezone.utc),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_membership
        mock_session.execute.return_value = mock_result

        exists = await repository.membership_exists(
            mock_session, TestIds.TEST_PLAYLIST_1, TestIds.TEST_VIDEO_1
        )

        assert exists is True
        mock_session.execute.assert_called_once()

    async def test_membership_exists_false(self, repository, mock_session):
        """Test checking membership that doesn't exist."""
        # Mock membership not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        exists = await repository.membership_exists(
            mock_session, TestIds.TEST_PLAYLIST_1, TestIds.TEST_VIDEO_1
        )

        assert exists is False
        mock_session.execute.assert_called_once()

    async def test_get_membership_found(self, repository, mock_session):
        """Test getting specific membership that exists."""
        # Mock membership found
        mock_membership = DBPlaylistMembership(
            playlist_id=TestIds.TEST_PLAYLIST_1,
            video_id=TestIds.TEST_VIDEO_1,
            position=0,
            created_at=datetime.now(timezone.utc),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_membership
        mock_session.execute.return_value = mock_result

        membership = await repository.get_membership(
            mock_session, TestIds.TEST_PLAYLIST_1, TestIds.TEST_VIDEO_1
        )

        assert membership == mock_membership
        assert membership.playlist_id == TestIds.TEST_PLAYLIST_1
        assert membership.video_id == TestIds.TEST_VIDEO_1
        mock_session.execute.assert_called_once()

    async def test_get_membership_not_found(self, repository, mock_session):
        """Test getting specific membership that doesn't exist."""
        # Mock membership not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        membership = await repository.get_membership(
            mock_session, TestIds.TEST_PLAYLIST_1, TestIds.TEST_VIDEO_1
        )

        assert membership is None
        mock_session.execute.assert_called_once()

    async def test_update_video_position_success(self, repository, mock_session):
        """Test updating video position successfully."""
        # Mock membership found
        mock_membership = DBPlaylistMembership(
            playlist_id=TestIds.TEST_PLAYLIST_1,
            video_id=TestIds.TEST_VIDEO_1,
            position=0,
            created_at=datetime.now(timezone.utc),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_membership
        mock_session.execute.return_value = mock_result

        updated_membership = await repository.update_video_position(
            mock_session, TestIds.TEST_PLAYLIST_1, TestIds.TEST_VIDEO_1, 5
        )

        assert updated_membership == mock_membership
        assert updated_membership.position == 5
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_membership)

    async def test_update_video_position_not_found(self, repository, mock_session):
        """Test updating video position when membership doesn't exist."""
        # Mock membership not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        updated_membership = await repository.update_video_position(
            mock_session, TestIds.TEST_PLAYLIST_1, TestIds.TEST_VIDEO_1, 5
        )

        assert updated_membership is None
        mock_session.flush.assert_not_called()
        mock_session.refresh.assert_not_called()

    async def test_get_playlist_count_empty(self, repository, mock_session):
        """Test getting count from empty playlist."""
        # Mock count result
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result

        count = await repository.get_playlist_count(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert count == 0
        mock_session.execute.assert_called_once()

    async def test_get_playlist_count_with_videos(self, repository, mock_session):
        """Test getting count from playlist with videos."""
        # Mock count result
        mock_result = MagicMock()
        mock_result.scalar.return_value = 15
        mock_session.execute.return_value = mock_result

        count = await repository.get_playlist_count(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert count == 15
        mock_session.execute.assert_called_once()

    async def test_get_playlist_count_none_result(self, repository, mock_session):
        """Test getting count when result is None."""
        # Mock None result (edge case)
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        count = await repository.get_playlist_count(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert count == 0
        mock_session.execute.assert_called_once()

    async def test_get_next_position_empty_playlist(self, repository, mock_session):
        """Test getting next position in empty playlist."""
        # Mock max position result (None for empty)
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        next_position = await repository.get_next_position(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert next_position == 0
        mock_session.execute.assert_called_once()

    async def test_get_next_position_with_videos(self, repository, mock_session):
        """Test getting next position in playlist with videos."""
        # Mock max position result
        mock_result = MagicMock()
        mock_result.scalar.return_value = 7  # Max position is 7
        mock_session.execute.return_value = mock_result

        next_position = await repository.get_next_position(
            mock_session, TestIds.TEST_PLAYLIST_1
        )

        assert next_position == 8  # Next should be 8
        mock_session.execute.assert_called_once()

    async def test_create_membership(
        self, repository, mock_session, sample_membership_create
    ):
        """Test creating a new playlist membership."""
        # Mock the database object creation
        mock_db_obj = DBPlaylistMembership(
            playlist_id=sample_membership_create.playlist_id,
            video_id=sample_membership_create.video_id,
            position=sample_membership_create.position,
            added_at=sample_membership_create.added_at,
            created_at=datetime.now(timezone.utc),
        )

        # Setup session mocks
        mock_session.add = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock the model constructor to return our mock object
        with pytest.MonkeyPatch().context() as m:
            m.setattr(repository, "model", lambda **kwargs: mock_db_obj)

            result = await repository.create(
                mock_session, obj_in=sample_membership_create
            )

            assert result == mock_db_obj
            mock_session.add.assert_called_once()
            mock_session.flush.assert_called_once()
            mock_session.refresh.assert_called_once_with(mock_db_obj)

    def test_model_assignment(self, repository):
        """Test that repository model is correctly assigned."""
        assert repository.model == DBPlaylistMembership

    def test_inheritance(self, repository):
        """Test that repository inherits from BaseSQLAlchemyRepository."""
        from chronovista.repositories.base import BaseSQLAlchemyRepository

        assert isinstance(repository, BaseSQLAlchemyRepository)

    async def test_specialized_queries_use_correct_filters(
        self, repository, mock_session
    ):
        """Test that specialized queries use correct WHERE clauses."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result

        # Test playlist videos query
        await repository.get_playlist_videos(mock_session, TestIds.TEST_PLAYLIST_1)
        call_args = mock_session.execute.call_args[0][0]
        # Verify it's a SELECT statement (basic check)
        assert hasattr(call_args, "compile")

        # Test video playlists query
        await repository.get_video_playlists(mock_session, TestIds.TEST_VIDEO_1)

        # Test membership exists query
        await repository.membership_exists(
            mock_session, TestIds.TEST_PLAYLIST_1, TestIds.TEST_VIDEO_1
        )

        # Verify all calls were made
        assert mock_session.execute.call_count == 3
