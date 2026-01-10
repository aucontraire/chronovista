"""
Test ChannelTopicRepository functionality.

Tests the ChannelTopicRepository class for managing channel-topic relationships
with comprehensive coverage of CRUD operations, search, and analytics.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import ChannelTopic as ChannelTopicDB
from chronovista.models.channel_topic import (
    ChannelTopicCreate,
    ChannelTopicSearchFilters,
    ChannelTopicUpdate,
)
from chronovista.repositories.channel_topic_repository import ChannelTopicRepository
from tests.factories import (
    ChannelTopicTestData,
    TestIds,
    create_channel_topic_create,
    create_channel_topic_filters,
    create_channel_topic_update,
)

# Mark all tests as async for this module
pytestmark = pytest.mark.asyncio


class TestChannelTopicRepository:
    """Test ChannelTopicRepository functionality."""

    @pytest.fixture
    def repository(self):
        """Create ChannelTopicRepository instance."""
        return ChannelTopicRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_channel_topic_create(self):
        """Create sample ChannelTopicCreate data."""
        return create_channel_topic_create(
            channel_id=TestIds.TEST_CHANNEL_1, topic_id=TestIds.MUSIC_TOPIC
        )

    @pytest.fixture
    def sample_channel_topic_db(self):
        """Create sample ChannelTopicDB instance."""
        return ChannelTopicDB(
            channel_id=TestIds.TEST_CHANNEL_1,
            topic_id=TestIds.MUSIC_TOPIC,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_repository_initialization(self, repository):
        """Test repository initializes correctly."""
        assert repository.model == ChannelTopicDB
        assert isinstance(repository, ChannelTopicRepository)

    @pytest.mark.asyncio
    async def test_get_by_composite_key_success(
        self, repository, mock_session, sample_channel_topic_db
    ):
        """Test get_by_composite_key returns channel topic when found."""
        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_channel_topic_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC
        )

        assert result == sample_channel_topic_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_composite_key_not_found(self, repository, mock_session):
        """Test get_by_composite_key returns None when not found."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC
        )

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_composite_key_true(self, repository, mock_session):
        """Test exists_by_composite_key returns True when channel topic exists."""
        # Mock result with data
        mock_result = MagicMock()
        mock_result.first.return_value = ("some_channel_id",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_composite_key_false(self, repository, mock_session):
        """Test exists_by_composite_key returns False when channel topic doesn't exist."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC
        )

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topics_by_channel_id(
        self, repository, mock_session, sample_channel_topic_db
    ):
        """Test get_topics_by_channel_id returns all topics for a channel."""
        # Mock result with multiple topics
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_channel_topic_db]
        mock_session.execute.return_value = mock_result

        result = await repository.get_topics_by_channel_id(
            mock_session, TestIds.TEST_CHANNEL_1
        )

        assert result == [sample_channel_topic_db]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channels_by_topic_id(
        self, repository, mock_session, sample_channel_topic_db
    ):
        """Test get_channels_by_topic_id returns all channels for a topic."""
        # Mock result with multiple channels
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_channel_topic_db]
        mock_session.execute.return_value = mock_result

        result = await repository.get_channels_by_topic_id(
            mock_session, TestIds.MUSIC_TOPIC
        )

        assert result == [sample_channel_topic_db]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_channel_topics(self, repository, mock_session):
        """Test bulk_create_channel_topics creates multiple topics efficiently."""
        # Mock get_by_composite_key to return None (not exists)
        repository.get_by_composite_key = AsyncMock(return_value=None)
        # Mock create method
        repository.create = AsyncMock(
            side_effect=lambda session, obj_in: ChannelTopicDB(
                channel_id=obj_in.channel_id,
                topic_id=obj_in.topic_id,
                created_at=datetime.now(timezone.utc),
            )
        )

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]

        result = await repository.bulk_create_channel_topics(
            mock_session, TestIds.TEST_CHANNEL_1, topic_ids
        )

        assert len(result) == 2
        assert all(isinstance(topic, ChannelTopicDB) for topic in result)
        assert repository.create.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_by_channel_id(self, repository, mock_session):
        """Test delete_by_channel_id removes all topics for a channel."""
        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        mock_session.execute.return_value = mock_count_result

        result = await repository.delete_by_channel_id(
            mock_session, TestIds.TEST_CHANNEL_1
        )

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
    async def test_search_channel_topics_with_filters(self, repository, mock_session):
        """Test search_channel_topics applies filters correctly."""
        # Create search filters
        filters = create_channel_topic_filters(
            channel_ids=[TestIds.TEST_CHANNEL_1], topic_ids=[TestIds.MUSIC_TOPIC]
        )

        # Mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.search_channel_topics(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_popular_topics(self, repository, mock_session):
        """Test get_popular_topics returns topics by channel count."""
        # Mock result with topic counts
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.MUSIC_TOPIC, 25),
            (TestIds.GAMING_TOPIC, 18),
        ]
        mock_session.execute.return_value = mock_result

        result = await repository.get_popular_topics(mock_session, limit=10)

        expected = [(TestIds.MUSIC_TOPIC, 25), (TestIds.GAMING_TOPIC, 18)]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_related_topics(self, repository, mock_session):
        """Test get_related_topics finds topics that co-occur."""
        # Mock result with related topics
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.GAMING_TOPIC, 8),
            (TestIds.ENTERTAINMENT_TOPIC, 5),
        ]
        mock_session.execute.return_value = mock_result

        result = await repository.get_related_topics(
            mock_session, TestIds.MUSIC_TOPIC, limit=20
        )

        expected = [(TestIds.GAMING_TOPIC, 8), (TestIds.ENTERTAINMENT_TOPIC, 5)]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_channels_by_topics_match_any(self, repository, mock_session):
        """Test find_channels_by_topics with match_all=False."""
        # Mock result with channel IDs
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.TEST_CHANNEL_1,),
            (TestIds.TEST_CHANNEL_2,),
        ]
        mock_session.execute.return_value = mock_result

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        result = await repository.find_channels_by_topics(
            mock_session, topic_ids, match_all=False
        )

        expected = [TestIds.TEST_CHANNEL_1, TestIds.TEST_CHANNEL_2]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_channels_by_topics_match_all(self, repository, mock_session):
        """Test find_channels_by_topics with match_all=True."""
        # Mock result with channel IDs
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.TEST_CHANNEL_1,),
        ]
        mock_session.execute.return_value = mock_result

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        result = await repository.find_channels_by_topics(
            mock_session, topic_ids, match_all=True
        )

        expected = [TestIds.TEST_CHANNEL_1]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topic_channel_count(self, repository, mock_session):
        """Test get_topic_channel_count returns count for a topic."""
        # Mock count result
        mock_result = MagicMock()
        mock_result.scalar.return_value = 15
        mock_session.execute.return_value = mock_result

        result = await repository.get_topic_channel_count(
            mock_session, TestIds.MUSIC_TOPIC
        )

        assert result == 15
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_count_by_topics(self, repository, mock_session):
        """Test get_channel_count_by_topics returns counts for multiple topics."""
        # Mock result with topic counts
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.MUSIC_TOPIC, 15),
            (TestIds.GAMING_TOPIC, 12),
        ]
        mock_session.execute.return_value = mock_result

        topic_ids = [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        result = await repository.get_channel_count_by_topics(mock_session, topic_ids)

        expected = {TestIds.MUSIC_TOPIC: 15, TestIds.GAMING_TOPIC: 12}
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_topic_overlap(self, repository, mock_session):
        """Test get_channel_topic_overlap finds common topics between channels."""
        # Mock result with common topic IDs
        mock_result = MagicMock()
        mock_result.__iter__.return_value = [
            (TestIds.MUSIC_TOPIC,),
            (TestIds.ENTERTAINMENT_TOPIC,),
        ]
        mock_session.execute.return_value = mock_result

        result = await repository.get_channel_topic_overlap(
            mock_session, TestIds.TEST_CHANNEL_1, TestIds.TEST_CHANNEL_2
        )

        expected = [TestIds.MUSIC_TOPIC, TestIds.ENTERTAINMENT_TOPIC]
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_with_valid_tuple(
        self, repository, mock_session, sample_channel_topic_db
    ):
        """Test get method with valid composite key tuple."""
        repository.get_by_composite_key = AsyncMock(
            return_value=sample_channel_topic_db
        )

        result = await repository.get(
            mock_session, (TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC)
        )

        assert result == sample_channel_topic_db
        repository.get_by_composite_key.assert_called_once_with(
            mock_session, TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC
        )

    # Note: test_get_with_invalid_id removed - type system now enforces Tuple[str, str]

    @pytest.mark.asyncio
    async def test_exists_with_valid_tuple(self, repository, mock_session):
        """Test exists method with valid composite key tuple."""
        repository.exists_by_composite_key = AsyncMock(return_value=True)

        result = await repository.exists(
            mock_session, (TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC)
        )

        assert result is True
        repository.exists_by_composite_key.assert_called_once_with(
            mock_session, TestIds.TEST_CHANNEL_1, TestIds.MUSIC_TOPIC
        )

    # Note: test_exists_with_invalid_id removed - type system now enforces Tuple[str, str]

    @pytest.mark.asyncio
    async def test_replace_channel_topics(self, repository, mock_session):
        """Test replace_channel_topics replaces all topics for a channel."""
        # Mock bulk_create_channel_topics
        created_topics = [
            ChannelTopicDB(
                channel_id=TestIds.TEST_CHANNEL_1,
                topic_id=TestIds.MUSIC_TOPIC,
                created_at=datetime.now(timezone.utc),
            )
        ]
        repository.bulk_create_channel_topics = AsyncMock(return_value=created_topics)

        topic_ids = [TestIds.MUSIC_TOPIC]

        result = await repository.replace_channel_topics(
            mock_session, TestIds.TEST_CHANNEL_1, topic_ids
        )

        assert result == created_topics
        mock_session.execute.assert_called_once()  # For delete
        repository.bulk_create_channel_topics.assert_called_once_with(
            mock_session, TestIds.TEST_CHANNEL_1, topic_ids
        )

    @pytest.mark.asyncio
    async def test_create_or_update_existing(
        self, repository, mock_session, sample_channel_topic_db
    ):
        """Test create_or_update returns existing when topic already exists."""
        repository.get_by_composite_key = AsyncMock(
            return_value=sample_channel_topic_db
        )

        topic_create = create_channel_topic_create(
            channel_id=TestIds.TEST_CHANNEL_1, topic_id=TestIds.MUSIC_TOPIC
        )

        result = await repository.create_or_update(mock_session, topic_create)

        assert result == sample_channel_topic_db
        repository.get_by_composite_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_new(self, repository, mock_session):
        """Test create_or_update creates new when topic doesn't exist."""
        repository.get_by_composite_key = AsyncMock(return_value=None)

        new_topic = ChannelTopicDB(
            channel_id=TestIds.TEST_CHANNEL_1,
            topic_id=TestIds.MUSIC_TOPIC,
            created_at=datetime.now(timezone.utc),
        )
        repository.create = AsyncMock(return_value=new_topic)

        topic_create = create_channel_topic_create(
            channel_id=TestIds.TEST_CHANNEL_1, topic_id=TestIds.MUSIC_TOPIC
        )

        result = await repository.create_or_update(mock_session, topic_create)

        assert result == new_topic
        repository.get_by_composite_key.assert_called_once()
        repository.create.assert_called_once()
