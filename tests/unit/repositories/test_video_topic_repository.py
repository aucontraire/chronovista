"""
Test VideoTopicRepository functionality.

Tests the VideoTopicRepository class for managing video-topic relationships
with comprehensive coverage of CRUD operations, search, and analytics.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoTopic as VideoTopicDB
from chronovista.models.video_topic import (
    VideoTopicCreate,
    VideoTopicSearchFilters,
    VideoTopicUpdate,
)
from chronovista.repositories.video_topic_repository import VideoTopicRepository
from tests.factories import (
    TestIds,
    VideoTopicTestData,
    create_video_topic_create,
    create_video_topic_filters,
    create_video_topic_update,
)

# Mark all tests as async for this module
pytestmark = pytest.mark.asyncio


class TestVideoTopicRepository:
    """Test VideoTopicRepository functionality."""

    @pytest.fixture
    def repository(self):
        """Create VideoTopicRepository instance."""
        return VideoTopicRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_video_topic_create(self):
        """Create sample VideoTopicCreate data."""
        return create_video_topic_create(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.MUSIC_TOPIC,
            relevance_type="primary",
        )

    @pytest.fixture
    def sample_video_topic_db(self):
        """Create sample VideoTopicDB instance."""
        return VideoTopicDB(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.MUSIC_TOPIC,
            relevance_type="primary",
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_repository_initialization(self, repository):
        """Test repository initializes correctly."""
        assert repository.model == VideoTopicDB
        assert isinstance(repository, VideoTopicRepository)

    @pytest.mark.asyncio
    async def test_get_by_composite_key_success(
        self, repository, mock_session, sample_video_topic_db
    ):
        """Test get_by_composite_key returns video topic when found."""
        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_video_topic_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC
        )

        assert result == sample_video_topic_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_composite_key_not_found(self, repository, mock_session):
        """Test get_by_composite_key returns None when not found."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC
        )

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_composite_key_true(self, repository, mock_session):
        """Test exists_by_composite_key returns True when video topic exists."""
        # Mock result with data
        mock_result = MagicMock()
        mock_result.first.return_value = ("some_video_id",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_composite_key_false(self, repository, mock_session):
        """Test exists_by_composite_key returns False when video topic doesn't exist."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC
        )

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topics_by_video_id(
        self, repository, mock_session, sample_video_topic_db
    ):
        """Test get_topics_by_video_id returns all topics for a video."""
        # Mock result with multiple topics
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_video_topic_db]
        mock_session.execute.return_value = mock_result

        result = await repository.get_topics_by_video_id(
            mock_session, TestIds.TEST_VIDEO_1
        )

        assert result == [sample_video_topic_db]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_videos_by_topic_id(
        self, repository, mock_session, sample_video_topic_db
    ):
        """Test get_videos_by_topic_id returns all videos for a topic."""
        # Mock result with multiple videos
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_video_topic_db]
        mock_session.execute.return_value = mock_result

        result = await repository.get_videos_by_topic_id(
            mock_session, TestIds.MUSIC_TOPIC
        )

        assert result == [sample_video_topic_db]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_video_topics(self, repository, mock_session):
        """Test bulk_create_video_topics creates multiple topics efficiently."""
        # Mock get_by_composite_key to return None (not exists)
        repository.get_by_composite_key = AsyncMock(return_value=None)
        # Mock create method
        repository.create = AsyncMock(
            side_effect=lambda session, obj_in: VideoTopicDB(
                video_id=obj_in.video_id,
                topic_id=obj_in.topic_id,
                relevance_type=obj_in.relevance_type,
                created_at=datetime.now(timezone.utc),
            )
        )

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        relevance_types = ["primary", "relevant"]

        result = await repository.bulk_create_video_topics(
            mock_session, TestIds.TEST_VIDEO_1, topic_ids, relevance_types
        )

        assert len(result) == 2
        assert all(isinstance(topic, VideoTopicDB) for topic in result)
        assert repository.create.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_by_video_id(self, repository, mock_session):
        """Test delete_by_video_id removes all topics for a video."""
        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        mock_session.execute.return_value = mock_count_result

        result = await repository.delete_by_video_id(mock_session, TestIds.TEST_VIDEO_1)

        assert result == 3
        assert mock_session.execute.call_count == 2  # Count + Delete
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_topic_id(self, repository, mock_session):
        """Test delete_by_topic_id removes all instances of a topic."""
        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_count_result

        result = await repository.delete_by_topic_id(mock_session, TestIds.MUSIC_TOPIC)

        assert result == 5
        assert mock_session.execute.call_count == 2  # Count + Delete
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_video_topics_with_filters(self, repository, mock_session):
        """Test search_video_topics applies filters correctly."""
        # Create search filters
        filters = create_video_topic_filters(
            video_ids=[TestIds.TEST_VIDEO_1],
            topic_ids=[TestIds.MUSIC_TOPIC],
            relevance_types=["primary"],
        )

        # Mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.search_video_topics(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_popular_topics(self, repository, mock_session):
        """Test get_popular_topics returns topics by video count."""
        # Mock result with topic counts
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.MUSIC_TOPIC, 50),
            (TestIds.GAMING_TOPIC, 35),
        ]
        mock_session.execute.return_value = mock_result

        result = await repository.get_popular_topics(mock_session, limit=10)

        expected = [(TestIds.MUSIC_TOPIC, 50), (TestIds.GAMING_TOPIC, 35)]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_related_topics(self, repository, mock_session):
        """Test get_related_topics finds topics that co-occur."""
        # Mock result with related topics
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.GAMING_TOPIC, 15),
            (TestIds.ENTERTAINMENT_TOPIC, 8),
        ]
        mock_session.execute.return_value = mock_result

        result = await repository.get_related_topics(
            mock_session, TestIds.MUSIC_TOPIC, limit=20
        )

        expected = [(TestIds.GAMING_TOPIC, 15), (TestIds.ENTERTAINMENT_TOPIC, 8)]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_videos_by_topics_match_any(self, repository, mock_session):
        """Test find_videos_by_topics with match_all=False."""
        # Mock result with video IDs
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.TEST_VIDEO_1,),
            (TestIds.TEST_VIDEO_2,),
        ]
        mock_session.execute.return_value = mock_result

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        result = await repository.find_videos_by_topics(
            mock_session, topic_ids, match_all=False
        )

        expected = [TestIds.TEST_VIDEO_1, TestIds.TEST_VIDEO_2]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_videos_by_topics_match_all(self, repository, mock_session):
        """Test find_videos_by_topics with match_all=True."""
        # Mock result with video IDs
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.TEST_VIDEO_1,),
        ]
        mock_session.execute.return_value = mock_result

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        result = await repository.find_videos_by_topics(
            mock_session, topic_ids, match_all=True
        )

        expected = [TestIds.TEST_VIDEO_1]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topic_video_count(self, repository, mock_session):
        """Test get_topic_video_count returns count for a topic."""
        # Mock count result
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute.return_value = mock_result

        result = await repository.get_topic_video_count(
            mock_session, TestIds.MUSIC_TOPIC
        )

        assert result == 42
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_video_count_by_topics(self, repository, mock_session):
        """Test get_video_count_by_topics returns counts for multiple topics."""
        # Mock result with topic counts
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.MUSIC_TOPIC, 42),
            (TestIds.GAMING_TOPIC, 28),
        ]
        mock_session.execute.return_value = mock_result

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        result = await repository.get_video_count_by_topics(mock_session, topic_ids)

        expected = {TestIds.MUSIC_TOPIC: 42, TestIds.GAMING_TOPIC: 28}
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topics_by_relevance_type(
        self, repository, mock_session, sample_video_topic_db
    ):
        """Test get_topics_by_relevance_type returns topics by relevance."""
        # Mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_video_topic_db]
        mock_session.execute.return_value = mock_result

        result = await repository.get_topics_by_relevance_type(mock_session, "primary")

        assert result == [sample_video_topic_db]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_with_valid_tuple(
        self, repository, mock_session, sample_video_topic_db
    ):
        """Test get method with valid composite key tuple."""
        repository.get_by_composite_key = AsyncMock(return_value=sample_video_topic_db)

        result = await repository.get(
            mock_session, (TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC)
        )

        assert result == sample_video_topic_db
        repository.get_by_composite_key.assert_called_once_with(
            mock_session, TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC
        )

    # Note: test_get_with_invalid_id removed - type system now enforces Tuple[str, str]

    @pytest.mark.asyncio
    async def test_exists_with_valid_tuple(self, repository, mock_session):
        """Test exists method with valid composite key tuple."""
        repository.exists_by_composite_key = AsyncMock(return_value=True)

        result = await repository.exists(
            mock_session, (TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC)
        )

        assert result is True
        repository.exists_by_composite_key.assert_called_once_with(
            mock_session, TestIds.TEST_VIDEO_1, TestIds.MUSIC_TOPIC
        )

    # Note: test_exists_with_invalid_id removed - type system now enforces Tuple[str, str]

    @pytest.mark.asyncio
    async def test_replace_video_topics(self, repository, mock_session):
        """Test replace_video_topics replaces all topics for a video."""
        # Mock bulk_create_video_topics
        created_topics = [
            VideoTopicDB(
                video_id=TestIds.TEST_VIDEO_1,
                topic_id=TestIds.MUSIC_TOPIC,
                relevance_type="primary",
                created_at=datetime.now(timezone.utc),
            )
        ]
        repository.bulk_create_video_topics = AsyncMock(return_value=created_topics)

        topic_ids = [TestIds.MUSIC_TOPIC]
        relevance_types = ["primary"]

        result = await repository.replace_video_topics(
            mock_session, TestIds.TEST_VIDEO_1, topic_ids, relevance_types
        )

        assert result == created_topics
        mock_session.execute.assert_called_once()  # For delete
        repository.bulk_create_video_topics.assert_called_once_with(
            mock_session, TestIds.TEST_VIDEO_1, topic_ids, relevance_types
        )

    @pytest.mark.asyncio
    async def test_create_or_update_existing_topic(
        self, repository, mock_session, sample_video_topic_create
    ):
        """Test create_or_update updates existing video topic."""
        # Mock existing topic
        existing_topic = VideoTopicDB(
            video_id=sample_video_topic_create.video_id,
            topic_id=sample_video_topic_create.topic_id,
            relevance_type="secondary",
            created_at=datetime.now(timezone.utc),
        )
        repository.get_by_composite_key = AsyncMock(return_value=existing_topic)
        repository.update = AsyncMock(return_value=existing_topic)

        result = await repository.create_or_update(
            mock_session, sample_video_topic_create
        )

        assert result == existing_topic
        repository.get_by_composite_key.assert_called_once_with(
            mock_session,
            sample_video_topic_create.video_id,
            sample_video_topic_create.topic_id,
        )
        repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_new_topic(
        self, repository, mock_session, sample_video_topic_create
    ):
        """Test create_or_update creates new video topic."""
        # Mock no existing topic
        repository.get_by_composite_key = AsyncMock(return_value=None)

        new_topic = VideoTopicDB(
            video_id=sample_video_topic_create.video_id,
            topic_id=sample_video_topic_create.topic_id,
            relevance_type=sample_video_topic_create.relevance_type,
            created_at=datetime.now(timezone.utc),
        )
        repository.create = AsyncMock(return_value=new_topic)

        result = await repository.create_or_update(
            mock_session, sample_video_topic_create
        )

        assert result == new_topic
        repository.get_by_composite_key.assert_called_once_with(
            mock_session,
            sample_video_topic_create.video_id,
            sample_video_topic_create.topic_id,
        )
        repository.create.assert_called_once_with(
            mock_session, obj_in=sample_video_topic_create
        )

    @pytest.mark.asyncio
    async def test_bulk_create_video_topics_with_existing(
        self, repository, mock_session
    ):
        """Test bulk_create_video_topics handles existing topics."""
        # Mock get_by_composite_key to return existing for first topic, None for second
        existing_topic = VideoTopicDB(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.MUSIC_TOPIC,
            relevance_type="primary",
            created_at=datetime.now(timezone.utc),
        )

        def mock_get_existing(session, video_id, topic_id):
            if topic_id == TestIds.MUSIC_TOPIC:
                return existing_topic
            return None

        repository.get_by_composite_key = AsyncMock(side_effect=mock_get_existing)

        # Mock create method for new topics
        new_topic = VideoTopicDB(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.GAMING_TOPIC,
            relevance_type="relevant",
            created_at=datetime.now(timezone.utc),
        )
        repository.create = AsyncMock(return_value=new_topic)

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        relevance_types = ["primary", "relevant"]

        result = await repository.bulk_create_video_topics(
            mock_session, TestIds.TEST_VIDEO_1, topic_ids, relevance_types
        )

        assert len(result) == 2
        assert result[0] == existing_topic  # Existing topic returned
        assert result[1] == new_topic  # New topic created
        repository.create.assert_called_once()  # Only called for new topic

    @pytest.mark.asyncio
    async def test_get_video_topic_statistics(self, repository, mock_session):
        """Test get_video_topic_statistics returns comprehensive statistics."""
        # Mock all the database queries with different return values
        mock_results = [
            MagicMock(scalar=MagicMock(return_value=100)),  # total_video_topics
            MagicMock(scalar=MagicMock(return_value=25)),  # unique_topics
            MagicMock(scalar=MagicMock(return_value=50)),  # unique_videos
            MagicMock(scalar=MagicMock(return_value=2.5)),  # avg_topics_per_video
            # most_common_topics
            MagicMock(
                __iter__=MagicMock(
                    return_value=iter(
                        [(TestIds.MUSIC_TOPIC, 30), (TestIds.GAMING_TOPIC, 20)]
                    )
                )
            ),
            # relevance_type_distribution
            MagicMock(
                __iter__=MagicMock(
                    return_value=iter([("primary", 60), ("relevant", 40)])
                )
            ),
        ]

        mock_session.execute.side_effect = mock_results

        result = await repository.get_video_topic_statistics(mock_session)

        assert result.total_video_topics == 100
        assert result.unique_topics == 25
        assert result.unique_videos == 50
        assert result.avg_topics_per_video == 2.5
        assert result.most_common_topics == [
            (TestIds.MUSIC_TOPIC, 30),
            (TestIds.GAMING_TOPIC, 20),
        ]
        assert result.relevance_type_distribution == {"primary": 60, "relevant": 40}
        assert mock_session.execute.call_count == 6

    @pytest.mark.asyncio
    async def test_find_videos_by_topics_empty_list(self, repository, mock_session):
        """Test find_videos_by_topics returns empty list for empty topic_ids."""
        result = await repository.find_videos_by_topics(
            mock_session, [], match_all=False
        )
        assert result == []

        result = await repository.find_videos_by_topics(
            mock_session, [], match_all=True
        )
        assert result == []

        # Should not call database when topic_ids is empty
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_video_count_by_topics_empty_list(self, repository, mock_session):
        """Test get_video_count_by_topics returns empty dict for empty topic_ids."""
        result = await repository.get_video_count_by_topics(mock_session, [])
        assert result == {}

        # Should not call database when topic_ids is empty
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_topics(self, repository, mock_session):
        """Test cleanup_orphaned_topics returns placeholder value."""
        result = await repository.cleanup_orphaned_topics(mock_session)
        assert result == 0

        # Should not call database as it's a placeholder implementation
        mock_session.execute.assert_not_called()
