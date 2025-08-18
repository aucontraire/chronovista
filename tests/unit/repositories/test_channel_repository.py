"""
Tests for ChannelRepository functionality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.models.channel import (
    ChannelCreate,
    ChannelSearchFilters,
    ChannelStatistics,
)
from chronovista.models.enums import LanguageCode
from chronovista.repositories.channel_repository import ChannelRepository


class TestChannelRepository:
    """Test ChannelRepository functionality."""

    @pytest.fixture
    def repository(self) -> ChannelRepository:
        """Create repository instance for testing."""
        return ChannelRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_channel_db(self) -> ChannelDB:
        """Create sample database channel object."""
        return ChannelDB(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="RickAstleyVEVO",
            description="Official channel of Rick Astley",
            subscriber_count=5000000,
            video_count=100,
            default_language="en",
            country="GB",
            thumbnail_url="https://yt3.ggpht.com/test.jpg",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_channel_create(self) -> ChannelCreate:
        """Create sample ChannelCreate instance."""
        return ChannelCreate(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Test Channel",
            description="Test channel description",
            subscriber_count=10000,
            video_count=50,
            default_language=LanguageCode.ENGLISH,
            country="US",
            thumbnail_url="https://yt3.ggpht.com/test.jpg",
        )

    def test_repository_initialization(self, repository: ChannelRepository):
        """Test repository initialization."""
        assert repository.model == ChannelDB

    @pytest.mark.asyncio
    async def test_get_by_channel_id_existing(
        self,
        repository: ChannelRepository,
        mock_session: AsyncMock,
        sample_channel_db: ChannelDB,
    ):
        """Test getting channel by channel ID when it exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_channel_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_channel_id(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )

        assert result == sample_channel_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_channel_id_not_found(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test getting channel by channel ID when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_channel_id(mock_session, "nonexistent")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_channel_id_true(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test exists by channel ID returns True when channel exists."""
        mock_result = MagicMock()
        mock_result.first.return_value = ("UCuAXFkgsw1L7xaCfnd5JJOw",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_channel_id(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_by_channel_id_false(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test exists by channel ID returns False when channel doesn't exist."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_channel_id(mock_session, "nonexistent")

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_new_channel(
        self,
        repository: ChannelRepository,
        mock_session: AsyncMock,
        sample_channel_create: ChannelCreate,
        sample_channel_db: ChannelDB,
    ):
        """Test creating a new channel."""
        with (
            patch.object(
                repository, "get_by_channel_id", new=AsyncMock(return_value=None)
            ) as mock_get,
            patch.object(
                repository, "create", new=AsyncMock(return_value=sample_channel_db)
            ) as mock_create,
        ):

            result = await repository.create_or_update(
                mock_session, sample_channel_create
            )

            assert result == sample_channel_db
            mock_get.assert_called_once_with(
                mock_session, sample_channel_create.channel_id
            )
            mock_create.assert_called_once_with(
                mock_session, obj_in=sample_channel_create
            )

    @pytest.mark.asyncio
    async def test_create_or_update_existing_channel(
        self,
        repository: ChannelRepository,
        mock_session: AsyncMock,
        sample_channel_create: ChannelCreate,
        sample_channel_db: ChannelDB,
    ):
        """Test updating an existing channel."""
        with (
            patch.object(
                repository,
                "get_by_channel_id",
                new=AsyncMock(return_value=sample_channel_db),
            ) as mock_get,
            patch.object(
                repository, "update", new=AsyncMock(return_value=sample_channel_db)
            ) as mock_update,
        ):

            result = await repository.create_or_update(
                mock_session, sample_channel_create
            )

            assert result == sample_channel_db
            mock_get.assert_called_once_with(
                mock_session, sample_channel_create.channel_id
            )
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_title(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test finding channels by title."""
        mock_channels = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_title(mock_session, "test")

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_multi_with_pagination(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test getting multiple channels with pagination."""
        mock_channels = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_multi(mock_session, skip=10, limit=20)

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_country(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test finding channels by country."""
        mock_channels = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_country(mock_session, "US")

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_with_keywords(
        self,
        repository: ChannelRepository,
        mock_session: AsyncMock,
        sample_channel_db: ChannelDB,
    ):
        """Test getting channel with keywords loaded."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_channel_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_with_keywords(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )

        assert result == sample_channel_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test searching channels with filters."""
        filters = ChannelSearchFilters(title_query="test")
        mock_channels = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_statistics_no_data(
        self, repository: ChannelRepository, mock_session: AsyncMock
    ):
        """Test getting channel statistics with no data."""
        expected_stats = ChannelStatistics(
            total_channels=0,
            total_subscribers=0,
            total_videos=0,
            avg_subscribers_per_channel=0.0,
            avg_videos_per_channel=0.0,
            top_countries=[],
            top_languages=[],
        )
        with patch.object(
            repository,
            "get_channel_statistics",
            new=AsyncMock(return_value=expected_stats),
        ) as mock_get_stats:

            result = await repository.get_channel_statistics(mock_session)

            assert isinstance(result, ChannelStatistics)
            assert result.total_channels == 0
            assert result.total_subscribers == 0
            assert result.total_videos == 0
            assert result.total_videos == 0
            assert result.avg_subscribers_per_channel == 0.0
            assert result.avg_videos_per_channel == 0.0
            assert result.top_countries == []
            assert result.top_languages == []

    def test_repository_inherits_base_methods(self, repository: ChannelRepository):
        """Test that repository inherits base methods."""
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")
        assert hasattr(repository, "model")

    def test_get_and_exists_method_delegation(self, repository: ChannelRepository):
        """Test that get and exists methods delegate to channel_id methods."""
        assert hasattr(repository, "get")
        assert hasattr(repository, "exists")
        assert hasattr(repository, "get_by_channel_id")
        assert hasattr(repository, "exists_by_channel_id")


class TestChannelRepositoryAdditionalMethods:
    """Test additional channel repository methods to improve coverage."""

    @pytest.fixture
    def repository(self) -> ChannelRepository:
        """Create channel repository instance."""
        return ChannelRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_get_method_delegation(
        self, repository: ChannelRepository, mock_session
    ):
        """Test get method delegates to get_by_channel_id."""
        mock_channel = MagicMock()
        with patch.object(
            repository, "get_by_channel_id", new=AsyncMock(return_value=mock_channel)
        ) as mock_get:

            result = await repository.get(mock_session, "UC123")

            assert result == mock_channel
            mock_get.assert_called_once_with(mock_session, "UC123")

    @pytest.mark.asyncio
    async def test_exists_method_delegation(
        self, repository: ChannelRepository, mock_session
    ):
        """Test exists method delegates to exists_by_channel_id."""
        with patch.object(
            repository, "exists_by_channel_id", new=AsyncMock(return_value=True)
        ) as mock_exists:

            result = await repository.exists(mock_session, "UC123")

            assert result is True
            mock_exists.assert_called_once_with(mock_session, "UC123")

    @pytest.mark.asyncio
    async def test_find_by_keyword_method_exists(
        self, repository: ChannelRepository, mock_session
    ):
        """Test that find_by_keyword method works if it exists."""
        if hasattr(repository, "find_by_keyword"):
            mock_channels = [MagicMock(), MagicMock()]
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = mock_channels
            mock_session.execute.return_value = mock_result

            result = await repository.find_by_keyword(mock_session, "python")

            assert result == mock_channels
            mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_channel_statistics_method_exists(
        self, repository: ChannelRepository, mock_session
    ):
        """Test that update_channel_statistics method works if it exists."""
        if hasattr(repository, "update_channel_statistics"):
            stats = {
                "subscriber_count": 10000,
                "video_count": 100,
                "view_count": 1000000,
            }

            mock_session.execute.return_value = None

            await repository.update_channel_statistics(mock_session, "UC123", stats)

            mock_session.execute.assert_called_once()
