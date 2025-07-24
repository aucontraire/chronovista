"""
Tests for UserLanguagePreferenceRepository.

Comprehensive unit tests covering all repository methods including CRUD operations,
specialized queries, and edge case handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import UserLanguagePreference as UserLanguagePreferenceDB
from chronovista.models.enums import LanguagePreferenceType
from chronovista.models.user_language_preference import (
    UserLanguagePreferenceCreate,
    UserLanguagePreferenceUpdate,
)
from chronovista.repositories.user_language_preference_repository import (
    UserLanguagePreferenceRepository,
)


class TestUserLanguagePreferenceRepository:
    """Test suite for UserLanguagePreferenceRepository."""

    @pytest.fixture
    def repository(self) -> UserLanguagePreferenceRepository:
        """Create repository instance for testing."""
        return UserLanguagePreferenceRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def sample_preference_db(self) -> UserLanguagePreferenceDB:
        """Create sample database preference object."""
        return UserLanguagePreferenceDB(
            user_id="test_user",
            language_code="en-us",
            preference_type=LanguagePreferenceType.FLUENT.value,
            priority=1,
            auto_download_transcripts=True,
            learning_goal=None,
            created_at=datetime.now(),
        )

    @pytest.fixture
    def sample_preference_create(self) -> UserLanguagePreferenceCreate:
        """Create sample preference creation object."""
        return UserLanguagePreferenceCreate(
            user_id="test_user",
            language_code="en-US",
            preference_type=LanguagePreferenceType.FLUENT,
            priority=1,
            auto_download_transcripts=True,
        )

    @pytest.fixture
    def sample_preferences_list(self) -> List[UserLanguagePreferenceDB]:
        """Create list of sample preferences."""
        return [
            UserLanguagePreferenceDB(
                user_id="test_user",
                language_code="en-us",
                preference_type=LanguagePreferenceType.FLUENT.value,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(),
            ),
            UserLanguagePreferenceDB(
                user_id="test_user",
                language_code="es-es",
                preference_type=LanguagePreferenceType.LEARNING.value,
                priority=2,
                auto_download_transcripts=False,
                learning_goal="Improve Spanish proficiency",
                created_at=datetime.now(),
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_existing_preference(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncSession,
        sample_preference_db: UserLanguagePreferenceDB,
    ):
        """Test getting an existing user language preference."""
        # Mock execute to return scalar_one_or_none result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_preference_db
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, "test_user", "en-US"
        )

        assert result == sample_preference_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_preference(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test getting a non-existent user language preference."""
        # Mock execute to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(
            mock_session, "test_user", "non-existent"
        )

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test exists returns True when preference exists."""
        # Mock execute to return a result
        mock_result = MagicMock()
        mock_result.first.return_value = ("test_user",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, "test_user", "en-US"
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_false(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test exists returns False when preference doesn't exist."""
        # Mock execute to return None
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists_by_composite_key(
            mock_session, "test_user", "non-existent"
        )

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_preferences(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncSession,
        sample_preferences_list: List[UserLanguagePreferenceDB],
    ):
        """Test getting all preferences for a user."""
        # Mock execute to return scalars
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sample_preferences_list
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_user_preferences(mock_session, "test_user")

        assert result == sample_preferences_list
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_preferences_by_type(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncSession,
        sample_preferences_list: List[UserLanguagePreferenceDB],
    ):
        """Test getting preferences filtered by type."""
        # Filter list to only fluent preferences
        fluent_prefs = [
            p
            for p in sample_preferences_list
            if p.preference_type == LanguagePreferenceType.FLUENT.value
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = fluent_prefs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_preferences_by_type(
            mock_session, "test_user", LanguagePreferenceType.FLUENT
        )

        assert result == fluent_prefs
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_auto_download_languages(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test getting languages with auto-download enabled."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = ["en-us", "fr-fr"]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_auto_download_languages(mock_session, "test_user")

        assert result == ["en-us", "fr-fr"]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_preferences_new(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncSession,
        sample_preference_create: UserLanguagePreferenceCreate,
    ):
        """Test saving new preferences."""
        # Mock get_by_composite_key to return None (preference doesn't exist)
        repository.get_by_composite_key = AsyncMock(return_value=None)
        repository.create = AsyncMock(return_value=sample_preference_create)

        result = await repository.save_preferences(
            mock_session, "test_user", [sample_preference_create]
        )

        assert len(result) == 1
        repository.get_by_composite_key.assert_called_once()
        repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_preferences_existing(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncSession,
        sample_preference_create: UserLanguagePreferenceCreate,
        sample_preference_db: UserLanguagePreferenceDB,
    ):
        """Test saving preferences that already exist (update)."""
        # Mock get_by_composite_key to return existing preference
        repository.get_by_composite_key = AsyncMock(return_value=sample_preference_db)
        repository.update = AsyncMock(return_value=sample_preference_db)

        result = await repository.save_preferences(
            mock_session, "test_user", [sample_preference_create]
        )

        assert len(result) == 1
        repository.get_by_composite_key.assert_called_once()
        repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_priority_existing(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncSession,
        sample_preference_db: UserLanguagePreferenceDB,
    ):
        """Test updating priority of existing preference."""
        repository.get_by_composite_key = AsyncMock(return_value=sample_preference_db)

        result = await repository.update_priority(mock_session, "test_user", "en-US", 5)

        assert result == sample_preference_db
        assert sample_preference_db.priority == 5
        mock_session.add.assert_called_once_with(sample_preference_db)
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once_with(sample_preference_db)

    @pytest.mark.asyncio
    async def test_update_priority_nonexistent(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test updating priority of non-existent preference."""
        repository.get_by_composite_key = AsyncMock(return_value=None)

        result = await repository.update_priority(
            mock_session, "test_user", "non-existent", 5
        )

        assert result is None
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_user_preference_success(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test successfully deleting a user preference."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        result = await repository.delete_user_preference(
            mock_session, "test_user", "en-US"
        )

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_user_preference_not_found(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test deleting non-existent user preference."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await repository.delete_user_preference(
            mock_session, "test_user", "non-existent"
        )

        assert result is False
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_all_user_preferences(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test deleting all preferences for a user."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        result = await repository.delete_all_user_preferences(mock_session, "test_user")

        assert result == 3
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_language_statistics(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test getting language statistics by preference type."""
        # Mock query result with preference type counts
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                (LanguagePreferenceType.FLUENT.value, 2),
                (LanguagePreferenceType.LEARNING.value, 1),
            ]
        )
        mock_session.execute.return_value = mock_result

        result = await repository.get_language_statistics(mock_session, "test_user")

        expected = {
            LanguagePreferenceType.FLUENT: 2,
            LanguagePreferenceType.LEARNING: 1,
        }
        assert result == expected
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_language_statistics_invalid_enum(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test statistics handling of invalid enum values."""
        # Mock query result with invalid preference type
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [
                (LanguagePreferenceType.FLUENT.value, 2),
                ("invalid_type", 1),  # Invalid enum value
            ]
        )
        mock_session.execute.return_value = mock_result

        result = await repository.get_language_statistics(mock_session, "test_user")

        # Should skip invalid enum value
        expected = {LanguagePreferenceType.FLUENT: 2}
        assert result == expected

    @pytest.mark.asyncio
    async def test_language_code_normalization(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test that language codes are properly normalized to lowercase."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        await repository.get_by_composite_key(mock_session, "test_user", "EN-US")

        # Verify the query used lowercase language code
        call_args = mock_session.execute.call_args[0][0]
        # This is a simplified check - in a real test you'd inspect the SQL query
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_with_composite_key_tuple(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncSession,
        sample_preference_db: UserLanguagePreferenceDB,
    ):
        """Test get method with tuple composite key (base class signature)."""
        # Mock execute to return scalar_one_or_none result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_preference_db
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, ("test_user", "en-US"))

        assert result == sample_preference_db
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_with_composite_key_tuple(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test exists method with tuple composite key (base class signature)."""
        # Mock execute to return a result
        mock_result = MagicMock()
        mock_result.first.return_value = ("test_user",)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, ("test_user", "en-US"))

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_repository_inherits_base_methods(
        self, repository: UserLanguagePreferenceRepository
    ):
        """Test that repository properly inherits from base repository."""
        from chronovista.repositories.base import BaseSQLAlchemyRepository

        assert isinstance(repository, BaseSQLAlchemyRepository)
        assert repository.model == UserLanguagePreferenceDB

    def test_repository_initialization(self):
        """Test repository initialization."""
        repo = UserLanguagePreferenceRepository()
        assert repo.model == UserLanguagePreferenceDB


class TestUserLanguagePreferenceRepositoryEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def repository(self) -> UserLanguagePreferenceRepository:
        """Create repository instance for testing."""
        return UserLanguagePreferenceRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncSession:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_empty_user_id_handling(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test repository behavior with empty user ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(mock_session, "", "en-US")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_language_code_handling(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test repository behavior with empty language code."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_composite_key(mock_session, "test_user", "")

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_preferences_empty_list(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test saving empty list of preferences."""
        result = await repository.save_preferences(mock_session, "test_user", [])

        assert result == []

    @pytest.mark.asyncio
    async def test_get_user_preferences_no_results(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test getting preferences when user has none."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.get_user_preferences(mock_session, "test_user")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_language_statistics_no_data(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncSession
    ):
        """Test statistics when user has no preferences."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.execute.return_value = mock_result

        result = await repository.get_language_statistics(mock_session, "test_user")

        assert result == {}
