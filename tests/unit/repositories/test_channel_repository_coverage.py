"""
Targeted tests for channel_repository.py to boost coverage to 90%.

Focuses on uncovered lines in channel repository methods.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.models.channel import ChannelCreate, ChannelUpdate
from chronovista.repositories.channel_repository import ChannelRepository

pytestmark = pytest.mark.asyncio


class TestChannelRepositoryCoverage:
    """Test channel repository to boost coverage."""

    @pytest.fixture
    def repository(self):
        """Create repository instance."""
        return ChannelRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_channel_create(self):
        """Create sample channel data."""
        return ChannelCreate(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Test Channel",
            description="Test Description",
        )

    @pytest.mark.asyncio
    async def test_get_by_channel_id_found(self, repository, mock_session):
        """Test get_by_channel_id when channel exists."""
        mock_channel = MagicMock(spec=ChannelDB)
        mock_channel.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_channel
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_channel_id(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )

        assert result == mock_channel
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_channel_id_not_found(self, repository, mock_session):
        """Test get_by_channel_id when channel doesn't exist."""
        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_channel_id(mock_session, "UCnotfound")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_update_new_channel(
        self, repository, mock_session, sample_channel_create
    ):
        """Test create_or_update with new channel."""
        # Mock that channel doesn't exist
        repository.get_by_channel_id = AsyncMock(return_value=None)

        # Mock create method
        mock_created_channel = MagicMock(spec=ChannelDB)
        repository.create = AsyncMock(return_value=mock_created_channel)

        result = await repository.create_or_update(mock_session, sample_channel_create)

        assert result == mock_created_channel
        repository.get_by_channel_id.assert_called_once_with(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )
        repository.create.assert_called_once_with(
            mock_session, obj_in=sample_channel_create
        )

    @pytest.mark.asyncio
    async def test_create_or_update_existing_channel(
        self, repository, mock_session, sample_channel_create
    ):
        """Test create_or_update with existing channel."""
        # Mock that channel exists
        mock_existing_channel = MagicMock(spec=ChannelDB)
        repository.get_by_channel_id = AsyncMock(return_value=mock_existing_channel)

        # Mock update method
        mock_updated_channel = MagicMock(spec=ChannelDB)
        repository.update = AsyncMock(return_value=mock_updated_channel)

        result = await repository.create_or_update(mock_session, sample_channel_create)

        assert result == mock_updated_channel
        repository.get_by_channel_id.assert_called_once_with(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )
        repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_title(self, repository, mock_session):
        """Test find_by_title method."""
        mock_channels = [MagicMock(spec=ChannelDB), MagicMock(spec=ChannelDB)]

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_title(mock_session, "test query")

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_statistics(self, repository, mock_session):
        """Test get_channel_statistics method."""
        from chronovista.models.channel import ChannelStatistics

        # Mock the stats query result
        mock_stats_row = MagicMock()
        mock_stats_row.total_channels = 100
        mock_stats_row.total_subscribers = 50000
        mock_stats_row.total_videos = 2000
        mock_stats_row.avg_subscribers = 500.0
        mock_stats_row.avg_videos = 20.0

        mock_result = MagicMock()
        mock_result.first.return_value = mock_stats_row
        mock_session.execute.return_value = mock_result

        result = await repository.get_channel_statistics(mock_session)

        assert isinstance(result, ChannelStatistics)
        assert result.total_channels == 100
        mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_top_channels_by_subscribers(self, repository, mock_session):
        """Test get_top_channels_by_subscribers method."""
        mock_channels = [MagicMock(spec=ChannelDB), MagicMock(spec=ChannelDB)]

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_top_channels_by_subscribers(
            mock_session, limit=10
        )

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_language(self, repository, mock_session):
        """Test find_by_language method."""
        mock_channels = [MagicMock(spec=ChannelDB), MagicMock(spec=ChannelDB)]

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_language(mock_session, "en")

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_country(self, repository, mock_session):
        """Test find_by_country method."""
        mock_channels = [MagicMock(spec=ChannelDB), MagicMock(spec=ChannelDB)]

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_channels
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_country(mock_session, "US")

        assert result == mock_channels
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_with_videos(self, repository, mock_session):
        """Test get_with_videos method."""
        mock_channel = MagicMock(spec=ChannelDB)
        mock_channel.channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_channel
        mock_session.execute.return_value = mock_result

        result = await repository.get_with_videos(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )

        assert result == mock_channel
        mock_session.execute.assert_called_once()


class TestChannelRepositoryEdgeCases:
    """Test edge cases for channel repository."""

    @pytest.fixture
    def repository(self):
        """Create repository instance."""
        return ChannelRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_find_by_title_empty_query(self, repository, mock_session):
        """Test find_by_title with empty query."""
        # Mock empty result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_title(mock_session, "")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_channel_statistics_empty(self, repository, mock_session):
        """Test get_channel_statistics with no results."""
        from chronovista.models.channel import ChannelStatistics

        # Mock empty result
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_channel_statistics(mock_session)

        assert isinstance(result, ChannelStatistics)
        assert result.total_channels == 0

    @pytest.mark.asyncio
    async def test_exists_by_channel_id(self, repository, mock_session):
        """Test exists_by_channel_id method."""
        # Mock the query result
        mock_result = MagicMock()
        mock_result.first.return_value = ("UCuAXFkgsw1L7xaCfnd5JJOw",)  # Channel exists
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_channel_id(
            mock_session, "UCuAXFkgsw1L7xaCfnd5JJOw"
        )

        assert result is True
        mock_session.execute.assert_called_once()
