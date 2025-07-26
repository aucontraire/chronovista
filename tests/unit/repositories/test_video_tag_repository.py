"""
Tests for VideoTagRepository functionality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.models.video_tag import (
    VideoTagCreate,
    VideoTagSearchFilters,
    VideoTagStatistics,
    VideoTagUpdate,
)
from chronovista.repositories.video_tag_repository import VideoTagRepository
from tests.factories.video_tag_factory import (
    VideoTagTestData,
    create_video_tag,
    create_video_tag_create,
)


class TestVideoTagRepository:
    """Test VideoTagRepository functionality."""

    @pytest.fixture
    def repository(self) -> VideoTagRepository:
        """Create repository instance for testing."""
        return VideoTagRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_video_tag_db(self) -> VideoTagDB:
        """Create sample database video tag object."""
        return VideoTagDB(
            video_id="dQw4w9WgXcQ",
            tag="music",
            tag_order=1,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_video_tag_create(self) -> VideoTagCreate:
        """Create sample VideoTagCreate instance."""
        return VideoTagCreate(
            video_id="dQw4w9WgXcQ",
            tag="music",
            tag_order=1,
        )

    def test_repository_initialization(self, repository: VideoTagRepository):
        """Test repository initialization."""
        assert repository.model == VideoTagDB

    @pytest.mark.asyncio
    async def test_get_existing_tag(
        self,
        repository: VideoTagRepository,
        mock_session: AsyncSession,
        sample_video_tag_db: VideoTagDB,
    ):
        """Test getting video tag by composite key when it exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_video_tag_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "music"
        )

        assert result == sample_video_tag_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_tag(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting video tag when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "nonexistent"
        )

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test exists returns True when tag exists."""
        mock_result = MagicMock()
        mock_result.first.return_value = ("dQw4w9WgXcQ",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "music"
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test exists returns False when tag doesn't exist."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, "dQw4w9WgXcQ", "nonexistent"
        )

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_video_id(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting all tags for a specific video."""
        mock_tags = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_tags
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_video_id(mock_session, "dQw4w9WgXcQ")

        assert result == mock_tags
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_tag(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting all videos with a specific tag."""
        mock_video_tags = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_video_tags
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_tag(mock_session, "music")

        assert result == mock_video_tags
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_new_tag(
        self,
        repository: VideoTagRepository,
        mock_session: AsyncSession,
        sample_video_tag_create: VideoTagCreate,
        sample_video_tag_db: VideoTagDB,
    ):
        """Test create_or_update with new tag."""
        repository.get_by_composite_key = AsyncMock(return_value=None)
        repository.create = AsyncMock(return_value=sample_video_tag_db)

        result = await repository.create_or_update(
            mock_session, sample_video_tag_create
        )

        assert result == sample_video_tag_db
        repository.get_by_composite_key.assert_called_once_with(
            mock_session, sample_video_tag_create.video_id, sample_video_tag_create.tag
        )
        repository.create.assert_called_once_with(
            mock_session, obj_in=sample_video_tag_create
        )

    @pytest.mark.asyncio
    async def test_create_or_update_existing_tag(
        self,
        repository: VideoTagRepository,
        mock_session: AsyncSession,
        sample_video_tag_create: VideoTagCreate,
        sample_video_tag_db: VideoTagDB,
    ):
        """Test create_or_update with existing tag."""
        repository.get_by_composite_key = AsyncMock(return_value=sample_video_tag_db)
        repository.update = AsyncMock(return_value=sample_video_tag_db)

        result = await repository.create_or_update(
            mock_session, sample_video_tag_create
        )

        assert result == sample_video_tag_db
        repository.get_by_composite_key.assert_called_once_with(
            mock_session, sample_video_tag_create.video_id, sample_video_tag_create.tag
        )
        repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_video_tags_new(
        self,
        repository: VideoTagRepository,
        mock_session: AsyncSession,
        sample_video_tag_db: VideoTagDB,
    ):
        """Test bulk creating new video tags."""
        repository.get_by_composite_key = AsyncMock(return_value=None)
        repository.create = AsyncMock(return_value=sample_video_tag_db)

        tags = ["music", "entertainment", "dance"]
        tag_orders = [1, 2, 3]
        result = await repository.bulk_create_video_tags(
            mock_session, "dQw4w9WgXcQ", tags, tag_orders
        )

        assert len(result) == 3
        assert repository.get_by_composite_key.call_count == 3
        assert repository.create.call_count == 3

    @pytest.mark.asyncio
    async def test_bulk_create_video_tags_mixed(
        self,
        repository: VideoTagRepository,
        mock_session: AsyncSession,
        sample_video_tag_db: VideoTagDB,
    ):
        """Test bulk creating with mix of new and existing tags."""
        # First tag exists, second doesn't
        repository.get_by_composite_key = AsyncMock(
            side_effect=[sample_video_tag_db, None]
        )
        repository.create = AsyncMock(return_value=sample_video_tag_db)

        tags = ["music", "entertainment"]
        result = await repository.bulk_create_video_tags(
            mock_session, "dQw4w9WgXcQ", tags
        )

        assert len(result) == 2
        assert repository.get_by_composite_key.call_count == 2
        assert repository.create.call_count == 1  # Only one new tag created

    @pytest.mark.asyncio
    async def test_delete_by_video_id(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test deleting all tags for a video."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        mock_session.execute.return_value = mock_count_result

        result = await repository.delete_by_video_id(mock_session, "dQw4w9WgXcQ")

        assert result == 3
        assert mock_session.execute.call_count == 2  # Count query + delete query
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_tag(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test deleting all instances of a specific tag."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_count_result

        result = await repository.delete_by_tag(mock_session, "music")

        assert result == 5
        assert mock_session.execute.call_count == 2  # Count query + delete query
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_tags_with_filters(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test searching tags with comprehensive filters."""
        filters = VideoTagSearchFilters(
            video_ids=["dQw4w9WgXcQ", "9bZkp7q19f0"],
            tags=["music", "entertainment"],
            tag_pattern="music",
            min_tag_order=1,
            max_tag_order=5,
            created_after=datetime(2023, 1, 1, tzinfo=timezone.utc),
            created_before=datetime(2023, 12, 31, tzinfo=timezone.utc),
        )

        mock_tags = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_tags
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_tags(mock_session, filters)

        assert result == mock_tags
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_tags_empty_filters(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test searching tags with empty filters."""
        filters = VideoTagSearchFilters()

        mock_tags = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_tags
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_tags(mock_session, filters)

        assert result == mock_tags
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_popular_tags(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting popular tags."""
        expected_tags = [("music", 100), ("gaming", 85), ("tech", 70)]
        mock_session.execute.return_value = expected_tags

        result = await repository.get_popular_tags(mock_session, limit=3)

        assert result == expected_tags
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_related_tags(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting related tags."""
        expected_related = [("dance", 25), ("pop", 20), ("cover", 15)]
        mock_session.execute.return_value = expected_related

        result = await repository.get_related_tags(mock_session, "music", limit=3)

        assert result == expected_related
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_video_tag_statistics(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting comprehensive tag statistics."""
        # Mock different execute calls for different queries
        mock_session.execute.side_effect = [
            MagicMock(scalar=lambda: 1000),  # total_tags
            MagicMock(scalar=lambda: 500),  # unique_tags
            MagicMock(scalar=lambda: 3.5),  # avg_tags_per_video
            [("music", 100), ("gaming", 85)],  # most_common_tags
        ]

        result = await repository.get_video_tag_statistics(mock_session)

        assert isinstance(result, VideoTagStatistics)
        assert result.total_tags == 1000
        assert result.unique_tags == 500
        assert result.avg_tags_per_video == 3.5
        assert result.most_common_tags == [("music", 100), ("gaming", 85)]
        assert result.tag_distribution == {"music": 100, "gaming": 85}

    @pytest.mark.asyncio
    async def test_find_videos_by_tags_any(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test finding videos that have ANY of the specified tags."""
        expected_videos = ["dQw4w9WgXcQ", "9bZkp7q19f0"]
        mock_session.execute.return_value = [(vid,) for vid in expected_videos]

        result = await repository.find_videos_by_tags(
            mock_session, ["music", "gaming"], match_all=False
        )

        assert result == expected_videos
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_videos_by_tags_all(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test finding videos that have ALL of the specified tags."""
        expected_videos = ["dQw4w9WgXcQ"]
        mock_session.execute.return_value = [(vid,) for vid in expected_videos]

        result = await repository.find_videos_by_tags(
            mock_session, ["music", "gaming"], match_all=True
        )

        assert result == expected_videos
        # Called once for the final intersected query
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_videos_by_tags_empty_list(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test finding videos with empty tag list."""
        result = await repository.find_videos_by_tags(mock_session, [])

        assert result == []
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_tag_video_count(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting video count for a specific tag."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute.return_value = mock_result

        result = await repository.get_tag_video_count(mock_session, "music")

        assert result == 42
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_video_count_by_tags(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting video counts for multiple tags."""
        expected_counts = [("music", 100), ("gaming", 85), ("tech", 70)]
        mock_session.execute.return_value = expected_counts

        result = await repository.get_video_count_by_tags(
            mock_session, ["music", "gaming", "tech"]
        )

        expected_dict = {"music": 100, "gaming": 85, "tech": 70}
        assert result == expected_dict
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_video_count_by_tags_empty(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test getting video counts with empty tag list."""
        result = await repository.get_video_count_by_tags(mock_session, [])

        assert result == {}
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_tags(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test cleanup of orphaned tags."""
        # Currently returns 0 as placeholder
        result = await repository.cleanup_orphaned_tags(mock_session)

        assert result == 0


class TestVideoTagRepositoryIntegration:
    """Integration tests for VideoTagRepository with factory data."""

    @pytest.fixture
    def repository(self) -> VideoTagRepository:
        """Create repository instance."""
        return VideoTagRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_tag_lifecycle_with_factory_data(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test complete tag lifecycle using factory data."""
        # Create tag using factory
        tag_create = create_video_tag_create(
            video_id="dQw4w9WgXcQ", tag="music", tag_order=1
        )

        # Mock database tag
        mock_tag_db = MagicMock()
        mock_tag_db.video_id = tag_create.video_id
        mock_tag_db.tag = tag_create.tag
        mock_tag_db.tag_order = tag_create.tag_order

        # Mock repository operations
        repository.get_by_composite_key = AsyncMock(return_value=None)  # New tag
        repository.create = AsyncMock(return_value=mock_tag_db)

        # Create tag
        result = await repository.create_or_update(mock_session, tag_create)

        assert result == mock_tag_db
        repository.create.assert_called_once_with(mock_session, obj_in=tag_create)

    @pytest.mark.asyncio
    async def test_search_with_test_data_patterns(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test search functionality with common test data patterns."""
        # Use test data patterns
        filters = VideoTagSearchFilters(
            video_ids=VideoTagTestData.VALID_VIDEO_IDS[:2],
            tags=VideoTagTestData.VALID_TAGS[:3],
            tag_pattern="music",
        )

        mock_tags = [MagicMock() for _ in range(5)]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_tags
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_tags(mock_session, filters)

        assert len(result) == 5
        mock_session.execute.assert_called_once()

    def test_repository_inherits_base_methods(self, repository: VideoTagRepository):
        """Test that repository inherits base methods."""
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")
        assert hasattr(repository, "model")

    def test_composite_key_methods(self, repository: VideoTagRepository):
        """Test that repository has composite key specific methods."""
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "get_by_composite_key")
        assert hasattr(repository, "exists_by_composite_key")
        assert hasattr(repository, "get_by_video_id")
        assert hasattr(repository, "get_by_tag")
        assert hasattr(repository, "bulk_create_video_tags")
        assert hasattr(repository, "replace_video_tags")
        assert hasattr(repository, "get_popular_tags")
        assert hasattr(repository, "get_related_tags")

    @pytest.mark.asyncio
    async def test_base_get_with_composite_key(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test base get method with composite key tuple."""
        repository.get_by_composite_key = AsyncMock(return_value=MagicMock())

        result = await repository.get(mock_session, ("dQw4w9WgXcQ", "music"))

        assert result is not None
        repository.get_by_composite_key.assert_called_once_with(
            mock_session, "dQw4w9WgXcQ", "music"
        )

    @pytest.mark.asyncio
    async def test_base_get_with_invalid_key(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test base get method with invalid key format."""
        result = await repository.get(mock_session, "invalid_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_base_exists_with_composite_key(
        self, repository: VideoTagRepository, mock_session: AsyncSession
    ):
        """Test base exists method with composite key tuple."""
        repository.exists_by_composite_key = AsyncMock(return_value=True)

        result = await repository.exists(mock_session, ("dQw4w9WgXcQ", "music"))

        assert result is True
        repository.exists_by_composite_key.assert_called_once_with(
            mock_session, "dQw4w9WgXcQ", "music"
        )
