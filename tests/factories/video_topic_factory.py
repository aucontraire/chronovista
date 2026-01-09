"""
Factory for VideoTopic models using factory_boy.

Provides reusable test data factories for all VideoTopic model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import factory
from factory import Faker, LazyAttribute
from factory.faker import Faker as FakerType

from chronovista.models.video_topic import (
    VideoTopic,
    VideoTopicBase,
    VideoTopicCreate,
    VideoTopicSearchFilters,
    VideoTopicStatistics,
    VideoTopicUpdate,
)


class VideoTopicBaseFactory(factory.Factory[VideoTopicBase]):
    """Factory for VideoTopicBase models."""

    class Meta:
        model = VideoTopicBase

    video_id: Any = Faker("lexify", text="???????????")  # 11-char YouTube ID pattern
    topic_id: Any = Faker("lexify", text="topic_????????????????")  # Valid topic ID pattern
    relevance_type: Any = Faker(
        "random_element", elements=["primary", "relevant", "suggested"]
    )


class VideoTopicCreateFactory(VideoTopicBaseFactory):
    """Factory for VideoTopicCreate models."""

    class Meta:
        model = VideoTopicCreate


class VideoTopicUpdateFactory(factory.Factory[VideoTopicUpdate]):
    """Factory for VideoTopicUpdate models."""

    class Meta:
        model = VideoTopicUpdate

    relevance_type: Any = Faker(
        "random_element", elements=["primary", "relevant", "suggested"]
    )


class VideoTopicFactory(VideoTopicBaseFactory):
    """Factory for full VideoTopic models."""

    class Meta:
        model = VideoTopic

    created_at: Any = Faker("date_time", tzinfo=timezone.utc)


class VideoTopicSearchFiltersFactory(factory.Factory[VideoTopicSearchFilters]):
    """Factory for VideoTopicSearchFilters models."""

    class Meta:
        model = VideoTopicSearchFilters

    video_ids: Any = factory.LazyFunction(lambda: ["dQw4w9WgXcQ", "9bZkp7q19f0"])
    topic_ids: Any = factory.LazyFunction(
        lambda: ["topic_music", "topic_gaming", "topic_education"]
    )
    relevance_types: Any = factory.LazyFunction(lambda: ["primary", "relevant"])
    created_after: Any = Faker("date_time", tzinfo=timezone.utc)
    created_before: Any = Faker("date_time", tzinfo=timezone.utc)


class VideoTopicStatisticsFactory(factory.Factory[VideoTopicStatistics]):
    """Factory for VideoTopicStatistics models."""

    class Meta:
        model = VideoTopicStatistics

    total_video_topics: Any = Faker("random_int", min=100, max=10000)
    unique_topics: Any = LazyAttribute(
        lambda obj: int(obj.total_video_topics * 0.6)
    )  # 60% unique
    unique_videos: Any = LazyAttribute(
        lambda obj: int(obj.total_video_topics * 0.8)
    )  # 80% unique
    avg_topics_per_video: Any = Faker(
        "pyfloat", min_value=1.0, max_value=4.0, right_digits=2
    )
    most_common_topics: Any = factory.LazyFunction(
        lambda: [
            ("topic_music", 145),
            ("topic_gaming", 122),
            ("topic_education", 98),
            ("topic_entertainment", 87),
            ("topic_technology", 76),
        ]
    )
    relevance_type_distribution: Any = factory.LazyFunction(
        lambda: {"primary": 65, "relevant": 28, "suggested": 12}
    )


# Convenience factory methods
def create_video_topic(**kwargs: Any) -> VideoTopic:
    """Create a VideoTopic with keyword arguments."""
    result = VideoTopicFactory.build(**kwargs)
    assert isinstance(result, VideoTopic)
    return result


def create_video_topic_create(**kwargs: Any) -> VideoTopicCreate:
    """Create a VideoTopicCreate with keyword arguments."""
    result = VideoTopicCreateFactory.build(**kwargs)
    assert isinstance(result, VideoTopicCreate)
    return result


def create_video_topic_update(**kwargs: Any) -> VideoTopicUpdate:
    """Create a VideoTopicUpdate with keyword arguments."""
    result = VideoTopicUpdateFactory.build(**kwargs)
    assert isinstance(result, VideoTopicUpdate)
    return result


def create_video_topic_filters(**kwargs: Any) -> VideoTopicSearchFilters:
    """Create VideoTopicSearchFilters with keyword arguments."""
    result = VideoTopicSearchFiltersFactory.build(**kwargs)
    assert isinstance(result, VideoTopicSearchFilters)
    return result


def create_video_topic_statistics(**kwargs: Any) -> VideoTopicStatistics:
    """Create VideoTopicStatistics with keyword arguments."""
    result = VideoTopicStatisticsFactory.build(**kwargs)
    assert isinstance(result, VideoTopicStatistics)
    return result


# Common test data patterns
class VideoTopicTestData:
    """Common test data patterns for VideoTopic models."""

    VALID_VIDEO_IDS = ["dQw4w9WgXcQ", "9bZkp7q19f0", "jNQXAC9IVRw", "astISOttCQ0"]

    VALID_TOPIC_IDS = [
        "topic_music",
        "topic_gaming",
        "topic_education",
        "topic_entertainment",
        "topic_technology",
        "topic_sports",
        "topic_news",
        "topic_comedy",
        "topic_science",
        "topic_travel",
    ]

    VALID_RELEVANCE_TYPES = ["primary", "relevant", "suggested"]

    INVALID_VIDEO_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short
        "x" * 25,  # Too long
    ]

    INVALID_TOPIC_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "x" * 51,  # Too long
    ]

    INVALID_RELEVANCE_TYPES = [
        "",  # Empty
        "   ",  # Whitespace
        "invalid",  # Not in allowed list
        "PRIMARY",  # Wrong case
    ]

    @classmethod
    def valid_video_topic_data(cls) -> dict[str, Any]:
        """Get valid video topic data."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[0],
            "topic_id": cls.VALID_TOPIC_IDS[0],
            "relevance_type": cls.VALID_RELEVANCE_TYPES[0],
        }

    @classmethod
    def minimal_video_topic_data(cls) -> dict[str, Any]:
        """Get minimal valid video topic data."""
        return {"video_id": cls.VALID_VIDEO_IDS[1], "topic_id": cls.VALID_TOPIC_IDS[1]}

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict[str, Any]:
        """Get comprehensive search filters data."""
        return {
            "video_ids": cls.VALID_VIDEO_IDS[:2],
            "topic_ids": cls.VALID_TOPIC_IDS[:3],
            "relevance_types": cls.VALID_RELEVANCE_TYPES[:2],
            "created_after": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "created_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
        }
