"""
Tests for video localization Pydantic models.

Tests validation, keyword arguments, serialization, and model methods
for all VideoLocalization model variants using factory pattern for DRY.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.video_localization import (
    VideoLocalization,
    VideoLocalizationBase,
    VideoLocalizationCreate,
    VideoLocalizationSearchFilters,
    VideoLocalizationStatistics,
    VideoLocalizationUpdate,
)
from chronovista.models.enums import LanguageCode

from tests.factories.video_localization_factory import (
    VideoLocalizationBaseFactory,
    VideoLocalizationCreateFactory,
    VideoLocalizationFactory,
    VideoLocalizationSearchFiltersFactory,
    VideoLocalizationStatisticsFactory,
    VideoLocalizationTestData,
    VideoLocalizationUpdateFactory,
    create_video_localization,
)


class TestVideoLocalizationBase:
    """Test VideoLocalizationBase model using factories."""

    def test_create_valid_video_localization_base(self):
        """Test creating valid VideoLocalizationBase with keyword arguments."""
        localization = VideoLocalizationBaseFactory.build(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            localized_title="Test Video Title",
            localized_description="Test description",
        )

        assert localization.video_id == "dQw4w9WgXcQ"
        assert localization.language_code == LanguageCode.ENGLISH
        assert localization.localized_title == "Test Video Title"
        assert localization.localized_description == "Test description"

    def test_create_video_localization_base_minimal(self):
        """Test creating VideoLocalizationBase with minimal required fields."""
        localization = VideoLocalizationBaseFactory.build(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.SPANISH,
            localized_title="Título de prueba",
            localized_description=None,
        )

        assert localization.video_id == "dQw4w9WgXcQ"
        assert localization.language_code == LanguageCode.SPANISH
        assert localization.localized_title == "Título de prueba"
        assert localization.localized_description is None

    def test_factory_generates_valid_defaults(self):
        """Test that factory generates valid models with defaults."""
        localization = VideoLocalizationBaseFactory.build()

        assert isinstance(localization, VideoLocalizationBase)
        assert len(localization.video_id) >= 8
        assert len(localization.video_id) <= 20
        assert len(localization.language_code.value) >= 2
        assert len(localization.language_code.value) <= 10
        assert len(localization.localized_title) >= 1

    @pytest.mark.parametrize(
        "invalid_video_id", VideoLocalizationTestData.INVALID_VIDEO_IDS
    )
    def test_video_id_validation_invalid(self, invalid_video_id):
        """Test video_id validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            VideoLocalizationBaseFactory.build(video_id=invalid_video_id)

    @pytest.mark.parametrize(
        "valid_video_id", VideoLocalizationTestData.VALID_VIDEO_IDS
    )
    def test_video_id_validation_valid(self, valid_video_id):
        """Test video_id validation with various valid inputs."""
        localization = VideoLocalizationBaseFactory.build(video_id=valid_video_id)
        assert localization.video_id == valid_video_id

    @pytest.mark.parametrize(
        "invalid_language_code", VideoLocalizationTestData.INVALID_LANGUAGE_CODES
    )
    def test_language_code_validation_invalid(self, invalid_language_code):
        """Test language_code validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            VideoLocalizationBaseFactory.build(language_code=invalid_language_code)

    @pytest.mark.parametrize(
        "valid_language_code", VideoLocalizationTestData.VALID_LANGUAGE_CODES
    )
    def test_language_code_validation_valid(self, valid_language_code):
        """Test language_code validation with various valid inputs."""
        localization = VideoLocalizationBaseFactory.build(language_code=valid_language_code)
        assert localization.language_code == valid_language_code

    @pytest.mark.parametrize("invalid_title", VideoLocalizationTestData.INVALID_TITLES)
    def test_localized_title_validation_invalid(self, invalid_title):
        """Test localized_title validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            VideoLocalizationBaseFactory.build(localized_title=invalid_title)

    @pytest.mark.parametrize(
        "invalid_description", VideoLocalizationTestData.INVALID_DESCRIPTIONS
    )
    def test_localized_description_validation_invalid(self, invalid_description):
        """Test localized_description validation with invalid inputs."""
        with pytest.raises(ValidationError):
            VideoLocalizationBaseFactory.build(localized_description=invalid_description)

    def test_localized_description_empty_becomes_none(self):
        """Test that empty description becomes None."""
        localization = VideoLocalizationBaseFactory.build(localized_description="   ")
        assert localization.localized_description is None

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        localization = VideoLocalizationBaseFactory.build(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            localized_title="Test Title",
            localized_description="Test description",
        )

        data = localization.model_dump()
        expected = {
            "video_id": "dQw4w9WgXcQ",
            "language_code": "en",
            "localized_title": "Test Title",
            "localized_description": "Test description",
        }

        assert data == expected

    def test_model_validate_functionality(self):
        """Test model_validate() method for deserialization."""
        data = VideoLocalizationTestData.valid_video_localization_data()

        localization = VideoLocalizationBase.model_validate(data)

        assert localization.video_id == data["video_id"]
        assert localization.language_code == data["language_code"]
        assert localization.localized_title == data["localized_title"]
        assert localization.localized_description == data["localized_description"]


class TestVideoLocalizationCreate:
    """Test VideoLocalizationCreate model using factories."""

    def test_create_valid_video_localization_create(self):
        """Test creating valid VideoLocalizationCreate with keyword arguments."""
        localization = VideoLocalizationCreateFactory.build(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.FRENCH,
            localized_title="Titre de test",
            localized_description="Description de test",
        )

        assert localization.video_id == "dQw4w9WgXcQ"
        assert localization.language_code == LanguageCode.FRENCH
        assert localization.localized_title == "Titre de test"
        assert localization.localized_description == "Description de test"

    def test_inherits_base_validation(self):
        """Test that VideoLocalizationCreate inherits base validation."""
        with pytest.raises(ValidationError):
            VideoLocalizationCreateFactory.build(video_id="   ")

    def test_factory_generates_valid_model(self):
        """Test factory generates valid VideoLocalizationCreate models."""
        localization = VideoLocalizationCreateFactory.build()

        assert isinstance(localization, VideoLocalizationCreate)
        assert isinstance(localization, VideoLocalizationBase)  # Inheritance check


class TestVideoLocalizationUpdate:
    """Test VideoLocalizationUpdate model using factories."""

    def test_create_valid_video_localization_update(self):
        """Test creating valid VideoLocalizationUpdate with keyword arguments."""
        update = VideoLocalizationUpdateFactory.build(
            localized_title="Updated Title", localized_description="Updated description"
        )

        assert update.localized_title == "Updated Title"
        assert update.localized_description == "Updated description"

    def test_create_empty_video_localization_update(self):
        """Test creating empty VideoLocalizationUpdate."""
        update = VideoLocalizationUpdate()

        assert update.localized_title is None
        assert update.localized_description is None

    def test_title_validation_in_update(self):
        """Test title validation in update model."""
        with pytest.raises(ValidationError):
            VideoLocalizationUpdateFactory.build(localized_title="")

    def test_description_empty_becomes_none(self):
        """Test that empty description becomes None in update."""
        update = VideoLocalizationUpdateFactory.build(localized_description="   ")
        assert update.localized_description is None

    def test_model_dump_excludes_none(self):
        """Test model_dump() excludes None values."""
        update = VideoLocalizationUpdate()

        data = update.model_dump(exclude_none=True)

        assert data == {}

    def test_factory_generates_valid_updates(self):
        """Test factory generates valid update models."""
        update = VideoLocalizationUpdateFactory.build()

        assert isinstance(update, VideoLocalizationUpdate)
        assert update.localized_title is not None


class TestVideoLocalization:
    """Test VideoLocalization full model using factories."""

    def test_create_valid_video_localization(self):
        """Test creating valid VideoLocalization with keyword arguments."""
        now = datetime.now(timezone.utc)
        localization = VideoLocalizationFactory.build(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.JAPANESE,
            localized_title="テストビデオ",
            localized_description="テストの説明",
            created_at=now,
        )

        assert localization.video_id == "dQw4w9WgXcQ"
        assert localization.language_code == LanguageCode.JAPANESE
        assert localization.localized_title == "テストビデオ"
        assert localization.localized_description == "テストの説明"
        assert localization.created_at == now

    def test_from_attributes_compatibility(self):
        """Test ORM compatibility with from_attributes."""

        # Simulate SQLAlchemy model attributes
        class MockVideoLocalizationDB:
            video_id = "dQw4w9WgXcQ"
            language_code = LanguageCode.GERMAN
            localized_title = "Test Video"
            localized_description = "Beschreibung"
            created_at = datetime.now(timezone.utc)

        mock_db = MockVideoLocalizationDB()
        localization = VideoLocalization.model_validate(mock_db, from_attributes=True)

        assert localization.video_id == "dQw4w9WgXcQ"
        assert localization.language_code == LanguageCode.GERMAN
        assert localization.localized_title == "Test Video"
        assert localization.localized_description == "Beschreibung"
        assert isinstance(localization.created_at, datetime)

    def test_factory_generates_full_model(self):
        """Test factory generates complete VideoLocalization models."""
        localization = VideoLocalizationFactory.build()

        assert isinstance(localization, VideoLocalization)
        assert isinstance(localization, VideoLocalizationBase)  # Inheritance
        assert isinstance(localization.created_at, datetime)
        assert localization.created_at.tzinfo is not None  # Has timezone


class TestVideoLocalizationSearchFilters:
    """Test VideoLocalizationSearchFilters model using factories."""

    def test_create_comprehensive_filters(self):
        """Test creating comprehensive search filters with keyword arguments."""
        data = VideoLocalizationTestData.comprehensive_search_filters_data()
        filters = VideoLocalizationSearchFiltersFactory.build(**data)

        assert filters.video_ids == data["video_ids"]
        assert filters.language_codes == data["language_codes"]
        assert filters.title_query == data["title_query"]
        assert filters.description_query == data["description_query"]
        assert filters.has_description == data["has_description"]
        assert filters.created_after == data["created_after"]
        assert filters.created_before == data["created_before"]

    def test_create_empty_filters(self):
        """Test creating empty search filters."""
        filters = VideoLocalizationSearchFilters()

        assert filters.video_ids is None
        assert filters.language_codes is None
        assert filters.title_query is None
        assert filters.description_query is None
        assert filters.has_description is None
        assert filters.created_after is None
        assert filters.created_before is None

    def test_factory_generates_valid_filters(self):
        """Test factory generates valid search filters."""
        filters = VideoLocalizationSearchFiltersFactory.build()

        assert isinstance(filters, VideoLocalizationSearchFilters)
        assert isinstance(filters.video_ids, list)
        assert isinstance(filters.language_codes, list)
        assert len(filters.video_ids) > 0
        assert len(filters.language_codes) > 0

    def test_query_validation_empty_string(self):
        """Test query validation with empty strings."""
        with pytest.raises(ValidationError):
            VideoLocalizationSearchFiltersFactory.build(title_query="")

        with pytest.raises(ValidationError):
            VideoLocalizationSearchFiltersFactory.build(description_query="")


class TestVideoLocalizationStatistics:
    """Test VideoLocalizationStatistics model using factories."""

    def test_create_valid_statistics(self):
        """Test creating valid VideoLocalizationStatistics with keyword arguments."""
        stats = VideoLocalizationStatisticsFactory.build(
            total_localizations=1000,
            unique_videos=600,
            unique_languages=15,
            avg_localizations_per_video=1.67,
            top_languages=[("en", 200), ("es", 150), ("fr", 100)],
            localization_coverage={"en": 200, "es": 150, "fr": 100},
            videos_with_descriptions=480,
        )

        assert stats.total_localizations == 1000
        assert stats.unique_videos == 600
        assert stats.unique_languages == 15
        assert stats.avg_localizations_per_video == 1.67
        assert stats.top_languages == [("en", 200), ("es", 150), ("fr", 100)]
        assert stats.localization_coverage == {"en": 200, "es": 150, "fr": 100}
        assert stats.videos_with_descriptions == 480

    def test_create_minimal_statistics(self):
        """Test creating minimal VideoLocalizationStatistics."""
        stats = VideoLocalizationStatistics(
            total_localizations=50,
            unique_videos=30,
            unique_languages=5,
            avg_localizations_per_video=1.67,
            videos_with_descriptions=25,
        )

        assert stats.total_localizations == 50
        assert stats.unique_videos == 30
        assert stats.unique_languages == 5
        assert stats.videos_with_descriptions == 25
        assert stats.top_languages == []
        assert stats.localization_coverage == {}

    def test_factory_generates_realistic_statistics(self):
        """Test factory generates realistic statistics."""
        stats = VideoLocalizationStatisticsFactory.build()

        assert isinstance(stats, VideoLocalizationStatistics)
        assert stats.total_localizations > 0
        assert stats.unique_videos <= stats.total_localizations
        assert stats.unique_languages > 0
        assert stats.avg_localizations_per_video > 0
        assert stats.videos_with_descriptions <= stats.unique_videos
        assert isinstance(stats.top_languages, list)
        assert isinstance(stats.localization_coverage, dict)


class TestVideoLocalizationModelInteractions:
    """Test interactions between different VideoLocalization models using factories."""

    def test_create_then_update_workflow(self):
        """Test typical create then update workflow with keyword arguments."""
        # Create
        localization_create = VideoLocalizationCreateFactory.build(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            localized_title="Original Title",
            localized_description="Original description",
        )

        # Simulate creation
        now = datetime.now(timezone.utc)
        localization_full = VideoLocalizationFactory.build(
            video_id=localization_create.video_id,
            language_code=localization_create.language_code,
            localized_title=localization_create.localized_title,
            localized_description=localization_create.localized_description,
            created_at=now,
        )

        # Update
        localization_update = VideoLocalizationUpdateFactory.build(
            localized_title="Updated Title", localized_description=None
        )

        # Apply update (simulated)
        updated_data = localization_full.model_dump()
        update_data = localization_update.model_dump(exclude_unset=True)
        updated_data.update(update_data)

        localization_updated = VideoLocalization.model_validate(updated_data)

        assert localization_updated.video_id == "dQw4w9WgXcQ"
        assert localization_updated.language_code == LanguageCode.ENGLISH
        assert localization_updated.localized_title == "Updated Title"
        assert localization_updated.localized_description is None

    def test_search_filters_serialization(self):
        """Test search filters serialization for API usage."""
        filters = VideoLocalizationSearchFilters(
            video_ids=["dQw4w9WgXcQ"],
            language_codes=[LanguageCode.ENGLISH, LanguageCode.SPANISH],
            title_query="tutorial",
            has_description=True,
        )

        # Simulate API query parameters
        query_params = filters.model_dump(exclude_none=True)

        expected = {
            "video_ids": ["dQw4w9WgXcQ"],
            "language_codes": ["en", "es"],
            "title_query": "tutorial",
            "has_description": True,
        }

        assert query_params == expected

    def test_statistics_aggregation_pattern(self):
        """Test statistics model for aggregation results."""
        # Simulate aggregation data from database
        aggregation_result = {
            "total_localizations": 2500,
            "unique_videos": 1000,
            "unique_languages": 12,
            "avg_localizations_per_video": 2.5,
            "top_languages": [("en", 500), ("es", 300), ("fr", 200)],
            "localization_coverage": {
                "en": 500,
                "es": 300,
                "fr": 200,
                "de": 150,
                "ja": 100,
            },
            "videos_with_descriptions": 800,
        }

        stats = VideoLocalizationStatistics.model_validate(aggregation_result)

        assert stats.total_localizations == 2500
        assert stats.unique_videos == 1000
        assert len(stats.top_languages) == 3
        assert len(stats.localization_coverage) == 5
        assert stats.top_languages[0] == ("en", 500)
        assert stats.videos_with_descriptions == 800

    def test_convenience_factory_functions(self):
        """Test convenience factory functions for easy model creation."""
        # Test convenience function
        localization = create_video_localization(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.SPANISH,
            localized_title="Título de prueba",
        )

        assert isinstance(localization, VideoLocalization)
        assert localization.video_id == "dQw4w9WgXcQ"
        assert localization.language_code == LanguageCode.SPANISH
        assert localization.localized_title == "Título de prueba"
        assert isinstance(localization.created_at, datetime)

    def test_factory_inheritance_consistency(self):
        """Test that factory-created models maintain proper inheritance."""
        base = VideoLocalizationBaseFactory.build()
        create = VideoLocalizationCreateFactory.build()
        full = VideoLocalizationFactory.build()

        # All should be instances of VideoLocalizationBase
        assert isinstance(base, VideoLocalizationBase)
        assert isinstance(create, VideoLocalizationBase)
        assert isinstance(full, VideoLocalizationBase)

        # Specific type checks
        assert isinstance(create, VideoLocalizationCreate)
        assert isinstance(full, VideoLocalization)

    def test_language_code_normalization(self):
        """Test that language codes are normalized to lowercase."""
        # Test that valid LanguageCode enum values work correctly
        from chronovista.models.enums import LanguageCode

        test_cases = [
            (LanguageCode.ENGLISH, "en"),
            (LanguageCode.ENGLISH_US, "en-US"),
            (LanguageCode.CHINESE_SIMPLIFIED, "zh-CN"),
            (LanguageCode.PORTUGUESE_BR, "pt-BR"),
        ]

        for input_enum, expected_value in test_cases:
            localization = VideoLocalizationBaseFactory.build(language_code=input_enum)
            assert localization.language_code.value == expected_value

    def test_multilingual_content_handling(self):
        """Test handling of various multilingual content."""
        multilingual_test_cases = [
            (LanguageCode.ENGLISH, "English Title", "English description"),
            (LanguageCode.SPANISH, "Título en Español", "Descripción en español"),
            (LanguageCode.FRENCH, "Titre en Français", "Description en français"),
            (LanguageCode.JAPANESE, "日本語のタイトル", "日本語の説明"),
            (LanguageCode.KOREAN, "한국어 제목", "한국어 설명"),
            (LanguageCode.CHINESE_SIMPLIFIED, "中文标题", "中文描述"),
        ]

        for lang_code_enum, title, description in multilingual_test_cases:
            localization = VideoLocalizationBaseFactory.build(
                language_code=lang_code_enum,
                localized_title=title,
                localized_description=description,
            )

            assert localization.language_code == lang_code_enum
            assert localization.localized_title == title
            assert localization.localized_description == description
