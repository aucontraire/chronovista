"""
Factory for ChannelKeyword models using factory_boy.

Provides reusable test data factories for all ChannelKeyword model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import factory
from factory import Faker, LazyAttribute

from chronovista.models.channel_keyword import (
    ChannelKeyword,
    ChannelKeywordAnalytics,
    ChannelKeywordBase,
    ChannelKeywordCreate,
    ChannelKeywordSearchFilters,
    ChannelKeywordStatistics,
    ChannelKeywordUpdate,
)


class ChannelKeywordBaseFactory(factory.Factory[ChannelKeywordBase]):
    """Factory for ChannelKeywordBase models."""

    class Meta:
        model = ChannelKeywordBase

    channel_id: Any = Faker(
        "lexify", text="UC??????????????????????"
    )  # YouTube channel ID pattern (24 chars: UC + 22 ?)
    keyword: Any = Faker("word")
    keyword_order: Any = Faker("random_int", min=0, max=50)


class ChannelKeywordCreateFactory(ChannelKeywordBaseFactory):
    """Factory for ChannelKeywordCreate models."""

    class Meta:
        model = ChannelKeywordCreate


class ChannelKeywordUpdateFactory(factory.Factory[ChannelKeywordUpdate]):
    """Factory for ChannelKeywordUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = ChannelKeywordUpdate

    # No default values - respects model defaults (None for all fields)
    # Values will only be generated when explicitly passed to build()


class ChannelKeywordFactory(ChannelKeywordBaseFactory):
    """Factory for full ChannelKeyword models."""

    class Meta:
        model = ChannelKeyword

    created_at: Any = Faker("date_time", tzinfo=timezone.utc)


class ChannelKeywordSearchFiltersFactory(factory.Factory[ChannelKeywordSearchFilters]):
    """Factory for ChannelKeywordSearchFilters models."""

    class Meta:
        model = ChannelKeywordSearchFilters

    channel_ids: Any = factory.LazyFunction(
        lambda: ["UCuAXFkgsw1L7xaCfnd5JJOw", "UC-lHJZR3Gqxm24_Vd_AJ5Yw"]
    )
    keywords: Any = factory.LazyFunction(lambda: ["gaming", "technology", "tutorial"])
    keyword_pattern: Any = Faker("word")
    min_keyword_order: Any = Faker("random_int", min=0, max=5)
    max_keyword_order: Any = Faker("random_int", min=6, max=20)
    has_order: Any = Faker("boolean")
    created_after: Any = Faker("date_time", tzinfo=timezone.utc)
    created_before: Any = Faker("date_time", tzinfo=timezone.utc)


class ChannelKeywordStatisticsFactory(factory.Factory[ChannelKeywordStatistics]):
    """Factory for ChannelKeywordStatistics models."""

    class Meta:
        model = ChannelKeywordStatistics

    total_keywords: Any = Faker("random_int", min=100, max=5000)
    unique_keywords: Any = LazyAttribute(
        lambda obj: int(obj.total_keywords * 0.8)
    )  # 80% unique
    unique_channels: Any = Faker("random_int", min=50, max=500)
    avg_keywords_per_channel: Any = LazyAttribute(
        lambda obj: round(obj.total_keywords / obj.unique_channels, 2)
    )
    most_common_keywords: Any = factory.LazyFunction(
        lambda: [
            ("gaming", 95),
            ("tech", 88),
            ("tutorial", 76),
            ("review", 65),
            ("music", 52),
        ]
    )
    keyword_distribution: Any = factory.LazyFunction(
        lambda: {"gaming": 45, "tech": 38, "tutorial": 32, "review": 28, "music": 25}
    )
    channels_with_ordered_keywords: Any = LazyAttribute(
        lambda obj: int(obj.unique_channels * 0.6)
    )  # 60% have ordered keywords


class ChannelKeywordAnalyticsFactory(factory.Factory[ChannelKeywordAnalytics]):
    """Factory for ChannelKeywordAnalytics models."""

    class Meta:
        model = ChannelKeywordAnalytics

    keyword_trends: Any = factory.LazyFunction(
        lambda: {
            "gaming": [12, 15, 18, 20, 22, 19, 17, 21, 24, 26, 23, 25],
            "tech": [8, 10, 12, 14, 16, 15, 13, 17, 19, 18, 20, 22],
        }
    )
    semantic_clusters: Any = factory.LazyFunction(
        lambda: [
            {
                "cluster_id": 0,
                "keywords": ["gaming", "esports", "streaming"],
                "similarity": 0.85,
            },
            {
                "cluster_id": 1,
                "keywords": ["tech", "programming", "software"],
                "similarity": 0.78,
            },
            {
                "cluster_id": 2,
                "keywords": ["tutorial", "education", "learning"],
                "similarity": 0.72,
            },
        ]
    )
    topic_keywords: Any = factory.LazyFunction(
        lambda: {
            "entertainment": ["gaming", "music", "comedy", "vlogs", "streaming"],
            "education": ["tutorial", "science", "math", "history", "language"],
            "technology": ["programming", "software", "hardware", "AI", "web"],
            "lifestyle": ["travel", "food", "fashion", "fitness", "health"],
        }
    )
    keyword_similarity: Any = factory.LazyFunction(
        lambda: {
            "gaming-esports": 0.92,
            "tech-programming": 0.88,
            "tutorial-education": 0.85,
            "music-entertainment": 0.79,
            "science-education": 0.75,
            "AI-technology": 0.82,
            "fitness-health": 0.71,
            "travel-lifestyle": 0.68,
            "comedy-entertainment": 0.73,
            "software-programming": 0.89,
        }
    )


# Convenience factory methods
def create_channel_keyword(**kwargs: Any) -> ChannelKeyword:
    """Create a ChannelKeyword with keyword arguments."""
    result = ChannelKeywordFactory.build(**kwargs)
    assert isinstance(result, ChannelKeyword)
    return result


def create_channel_keyword_create(**kwargs: Any) -> ChannelKeywordCreate:
    """Create a ChannelKeywordCreate with keyword arguments."""
    result = ChannelKeywordCreateFactory.build(**kwargs)
    assert isinstance(result, ChannelKeywordCreate)
    return result


def create_channel_keyword_update(**kwargs: Any) -> ChannelKeywordUpdate:
    """Create a ChannelKeywordUpdate with keyword arguments."""
    result = ChannelKeywordUpdateFactory.build(**kwargs)
    assert isinstance(result, ChannelKeywordUpdate)
    return result


def create_channel_keyword_filters(**kwargs: Any) -> ChannelKeywordSearchFilters:
    """Create ChannelKeywordSearchFilters with keyword arguments."""
    result = ChannelKeywordSearchFiltersFactory.build(**kwargs)
    assert isinstance(result, ChannelKeywordSearchFilters)
    return result


def create_channel_keyword_statistics(**kwargs: Any) -> ChannelKeywordStatistics:
    """Create ChannelKeywordStatistics with keyword arguments."""
    result = ChannelKeywordStatisticsFactory.build(**kwargs)
    assert isinstance(result, ChannelKeywordStatistics)
    return result


def create_channel_keyword_analytics(**kwargs: Any) -> ChannelKeywordAnalytics:
    """Create ChannelKeywordAnalytics with keyword arguments."""
    result = ChannelKeywordAnalyticsFactory.build(**kwargs)
    assert isinstance(result, ChannelKeywordAnalytics)
    return result


# Common test data patterns
class ChannelKeywordTestData:
    """Common test data patterns for ChannelKeyword models."""

    VALID_CHANNEL_IDS = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",
        "UC-lHJZR3Gqxm24_Vd_AJ5Yw",
        "UCBJycsmduvYEL83R_U4JriQ",
        "UCsXVk37bltHxD1rDPwtNM8Q",
    ]

    VALID_KEYWORDS = [
        "gaming",
        "technology",
        "tutorial",
        "review",
        "unboxing",
        "programming",
        "music",
        "entertainment",
        "education",
        "science",
        "how-to",
        "DIY",
        "coding",
        "software",
        "hardware",
    ]

    INVALID_CHANNEL_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short
        "x" * 25,  # Too long
        "invalidformat",  # Invalid format
        "12345678901234567890",  # Numbers only
    ]

    INVALID_KEYWORDS = [
        "",  # Empty
        "   ",  # Whitespace
        "x" * 101,  # Too long
    ]

    @classmethod
    def valid_channel_keyword_data(cls) -> dict[str, Any]:
        """Get valid channel keyword data."""
        return {
            "channel_id": cls.VALID_CHANNEL_IDS[0],
            "keyword": cls.VALID_KEYWORDS[0],
            "keyword_order": 1,
        }

    @classmethod
    def minimal_channel_keyword_data(cls) -> dict[str, Any]:
        """Get minimal valid channel keyword data."""
        return {
            "channel_id": cls.VALID_CHANNEL_IDS[1],
            "keyword": cls.VALID_KEYWORDS[1],
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict[str, Any]:
        """Get comprehensive search filters data."""
        return {
            "channel_ids": cls.VALID_CHANNEL_IDS[:2],
            "keywords": cls.VALID_KEYWORDS[:3],
            "keyword_pattern": "tech",
            "min_keyword_order": 1,
            "max_keyword_order": 10,
            "has_order": True,
            "created_after": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "created_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
        }
