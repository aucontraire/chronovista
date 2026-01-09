"""
Factory for VideoLocalization models using factory_boy.

Provides reusable test data factories for all VideoLocalization model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import factory
from factory import Faker, LazyAttribute

from chronovista.models.enums import LanguageCode
from chronovista.models.video_localization import (
    VideoLocalization,
    VideoLocalizationBase,
    VideoLocalizationCreate,
    VideoLocalizationSearchFilters,
    VideoLocalizationStatistics,
    VideoLocalizationUpdate,
)


class VideoLocalizationBaseFactory(factory.Factory[VideoLocalizationBase]):
    """Factory for VideoLocalizationBase models."""

    class Meta:
        model = VideoLocalizationBase

    video_id: Any = Faker("lexify", text="???????????")  # 11-char YouTube ID pattern
    language_code: Any = Faker(
        "random_element",
        elements=[
            LanguageCode.ENGLISH,
            LanguageCode.SPANISH,
            LanguageCode.FRENCH,
            LanguageCode.GERMAN,
            LanguageCode.JAPANESE,
            LanguageCode.KOREAN,
            LanguageCode.CHINESE_SIMPLIFIED,
            LanguageCode.PORTUGUESE,
        ],
    )
    localized_title: Any = Faker("sentence", nb_words=6)
    localized_description: Any = Faker("text", max_nb_chars=500)


class VideoLocalizationCreateFactory(VideoLocalizationBaseFactory):
    """Factory for VideoLocalizationCreate models."""

    class Meta:
        model = VideoLocalizationCreate


class VideoLocalizationUpdateFactory(factory.Factory[VideoLocalizationUpdate]):
    """Factory for VideoLocalizationUpdate models."""

    class Meta:
        model = VideoLocalizationUpdate

    localized_title: Any = Faker("sentence", nb_words=5)
    localized_description: Any = Faker("text", max_nb_chars=300)


class VideoLocalizationFactory(VideoLocalizationBaseFactory):
    """Factory for full VideoLocalization models."""

    class Meta:
        model = VideoLocalization

    created_at: Any = Faker("date_time", tzinfo=timezone.utc)


class VideoLocalizationSearchFiltersFactory(factory.Factory[VideoLocalizationSearchFilters]):
    """Factory for VideoLocalizationSearchFilters models."""

    class Meta:
        model = VideoLocalizationSearchFilters

    video_ids: Any = factory.LazyFunction(lambda: ["dQw4w9WgXcQ", "9bZkp7q19f0"])
    language_codes: Any = factory.LazyFunction(
        lambda: [LanguageCode.ENGLISH, LanguageCode.SPANISH]
    )
    title_query: Any = Faker("word")
    description_query: Any = Faker("word")
    has_description: Any = Faker("boolean")
    created_after: Any = Faker("date_time", tzinfo=timezone.utc)
    created_before: Any = Faker("date_time", tzinfo=timezone.utc)


class VideoLocalizationStatisticsFactory(factory.Factory[VideoLocalizationStatistics]):
    """Factory for VideoLocalizationStatistics models."""

    class Meta:
        model = VideoLocalizationStatistics

    total_localizations: Any = Faker("random_int", min=100, max=5000)
    unique_videos: Any = LazyAttribute(
        lambda obj: int(obj.total_localizations * 0.6)
    )  # 60% unique videos
    unique_languages: Any = Faker("random_int", min=5, max=20)
    avg_localizations_per_video: Any = LazyAttribute(
        lambda obj: round(obj.total_localizations / obj.unique_videos, 2)
    )
    top_languages: Any = factory.LazyFunction(
        lambda: [("en", 150), ("es", 120), ("fr", 100), ("de", 80), ("ja", 60)]
    )
    localization_coverage: Any = factory.LazyFunction(
        lambda: {"en": 150, "es": 120, "fr": 100, "de": 80, "ja": 60, "ko": 40}
    )
    videos_with_descriptions: Any = LazyAttribute(
        lambda obj: int(obj.unique_videos * 0.8)
    )  # 80% have descriptions


# Convenience factory methods
def create_video_localization(**kwargs: Any) -> VideoLocalization:
    """Create a VideoLocalization with keyword arguments."""
    result = VideoLocalizationFactory.build(**kwargs)
    assert isinstance(result, VideoLocalization)
    return result


def create_video_localization_create(**kwargs: Any) -> VideoLocalizationCreate:
    """Create a VideoLocalizationCreate with keyword arguments."""
    result = VideoLocalizationCreateFactory.build(**kwargs)
    assert isinstance(result, VideoLocalizationCreate)
    return result


def create_video_localization_update(**kwargs: Any) -> VideoLocalizationUpdate:
    """Create a VideoLocalizationUpdate with keyword arguments."""
    result = VideoLocalizationUpdateFactory.build(**kwargs)
    assert isinstance(result, VideoLocalizationUpdate)
    return result


def create_video_localization_filters(**kwargs: Any) -> VideoLocalizationSearchFilters:
    """Create VideoLocalizationSearchFilters with keyword arguments."""
    result = VideoLocalizationSearchFiltersFactory.build(**kwargs)
    assert isinstance(result, VideoLocalizationSearchFilters)
    return result


def create_video_localization_statistics(**kwargs: Any) -> VideoLocalizationStatistics:
    """Create VideoLocalizationStatistics with keyword arguments."""
    result = VideoLocalizationStatisticsFactory.build(**kwargs)
    assert isinstance(result, VideoLocalizationStatistics)
    return result


# Common test data patterns
class VideoLocalizationTestData:
    """Common test data patterns for VideoLocalization models."""

    VALID_VIDEO_IDS = ["dQw4w9WgXcQ", "9bZkp7q19f0", "jNQXAC9IVRw", "astISOttCQ0"]

    VALID_LANGUAGE_CODES = [
        LanguageCode.ENGLISH,
        LanguageCode.SPANISH,
        LanguageCode.FRENCH,
        LanguageCode.GERMAN,
        LanguageCode.JAPANESE,
        LanguageCode.KOREAN,
        LanguageCode.CHINESE_SIMPLIFIED,
        LanguageCode.PORTUGUESE,
        LanguageCode.ENGLISH,  # English (default)
        LanguageCode.ENGLISH,  # English (UK) - using base enum
        LanguageCode.PORTUGUESE,  # Portuguese (Brazil) - using base enum
    ]

    # String language codes for statistics and raw API data
    VALID_LANGUAGE_CODE_STRINGS = [
        "en",  # English
        "es",  # Spanish
        "fr",  # French
        "de",  # German
        "ja",  # Japanese
        "ko",  # Korean
        "zh-CN",  # Chinese Simplified
        "pt",  # Portuguese
        "en-US",  # English (US)
        "en-GB",  # English (UK)
        "pt-BR",  # Portuguese (Brazil)
    ]

    INVALID_VIDEO_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short
        "x" * 25,  # Too long
    ]

    INVALID_LANGUAGE_CODES = [
        "",  # Empty
        "   ",  # Whitespace
        "x",  # Too short
        "invalid",  # Invalid format
        "123",  # Numbers only
        "en-",  # Incomplete
        "en-123456",  # Invalid region format
        "toolong",  # Too long language code
    ]

    INVALID_TITLES = [
        "",  # Empty
        "   ",  # Whitespace
        "x" * 1001,  # Too long
    ]

    INVALID_DESCRIPTIONS = [
        "x" * 50001,  # Too long (over 50,000 chars)
    ]

    @classmethod
    def valid_video_localization_data(cls) -> dict[str, Any]:
        """Get valid video localization data."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[0],
            "language_code": cls.VALID_LANGUAGE_CODES[0],
            "localized_title": "Test Video Title",
            "localized_description": "Test video description",
        }

    @classmethod
    def minimal_video_localization_data(cls) -> dict[str, Any]:
        """Get minimal valid video localization data."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[1],
            "language_code": cls.VALID_LANGUAGE_CODES[1],
            "localized_title": "Minimal Title",
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict[str, Any]:
        """Get comprehensive search filters data."""
        return {
            "video_ids": cls.VALID_VIDEO_IDS[:2],
            "language_codes": cls.VALID_LANGUAGE_CODES[:3],
            "title_query": "tutorial",
            "description_query": "how to",
            "has_description": True,
            "created_after": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "created_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
        }
