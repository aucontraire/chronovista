"""
Comprehensive coverage tests for channel_repository.py search_channels method.

Targets uncovered lines 240, 244-248, 252-256, 260, 263, 267, 270, 274-287.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.channel import ChannelSearchFilters
from chronovista.models.enums import LanguageCode
from chronovista.repositories.channel_repository import ChannelRepository

pytestmark = pytest.mark.asyncio


class TestChannelRepositorySearchCoverage:
    """Test channel repository search_channels method comprehensively."""

    @pytest.fixture
    def repository(self):
        """Create repository instance."""
        return ChannelRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_search_channels_description_query(self, repository, mock_session):
        """Test search_channels with description_query filter (line 240)."""
        filters = ChannelSearchFilters(description_query="gaming tutorials")

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_language_codes(self, repository, mock_session):
        """Test search_channels with language_codes filter (lines 244-248)."""
        filters = ChannelSearchFilters(
            language_codes=[
                LanguageCode.ENGLISH,
                LanguageCode.SPANISH,
                LanguageCode.FRENCH,
            ]
        )

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_countries(self, repository, mock_session):
        """Test search_channels with countries filter (lines 252-256)."""
        filters = ChannelSearchFilters(countries=["US", "CA", "GB"])

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_min_subscriber_count(self, repository, mock_session):
        """Test search_channels with min_subscriber_count filter (line 260)."""
        filters = ChannelSearchFilters(min_subscriber_count=1000)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_max_subscriber_count(self, repository, mock_session):
        """Test search_channels with max_subscriber_count filter (line 263)."""
        filters = ChannelSearchFilters(max_subscriber_count=10000)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_min_video_count(self, repository, mock_session):
        """Test search_channels with min_video_count filter (line 267)."""
        filters = ChannelSearchFilters(min_video_count=50)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_max_video_count(self, repository, mock_session):
        """Test search_channels with max_video_count filter (line 270)."""
        filters = ChannelSearchFilters(max_video_count=200)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_has_keywords_true(self, repository, mock_session):
        """Test search_channels with has_keywords=True filter (lines 274-280)."""
        filters = ChannelSearchFilters(has_keywords=True)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_has_keywords_false(self, repository, mock_session):
        """Test search_channels with has_keywords=False filter (lines 281-287)."""
        filters = ChannelSearchFilters(has_keywords=False)

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_channels_comprehensive_filters(
        self, repository, mock_session
    ):
        """Test search_channels with multiple filters combined."""
        filters = ChannelSearchFilters(
            title_query="tech",
            description_query="tutorials",
            language_codes=[LanguageCode.ENGLISH],
            countries=["US"],
            min_subscriber_count=1000,
            max_subscriber_count=50000,
            min_video_count=10,
            max_video_count=500,
            has_keywords=True,
        )

        # Mock the query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.search_channels(mock_session, filters)

        assert result == []
        mock_session.execute.assert_called_once()
