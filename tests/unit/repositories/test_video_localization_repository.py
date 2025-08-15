"""
Tests for VideoLocalizationRepository functionality.

Comprehensive test suite covering all VideoLocalizationRepository operations
including CRUD, composite key handling, multi-language analytics, and search.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import VideoLocalization as VideoLocalizationDB
from chronovista.models.enums import LanguageCode
from chronovista.models.video_localization import (
    VideoLocalizationCreate,
    VideoLocalizationSearchFilters,
    VideoLocalizationStatistics,
)
from chronovista.repositories.video_localization_repository import (
    VideoLocalizationRepository,
)
from tests.factories import (
    VideoLocalizationSearchFiltersFactory,
    VideoLocalizationStatisticsFactory,
    VideoLocalizationTestData,
    create_video_localization_create,
)


class TestVideoLocalizationRepository:
    """Test VideoLocalizationRepository functionality."""

    @pytest.fixture
    def repository(self) -> VideoLocalizationRepository:
        """Create repository instance for testing."""
        return VideoLocalizationRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        # Configure execute to return a mock result by default
        session.execute = AsyncMock()
        session.delete = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def sample_localization_db(self) -> VideoLocalizationDB:
        """Create sample database video localization object."""
        return VideoLocalizationDB(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH.value,
            localized_title="Never Gonna Give You Up",
            localized_description="Official music video description",
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_localization_create(self) -> VideoLocalizationCreate:
        """Create sample VideoLocalizationCreate object."""
        return VideoLocalizationCreate(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            localized_title="Never Gonna Give You Up",
            localized_description="Official music video description",
        )

    # Basic CRUD Operations

    @pytest.mark.asyncio
    async def test_get_by_composite_key_success(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test successful retrieval by composite key."""
        # Arrange
        expected_localization = VideoLocalizationDB(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH.value,
            localized_title="Test Title",
            localized_description="Test Description",
            created_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_localization
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_by_composite_key(
            mock_session, "dQw4w9WgXcQ", LanguageCode.ENGLISH.value
        )

        # Assert
        assert result == expected_localization
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_composite_key_not_found(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test retrieval when localization doesn't exist."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_by_composite_key(
            mock_session, "nonexistent", LanguageCode.ENGLISH.value
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_tuple_id(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test get method with tuple ID (composite key)."""
        # Arrange
        expected_localization = VideoLocalizationDB(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH.value,
            localized_title="Test Title",
            localized_description="Test Description",
            created_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_localization
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get(mock_session, ("dQw4w9WgXcQ", LanguageCode.ENGLISH.value))

        # Assert
        assert result == expected_localization

    @pytest.mark.asyncio
    async def test_get_with_invalid_id(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test get method with invalid ID format."""
        # Act
        result = await repository.get(mock_session, "invalid_id")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_exists_by_composite_key_true(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test exists method returns True when localization exists."""
        # Arrange
        mock_result = MagicMock()
        mock_result.first.return_value = ("dQw4w9WgXcQ",)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.exists_by_composite_key(
            mock_session, "dQw4w9WgXcQ", LanguageCode.ENGLISH.value
        )

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_by_composite_key_false(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test exists method returns False when localization doesn't exist."""
        # Arrange
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.exists_by_composite_key(
            mock_session, "nonexistent", LanguageCode.ENGLISH.value
        )

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_with_tuple_id(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test exists method with tuple ID."""
        # Arrange
        mock_result = MagicMock()
        mock_result.first.return_value = ("dQw4w9WgXcQ",)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.exists(mock_session, ("dQw4w9WgXcQ", LanguageCode.ENGLISH.value))

        # Assert
        assert result is True

    # Video-Specific Operations

    @pytest.mark.asyncio
    async def test_get_by_video_id(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting all localizations for a video."""
        # Arrange
        localizations = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="English Title",
                localized_description="English Description",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.SPANISH.value,
                localized_title="Título en Español",
                localized_description="Descripción en español",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = localizations
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_by_video_id(mock_session, "dQw4w9WgXcQ")

        # Assert
        assert len(result) == 2
        assert result[0].language_code == LanguageCode.ENGLISH.value
        assert result[1].language_code == LanguageCode.SPANISH.value

    @pytest.mark.asyncio
    async def test_get_by_language_code(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting localizations by language code."""
        # Arrange
        localizations = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="English Title 1",
                localized_description="English Description 1",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="9bZkp7q19f0",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="English Title 2",
                localized_description="English Description 2",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = localizations
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_by_language_code(mock_session, LanguageCode.ENGLISH.value)

        # Assert
        assert len(result) == 2
        assert all(loc.language_code == LanguageCode.ENGLISH.value for loc in result)

    @pytest.mark.asyncio
    async def test_get_with_video(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting localization with video relationship loaded."""
        # Arrange
        localization_with_video = VideoLocalizationDB(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH.value,
            localized_title="Test Title",
            localized_description="Test Description",
            created_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = localization_with_video
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_with_video(mock_session, "dQw4w9WgXcQ", LanguageCode.ENGLISH.value)

        # Assert
        assert result == localization_with_video
        # Verify selectinload was used
        mock_session.execute.assert_called_once()

    # Create and Update Operations

    @pytest.mark.asyncio
    async def test_create_or_update_new_localization(
        self,
        repository: VideoLocalizationRepository,
        mock_session: AsyncMock,
        sample_localization_create: VideoLocalizationCreate,
    ):
        """Test creating new localization when it doesn't exist."""
        # Arrange
        new_localization = VideoLocalizationDB(
            video_id=sample_localization_create.video_id,
            language_code=sample_localization_create.language_code.value,
            localized_title=sample_localization_create.localized_title,
            localized_description=sample_localization_create.localized_description,
            created_at=datetime.now(timezone.utc),
        )

        # Mock that localization doesn't exist
        mock_result_exists = MagicMock()
        mock_result_exists.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result_exists

        # Mock create operation
        with patch.object(repository, 'create', new=AsyncMock(return_value=new_localization)) as mock_create:
            # Act
            result = await repository.create_or_update(
                mock_session, sample_localization_create
            )

            # Assert
            assert result == new_localization
            mock_create.assert_called_once_with(
                mock_session, obj_in=sample_localization_create
            )

    @pytest.mark.asyncio
    async def test_create_or_update_existing_localization(
        self,
        repository: VideoLocalizationRepository,
        mock_session: AsyncMock,
        sample_localization_create: VideoLocalizationCreate,
    ):
        """Test updating existing localization."""
        # Arrange
        existing_localization = VideoLocalizationDB(
            video_id=sample_localization_create.video_id,
            language_code=sample_localization_create.language_code.value,
            localized_title="Old Title",
            localized_description="Old Description",
            created_at=datetime.now(timezone.utc),
        )

        updated_localization = VideoLocalizationDB(
            video_id=sample_localization_create.video_id,
            language_code=sample_localization_create.language_code.value,
            localized_title=sample_localization_create.localized_title,
            localized_description=sample_localization_create.localized_description,
            created_at=datetime.now(timezone.utc),
        )

        # Mock that localization exists
        mock_result_exists = MagicMock()
        mock_result_exists.scalar_one_or_none.return_value = existing_localization
        mock_session.execute.return_value = mock_result_exists

        # Mock update operation
        with patch.object(repository, 'update', new=AsyncMock(return_value=updated_localization)) as mock_update:
            # Act
            result = await repository.create_or_update(
                mock_session, sample_localization_create
            )

            # Assert
            assert result == updated_localization
            mock_update.assert_called_once()

    # Search Operations

    @pytest.mark.asyncio
    async def test_search_localizations_with_filters(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test searching localizations with various filters."""
        # Arrange
        filters = VideoLocalizationSearchFilters(
            video_ids=["dQw4w9WgXcQ"],
            language_codes=[LanguageCode.ENGLISH.value, LanguageCode.SPANISH.value],
            title_query="tutorial",
            has_description=True,
        )

        expected_localizations = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Tutorial Video",
                localized_description="Learning tutorial",
                created_at=datetime.now(timezone.utc),
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = expected_localizations
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.search_localizations(mock_session, filters)

        # Assert
        assert len(result) == 1
        assert result[0].localized_title == "Tutorial Video"

    @pytest.mark.asyncio
    async def test_search_localizations_empty_filters(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test searching with empty filters."""
        # Arrange
        filters = VideoLocalizationSearchFilters()
        all_localizations = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Title 1",
                localized_description="Description 1",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="9bZkp7q19f0",
                language_code=LanguageCode.SPANISH.value,
                localized_title="Título 2",
                localized_description="Descripción 2",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = all_localizations
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.search_localizations(mock_session, filters)

        # Assert
        assert len(result) == 2

    # Language Analytics

    @pytest.mark.asyncio
    async def test_get_supported_languages(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting supported languages for a video."""
        # Arrange
        mock_result = MagicMock()
        mock_result.__iter__.return_value = iter([(LanguageCode.ENGLISH.value,), (LanguageCode.SPANISH.value,), (LanguageCode.FRENCH.value,)])
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_supported_languages(mock_session, "dQw4w9WgXcQ")

        # Assert
        assert result == [LanguageCode.ENGLISH.value, LanguageCode.SPANISH.value, LanguageCode.FRENCH.value]

    @pytest.mark.asyncio
    async def test_get_videos_by_language(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting videos that have localizations in a specific language."""
        # Arrange
        mock_result = MagicMock()
        mock_result.__iter__.return_value = iter([("dQw4w9WgXcQ",), ("9bZkp7q19f0",)])
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_videos_by_language(mock_session, LanguageCode.ENGLISH.value)

        # Assert
        assert result == ["dQw4w9WgXcQ", "9bZkp7q19f0"]

    @pytest.mark.asyncio
    async def test_get_multilingual_videos(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting videos with multiple language localizations."""
        # Arrange
        mock_result = MagicMock()
        mock_result.__iter__.return_value = iter(
            [("dQw4w9WgXcQ", 3), ("9bZkp7q19f0", 2)]
        )
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_multilingual_videos(mock_session, min_languages=2)

        # Assert
        assert result == [("dQw4w9WgXcQ", 3), ("9bZkp7q19f0", 2)]

    @pytest.mark.asyncio
    async def test_get_language_coverage(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting language coverage statistics."""
        # Arrange
        mock_result = MagicMock()
        mock_result.__iter__.return_value = iter([(LanguageCode.ENGLISH.value, 150), (LanguageCode.SPANISH.value, 100), (LanguageCode.FRENCH.value, 50)])
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_language_coverage(mock_session)

        # Assert
        assert result == {LanguageCode.ENGLISH.value: 150, LanguageCode.SPANISH.value: 100, LanguageCode.FRENCH.value: 50}

    @pytest.mark.asyncio
    async def test_find_missing_localizations(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test finding missing localizations for target languages."""
        # Arrange
        target_languages = [LanguageCode.ENGLISH.value, LanguageCode.SPANISH.value, LanguageCode.FRENCH.value]
        mock_result = MagicMock()
        # Video 1 has EN and ES, missing FR
        # Video 2 has only EN, missing ES and FR
        mock_result.__iter__.return_value = iter(
            [
                ("dQw4w9WgXcQ", LanguageCode.ENGLISH.value),
                ("dQw4w9WgXcQ", LanguageCode.SPANISH.value),
                ("9bZkp7q19f0", LanguageCode.ENGLISH.value),
            ]
        )
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.find_missing_localizations(
            mock_session, target_languages, video_ids=["dQw4w9WgXcQ", "9bZkp7q19f0"]
        )

        # Assert
        assert "dQw4w9WgXcQ" in result
        assert result["dQw4w9WgXcQ"] == [LanguageCode.FRENCH.value]
        assert "9bZkp7q19f0" in result
        assert result["9bZkp7q19f0"] == [LanguageCode.SPANISH.value, LanguageCode.FRENCH.value]

    # Statistics

    @pytest.mark.asyncio
    async def test_get_localization_statistics(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting comprehensive localization statistics."""
        # Arrange
        mock_stats = MagicMock()
        mock_stats.total_localizations = 500
        mock_stats.unique_videos = 200
        mock_stats.unique_languages = 10
        mock_stats.avg_localizations_per_video = 2.5
        mock_stats.videos_with_descriptions = 150

        mock_result_total = MagicMock()
        mock_result_total.first.return_value = mock_stats

        mock_result_avg = MagicMock()
        mock_result_avg.scalar.return_value = 2.5

        mock_result_languages = MagicMock()
        mock_result_languages.__iter__.return_value = iter([(LanguageCode.ENGLISH.value, 150), (LanguageCode.SPANISH.value, 100)])

        mock_result_coverage = MagicMock()
        mock_result_coverage.__iter__.return_value = iter([(LanguageCode.ENGLISH.value, 150), (LanguageCode.SPANISH.value, 100)])

        # Configure mock to return different results for different queries
        mock_session.execute.side_effect = [
            mock_result_total,
            mock_result_avg,
            mock_result_languages,
            mock_result_coverage,
        ]

        # Act
        result = await repository.get_localization_statistics(mock_session)

        # Assert
        assert isinstance(result, VideoLocalizationStatistics)
        assert result.total_localizations == 500
        assert result.unique_videos == 200
        assert result.unique_languages == 10
        assert result.avg_localizations_per_video == 2.5
        assert result.videos_with_descriptions == 150

    @pytest.mark.asyncio
    async def test_get_localization_statistics_empty_database(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting statistics when database is empty."""
        # Arrange
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_localization_statistics(mock_session)

        # Assert
        assert result.total_localizations == 0
        assert result.unique_videos == 0
        assert result.unique_languages == 0

    # Bulk Operations

    @pytest.mark.asyncio
    async def test_bulk_create_localizations(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test bulk creating localizations."""
        # Arrange
        localizations_to_create = [
            VideoLocalizationCreate(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH,
                localized_title="Title 1",
                localized_description="Description 1",
            ),
            VideoLocalizationCreate(
                video_id="9bZkp7q19f0",
                language_code=LanguageCode.SPANISH,
                localized_title="Título 2",
                localized_description="Descripción 2",
            ),
        ]

        created_localizations = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Title 1",
                localized_description="Description 1",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="9bZkp7q19f0",
                language_code=LanguageCode.SPANISH.value,
                localized_title="Título 2",
                localized_description="Descripción 2",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        # Mock that localizations don't exist
        mock_result_exists = MagicMock()
        mock_result_exists.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result_exists

        # Mock create operations
        with patch.object(repository, 'create', new=AsyncMock(side_effect=created_localizations)) as mock_create:
            # Act
            result = await repository.bulk_create_localizations(
                mock_session, localizations_to_create
            )

            # Assert
            assert len(result) == 2
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_bulk_create_video_localizations(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test bulk creating localizations for a single video."""
        # Arrange
        video_id = "dQw4w9WgXcQ"
        localizations_data = {
            LanguageCode.ENGLISH.value: {"title": "English Title", "description": "English Description"},
            LanguageCode.SPANISH.value: {
                "title": "Título en Español",
                "description": "Descripción en español",
            },
        }

        created_localizations = [
            VideoLocalizationDB(
                video_id=video_id,
                language_code=LanguageCode.ENGLISH.value,
                localized_title="English Title",
                localized_description="English Description",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id=video_id,
                language_code=LanguageCode.SPANISH.value,
                localized_title="Título en Español",
                localized_description="Descripción en español",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        # Mock that localizations don't exist
        mock_result_exists = MagicMock()
        mock_result_exists.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result_exists

        # Mock create operations
        with patch.object(repository, 'create', new=AsyncMock(side_effect=created_localizations)) as mock_create:
            # Act
            result = await repository.bulk_create_video_localizations(
                mock_session, video_id, localizations_data
            )

            # Assert
            assert len(result) == 2
            assert mock_create.call_count == 2

    # Delete Operations

    @pytest.mark.asyncio
    async def test_delete_by_video_id(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test deleting all localizations for a video."""
        # Arrange
        localizations_to_delete = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="English Title",
                localized_description="English Description",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.SPANISH.value,
                localized_title="Título en Español",
                localized_description="Descripción en español",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        mock_localizations_result = MagicMock()
        mock_localizations_result.scalars.return_value.all.return_value = (
            localizations_to_delete
        )

        mock_session.execute.side_effect = [
            mock_count_result,
            mock_localizations_result,
        ]

        # Act
        result = await repository.delete_by_video_id(mock_session, "dQw4w9WgXcQ")

        # Assert
        assert result == 2
        assert mock_session.delete.call_count == 2
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_by_language_code(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test deleting all localizations for a language."""
        # Arrange
        localizations_to_delete = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Title 1",
                localized_description="Description 1",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="9bZkp7q19f0",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Title 2",
                localized_description="Description 2",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        mock_localizations_result = MagicMock()
        mock_localizations_result.scalars.return_value.all.return_value = (
            localizations_to_delete
        )

        mock_session.execute.side_effect = [
            mock_count_result,
            mock_localizations_result,
        ]

        # Act
        result = await repository.delete_by_language_code(mock_session, LanguageCode.ENGLISH.value)

        # Assert
        assert result == 2
        assert mock_session.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_by_composite_key(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test deleting by composite key."""
        # Arrange
        localization_to_delete = VideoLocalizationDB(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH.value,
            localized_title="Title to Delete",
            localized_description="Description to delete",
            created_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = localization_to_delete
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.delete_by_composite_key(
            mock_session, "dQw4w9WgXcQ", LanguageCode.ENGLISH.value
        )

        # Assert
        assert result == localization_to_delete
        mock_session.delete.assert_called_once_with(localization_to_delete)
        mock_session.flush.assert_awaited_once()

    # Advanced Analytics

    @pytest.mark.asyncio
    async def test_get_preferred_localizations(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting preferred localizations based on language preferences."""
        # Arrange
        video_ids = ["dQw4w9WgXcQ", "9bZkp7q19f0"]
        preferred_languages = [LanguageCode.SPANISH.value, LanguageCode.ENGLISH.value]  # Spanish preferred, English fallback

        localizations = [
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Video 1 English",
                localized_description="English description",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.SPANISH.value,
                localized_title="Video 1 Español",
                localized_description="Descripción en español",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="9bZkp7q19f0",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Video 2 English",
                localized_description="English description",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = localizations
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.get_preferred_localizations(
            mock_session, video_ids, preferred_languages
        )

        # Assert
        assert len(result) == 2
        # Video1 should have Spanish (preferred)
        video1_localization = result["dQw4w9WgXcQ"]
        assert video1_localization is not None
        assert video1_localization.language_code == LanguageCode.SPANISH.value
        # Video2 should have English (fallback)
        video2_localization = result["9bZkp7q19f0"]
        assert video2_localization is not None
        assert video2_localization.language_code == LanguageCode.ENGLISH.value

    @pytest.mark.asyncio
    async def test_find_similar_content(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test finding similar content based on title similarity."""
        # Arrange
        target_localization = VideoLocalizationDB(
            video_id="target_video",
            language_code=LanguageCode.ENGLISH.value,
            localized_title="Python Programming Tutorial",
            localized_description="Learn Python programming",
            created_at=datetime.now(timezone.utc),
        )

        similar_localizations = [
            VideoLocalizationDB(
                video_id="similar_video1",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="Advanced Python Programming",
                localized_description="Advanced Python concepts",
                created_at=datetime.now(timezone.utc),
            ),
            VideoLocalizationDB(
                video_id="similar_video2",
                language_code=LanguageCode.ENGLISH.value,
                localized_title="JavaScript Tutorial",
                localized_description="Learn JavaScript",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_result_target = MagicMock()
        mock_result_target.scalar_one_or_none.return_value = target_localization

        mock_result_others = MagicMock()
        mock_result_others.scalars.return_value.all.return_value = similar_localizations

        mock_session.execute.side_effect = [mock_result_target, mock_result_others]

        # Act
        result = await repository.find_similar_content(
            mock_session, "target_video", LanguageCode.ENGLISH.value
        )

        # Assert
        assert len(result) > 0
        # Should find similar Python content
        similar_localization, similarity_score = result[0]
        assert similarity_score > 0

    @pytest.mark.asyncio
    async def test_get_localization_quality_metrics(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test getting localization quality metrics."""
        # Arrange
        mock_title_length = MagicMock()
        mock_title_length.scalar.return_value = 45.5

        mock_coverage_stats = MagicMock()
        mock_coverage_stats.total = 100
        mock_coverage_stats.with_description = 80

        mock_coverage_result = MagicMock()
        mock_coverage_result.first.return_value = mock_coverage_stats

        mock_session.execute.side_effect = [mock_title_length, mock_coverage_result]

        # Act
        result = await repository.get_localization_quality_metrics(mock_session)

        # Assert
        assert "average_title_length" in result
        assert result["average_title_length"] == 45.5
        assert "description_coverage" in result
        assert result["description_coverage"] == 0.8


# Integration Tests with Factories


class TestVideoLocalizationRepositoryWithFactories:
    """Integration tests using factory_boy factories."""

    @pytest.fixture
    def repository(self) -> VideoLocalizationRepository:
        """Create repository instance for testing."""
        return VideoLocalizationRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        # Configure execute to return a mock result by default
        session.execute = AsyncMock()
        session.delete = AsyncMock()
        session.flush = AsyncMock()
        return session

    def test_create_localization_with_factory(self):
        """Test creating localization using factory."""
        # Act
        localization_create = create_video_localization_create(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            localized_title="Factory Test Title",
        )

        # Assert
        assert localization_create.video_id == "dQw4w9WgXcQ"
        assert localization_create.language_code == LanguageCode.ENGLISH
        assert localization_create.localized_title == "Factory Test Title"

    def test_create_search_filters_with_factory(self):
        """Test creating search filters using factory."""
        # Act
        filters = VideoLocalizationSearchFiltersFactory.build(
            video_ids=VideoLocalizationTestData.VALID_VIDEO_IDS[:2],
            language_codes=[LanguageCode.ENGLISH.value, LanguageCode.SPANISH.value],
            title_query="tutorial",
        )

        # Assert
        assert filters.video_ids is not None
        assert len(filters.video_ids) == 2
        assert filters.language_codes == [LanguageCode.ENGLISH.value, LanguageCode.SPANISH.value]
        assert filters.title_query == "tutorial"

    def test_create_statistics_with_factory(self):
        """Test creating statistics using factory."""
        # Act
        stats = VideoLocalizationStatisticsFactory.build(
            total_localizations=1000, unique_videos=400
        )

        # Assert
        assert stats.total_localizations == 1000
        assert stats.unique_videos == 400
        assert stats.avg_localizations_per_video > 0

    def test_use_test_data_patterns(self):
        """Test using common test data patterns."""
        # Act
        valid_data = VideoLocalizationTestData.valid_video_localization_data()
        minimal_data = VideoLocalizationTestData.minimal_video_localization_data()

        # Assert
        assert valid_data["video_id"] in VideoLocalizationTestData.VALID_VIDEO_IDS
        assert (
            valid_data["language_code"]
            in VideoLocalizationTestData.VALID_LANGUAGE_CODES
        )
        assert minimal_data["localized_title"] == "Minimal Title"

    def test_invalid_data_patterns(self):
        """Test invalid data patterns."""
        # Assert invalid patterns are defined
        assert len(VideoLocalizationTestData.INVALID_VIDEO_IDS) > 0
        assert len(VideoLocalizationTestData.INVALID_LANGUAGE_CODES) > 0
        assert len(VideoLocalizationTestData.INVALID_TITLES) > 0
        assert len(VideoLocalizationTestData.INVALID_DESCRIPTIONS) > 0


# Error Handling Tests


class TestVideoLocalizationRepositoryErrorHandling:
    """Test error handling in VideoLocalizationRepository."""

    @pytest.fixture
    def repository(self) -> VideoLocalizationRepository:
        """Create repository instance for testing."""
        return VideoLocalizationRepository()

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        # Configure execute to return a mock result by default
        session.execute = AsyncMock()
        session.delete = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_by_composite_key_with_none_values(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test handling None values in composite key operations."""
        # Act & Assert
        result = await repository.get_by_composite_key(mock_session, None, LanguageCode.ENGLISH.value)  # type: ignore
        # Should handle gracefully without crashing

        result = await repository.get_by_composite_key(mock_session, "video_id", None)  # type: ignore
        # Should handle gracefully without crashing

    @pytest.mark.asyncio
    async def test_search_with_empty_filters(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test search with empty filters."""
        # Arrange
        empty_filters = VideoLocalizationSearchFilters()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        result = await repository.search_localizations(mock_session, empty_filters)

        # Should handle gracefully and return empty list
        assert result == []

    @pytest.mark.asyncio
    async def test_bulk_operations_with_empty_lists(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test bulk operations with empty input lists."""
        # Act
        result = await repository.bulk_create_localizations(mock_session, [])

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_analytics_operations_with_empty_parameters(
        self, repository: VideoLocalizationRepository, mock_session: AsyncMock
    ):
        """Test analytics operations with empty parameters."""
        # Act
        preferred_result = await repository.get_preferred_localizations(
            mock_session, [], []
        )

        # Assert
        assert preferred_result == {}

        missing_result = await repository.find_missing_localizations(
            mock_session, [], []
        )

        # Assert
        assert missing_result == {}
