"""
Tests for BaseSQLAlchemyRepository functionality.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Video as VideoDB
from chronovista.models.video import VideoCreate, VideoUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository
from tests.factories.video_factory import VideoCreateFactory, create_video_update

pytestmark = pytest.mark.asyncio


class TestBaseSQLAlchemyRepository:
    """Test BaseSQLAlchemyRepository functionality."""

    class MockRepository(BaseSQLAlchemyRepository[VideoDB, VideoCreate, VideoUpdate]):
        """Mock repository for testing."""

        def __init__(self) -> None:
            super().__init__(VideoDB)

    @pytest.fixture
    def repository(self) -> "TestBaseSQLAlchemyRepository.MockRepository":
        """Create repository instance for testing."""
        return self.MockRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_video_create(self) -> VideoCreate:
        """Create mock VideoCreate object."""
        from datetime import datetime, timezone

        return VideoCreate(
            video_id="dQw4w9WgXcQ",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Test Video",
            description="Test description",
            upload_date=datetime.now(timezone.utc),
            duration=120,
        )

    @pytest.fixture
    def mock_video_db(self) -> VideoDB:
        """Create mock VideoDB object."""
        video = MagicMock(spec=VideoDB)
        video.video_id = "dQw4w9WgXcQ"
        video.title = "Test Video"
        return video

    def test_repository_initialization(self, repository):
        """Test repository initialization."""
        assert repository.model == VideoDB

    @pytest.mark.asyncio
    async def test_create_success(
        self,
        repository,
        mock_session: AsyncMock,
        mock_video_create: VideoCreate,
        mock_video_db: VideoDB,
    ):
        """Test successful creation."""
        # Mock the model constructor
        repository.model = MagicMock(return_value=mock_video_db)

        result = await repository.create(mock_session, obj_in=mock_video_create)

        assert result == mock_video_db
        mock_session.add.assert_called_once_with(mock_video_db)
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_video_db)

    @pytest.mark.asyncio
    async def test_create_with_dict(
        self, repository, mock_session: AsyncMock, mock_video_db: VideoDB
    ):
        """Test creation with dictionary input."""
        obj_dict = {
            "video_id": "dQw4w9WgXcQ",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "title": "Test Video",
        }

        obj = VideoCreateFactory.build(**obj_dict)

        # Mock the model constructor
        repository.model = MagicMock(return_value=mock_video_db)

        result = await repository.create(mock_session, obj_in=obj)

        assert result == mock_video_db
        mock_session.add.assert_called_once_with(mock_video_db)

    @pytest.mark.asyncio
    async def test_update_with_pydantic_model(
        self, repository, mock_session: AsyncMock, mock_video_db: VideoDB
    ):
        """Test update with Pydantic model."""
        update_data = create_video_update(title="Updated Title")

        result = await repository.update(
            mock_session, db_obj=mock_video_db, obj_in=update_data
        )

        assert result == mock_video_db
        assert mock_video_db.title == "Updated Title"
        mock_session.add.assert_called_once_with(mock_video_db)
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_video_db)

    @pytest.mark.asyncio
    async def test_update_with_dict(
        self, repository, mock_session: AsyncMock, mock_video_db: VideoDB
    ):
        """Test update with dictionary."""
        update_dict = {"title": "Updated Title", "description": "Updated description"}

        result = await repository.update(
            mock_session, db_obj=mock_video_db, obj_in=update_dict
        )

        assert result == mock_video_db
        mock_session.add.assert_called_once_with(mock_video_db)

    @pytest.mark.asyncio
    async def test_delete_success(
        self, repository, mock_session: AsyncMock, mock_video_db: VideoDB
    ):
        """Test successful deletion."""
        # Mock the get method to return the mock object
        repository.get = AsyncMock(return_value=mock_video_db)

        result = await repository.delete(mock_session, id="test_id")

        assert result == mock_video_db
        repository.get.assert_called_once_with(mock_session, "test_id")
        mock_session.delete.assert_called_once_with(mock_video_db)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_multi_default_params(self, repository, mock_session: AsyncMock):
        """Test get_multi with default parameters."""
        mock_videos = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_videos
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_multi(mock_session)

        assert result == mock_videos
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_multi_with_params(self, repository, mock_session: AsyncMock):
        """Test get_multi with custom parameters."""
        mock_videos = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_videos
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_multi(mock_session, skip=10, limit=50)

        assert result == mock_videos
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_multi_empty_result(self, repository, mock_session: AsyncMock):
        """Test get_multi with empty result."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_multi(mock_session)

        assert result == []
        mock_session.execute.assert_called_once()

    def test_model_property(self, repository):
        """Test model property access."""
        assert repository.model == VideoDB

    @pytest.mark.asyncio
    async def test_create_error_handling(self, repository, mock_session: AsyncMock):
        """Test create method error handling."""
        from datetime import datetime, timezone

        # Use valid Video data but mock session to raise exception during add
        valid_obj = VideoCreateFactory.build(
            video_id="dQw4w9WgXcQ",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Test Video",
            upload_date=datetime.now(timezone.utc),
            duration=120,
        )

        # Mock session to raise exception
        mock_session.add.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await repository.create(mock_session, obj_in=valid_obj)

    @pytest.mark.asyncio
    async def test_update_error_handling(
        self, repository, mock_session: AsyncMock, mock_video_db: VideoDB
    ):
        """Test update method error handling."""
        # Mock session to raise exception
        mock_session.add.side_effect = Exception("Database error")

        # Use valid update data
        update_data = {"title": "Updated Title"}

        with pytest.raises(Exception, match="Database error"):
            await repository.update(
                mock_session, db_obj=mock_video_db, obj_in=update_data
            )

    @pytest.mark.asyncio
    async def test_delete_error_handling(
        self, repository, mock_session: AsyncMock, mock_video_db: VideoDB
    ):
        """Test delete method error handling."""
        # Mock session to raise exception
        mock_session.delete.side_effect = Exception("Database error")

        # Mock get method to return the object first
        repository.get = AsyncMock(return_value=mock_video_db)

        with pytest.raises(Exception, match="Database error"):
            await repository.delete(mock_session, id="test_id")


class TestBaseRepositoryEdgeCases:
    """Test edge cases for base repository."""

    class MockRepository(BaseSQLAlchemyRepository[VideoDB, VideoCreate, VideoUpdate]):
        """Mock repository for testing."""

        def __init__(self) -> None:
            super().__init__(VideoDB)

    @pytest.fixture
    def repository(self) -> "TestBaseRepositoryEdgeCases.MockRepository":
        """Create repository instance for testing."""
        return self.MockRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_update_with_none_values(self, repository, mock_session: AsyncMock):
        """Test update with None values."""
        mock_video_db = MagicMock()
        update_data = create_video_update(title=None, description="Updated")

        result = await repository.update(
            mock_session, db_obj=mock_video_db, obj_in=update_data
        )

        assert result == mock_video_db
        # Should set description but not title since it's None
        assert mock_video_db.description == "Updated"
        # Title should not be set to None since it was excluded
        mock_session.add.assert_called_once_with(mock_video_db)

    @pytest.mark.asyncio
    async def test_create_with_minimal_data(self, repository, mock_session: AsyncMock):
        """Test create with minimal required data."""
        mock_video_db = MagicMock()
        repository.model = MagicMock(return_value=mock_video_db)

        # Create minimal valid VideoCreate object
        minimal_obj = VideoCreateFactory.build()

        result = await repository.create(mock_session, obj_in=minimal_obj)

        assert result == mock_video_db

    @pytest.mark.asyncio
    async def test_update_with_empty_dict(self, repository, mock_session: AsyncMock):
        """Test update with empty dictionary."""
        mock_video_db = MagicMock()

        result = await repository.update(mock_session, db_obj=mock_video_db, obj_in={})

        assert result == mock_video_db
        mock_session.add.assert_called_once_with(mock_video_db)

    @pytest.mark.asyncio
    async def test_session_operations_order(self, repository, mock_session: AsyncMock):
        """Test that session operations are called in correct order."""
        from datetime import datetime, timezone

        mock_video_create = VideoCreate(
            video_id="dQw4w9WgXcQ",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Test",
            upload_date=datetime.now(timezone.utc),
            duration=120,
        )
        mock_video_db = MagicMock()
        repository.model = MagicMock(return_value=mock_video_db)

        await repository.create(mock_session, obj_in=mock_video_create)

        # Verify call order
        call_order = [call[0] for call in mock_session.method_calls]
        expected_methods = ["add", "flush", "refresh"]

        for method in expected_methods:
            assert method in call_order
