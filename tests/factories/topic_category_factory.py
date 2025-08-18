"""
Factory for TopicCategory models using factory_boy.

Provides reusable test data factories for all TopicCategory model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

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


class TopicCategoryBaseFactory(factory.Factory):
    """Factory for TopicCategoryBase models."""

    class Meta:
        model = TopicCategoryBase

    topic_id = Faker("lexify", text="topic_????")  # e.g., topic_1234
    category_name = Faker("word")
    parent_topic_id = None  # Most topics are root by default
    topic_type = Faker("random_element", elements=["youtube", "custom"])


class TopicCategoryCreateFactory(TopicCategoryBaseFactory):
    """Factory for TopicCategoryCreate models."""

    class Meta:
        model = TopicCategoryCreate


class TopicCategoryUpdateFactory(factory.Factory):
    """Factory for TopicCategoryUpdate models."""

    class Meta:
        model = TopicCategoryUpdate

    category_name = Faker("word")
    parent_topic_id = None
    topic_type = Faker("random_element", elements=["youtube", "custom"])


class TopicCategoryFactory(TopicCategoryBaseFactory):
    """Factory for full TopicCategory models."""

    class Meta:
        model = TopicCategory

    created_at = Faker("date_time", tzinfo=timezone.utc)


class TopicCategorySearchFiltersFactory(factory.Factory):
    """Factory for TopicCategorySearchFilters models."""

    class Meta:
        model = TopicCategorySearchFilters

    topic_ids = factory.LazyFunction(lambda: ["gaming", "tech", "education"])
    category_name_query = Faker("word")
    parent_topic_ids = factory.LazyFunction(lambda: ["entertainment", "technology"])
    topic_types = factory.LazyFunction(lambda: ["youtube", "custom"])
    is_root_topic = Faker("boolean")
    has_children = Faker("boolean")
    max_depth = Faker("random_int", min=1, max=5)
    created_after = Faker("date_time", tzinfo=timezone.utc)
    created_before = Faker("date_time", tzinfo=timezone.utc)


class TopicCategoryStatisticsFactory(factory.Factory):
    """Factory for TopicCategoryStatistics models."""

    class Meta:
        model = TopicCategoryStatistics

    total_topics = Faker("random_int", min=50, max=500)
    root_topics = LazyAttribute(
        lambda obj: int(obj.total_topics * 0.2)
    )  # 20% are root topics
    max_hierarchy_depth = Faker("random_int", min=2, max=6)
    avg_children_per_topic = LazyAttribute(
        lambda obj: round((obj.total_topics - obj.root_topics) / obj.root_topics, 2)
    )
    topic_type_distribution = factory.LazyFunction(
        lambda: {"youtube": 180, "custom": 120}
    )
    most_popular_topics = factory.LazyFunction(
        lambda: [
            ("gaming", 45),
            ("music", 38),
            ("tech", 32),
            ("education", 28),
            ("entertainment", 25),
        ]
    )
    hierarchy_distribution = factory.LazyFunction(
        lambda: {
            0: 20,
            1: 45,
            2: 30,
            3: 15,
            4: 5,
        }  # Level 0 = roots, decreasing by level
    )


class TopicCategoryHierarchyFactory(factory.Factory):
    """Factory for TopicCategoryHierarchy models."""

    class Meta:
        model = TopicCategoryHierarchy

    topic_id = Faker("lexify", text="topic_????")
    category_name = Faker("word")
    topic_type = Faker("random_element", elements=["youtube", "custom"])
    level = Faker("random_int", min=0, max=3)
    children = factory.LazyFunction(lambda: [])  # Empty by default
    path = factory.LazyFunction(lambda: ["root", "entertainment"])


class TopicCategoryAnalyticsFactory(factory.Factory):
    """Factory for TopicCategoryAnalytics models."""

    class Meta:
        model = TopicCategoryAnalytics

    topic_trends = factory.LazyFunction(
        lambda: {
            "gaming": [10, 12, 15, 18, 20, 22, 25, 28, 30, 32, 35, 38],
            "music": [8, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29],
        }
    )
    topic_relationships = factory.LazyFunction(
        lambda: {
            "gaming": ["esports", "streaming", "reviews"],
            "music": ["pop", "rock", "classical", "playlists"],
            "education": ["tutorial", "science", "math", "language"],
        }
    )
    semantic_similarity = factory.LazyFunction(
        lambda: {
            "gaming-esports": 0.92,
            "music-entertainment": 0.78,
            "education-tutorial": 0.85,
            "tech-programming": 0.88,
            "fitness-health": 0.72,
        }
    )
    content_classification = factory.LazyFunction(
        lambda: {
            "gaming": {"entertainment": 0.95, "technology": 0.75, "education": 0.25},
            "tutorial": {"education": 0.92, "technology": 0.65, "entertainment": 0.35},
            "music": {"entertainment": 0.98, "arts": 0.88, "culture": 0.65},
        }
    )


# Convenience factory methods
def create_topic_category(**kwargs) -> TopicCategory:
    """Create a TopicCategory with keyword arguments."""
    return cast(TopicCategory, TopicCategoryFactory.build(**kwargs))


def create_topic_category_create(**kwargs) -> TopicCategoryCreate:
    """Create a TopicCategoryCreate with keyword arguments."""
    return cast(TopicCategoryCreate, TopicCategoryCreateFactory.build(**kwargs))


def create_topic_category_update(**kwargs) -> TopicCategoryUpdate:
    """Create a TopicCategoryUpdate with keyword arguments."""
    return cast(TopicCategoryUpdate, TopicCategoryUpdateFactory.build(**kwargs))


def create_topic_category_filters(**kwargs) -> TopicCategorySearchFilters:
    """Create TopicCategorySearchFilters with keyword arguments."""
    return cast(
        TopicCategorySearchFilters, TopicCategorySearchFiltersFactory.build(**kwargs)
    )


def create_topic_category_statistics(**kwargs) -> TopicCategoryStatistics:
    """Create TopicCategoryStatistics with keyword arguments."""
    return cast(TopicCategoryStatistics, TopicCategoryStatisticsFactory.build(**kwargs))


def create_topic_category_hierarchy(**kwargs) -> TopicCategoryHierarchy:
    """Create TopicCategoryHierarchy with keyword arguments."""
    return cast(TopicCategoryHierarchy, TopicCategoryHierarchyFactory.build(**kwargs))


def create_topic_category_analytics(**kwargs) -> TopicCategoryAnalytics:
    """Create TopicCategoryAnalytics with keyword arguments."""
    return cast(TopicCategoryAnalytics, TopicCategoryAnalyticsFactory.build(**kwargs))


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
    def valid_topic_category_data(cls) -> dict:
        """Get valid topic category data."""
        return {
            "topic_id": cls.VALID_TOPIC_IDS[0],
            "category_name": cls.VALID_CATEGORY_NAMES[0],
            "parent_topic_id": None,
            "topic_type": "youtube",
        }

    @classmethod
    def hierarchical_topic_data(cls) -> dict:
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
    def custom_topic_data(cls) -> dict:
        """Get custom topic data."""
        return {
            "topic_id": "custom_ai_ml",
            "category_name": "AI & Machine Learning",
            "parent_topic_id": "technology",
            "topic_type": "custom",
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict:
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
    def hierarchy_tree_data(cls) -> dict:
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
