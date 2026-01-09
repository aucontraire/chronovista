"""
Factory for TopicCategory models using factory_boy.

Provides reusable test data factories for all TopicCategory model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import factory
from factory import Faker, LazyAttribute

from chronovista.models.topic_category import (
    TopicCategory,
    TopicCategoryAnalytics,
    TopicCategoryBase,
    TopicCategoryCreate,
    TopicCategoryHierarchy,
    TopicCategorySearchFilters,
    TopicCategoryStatistics,
    TopicCategoryUpdate,
)


class TopicCategoryBaseFactory(factory.Factory[TopicCategoryBase]):
    """Factory for TopicCategoryBase models."""

    class Meta:
        model = TopicCategoryBase

    topic_id: Any = Faker("lexify", text="topic_????")  # e.g., topic_1234
    category_name: Any = Faker("word")
    parent_topic_id = None  # Most topics are root by default
    topic_type: Any = Faker("random_element", elements=["youtube", "custom"])


class TopicCategoryCreateFactory(TopicCategoryBaseFactory):
    """Factory for TopicCategoryCreate models."""

    class Meta:
        model = TopicCategoryCreate


class TopicCategoryUpdateFactory(factory.Factory[TopicCategoryUpdate]):
    """Factory for TopicCategoryUpdate models."""

    class Meta:
        model = TopicCategoryUpdate

    category_name: Any = Faker("word")
    parent_topic_id = None
    topic_type: Any = Faker("random_element", elements=["youtube", "custom"])


class TopicCategoryFactory(TopicCategoryBaseFactory):
    """Factory for full TopicCategory models."""

    class Meta:
        model = TopicCategory

    created_at: Any = Faker("date_time", tzinfo=timezone.utc)


class TopicCategorySearchFiltersFactory(factory.Factory[TopicCategorySearchFilters]):
    """Factory for TopicCategorySearchFilters models."""

    class Meta:
        model = TopicCategorySearchFilters

    topic_ids: Any = factory.LazyFunction(lambda: ["gaming", "tech", "education"])
    category_name_query: Any = Faker("word")
    parent_topic_ids: Any = factory.LazyFunction(lambda: ["entertainment", "technology"])
    topic_types: Any = factory.LazyFunction(lambda: ["youtube", "custom"])
    is_root_topic: Any = Faker("boolean")
    has_children: Any = Faker("boolean")
    max_depth: Any = Faker("random_int", min=1, max=5)
    created_after: Any = Faker("date_time", tzinfo=timezone.utc)
    created_before: Any = Faker("date_time", tzinfo=timezone.utc)


class TopicCategoryStatisticsFactory(factory.Factory[TopicCategoryStatistics]):
    """Factory for TopicCategoryStatistics models."""

    class Meta:
        model = TopicCategoryStatistics

    total_topics: Any = Faker("random_int", min=50, max=500)
    root_topics: Any = LazyAttribute(
        lambda obj: int(obj.total_topics * 0.2)
    )  # 20% are root topics
    max_hierarchy_depth: Any = Faker("random_int", min=2, max=6)
    avg_children_per_topic: Any = LazyAttribute(
        lambda obj: round((obj.total_topics - obj.root_topics) / obj.root_topics, 2)
    )
    topic_type_distribution: Any = factory.LazyFunction(
        lambda: {"youtube": 180, "custom": 120}
    )
    most_popular_topics: Any = factory.LazyFunction(
        lambda: [
            ("gaming", 45),
            ("music", 38),
            ("tech", 32),
            ("education", 28),
            ("entertainment", 25),
        ]
    )
    hierarchy_distribution: Any = factory.LazyFunction(
        lambda: {
            0: 20,
            1: 45,
            2: 30,
            3: 15,
            4: 5,
        }  # Level 0 = roots, decreasing by level
    )


class TopicCategoryHierarchyFactory(factory.Factory[TopicCategoryHierarchy]):
    """Factory for TopicCategoryHierarchy models."""

    class Meta:
        model = TopicCategoryHierarchy

    topic_id: Any = Faker("lexify", text="topic_????")
    category_name: Any = Faker("word")
    topic_type: Any = Faker("random_element", elements=["youtube", "custom"])
    level: Any = Faker("random_int", min=0, max=3)
    children: Any = factory.LazyFunction(lambda: [])  # Empty by default
    path: Any = factory.LazyFunction(lambda: ["root", "entertainment"])


class TopicCategoryAnalyticsFactory(factory.Factory[TopicCategoryAnalytics]):
    """Factory for TopicCategoryAnalytics models."""

    class Meta:
        model = TopicCategoryAnalytics

    topic_trends: Any = factory.LazyFunction(
        lambda: {
            "gaming": [10, 12, 15, 18, 20, 22, 25, 28, 30, 32, 35, 38],
            "music": [8, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29],
        }
    )
    topic_relationships: Any = factory.LazyFunction(
        lambda: {
            "gaming": ["esports", "streaming", "reviews"],
            "music": ["pop", "rock", "classical", "playlists"],
            "education": ["tutorial", "science", "math", "language"],
        }
    )
    semantic_similarity: Any = factory.LazyFunction(
        lambda: {
            "gaming-esports": 0.92,
            "music-entertainment": 0.78,
            "education-tutorial": 0.85,
            "tech-programming": 0.88,
            "fitness-health": 0.72,
        }
    )
    content_classification: Any = factory.LazyFunction(
        lambda: {
            "gaming": {"entertainment": 0.95, "technology": 0.75, "education": 0.25},
            "tutorial": {"education": 0.92, "technology": 0.65, "entertainment": 0.35},
            "music": {"entertainment": 0.98, "arts": 0.88, "culture": 0.65},
        }
    )


# Convenience factory methods
def create_topic_category(**kwargs: Any) -> TopicCategory:
    """Create a TopicCategory with keyword arguments."""
    result = TopicCategoryFactory.build(**kwargs)
    assert isinstance(result, TopicCategory)
    return result


def create_topic_category_create(**kwargs: Any) -> TopicCategoryCreate:
    """Create a TopicCategoryCreate with keyword arguments."""
    result = TopicCategoryCreateFactory.build(**kwargs)
    assert isinstance(result, TopicCategoryCreate)
    return result


def create_topic_category_update(**kwargs: Any) -> TopicCategoryUpdate:
    """Create a TopicCategoryUpdate with keyword arguments."""
    result = TopicCategoryUpdateFactory.build(**kwargs)
    assert isinstance(result, TopicCategoryUpdate)
    return result


def create_topic_category_filters(**kwargs: Any) -> TopicCategorySearchFilters:
    """Create TopicCategorySearchFilters with keyword arguments."""
    result = TopicCategorySearchFiltersFactory.build(**kwargs)
    assert isinstance(result, TopicCategorySearchFilters)
    return result


def create_topic_category_statistics(**kwargs: Any) -> TopicCategoryStatistics:
    """Create TopicCategoryStatistics with keyword arguments."""
    result = TopicCategoryStatisticsFactory.build(**kwargs)
    assert isinstance(result, TopicCategoryStatistics)
    return result


def create_topic_category_hierarchy(**kwargs: Any) -> TopicCategoryHierarchy:
    """Create TopicCategoryHierarchy with keyword arguments."""
    result = TopicCategoryHierarchyFactory.build(**kwargs)
    assert isinstance(result, TopicCategoryHierarchy)
    return result


def create_topic_category_analytics(**kwargs: Any) -> TopicCategoryAnalytics:
    """Create TopicCategoryAnalytics with keyword arguments."""
    result = TopicCategoryAnalyticsFactory.build(**kwargs)
    assert isinstance(result, TopicCategoryAnalytics)
    return result


# Common test data patterns
class TopicCategoryTestData:
    """Common test data patterns for TopicCategory models."""

    VALID_TOPIC_IDS = [
        "gaming",
        "music",
        "tech",
        "education",
        "entertainment",
        "sports",
        "cooking",
        "travel",
        "fitness",
        "science",
        "art",
        "business",
        "finance",
        "health",
        "politics",
    ]

    VALID_CATEGORY_NAMES = [
        "Gaming",
        "Music & Audio",
        "Technology",
        "Education",
        "Entertainment",
        "Sports",
        "Food & Cooking",
        "Travel & Events",
        "Fitness & Health",
        "Science & Technology",
        "Arts & Crafts",
        "Business",
        "Finance",
        "Health & Wellness",
        "News & Politics",
    ]

    HIERARCHICAL_TOPICS = [
        # Root level topics
        ("entertainment", "Entertainment", None),
        ("technology", "Technology", None),
        ("education", "Education", None),
        # Second level
        ("gaming", "Gaming", "entertainment"),
        ("music", "Music", "entertainment"),
        ("programming", "Programming", "technology"),
        ("hardware", "Hardware", "technology"),
        ("tutorial", "Tutorials", "education"),
        ("science", "Science", "education"),
        # Third level
        ("esports", "Esports", "gaming"),
        ("indie-games", "Indie Games", "gaming"),
        ("pop-music", "Pop Music", "music"),
        ("classical", "Classical Music", "music"),
        ("web-dev", "Web Development", "programming"),
        ("mobile-dev", "Mobile Development", "programming"),
    ]

    INVALID_TOPIC_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "topic with spaces",  # Spaces not allowed
        "topic@invalid",  # Special characters
        "topic.invalid",  # Dots not allowed
        "x" * 51,  # Too long
    ]

    INVALID_CATEGORY_NAMES = [
        "",  # Empty
        "   ",  # Whitespace
        "x" * 256,  # Too long
    ]

    YOUTUBE_OFFICIAL_TOPICS = [
        ("film_animation", "Film & Animation"),
        ("autos_vehicles", "Autos & Vehicles"),
        ("music", "Music"),
        ("pets_animals", "Pets & Animals"),
        ("sports", "Sports"),
        ("travel_events", "Travel & Events"),
        ("gaming", "Gaming"),
        ("people_blogs", "People & Blogs"),
        ("comedy", "Comedy"),
        ("entertainment", "Entertainment"),
        ("news_politics", "News & Politics"),
        ("howto_style", "Howto & Style"),
        ("education", "Education"),
        ("science_technology", "Science & Technology"),
        ("nonprofits_activism", "Nonprofits & Activism"),
    ]

    @classmethod
    def valid_topic_category_data(cls) -> dict[str, Any]:
        """Get valid topic category data."""
        return {
            "topic_id": cls.VALID_TOPIC_IDS[0],
            "category_name": cls.VALID_CATEGORY_NAMES[0],
            "parent_topic_id": None,
            "topic_type": "youtube",
        }

    @classmethod
    def hierarchical_topic_data(cls) -> dict[str, Any]:
        """Get hierarchical topic data."""
        topic_id, category_name, parent_id = cls.HIERARCHICAL_TOPICS[
            5
        ]  # gaming -> entertainment
        return {
            "topic_id": topic_id,
            "category_name": category_name,
            "parent_topic_id": parent_id,
            "topic_type": "youtube",
        }

    @classmethod
    def custom_topic_data(cls) -> dict[str, Any]:
        """Get custom topic data."""
        return {
            "topic_id": "custom_ai_ml",
            "category_name": "AI & Machine Learning",
            "parent_topic_id": "technology",
            "topic_type": "custom",
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict[str, Any]:
        """Get comprehensive search filters data."""
        return {
            "topic_ids": cls.VALID_TOPIC_IDS[:3],
            "category_name_query": "tech",
            "parent_topic_ids": ["entertainment", "technology"],
            "topic_types": ["youtube", "custom"],
            "is_root_topic": False,
            "has_children": True,
            "max_depth": 3,
            "created_after": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "created_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
        }

    @classmethod
    def hierarchy_tree_data(cls) -> dict[str, Any]:
        """Get sample hierarchy tree data."""
        return {
            "topic_id": "entertainment",
            "category_name": "Entertainment",
            "topic_type": "youtube",
            "level": 0,
            "children": [
                {
                    "topic_id": "gaming",
                    "category_name": "Gaming",
                    "topic_type": "youtube",
                    "level": 1,
                    "children": [
                        {
                            "topic_id": "esports",
                            "category_name": "Esports",
                            "topic_type": "custom",
                            "level": 2,
                            "children": [],
                            "path": ["entertainment", "gaming", "esports"],
                        }
                    ],
                    "path": ["entertainment", "gaming"],
                }
            ],
            "path": ["entertainment"],
        }
