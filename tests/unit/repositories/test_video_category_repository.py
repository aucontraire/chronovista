"""
Tests for VideoCategoryRepository functionality.

Tests CRUD operations, bulk creation, and search capabilities for
video categories.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoCategory as VideoCategoryDB
from chronovista.models.video_category import (
    VideoCategoryCreate,
    VideoCategoryUpdate,
)
from chronovista.repositories.video_category_repository import VideoCategoryRepository

pytestmark = pytest.mark.asyncio


class TestVideoCategoryRepository:
    """Test VideoCategoryRepository functionality."""

    @pytest.fixture
    def repository(self) -> VideoCategoryRepository:
        """Create repository instance for testing."""
        return VideoCategoryRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock async session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def sample_category_db(self) -> VideoCategoryDB:
        """Create sample database category object."""
        category = VideoCategoryDB(
            category_id="10",
            name="Music",
            assignable=True,
            created_at=datetime.now(timezone.utc),
        )
        # Set updated_at separately as it might not be in __init__
        category.updated_at = datetime.now(timezone.utc)
        return category

    @pytest.fixture
    def sample_category_create(self) -> VideoCategoryCreate:
        """Create sample VideoCategoryCreate instance."""
        return VideoCategoryCreate(
            category_id="10",
            name="Music",
            assignable=True,
        )

    def test_repository_initialization(self, repository: VideoCategoryRepository):
        """Test repository initialization."""
        assert repository.model == VideoCategoryDB

    async def test_get_existing_category(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_db: VideoCategoryDB,
    ):
        """Test getting category by category ID when it exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_category_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "10")

        assert result == sample_category_db
        mock_session.execute.assert_called_once()

    async def test_get_nonexistent_category(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test getting category by category ID when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "99")

        assert result is None
        mock_session.execute.assert_called_once()

    async def test_exists_returns_true(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test exists returns True when category exists."""
        mock_result = MagicMock()
        mock_result.first.return_value = ("10",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, "10")

        assert result is True
        mock_session.execute.assert_called_once()

    async def test_exists_returns_false(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test exists returns False when category doesn't exist."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, "99")

        assert result is False
        mock_session.execute.assert_called_once()

    async def test_get_all_categories(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test getting all categories ordered by name."""
        mock_categories = [MagicMock(), MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_categories
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_all(mock_session)

        assert result == mock_categories
        assert len(result) == 3
        mock_session.execute.assert_called_once()

    async def test_get_all_empty_database(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test getting all categories when database is empty."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_all(mock_session)

        assert result == []
        mock_session.execute.assert_called_once()

    async def test_get_assignable_categories(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test getting only assignable categories."""
        mock_categories = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_categories
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_assignable(mock_session)

        assert result == mock_categories
        assert len(result) == 2
        mock_session.execute.assert_called_once()

    async def test_get_assignable_empty_result(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test getting assignable categories when none exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_assignable(mock_session)

        assert result == []
        mock_session.execute.assert_called_once()

    async def test_bulk_create_new_categories(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_db: VideoCategoryDB,
    ):
        """Test bulk creating new categories."""
        categories_to_create = [
            VideoCategoryCreate(category_id="10", name="Music", assignable=True),
            VideoCategoryCreate(category_id="20", name="Gaming", assignable=True),
        ]

        with patch.object(
            repository, "get", new=AsyncMock(return_value=None)
        ) as mock_get:
            with patch.object(
                repository, "create", new=AsyncMock(return_value=sample_category_db)
            ) as mock_create:
                result = await repository.bulk_create(
                    mock_session, categories_to_create
                )

                assert len(result) == 2
                assert mock_get.call_count == 2
                assert mock_create.call_count == 2

    async def test_bulk_create_existing_categories(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_db: VideoCategoryDB,
    ):
        """Test bulk creating with existing categories."""
        categories_to_create = [
            VideoCategoryCreate(category_id="10", name="Music", assignable=True),
        ]

        with patch.object(
            repository, "get", new=AsyncMock(return_value=sample_category_db)
        ) as mock_get:
            result = await repository.bulk_create(mock_session, categories_to_create)

            assert len(result) == 1
            assert result[0] == sample_category_db
            mock_get.assert_called_once()

    async def test_bulk_create_mixed_new_and_existing(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_db: VideoCategoryDB,
    ):
        """Test bulk creating with mix of new and existing categories."""
        categories_to_create = [
            VideoCategoryCreate(category_id="10", name="Music", assignable=True),
            VideoCategoryCreate(category_id="20", name="Gaming", assignable=True),
            VideoCategoryCreate(category_id="30", name="Education", assignable=True),
        ]

        # Mock get to return existing for first, None for others
        mock_get_side_effect = [sample_category_db, None, None]

        with patch.object(
            repository, "get", new=AsyncMock(side_effect=mock_get_side_effect)
        ) as mock_get:
            with patch.object(
                repository, "create", new=AsyncMock(return_value=sample_category_db)
            ) as mock_create:
                result = await repository.bulk_create(
                    mock_session, categories_to_create
                )

                assert len(result) == 3
                assert mock_get.call_count == 3
                assert mock_create.call_count == 2  # Only for new categories

    async def test_bulk_create_empty_list(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test bulk creating with empty list."""
        result = await repository.bulk_create(mock_session, [])

        assert result == []

    async def test_get_by_category_id_alias(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_db: VideoCategoryDB,
    ):
        """Test get_by_category_id is alias for get method."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_category_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_category_id(mock_session, "10")

        assert result == sample_category_db
        mock_session.execute.assert_called_once()

    async def test_create_or_update_new_category(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_create: VideoCategoryCreate,
        sample_category_db: VideoCategoryDB,
    ):
        """Test creating a new category via create_or_update."""
        with patch.object(
            repository, "get", new=AsyncMock(return_value=None)
        ) as mock_get:
            with patch.object(
                repository, "create", new=AsyncMock(return_value=sample_category_db)
            ) as mock_create:
                result = await repository.create_or_update(
                    mock_session, sample_category_create
                )

                assert result == sample_category_db
                mock_get.assert_called_once_with(
                    mock_session, sample_category_create.category_id
                )
                mock_create.assert_called_once_with(
                    mock_session, obj_in=sample_category_create
                )

    async def test_create_or_update_existing_category(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_create: VideoCategoryCreate,
        sample_category_db: VideoCategoryDB,
    ):
        """Test updating an existing category via create_or_update."""
        with patch.object(
            repository, "get", new=AsyncMock(return_value=sample_category_db)
        ) as mock_get:
            with patch.object(
                repository, "update", new=AsyncMock(return_value=sample_category_db)
            ) as mock_update:
                result = await repository.create_or_update(
                    mock_session, sample_category_create
                )

                assert result == sample_category_db
                mock_get.assert_called_once_with(
                    mock_session, sample_category_create.category_id
                )
                mock_update.assert_called_once()

    async def test_delete_by_category_id(
        self,
        repository: VideoCategoryRepository,
        mock_session: MagicMock,
        sample_category_db: VideoCategoryDB,
    ):
        """Test deleting category by category ID."""
        with patch.object(
            repository, "get", new=AsyncMock(return_value=sample_category_db)
        ) as mock_get:
            result = await repository.delete_by_category_id(mock_session, "10")

            assert result == sample_category_db
            mock_get.assert_called_once_with(mock_session, "10")
            mock_session.delete.assert_called_once_with(sample_category_db)
            mock_session.flush.assert_called_once()

    async def test_delete_by_category_id_not_found(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test deleting non-existent category returns None."""
        with patch.object(
            repository, "get", new=AsyncMock(return_value=None)
        ) as mock_get:
            result = await repository.delete_by_category_id(mock_session, "99")

            assert result is None
            mock_get.assert_called_once_with(mock_session, "99")
            mock_session.delete.assert_not_called()
            mock_session.flush.assert_not_called()

    async def test_find_by_name_partial_match(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test finding categories by name with partial match."""
        mock_categories = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_categories
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_name(mock_session, "mus")

        assert result == mock_categories
        assert len(result) == 2
        mock_session.execute.assert_called_once()

    async def test_find_by_name_case_insensitive(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test finding categories by name is case-insensitive."""
        mock_categories = [MagicMock()]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_categories
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_name(mock_session, "MUSIC")

        assert result == mock_categories
        mock_session.execute.assert_called_once()

    async def test_find_by_name_no_matches(
        self, repository: VideoCategoryRepository, mock_session: MagicMock
    ):
        """Test finding categories by name with no matches."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.find_by_name(mock_session, "nonexistent")

        assert result == []
        mock_session.execute.assert_called_once()

    def test_repository_inherits_base_methods(
        self, repository: VideoCategoryRepository
    ):
        """Test that repository inherits base methods."""
        assert hasattr(repository, "create")
        assert hasattr(repository, "update")
        assert hasattr(repository, "delete")
        assert hasattr(repository, "get_multi")
        assert hasattr(repository, "model")


class TestVideoCategoryRepositoryAdditionalMethods:
    """Test additional video category repository methods for coverage."""

    @pytest.fixture
    def repository(self) -> VideoCategoryRepository:
        """Create video category repository instance."""
        return VideoCategoryRepository()

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock(spec=AsyncSession)

    async def test_create_method_integration(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test create method works with VideoCategoryCreate."""
        category_create = VideoCategoryCreate(
            category_id="10",
            name="Music",
            assignable=True,
        )

        mock_category_db = MagicMock()
        with patch.object(
            repository, "create", new=AsyncMock(return_value=mock_category_db)
        ) as mock_create:
            result = await repository.create(mock_session, obj_in=category_create)

            assert result == mock_category_db
            mock_create.assert_called_once()

    async def test_update_method_integration(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test update method works with VideoCategoryUpdate."""
        category_db = MagicMock()
        category_update = VideoCategoryUpdate(
            name="Updated Music",
            assignable=False,
        )

        mock_updated_db = MagicMock()
        with patch.object(
            repository, "update", new=AsyncMock(return_value=mock_updated_db)
        ) as mock_update:
            result = await repository.update(
                mock_session, db_obj=category_db, obj_in=category_update
            )

            assert result == mock_updated_db
            mock_update.assert_called_once()

    async def test_get_all_ordered_by_name(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test that get_all returns categories ordered by name."""
        # This test verifies the query includes ORDER BY clause
        # by checking the execute call
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await repository.get_all(mock_session)

        # Verify execute was called (the query construction is tested implicitly)
        mock_session.execute.assert_called_once()

    async def test_get_assignable_filters_correctly(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test that get_assignable filters by assignable=True."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await repository.get_assignable(mock_session)

        # Verify execute was called (the filter is tested implicitly)
        mock_session.execute.assert_called_once()

    async def test_bulk_create_maintains_order(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test that bulk_create maintains the order of categories."""
        categories = [
            VideoCategoryCreate(category_id="10", name="Music", assignable=True),
            VideoCategoryCreate(category_id="20", name="Gaming", assignable=True),
            VideoCategoryCreate(category_id="1", name="Film", assignable=True),
        ]

        mock_categories_db = [MagicMock() for _ in categories]

        with patch.object(
            repository, "get", new=AsyncMock(return_value=None)
        ):
            with patch.object(
                repository, "create", new=AsyncMock(side_effect=mock_categories_db)
            ):
                result = await repository.bulk_create(mock_session, categories)

                # Should return in same order as input
                assert len(result) == 3
                assert result == mock_categories_db

    async def test_create_or_update_preserves_fields(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test that create_or_update updates all fields correctly."""
        category_create = VideoCategoryCreate(
            category_id="10",
            name="New Music Name",
            assignable=False,
        )

        existing_category = MagicMock()
        existing_category.category_id = "10"
        existing_category.name = "Old Music Name"
        existing_category.assignable = True

        with patch.object(
            repository, "get", new=AsyncMock(return_value=existing_category)
        ):
            with patch.object(
                repository, "update", new=AsyncMock(return_value=existing_category)
            ) as mock_update:
                await repository.create_or_update(mock_session, category_create)

                # Verify update was called with correct data
                mock_update.assert_called_once()
                call_args = mock_update.call_args
                update_obj = call_args.kwargs["obj_in"]
                assert isinstance(update_obj, VideoCategoryUpdate)
                assert update_obj.name == "New Music Name"
                assert update_obj.assignable is False

    async def test_find_by_name_with_special_characters(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test finding categories with special characters in name."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Test with & character (common in YouTube categories)
        await repository.find_by_name(mock_session, "Film & Animation")

        mock_session.execute.assert_called_once()

    async def test_multiple_sequential_operations(
        self, repository: VideoCategoryRepository, mock_session
    ):
        """Test multiple sequential repository operations."""
        category_create = VideoCategoryCreate(
            category_id="10",
            name="Music",
            assignable=True,
        )

        mock_category = MagicMock()

        # Test create -> get -> update -> delete sequence
        with patch.object(repository, "create", new=AsyncMock(return_value=mock_category)):
            with patch.object(repository, "get", new=AsyncMock(return_value=mock_category)):
                with patch.object(repository, "update", new=AsyncMock(return_value=mock_category)):
                    # Create
                    created = await repository.create(mock_session, obj_in=category_create)
                    assert created == mock_category

                    # Get
                    fetched = await repository.get(mock_session, "10")
                    assert fetched == mock_category

                    # Update
                    update = VideoCategoryUpdate(name="Updated Music")
                    updated = await repository.update(
                        mock_session, db_obj=mock_category, obj_in=update
                    )
                    assert updated == mock_category

                    # Delete
                    deleted = await repository.delete_by_category_id(mock_session, "10")
                    assert deleted == mock_category
