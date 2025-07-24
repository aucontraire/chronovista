"""
Factory for VideoLocalization models using factory_boy.

Provides reusable test data factories for all VideoLocalization model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone

import factory
from factory import Faker, LazyAttribute

from chronovista.models.video_localization import (
    VideoLocalization,
    VideoLocalizationBase,
    VideoLocalizationCreate,
    VideoLocalizationSearchFilters,
    VideoLocalizationStatistics,
    VideoLocalizationUpdate,
)


class VideoLocalizationBaseFactory(factory.Factory):
    """Factory for VideoLocalizationBase models."""

    class Meta:
        model = VideoLocalizationBase

    video_id = Faker("lexify", text="???????????")  # 11-char YouTube ID pattern
    language_code = Faker(
        "random_element", elements=["en", "es", "fr", "de", "ja", "ko", "zh-CN", "pt"]
    )
    localized_title = Faker("sentence", nb_words=6)
    localized_description = Faker("text", max_nb_chars=500)


class VideoLocalizationCreateFactory(VideoLocalizationBaseFactory):
    """Factory for VideoLocalizationCreate models."""

    class Meta:
        model = VideoLocalizationCreate


class VideoLocalizationUpdateFactory(factory.Factory):
    """Factory for VideoLocalizationUpdate models."""

    class Meta:
        model = VideoLocalizationUpdate

    localized_title = Faker("sentence", nb_words=5)
    localized_description = Faker("text", max_nb_chars=300)


class VideoLocalizationFactory(VideoLocalizationBaseFactory):
    """Factory for full VideoLocalization models."""

    class Meta:
        model = VideoLocalization

    created_at = Faker("date_time", tzinfo=timezone.utc)


class VideoLocalizationSearchFiltersFactory(factory.Factory):
    """Factory for VideoLocalizationSearchFilters models."""

    class Meta:
        model = VideoLocalizationSearchFilters

    video_ids = factory.LazyFunction(lambda: ["dQw4w9WgXcQ", "9bZkp7q19f0"])
    language_codes = factory.LazyFunction(lambda: ["en", "es"])
    title_query = Faker("word")
    description_query = Faker("word")
    has_description = Faker("boolean")
    created_after = Faker("date_time", tzinfo=timezone.utc)
    created_before = Faker("date_time", tzinfo=timezone.utc)


class VideoLocalizationStatisticsFactory(factory.Factory):
    """Factory for VideoLocalizationStatistics models."""

    class Meta:
        model = VideoLocalizationStatistics

    total_localizations = Faker("random_int", min=100, max=5000)
    unique_videos = LazyAttribute(
        lambda obj: int(obj.total_localizations * 0.6)
    )  # 60% unique videos
    unique_languages = Faker("random_int", min=5, max=20)
    avg_localizations_per_video = LazyAttribute(
        lambda obj: round(obj.total_localizations / obj.unique_videos, 2)
    )
    top_languages = factory.LazyFunction(
        lambda: [("en", 150), ("es", 120), ("fr", 100), ("de", 80), ("ja", 60)]
    )
    localization_coverage = factory.LazyFunction(
        lambda: {"en": 150, "es": 120, "fr": 100, "de": 80, "ja": 60, "ko": 40}
    )
    videos_with_descriptions = LazyAttribute(
        lambda obj: int(obj.unique_videos * 0.8)
    )  # 80% have descriptions


# Convenience factory methods
def create_video_localization(**kwargs) -> VideoLocalization:
    """Create a VideoLocalization with keyword arguments."""
    return VideoLocalizationFactory(**kwargs)


def create_video_localization_create(**kwargs) -> VideoLocalizationCreate:
    """Create a VideoLocalizationCreate with keyword arguments."""
    return VideoLocalizationCreateFactory(**kwargs)


def create_video_localization_update(**kwargs) -> VideoLocalizationUpdate:
    """Create a VideoLocalizationUpdate with keyword arguments."""
    return VideoLocalizationUpdateFactory(**kwargs)


def create_video_localization_filters(**kwargs) -> VideoLocalizationSearchFilters:
    """Create VideoLocalizationSearchFilters with keyword arguments."""
    return VideoLocalizationSearchFiltersFactory(**kwargs)


def create_video_localization_statistics(**kwargs) -> VideoLocalizationStatistics:
    """Create VideoLocalizationStatistics with keyword arguments."""
    return VideoLocalizationStatisticsFactory(**kwargs)


# Common test data patterns
class VideoLocalizationTestData:
    """Common test data patterns for VideoLocalization models."""

    VALID_VIDEO_IDS = ["dQw4w9WgXcQ", "9bZkp7q19f0", "jNQXAC9IVRw", "astISOttCQ0"]

    VALID_LANGUAGE_CODES = [
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
    def valid_video_localization_data(cls) -> dict:
        """Get valid video localization data."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[0],
            "language_code": cls.VALID_LANGUAGE_CODES[0],
            "localized_title": "Test Video Title",
            "localized_description": "Test video description",
        }

    @classmethod
    def minimal_video_localization_data(cls) -> dict:
        """Get minimal valid video localization data."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[1],
            "language_code": cls.VALID_LANGUAGE_CODES[1],
            "localized_title": "Minimal Title",
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict:
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
