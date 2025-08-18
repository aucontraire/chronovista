"""
Factory for ChannelTopic models using factory_boy.

Provides reusable test data factories for all ChannelTopic model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import factory
from factory import Faker, LazyAttribute

from chronovista.models.channel_topic import (
    ChannelTopic,
    ChannelTopicBase,
    ChannelTopicCreate,
    ChannelTopicSearchFilters,
    ChannelTopicStatistics,
    ChannelTopicUpdate,
)


class ChannelTopicBaseFactory(factory.Factory):
    """Factory for ChannelTopicBase models."""

    class Meta:
        model = ChannelTopicBase

    channel_id = Faker(
        "lexify", text="UC??????????????????????"
    )  # 24-char channel ID pattern
    topic_id = Faker("lexify", text="topic_????????????????")  # Valid topic ID pattern


class ChannelTopicCreateFactory(ChannelTopicBaseFactory):
    """Factory for ChannelTopicCreate models."""

    class Meta:
        model = ChannelTopicCreate


class ChannelTopicUpdateFactory(factory.Factory):
    """Factory for ChannelTopicUpdate models."""

    class Meta:
        model = ChannelTopicUpdate

    # Channel topics are typically static, but we keep this for consistency


class ChannelTopicFactory(ChannelTopicBaseFactory):
    """Factory for full ChannelTopic models."""

    class Meta:
        model = ChannelTopic

    created_at = Faker("date_time", tzinfo=timezone.utc)


class ChannelTopicSearchFiltersFactory(factory.Factory):
    """Factory for ChannelTopicSearchFilters models."""

    class Meta:
        model = ChannelTopicSearchFilters

    channel_ids = factory.LazyFunction(
        lambda: ["UCuAXFkgsw1L7xaCfnd5JJOw", "UC_x5XG1OV2P6uZZ5FSM9Ttw"]
    )
    topic_ids = factory.LazyFunction(
        lambda: ["topic_music", "topic_gaming", "topic_education"]
    )
    created_after = Faker("date_time", tzinfo=timezone.utc)
    created_before = Faker("date_time", tzinfo=timezone.utc)


class ChannelTopicStatisticsFactory(factory.Factory):
    """Factory for ChannelTopicStatistics models."""

    class Meta:
        model = ChannelTopicStatistics

    total_channel_topics = Faker("random_int", min=50, max=5000)
    unique_topics = LazyAttribute(
        lambda obj: int(obj.total_channel_topics * 0.4)
    )  # 40% unique
    unique_channels = LazyAttribute(
        lambda obj: int(obj.total_channel_topics * 0.9)
    )  # 90% unique
    avg_topics_per_channel = Faker(
        "pyfloat", min_value=1.0, max_value=6.0, right_digits=2
    )
    most_common_topics = factory.LazyFunction(
        lambda: [
            ("topic_music", 85),
            ("topic_gaming", 72),
            ("topic_education", 58),
            ("topic_entertainment", 45),
            ("topic_technology", 39),
        ]
    )
    topic_distribution = factory.LazyFunction(
        lambda: {
            "topic_music": 45,
            "topic_gaming": 38,
            "topic_education": 32,
            "topic_entertainment": 28,
            "topic_technology": 25,
        }
    )


# Convenience factory methods
def create_channel_topic(**kwargs) -> ChannelTopic:
    """Create a ChannelTopic with keyword arguments."""
    return cast(ChannelTopic, ChannelTopicFactory.build(**kwargs))


def create_channel_topic_create(**kwargs) -> ChannelTopicCreate:
    """Create a ChannelTopicCreate with keyword arguments."""
    return cast(ChannelTopicCreate, ChannelTopicCreateFactory.build(**kwargs))


def create_channel_topic_update(**kwargs) -> ChannelTopicUpdate:
    """Create a ChannelTopicUpdate with keyword arguments."""
    return cast(ChannelTopicUpdate, ChannelTopicUpdateFactory.build(**kwargs))


def create_channel_topic_filters(**kwargs) -> ChannelTopicSearchFilters:
    """Create ChannelTopicSearchFilters with keyword arguments."""
    return cast(
        ChannelTopicSearchFilters, ChannelTopicSearchFiltersFactory.build(**kwargs)
    )


def create_channel_topic_statistics(**kwargs) -> ChannelTopicStatistics:
    """Create ChannelTopicStatistics with keyword arguments."""
    return cast(ChannelTopicStatistics, ChannelTopicStatisticsFactory.build(**kwargs))


# Common test data patterns
class ChannelTopicTestData:
    """Common test data patterns for ChannelTopic models."""

    VALID_CHANNEL_IDS = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",  # Rick Astley
        "UC_x5XG1OV2P6uZZ5FSM9Ttw",  # Google Developers
        "UCMtFAi84ehTSYSE9XoHefig",  # Late Show
        "UCblfuW_4rakIf2h6aqANefA",  # Veritasium
    ]

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

    INVALID_CHANNEL_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "UC123",  # Too short
        "x" * 25,  # Too long
    ]

    INVALID_TOPIC_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "x" * 51,  # Too long
    ]

    @classmethod
    def valid_channel_topic_data(cls) -> dict:
        """Get valid channel topic data."""
        return {
            "channel_id": cls.VALID_CHANNEL_IDS[0],
            "topic_id": cls.VALID_TOPIC_IDS[0],
        }

    @classmethod
    def minimal_channel_topic_data(cls) -> dict:
        """Get minimal valid channel topic data."""
        return {
            "channel_id": cls.VALID_CHANNEL_IDS[1],
            "topic_id": cls.VALID_TOPIC_IDS[1],
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict:
        """Get comprehensive search filters data."""
        return {
            "channel_ids": cls.VALID_CHANNEL_IDS[:2],
            "topic_ids": cls.VALID_TOPIC_IDS[:3],
            "created_after": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "created_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
        }
