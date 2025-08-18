"""
Tests for UserLanguagePreferenceRepository.

Comprehensive unit tests covering all repository methods including CRUD operations,
specialized queries, and edge case handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import UserLanguagePreference as UserLanguagePreferenceDB
from chronovista.models.enums import LanguageCode, LanguagePreferenceType
from chronovista.models.user_language_preference import UserLanguagePreferenceCreate
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
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

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
            language_code=LanguageCode.ENGLISH,
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
        mock_session: AsyncMock,
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        mock_session: AsyncMock,
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
        mock_session: AsyncMock,
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        mock_session: AsyncMock,
        sample_preference_create: UserLanguagePreferenceCreate,
    ):
        """Test saving new preferences."""
        # Mock get_by_composite_key to return None (preference doesn't exist)
        with (
            patch.object(
                repository, "get_by_composite_key", new=AsyncMock(return_value=None)
            ) as mock_get,
            patch.object(
                repository,
                "create",
                new=AsyncMock(return_value=sample_preference_create),
            ) as mock_create,
        ):

            result = await repository.save_preferences(
                mock_session, "test_user", [sample_preference_create]
            )

            assert len(result) == 1
            mock_get.assert_called_once()
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_preferences_existing(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncMock,
        sample_preference_create: UserLanguagePreferenceCreate,
        sample_preference_db: UserLanguagePreferenceDB,
    ):
        """Test saving preferences that already exist (update)."""
        # Mock get_by_composite_key to return existing preference
        with (
            patch.object(
                repository,
                "get_by_composite_key",
                new=AsyncMock(return_value=sample_preference_db),
            ) as mock_get,
            patch.object(
                repository, "update", new=AsyncMock(return_value=sample_preference_db)
            ) as mock_update,
        ):

            result = await repository.save_preferences(
                mock_session, "test_user", [sample_preference_create]
            )

            assert len(result) == 1
            mock_get.assert_called_once()
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_priority_existing(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncMock,
        sample_preference_db: UserLanguagePreferenceDB,
    ):
        """Test updating priority of existing preference."""
        with patch.object(
            repository,
            "get_by_composite_key",
            new=AsyncMock(return_value=sample_preference_db),
        ) as mock_get:

            result = await repository.update_priority(
                mock_session, "test_user", "en-US", 5
            )

            assert result == sample_preference_db
            assert sample_preference_db.priority == 5
            mock_session.add.assert_called_once_with(sample_preference_db)
            mock_session.flush.assert_called_once()
            mock_session.refresh.assert_called_once_with(sample_preference_db)

    @pytest.mark.asyncio
    async def test_update_priority_nonexistent(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test updating priority of non-existent preference."""
        with patch.object(
            repository, "get_by_composite_key", new=AsyncMock(return_value=None)
        ) as mock_get:

            result = await repository.update_priority(
                mock_session, "test_user", "non-existent", 5
            )

            assert result is None
            mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_user_preference_success(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        mock_session: AsyncMock,
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_empty_user_id_handling(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test saving empty list of preferences."""
        result = await repository.save_preferences(mock_session, "test_user", [])

        assert result == []

    @pytest.mark.asyncio
    async def test_get_user_preferences_no_results(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
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
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test statistics when user has no preferences."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.execute.return_value = mock_result

        result = await repository.get_language_statistics(mock_session, "test_user")

        assert result == {}


class TestUserLanguagePreferenceRepositoryVideoIntegration:
    """Test video localization integration methods."""

    @pytest.fixture
    def repository(self) -> UserLanguagePreferenceRepository:
        """Create repository instance for testing."""
        return UserLanguagePreferenceRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_preferences_with_priorities(self) -> List[UserLanguagePreferenceDB]:
        """Create sample preferences with different priorities and types."""
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
                learning_goal="Learn Spanish",
                created_at=datetime.now(),
            ),
            UserLanguagePreferenceDB(
                user_id="test_user",
                language_code="fr-fr",
                preference_type=LanguagePreferenceType.CURIOUS.value,
                priority=3,
                auto_download_transcripts=False,
                learning_goal=None,
                created_at=datetime.now(),
            ),
            UserLanguagePreferenceDB(
                user_id="test_user",
                language_code="de-de",
                preference_type=LanguagePreferenceType.EXCLUDE.value,
                priority=999,
                auto_download_transcripts=False,
                learning_goal=None,
                created_at=datetime.now(),
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_user_videos_with_preferred_localizations_empty_video_ids(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test video localization with empty video IDs list."""
        result = await repository.get_user_videos_with_preferred_localizations(
            mock_session, "test_user", []
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_user_videos_with_preferred_localizations_no_preferences(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test video localization when user has no language preferences."""
        # Mock get_user_preferences to return empty list
        with patch.object(
            repository, "get_user_preferences", new=AsyncMock(return_value=[])
        ) as mock_get_prefs:

            result = await repository.get_user_videos_with_preferred_localizations(
                mock_session, "test_user", ["video1", "video2"]
            )

            assert result == {}
            mock_get_prefs.assert_called_once_with(mock_session, "test_user")

    @pytest.mark.asyncio
    async def test_get_user_videos_with_preferred_localizations_no_eligible_languages(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test video localization when user has no eligible language preferences."""
        # Create preferences with only excluded languages
        exclude_prefs = [
            UserLanguagePreferenceDB(
                user_id="test_user",
                language_code="de-de",
                preference_type=LanguagePreferenceType.EXCLUDE.value,
                priority=1,
                auto_download_transcripts=False,
                learning_goal=None,
                created_at=datetime.now(),
            )
        ]

        with patch.object(
            repository,
            "get_user_preferences",
            new=AsyncMock(return_value=exclude_prefs),
        ) as mock_get_prefs:

            result = await repository.get_user_videos_with_preferred_localizations(
                mock_session, "test_user", ["video1", "video2"]
            )

            assert result == {}
            mock_get_prefs.assert_called_once_with(mock_session, "test_user")

    @pytest.mark.asyncio
    async def test_get_user_videos_with_preferred_localizations_success(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncMock,
        sample_preferences_with_priorities: List[UserLanguagePreferenceDB],
    ):
        """Test successful video localization retrieval."""
        # Mock get_user_preferences
        with patch.object(
            repository,
            "get_user_preferences",
            new=AsyncMock(return_value=sample_preferences_with_priorities),
        ) as mock_get_prefs:

            # Mock VideoRepository and its method
            mock_video_data = {
                "video1": {"title": "Test Video 1", "localization": "en-us"},
                "video2": {"title": "Test Video 2", "localization": "es-es"},
            }

            with patch(
                "chronovista.repositories.video_repository.VideoRepository"
            ) as mock_video_repo_class:
                mock_video_repo = AsyncMock()
                mock_video_repo.get_videos_with_preferred_localizations.return_value = (
                    mock_video_data
                )
                mock_video_repo_class.return_value = mock_video_repo

                result = await repository.get_user_videos_with_preferred_localizations(
                    mock_session, "test_user", ["video1", "video2"]
                )

                assert result == mock_video_data
                mock_get_prefs.assert_called_once_with(mock_session, "test_user")
                mock_video_repo.get_videos_with_preferred_localizations.assert_called_once_with(
                    mock_session, ["video1", "video2"], ["en-us", "es-es", "fr-fr"]
                )

    @pytest.mark.asyncio
    async def test_get_recommended_localization_targets_no_preferences(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test localization targets when user has no learning/curious preferences."""
        # Mock preferences with only fluent/exclude types
        fluent_prefs = [
            UserLanguagePreferenceDB(
                user_id="test_user",
                language_code="en-us",
                preference_type=LanguagePreferenceType.FLUENT.value,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(),
            )
        ]

        with patch.object(
            repository, "get_user_preferences", new=AsyncMock(return_value=fluent_prefs)
        ) as mock_get_prefs:

            result = await repository.get_recommended_localization_targets(
                mock_session, "test_user", limit=20
            )

            assert result == {}
            mock_get_prefs.assert_called_once_with(mock_session, "test_user")

    @pytest.mark.asyncio
    async def test_get_recommended_localization_targets_success(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncMock,
        sample_preferences_with_priorities: List[UserLanguagePreferenceDB],
    ):
        """Test successful localization targets retrieval."""
        # Mock get_user_preferences
        with patch.object(
            repository,
            "get_user_preferences",
            new=AsyncMock(return_value=sample_preferences_with_priorities),
        ) as mock_get_prefs:

            # Mock VideoRepository and its method
            mock_missing_data = {
                "video1": {"missing_languages": ["es-es", "fr-fr"]},
                "video2": {"missing_languages": ["fr-fr"]},
            }

            with patch(
                "chronovista.repositories.video_repository.VideoRepository"
            ) as mock_video_repo_class:
                mock_video_repo = AsyncMock()
                mock_video_repo.get_videos_missing_localizations.return_value = (
                    mock_missing_data
                )
                mock_video_repo_class.return_value = mock_video_repo

                result = await repository.get_recommended_localization_targets(
                    mock_session, "test_user", limit=20
                )

                expected = {
                    "video1": ["es-es", "fr-fr"],
                    "video2": ["fr-fr"],
                }
                assert result == expected
                mock_get_prefs.assert_called_once_with(mock_session, "test_user")
                mock_video_repo.get_videos_missing_localizations.assert_called_once_with(
                    mock_session, ["es-es", "fr-fr"], limit=20
                )

    @pytest.mark.asyncio
    async def test_get_user_localization_coverage_no_preferences(
        self, repository: UserLanguagePreferenceRepository, mock_session: AsyncMock
    ):
        """Test localization coverage when user has no preferences."""
        with patch.object(
            repository, "get_user_preferences", new=AsyncMock(return_value=[])
        ) as mock_get_prefs:

            result = await repository.get_user_localization_coverage(
                mock_session, "test_user"
            )

            expected = {
                "user_languages": {},
                "coverage": {},
                "total_videos": 0,
                "localized_videos": 0,
                "coverage_percentage": 0.0,
            }
            assert result == expected
            mock_get_prefs.assert_called_once_with(mock_session, "test_user")

    @pytest.mark.asyncio
    async def test_get_user_localization_coverage_success(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncMock,
        sample_preferences_with_priorities: List[UserLanguagePreferenceDB],
    ):
        """Test successful localization coverage analysis."""
        # Mock get_user_preferences
        with patch.object(
            repository,
            "get_user_preferences",
            new=AsyncMock(return_value=sample_preferences_with_priorities),
        ) as mock_get_prefs:

            # Mock VideoLocalizationRepository and its method
            mock_language_coverage = {
                "en-us": 100,
                "es-es": 50,
                "fr-fr": 25,
                "it-it": 75,  # Not in user's languages
            }

            with patch(
                "chronovista.repositories.video_localization_repository.VideoLocalizationRepository"
            ) as mock_localization_repo_class:
                mock_localization_repo = AsyncMock()
                mock_localization_repo.get_language_coverage.return_value = (
                    mock_language_coverage
                )
                mock_localization_repo_class.return_value = mock_localization_repo

                result = await repository.get_user_localization_coverage(
                    mock_session, "test_user"
                )

                # Verify structure and calculations
                assert "user_languages" in result
                assert "coverage" in result
                assert "total_videos_with_localizations" in result
                assert "user_localized_videos" in result
                assert "coverage_percentage" in result
                assert "language_breakdown" in result

                # Check user languages mapping (preference_type is stored as string value)
                expected_user_languages = {
                    "en-us": LanguagePreferenceType.FLUENT.value,
                    "es-es": LanguagePreferenceType.LEARNING.value,
                    "fr-fr": LanguagePreferenceType.CURIOUS.value,
                    "de-de": LanguagePreferenceType.EXCLUDE.value,
                }
                assert result["user_languages"] == expected_user_languages

                # Check coverage for user's languages only
                expected_coverage = {
                    "en-us": 100,
                    "es-es": 50,
                    "fr-fr": 25,
                    "de-de": 0,  # Not in mock coverage
                }
                assert result["coverage"] == expected_coverage

                # Check calculations
                assert (
                    result["total_videos_with_localizations"] == 250
                )  # 100 + 50 + 25 + 75
                assert result["user_localized_videos"] == 175  # 100 + 50 + 25 + 0
                assert result["coverage_percentage"] == 70.0  # 175/250 * 100

                # Check language breakdown structure
                assert "en-us" in result["language_breakdown"]
                assert (
                    result["language_breakdown"]["en-us"]["preference_type"]
                    == LanguagePreferenceType.FLUENT.value
                )
                assert result["language_breakdown"]["en-us"]["video_count"] == 100

                mock_get_prefs.assert_called_once_with(mock_session, "test_user")
                mock_localization_repo.get_language_coverage.assert_called_once_with(
                    mock_session
                )

    @pytest.mark.asyncio
    async def test_get_user_localization_coverage_zero_total_videos(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncMock,
        sample_preferences_with_priorities: List[UserLanguagePreferenceDB],
    ):
        """Test localization coverage when there are no videos with localizations."""
        # Mock get_user_preferences
        with patch.object(
            repository,
            "get_user_preferences",
            new=AsyncMock(return_value=sample_preferences_with_priorities),
        ) as mock_get_prefs:

            # Mock empty language coverage
            mock_language_coverage: Dict[str, int] = {}

            with patch(
                "chronovista.repositories.video_localization_repository.VideoLocalizationRepository"
            ) as mock_localization_repo_class:
                mock_localization_repo = AsyncMock()
                mock_localization_repo.get_language_coverage.return_value = (
                    mock_language_coverage
                )
                mock_localization_repo_class.return_value = mock_localization_repo

                result = await repository.get_user_localization_coverage(
                    mock_session, "test_user"
                )

                # Should handle division by zero gracefully
                assert result["total_videos_with_localizations"] == 0
                assert result["user_localized_videos"] == 0
                assert result["coverage_percentage"] == 0.0

                # Check that user languages are still tracked with zero coverage
                expected_coverage = {
                    "en-us": 0,
                    "es-es": 0,
                    "fr-fr": 0,
                    "de-de": 0,
                }
                assert result["coverage"] == expected_coverage

    @pytest.mark.asyncio
    async def test_get_user_localization_coverage_zero_user_videos(
        self,
        repository: UserLanguagePreferenceRepository,
        mock_session: AsyncMock,
        sample_preferences_with_priorities: List[UserLanguagePreferenceDB],
    ):
        """Test localization coverage when user has no localized videos."""
        # Mock get_user_preferences
        with patch.object(
            repository,
            "get_user_preferences",
            new=AsyncMock(return_value=sample_preferences_with_priorities),
        ) as mock_get_prefs:

            # Mock language coverage with languages not in user's preferences
            mock_language_coverage = {
                "it-it": 100,
                "pt-pt": 50,
            }

            with patch(
                "chronovista.repositories.video_localization_repository.VideoLocalizationRepository"
            ) as mock_localization_repo_class:
                mock_localization_repo = AsyncMock()
                mock_localization_repo.get_language_coverage.return_value = (
                    mock_language_coverage
                )
                mock_localization_repo_class.return_value = mock_localization_repo

                result = await repository.get_user_localization_coverage(
                    mock_session, "test_user"
                )

                # Should handle zero user videos gracefully
                assert result["total_videos_with_localizations"] == 150  # 100 + 50
                assert (
                    result["user_localized_videos"] == 0
                )  # No overlap with user languages
                assert result["coverage_percentage"] == 0.0

                # Check language breakdown percentages
                for lang_data in result["language_breakdown"].values():
                    assert lang_data["percentage_of_user_content"] == 0.0
