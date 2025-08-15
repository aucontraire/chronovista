"""
Tests for TopicCategoryRepository functionality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TopicCategory as TopicCategoryDB
from chronovista.models.topic_category import (
    TopicCategoryCreate,
    TopicCategorySearchFilters,
    TopicCategoryStatistics
)
from chronovista.repositories.topic_category_repository import TopicCategoryRepository


class TestTopicCategoryRepository:
    """Test TopicCategoryRepository functionality."""

    @pytest.fixture
    def repository(self) -> TopicCategoryRepository:
        """Create repository instance for testing."""
        return TopicCategoryRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def sample_topic_db(self) -> TopicCategoryDB:
        """Create sample database topic object."""
        return TopicCategoryDB(
            topic_id="/m/019_rr",
            category_name="Technology",
            parent_topic_id=None,
            topic_type="youtube",
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_child_topic_db(self) -> TopicCategoryDB:
        """Create sample child topic object."""
        return TopicCategoryDB(
            topic_id="/m/05qjc",
            category_name="Programming",
            parent_topic_id="/m/019_rr",
            topic_type="youtube",
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_topic_create(self) -> TopicCategoryCreate:
        """Create sample TopicCategoryCreate instance."""
        return TopicCategoryCreate(
            topic_id="/m/019_rr",
            category_name="Technology",
            parent_topic_id=None,
            topic_type="youtube",
        )

    def test_repository_initialization(self, repository: TopicCategoryRepository):
        """Test repository initialization."""
        assert repository.model == TopicCategoryDB

    @pytest.mark.asyncio
    async def test_get_by_topic_id_existing(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_db: TopicCategoryDB,
    ):
        """Test getting topic by topic ID when it exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_topic_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_topic_id(mock_session, "/m/019_rr")

        assert result == sample_topic_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_topic_id_not_found(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test getting topic by topic ID when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_topic_id(mock_session, "/m/nonexistent")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_topic_id_true(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test exists by topic ID returns True when topic exists."""
        mock_result = MagicMock()
        mock_result.first.return_value = ("/m/019_rr",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_topic_id(mock_session, "/m/019_rr")

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_topic_id_false(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test exists by topic ID returns False when topic doesn't exist."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_topic_id(mock_session, "/m/nonexistent")

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_new_topic(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_create: TopicCategoryCreate,
        sample_topic_db: TopicCategoryDB,
    ):
        """Test creating a new topic."""
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=None)) as mock_get:
            with patch.object(repository, "create", new=AsyncMock(return_value=sample_topic_db)) as mock_create:
                result = await repository.create_or_update(mock_session, sample_topic_create)

                assert result == sample_topic_db
                mock_get.assert_called_once_with(
                    mock_session, sample_topic_create.topic_id
                )
                mock_create.assert_called_once_with(
                    mock_session, obj_in=sample_topic_create
                )

    @pytest.mark.asyncio
    async def test_create_or_update_existing_topic(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_create: TopicCategoryCreate,
        sample_topic_db: TopicCategoryDB,
    ):
        """Test updating an existing topic."""
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=sample_topic_db)) as mock_get:
            with patch.object(repository, "update", new=AsyncMock(return_value=sample_topic_db)) as mock_update:
                result = await repository.create_or_update(mock_session, sample_topic_create)

                assert result == sample_topic_db
                mock_get.assert_called_once_with(
                    mock_session, sample_topic_create.topic_id
                )
                mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_root_topics(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test getting root topics."""
        mock_topics = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_topics
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_root_topics(mock_session)

        assert result == mock_topics
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_children(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test getting child topics."""
        mock_topics = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_topics
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_children(mock_session, "/m/019_rr")

        assert result == mock_topics
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_name(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test finding topics by name."""
        mock_topics = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_topics
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_name(mock_session, "tech")

        assert result == mock_topics
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_type(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test finding topics by type."""
        mock_topics = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_topics
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_type(mock_session, "youtube")

        assert result == mock_topics
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_topics_with_filters(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test searching topics with filters."""
        filters = TopicCategorySearchFilters(
            category_name_query="tech", topic_types=["youtube"]
        )
        mock_topics = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_topics
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_topics(mock_session, filters)

        assert result == mock_topics
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topic_statistics_no_data(
        self, repository: TopicCategoryRepository, mock_session: MagicMock
    ):
        """Test getting topic statistics with no data."""
        # Mock scalar results to return 0 for counts
        mock_session.execute.return_value.scalar.return_value = 0

        # Mock empty results for group by queries
        empty_result = MagicMock()
        empty_result.__iter__ = lambda x: iter([])

        # Set up multiple execute calls
        mock_session.execute.side_effect = [
            MagicMock(scalar=lambda: 0),  # total_topics
            MagicMock(scalar=lambda: 0),  # root_topics
            empty_result,  # type_result
            empty_result,  # popular_result
        ]

        result = await repository.get_topic_statistics(mock_session)

        assert isinstance(result, TopicCategoryStatistics)
        assert result.total_topics == 0
        assert result.root_topics == 0
        assert result.topic_type_distribution == {}
        assert result.most_popular_topics == []

    @pytest.mark.asyncio
    async def test_delete_by_topic_id(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_db: TopicCategoryDB,
    ):
        """Test deleting topic by topic ID."""
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=sample_topic_db)) as mock_get:
            result = await repository.delete_by_topic_id(mock_session, "/m/019_rr")

            assert result == sample_topic_db
            mock_get.assert_called_once_with(mock_session, "/m/019_rr")
            mock_session.delete.assert_called_once_with(sample_topic_db)
            mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_new_topics(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_create: TopicCategoryCreate,
        sample_topic_db: TopicCategoryDB,
    ):
        """Test bulk creating new topics."""
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=None)) as mock_get:
            with patch.object(repository, "create", new=AsyncMock(return_value=sample_topic_db)) as mock_create:
                result = await repository.bulk_create(mock_session, [sample_topic_create])

                assert result == [sample_topic_db]
                mock_get.assert_called_once()
                mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_existing_topics(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_create: TopicCategoryCreate,
        sample_topic_db: TopicCategoryDB,
    ):
        """Test bulk creating with existing topics."""
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=sample_topic_db)) as mock_get:
            result = await repository.bulk_create(mock_session, [sample_topic_create])

            assert result == [sample_topic_db]
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topic_path_single_topic(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_db: TopicCategoryDB,
    ):
        """Test getting topic path for root topic."""
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=sample_topic_db)):
            result = await repository.get_topic_path(mock_session, "/m/019_rr")

            assert result == [sample_topic_db]

    @pytest.mark.asyncio
    async def test_get_topic_path_hierarchical(
        self,
        repository: TopicCategoryRepository,
        mock_session: MagicMock,
        sample_topic_db: TopicCategoryDB,
        sample_child_topic_db: TopicCategoryDB,
    ):
        """Test getting topic path for child topic."""
        # Mock returning child topic first, then parent
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(
            side_effect=[sample_child_topic_db, sample_topic_db]
        )):
            result = await repository.get_topic_path(mock_session, "/m/05qjc")

            # Should return path from root to child: [parent, child]
            assert len(result) == 2
            assert result[0] == sample_topic_db  # Parent (root)
            assert result[1] == sample_child_topic_db  # Child

    def test_repository_inherits_base_methods(
        self, repository: TopicCategoryRepository
    ):
        """Test that repository inherits base methods."""
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")
        assert hasattr(repository, "model")

    def test_get_and_exists_method_delegation(
        self, repository: TopicCategoryRepository
    ):
        """Test that get and exists methods delegate to topic_id methods."""
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "get_by_topic_id")
        assert hasattr(repository, "exists_by_topic_id")


class TestTopicCategoryRepositoryAdditionalMethods:
    """Test additional topic category repository methods to improve coverage."""

    @pytest.fixture
    def repository(self) -> TopicCategoryRepository:
        """Create topic category repository instance."""
        return TopicCategoryRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_get_method_delegation(
        self, repository: TopicCategoryRepository, mock_session
    ):
        """Test get method delegates to get_by_topic_id."""
        mock_topic = MagicMock()

        # Mock the execute call to return the topic
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_topic
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "/m/019_rr")

        assert result == mock_topic
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_method_delegation(
        self, repository: TopicCategoryRepository, mock_session
    ):
        """Test exists method delegates to exists_by_topic_id."""
        # Mock the execute call to return a topic ID (exists = True)
        mock_result = MagicMock()
        mock_result.first.return_value = ("/m/019_rr",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, "/m/019_rr")

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_topics_empty_filters(
        self, repository: TopicCategoryRepository, mock_session
    ):
        """Test searching topics with empty filters."""
        filters = TopicCategorySearchFilters()
        mock_topics = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_topics
        mock_session.execute.return_value = mock_result

        result = await repository.search_topics(mock_session, filters)

        assert result == mock_topics
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_topics_all_filters(
        self, repository: TopicCategoryRepository, mock_session
    ):
        """Test searching topics with all filters applied."""
        filters = TopicCategorySearchFilters(
            topic_ids=["/m/019_rr"],
            category_name_query="tech",
            parent_topic_ids=["/m/parent"],
            topic_types=["youtube"],
            is_root_topic=True,
            created_after=datetime.now(timezone.utc),
            created_before=datetime.now(timezone.utc),
        )
        mock_topics = [MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_topics
        mock_session.execute.return_value = mock_result

        result = await repository.search_topics(mock_session, filters)

        assert result == mock_topics
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topic_hierarchy_method_exists(
        self, repository: TopicCategoryRepository, mock_session
    ):
        """Test that get_topic_hierarchy method works."""
        mock_topic = MagicMock()
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=mock_topic)) as mock_get:
            result = await repository.get_topic_hierarchy(mock_session, "/m/019_rr")

            assert result == mock_topic
            mock_get.assert_called_once_with(mock_session, "/m/019_rr")

    @pytest.mark.asyncio
    async def test_get_topic_path_nonexistent_topic(
        self, repository: TopicCategoryRepository, mock_session
    ):
        """Test getting topic path for nonexistent topic."""
        with patch.object(repository, "get_by_topic_id", new=AsyncMock(return_value=None)):
            result = await repository.get_topic_path(mock_session, "/m/nonexistent")

            assert result == []
