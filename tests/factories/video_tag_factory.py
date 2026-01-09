"""
Factory for VideoTag models using factory_boy.

Provides reusable test data factories for all VideoTag model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import factory
from factory import Faker, LazyAttribute

from chronovista.models.video_tag import (
    VideoTag,
    VideoTagBase,
    VideoTagCreate,
    VideoTagSearchFilters,
    VideoTagStatistics,
    VideoTagUpdate,
)


class VideoTagBaseFactory(factory.Factory[VideoTagBase]):
    """Factory for VideoTagBase models."""

    class Meta:
        model = VideoTagBase

    video_id: Any = Faker("lexify", text="???????????")  # 11-char YouTube ID pattern
    tag: Any = Faker("word")
    tag_order: Any = Faker("random_int", min=0, max=100)


class VideoTagCreateFactory(VideoTagBaseFactory):
    """Factory for VideoTagCreate models."""

    class Meta:
        model = VideoTagCreate


class VideoTagUpdateFactory(factory.Factory[VideoTagUpdate]):
    """Factory for VideoTagUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = VideoTagUpdate

    # No default values - respects model defaults (None for all fields)
    # Values will only be generated when explicitly passed to build()


class VideoTagFactory(VideoTagBaseFactory):
    """Factory for full VideoTag models."""

    class Meta:
        model = VideoTag

    created_at: Any = Faker("date_time", tzinfo=timezone.utc)


class VideoTagSearchFiltersFactory(factory.Factory[VideoTagSearchFilters]):
    """Factory for VideoTagSearchFilters models."""

    class Meta:
        model = VideoTagSearchFilters

    video_ids: Any = factory.LazyFunction(lambda: ["dQw4w9WgXcQ", "9bZkp7q19f0"])
    tags: Any = factory.LazyFunction(lambda: ["gaming", "tutorial", "tech"])
    tag_pattern: Any = Faker("word")
    min_tag_order: Any = Faker("random_int", min=0, max=5)
    max_tag_order: Any = Faker("random_int", min=6, max=20)
    created_after: Any = Faker("date_time", tzinfo=timezone.utc)
    created_before: Any = Faker("date_time", tzinfo=timezone.utc)


class VideoTagStatisticsFactory(factory.Factory[VideoTagStatistics]):
    """Factory for VideoTagStatistics models."""

    class Meta:
        model = VideoTagStatistics

    total_tags: Any = Faker("random_int", min=100, max=10000)
    unique_tags: Any = LazyAttribute(lambda obj: int(obj.total_tags * 0.7))  # 70% unique
    avg_tags_per_video: Any = Faker("pyfloat", min_value=1.0, max_value=5.0, right_digits=2)
    most_common_tags: Any = factory.LazyFunction(
        lambda: [
            ("gaming", 95),
            ("tech", 88),
            ("tutorial", 76),
            ("review", 65),
            ("music", 52),
        ]
    )
    tag_distribution: Any = factory.LazyFunction(
        lambda: {"gaming": 45, "tech": 38, "tutorial": 32, "review": 28, "music": 25}
    )


# Convenience factory methods
def create_video_tag(**kwargs: Any) -> VideoTag:
    """Create a VideoTag with keyword arguments."""
    result = VideoTagFactory.build(**kwargs)
    assert isinstance(result, VideoTag)
    return result


def create_video_tag_create(**kwargs: Any) -> VideoTagCreate:
    """Create a VideoTagCreate with keyword arguments."""
    result = VideoTagCreateFactory.build(**kwargs)
    assert isinstance(result, VideoTagCreate)
    return result


def create_video_tag_update(**kwargs: Any) -> VideoTagUpdate:
    """Create a VideoTagUpdate with keyword arguments."""
    result = VideoTagUpdateFactory.build(**kwargs)
    assert isinstance(result, VideoTagUpdate)
    return result


def create_video_tag_filters(**kwargs: Any) -> VideoTagSearchFilters:
    """Create VideoTagSearchFilters with keyword arguments."""
    result = VideoTagSearchFiltersFactory.build(**kwargs)
    assert isinstance(result, VideoTagSearchFilters)
    return result


def create_video_tag_statistics(**kwargs: Any) -> VideoTagStatistics:
    """Create VideoTagStatistics with keyword arguments."""
    result = VideoTagStatisticsFactory.build(**kwargs)
    assert isinstance(result, VideoTagStatistics)
    return result


# Common test data patterns
class VideoTagTestData:
    """Common test data patterns for VideoTag models."""

    VALID_VIDEO_IDS = ["dQw4w9WgXcQ", "9bZkp7q19f0", "jNQXAC9IVRw", "astISOttCQ0"]

    VALID_TAGS = [
        "music",
        "gaming",
        "tutorial",
        "entertainment",
        "education",
        "technology",
        "review",
        "unboxing",
        "vlog",
        "comedy",
    ]

    INVALID_VIDEO_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short
        "x" * 25,  # Too long
    ]

    INVALID_TAGS = [
        "",  # Empty
        "   ",  # Whitespace
        "x" * 501,  # Too long (max is 500)
    ]

    @classmethod
    def valid_video_tag_data(cls) -> dict[str, Any]:
        """Get valid video tag data."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[0],
            "tag": cls.VALID_TAGS[0],
            "tag_order": 1,
        }

    @classmethod
    def minimal_video_tag_data(cls) -> dict[str, Any]:
        """Get minimal valid video tag data."""
        return {"video_id": cls.VALID_VIDEO_IDS[1], "tag": cls.VALID_TAGS[1]}

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict[str, Any]:
        """Get comprehensive search filters data."""
        return {
            "video_ids": cls.VALID_VIDEO_IDS[:2],
            "tags": cls.VALID_TAGS[:3],
            "tag_pattern": "tutorial",
            "min_tag_order": 1,
            "max_tag_order": 10,
            "created_after": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "created_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
        }
