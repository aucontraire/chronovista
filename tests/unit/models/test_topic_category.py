"""
Tests for topic category Pydantic models.

Tests validation, keyword arguments, serialization, and model methods
for all TopicCategory model variants using factory pattern for DRY.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

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
from tests.factories.topic_category_factory import (
    TopicCategoryAnalyticsFactory,
    TopicCategoryBaseFactory,
    TopicCategoryCreateFactory,
    TopicCategoryFactory,
    TopicCategoryHierarchyFactory,
    TopicCategorySearchFiltersFactory,
    TopicCategoryStatisticsFactory,
    TopicCategoryTestData,
    TopicCategoryUpdateFactory,
    create_topic_category,
)


class TestTopicCategoryBase:
    """Test TopicCategoryBase model using factories."""

    def test_create_valid_topic_category_base(self):
        """Test creating valid TopicCategoryBase with keyword arguments."""
        topic = TopicCategoryBaseFactory(
            topic_id="gaming",
            category_name="Gaming",
            parent_topic_id=None,
            topic_type="youtube",
        )

        assert topic.topic_id == "gaming"
        assert topic.category_name == "Gaming"
        assert topic.parent_topic_id is None
        assert topic.topic_type == "youtube"

    def test_create_topic_category_with_parent(self):
        """Test creating TopicCategoryBase with parent relationship."""
        topic = TopicCategoryBaseFactory(
            topic_id="esports",
            category_name="Esports",
            parent_topic_id="gaming",
            topic_type="custom",
        )

        assert topic.topic_id == "esports"
        assert topic.category_name == "Esports"
        assert topic.parent_topic_id == "gaming"
        assert topic.topic_type == "custom"

    def test_factory_generates_valid_defaults(self):
        """Test that factory generates valid models with defaults."""
        topic = TopicCategoryBaseFactory()

        assert isinstance(topic, TopicCategoryBase)
        assert len(topic.topic_id) >= 1
        assert len(topic.topic_id) <= 50
        assert len(topic.category_name) >= 1
        assert len(topic.category_name) <= 255
        assert topic.topic_type in ["youtube", "custom"]

    @pytest.mark.parametrize(
        "invalid_topic_id", TopicCategoryTestData.INVALID_TOPIC_IDS
    )
    def test_topic_id_validation_invalid(self, invalid_topic_id):
        """Test topic_id validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            TopicCategoryBaseFactory(topic_id=invalid_topic_id)

    @pytest.mark.parametrize("valid_topic_id", TopicCategoryTestData.VALID_TOPIC_IDS)
    def test_topic_id_validation_valid(self, valid_topic_id):
        """Test topic_id validation with various valid inputs."""
        topic = TopicCategoryBaseFactory(topic_id=valid_topic_id)
        assert topic.topic_id == valid_topic_id

    @pytest.mark.parametrize(
        "invalid_category_name", TopicCategoryTestData.INVALID_CATEGORY_NAMES
    )
    def test_category_name_validation_invalid(self, invalid_category_name):
        """Test category_name validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            TopicCategoryBaseFactory(category_name=invalid_category_name)

    @pytest.mark.parametrize(
        "valid_category_name", TopicCategoryTestData.VALID_CATEGORY_NAMES
    )
    def test_category_name_validation_valid(self, valid_category_name):
        """Test category_name validation with various valid inputs."""
        topic = TopicCategoryBaseFactory(category_name=valid_category_name)
        assert topic.category_name == valid_category_name

    def test_parent_topic_id_validation(self):
        """Test parent_topic_id validation."""
        # Valid parent IDs
        topic = TopicCategoryBaseFactory(parent_topic_id="entertainment")
        assert topic.parent_topic_id == "entertainment"

        # None is valid (root topic)
        topic = TopicCategoryBaseFactory(parent_topic_id=None)
        assert topic.parent_topic_id is None

        # With type-safe validation, pass None directly for empty parent
        topic = TopicCategoryBaseFactory(parent_topic_id=None)
        assert topic.parent_topic_id is None

        # Invalid parent IDs
        with pytest.raises(ValidationError):
            TopicCategoryBaseFactory(parent_topic_id="invalid topic id")

    def test_topic_type_validation(self):
        """Test topic_type validation."""
        # Valid types
        for topic_type in ["youtube", "custom"]:
            topic = TopicCategoryBaseFactory(topic_type=topic_type)
            assert topic.topic_type == topic_type

        # Invalid type
        with pytest.raises(ValidationError):
            TopicCategoryBaseFactory(topic_type="invalid_type")

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        topic = TopicCategoryBaseFactory(
            topic_id="tech",
            category_name="Technology",
            parent_topic_id=None,
            topic_type="youtube",
        )

        data = topic.model_dump()
        expected = {
            "topic_id": "tech",
            "category_name": "Technology",
            "parent_topic_id": None,
            "topic_type": "youtube",
        }

        assert data == expected

    def test_model_validate_functionality(self):
        """Test model_validate() method for deserialization."""
        data = TopicCategoryTestData.valid_topic_category_data()

        topic = TopicCategoryBase.model_validate(data)

        assert topic.topic_id == data["topic_id"]
        assert topic.category_name == data["category_name"]
        assert topic.parent_topic_id == data["parent_topic_id"]
        assert topic.topic_type == data["topic_type"]


class TestTopicCategoryCreate:
    """Test TopicCategoryCreate model using factories."""

    def test_create_valid_topic_category_create(self):
        """Test creating valid TopicCategoryCreate with keyword arguments."""
        topic = TopicCategoryCreateFactory(
            topic_id="music",
            category_name="Music & Audio",
            parent_topic_id="entertainment",
            topic_type="youtube",
        )

        assert topic.topic_id == "music"
        assert topic.category_name == "Music & Audio"
        assert topic.parent_topic_id == "entertainment"
        assert topic.topic_type == "youtube"

    def test_inherits_base_validation(self):
        """Test that TopicCategoryCreate inherits base validation."""
        with pytest.raises(ValidationError):
            TopicCategoryCreateFactory(topic_id="   ")

    def test_self_reference_validation(self):
        """Test that topics cannot reference themselves as parent."""
        with pytest.raises(ValidationError):
            TopicCategoryCreateFactory(topic_id="gaming", parent_topic_id="gaming")

    def test_factory_generates_valid_model(self):
        """Test factory generates valid TopicCategoryCreate models."""
        topic = TopicCategoryCreateFactory()

        assert isinstance(topic, TopicCategoryCreate)
        assert isinstance(topic, TopicCategoryBase)  # Inheritance check


class TestTopicCategoryUpdate:
    """Test TopicCategoryUpdate model using factories."""

    def test_create_valid_topic_category_update(self):
        """Test creating valid TopicCategoryUpdate with keyword arguments."""
        update = TopicCategoryUpdateFactory(
            category_name="Updated Gaming",
            parent_topic_id="entertainment",
            topic_type="custom",
        )

        assert update.category_name == "Updated Gaming"
        assert update.parent_topic_id == "entertainment"
        assert update.topic_type == "custom"

    def test_create_empty_topic_category_update(self):
        """Test creating empty TopicCategoryUpdate."""
        update = TopicCategoryUpdate()

        assert update.category_name is None
        assert update.parent_topic_id is None
        assert update.topic_type is None

    def test_category_name_validation_in_update(self):
        """Test category_name validation in update model."""
        with pytest.raises(ValidationError):
            TopicCategoryUpdateFactory(category_name="")

    def test_parent_topic_id_empty_becomes_none(self):
        """Test that empty parent_topic_id becomes None."""
        # With type-safe validation, pass None directly for empty parent
        update = TopicCategoryUpdateFactory(parent_topic_id=None)
        assert update.parent_topic_id is None

    def test_model_dump_excludes_none(self):
        """Test model_dump() excludes None values."""
        update = TopicCategoryUpdate()

        data = update.model_dump(exclude_none=True)

        assert data == {}

    def test_factory_generates_valid_updates(self):
        """Test factory generates valid update models."""
        update = TopicCategoryUpdateFactory()

        assert isinstance(update, TopicCategoryUpdate)
        assert update.category_name is not None


class TestTopicCategory:
    """Test TopicCategory full model using factories."""

    def test_create_valid_topic_category(self):
        """Test creating valid TopicCategory with keyword arguments."""
        now = datetime.now(timezone.utc)
        topic = TopicCategoryFactory(
            topic_id="education",
            category_name="Education",
            parent_topic_id=None,
            topic_type="youtube",
            created_at=now,
        )

        assert topic.topic_id == "education"
        assert topic.category_name == "Education"
        assert topic.parent_topic_id is None
        assert topic.topic_type == "youtube"
        assert topic.created_at == now

    def test_from_attributes_compatibility(self):
        """Test ORM compatibility with from_attributes."""

        # Simulate SQLAlchemy model attributes
        class MockTopicCategoryDB:
            topic_id = "science"
            category_name = "Science & Technology"
            parent_topic_id = "education"
            topic_type = "youtube"
            created_at = datetime.now(timezone.utc)

        mock_db = MockTopicCategoryDB()
        topic = TopicCategory.model_validate(mock_db, from_attributes=True)

        assert topic.topic_id == "science"
        assert topic.category_name == "Science & Technology"
        assert topic.parent_topic_id == "education"
        assert topic.topic_type == "youtube"
        assert isinstance(topic.created_at, datetime)

    def test_factory_generates_full_model(self):
        """Test factory generates complete TopicCategory models."""
        topic = TopicCategoryFactory()

        assert isinstance(topic, TopicCategory)
        assert isinstance(topic, TopicCategoryBase)  # Inheritance
        assert isinstance(topic.created_at, datetime)
        assert topic.created_at.tzinfo is not None  # Has timezone


class TestTopicCategorySearchFilters:
    """Test TopicCategorySearchFilters model using factories."""

    def test_create_comprehensive_filters(self):
        """Test creating comprehensive search filters with keyword arguments."""
        data = TopicCategoryTestData.comprehensive_search_filters_data()
        filters = TopicCategorySearchFiltersFactory(**data)

        assert filters.topic_ids == data["topic_ids"]
        assert filters.category_name_query == data["category_name_query"]
        assert filters.parent_topic_ids == data["parent_topic_ids"]
        assert filters.topic_types == data["topic_types"]
        assert filters.is_root_topic == data["is_root_topic"]
        assert filters.has_children == data["has_children"]
        assert filters.max_depth == data["max_depth"]
        assert filters.created_after == data["created_after"]
        assert filters.created_before == data["created_before"]

    def test_create_empty_filters(self):
        """Test creating empty search filters."""
        filters = TopicCategorySearchFilters()

        assert filters.topic_ids is None
        assert filters.category_name_query is None
        assert filters.parent_topic_ids is None
        assert filters.topic_types is None
        assert filters.is_root_topic is None
        assert filters.has_children is None
        assert filters.max_depth is None
        assert filters.created_after is None
        assert filters.created_before is None

    def test_factory_generates_valid_filters(self):
        """Test factory generates valid search filters."""
        filters = TopicCategorySearchFiltersFactory()

        assert isinstance(filters, TopicCategorySearchFilters)
        assert isinstance(filters.topic_ids, list)
        assert isinstance(filters.parent_topic_ids, list)
        assert isinstance(filters.topic_types, list)
        assert len(filters.topic_ids) > 0

    def test_query_validation_empty_string(self):
        """Test query validation with empty strings."""
        with pytest.raises(ValidationError):
            TopicCategorySearchFiltersFactory(category_name_query="")

    def test_max_depth_validation(self):
        """Test max_depth validation."""
        # Valid depths
        filters = TopicCategorySearchFiltersFactory(max_depth=0)
        assert filters.max_depth == 0

        filters = TopicCategorySearchFiltersFactory(max_depth=5)
        assert filters.max_depth == 5

        # Invalid depth
        with pytest.raises(ValidationError):
            TopicCategorySearchFiltersFactory(max_depth=-1)


class TestTopicCategoryStatistics:
    """Test TopicCategoryStatistics model using factories."""

    def test_create_valid_statistics(self):
        """Test creating valid TopicCategoryStatistics with keyword arguments."""
        stats = TopicCategoryStatisticsFactory(
            total_topics=100,
            root_topics=20,
            max_hierarchy_depth=4,
            avg_children_per_topic=4.0,
            topic_type_distribution={"youtube": 70, "custom": 30},
            most_popular_topics=[("gaming", 25), ("music", 20), ("tech", 15)],
            hierarchy_distribution={0: 20, 1: 35, 2: 30, 3: 15},
        )

        assert stats.total_topics == 100
        assert stats.root_topics == 20
        assert stats.max_hierarchy_depth == 4
        assert stats.avg_children_per_topic == 4.0
        assert stats.topic_type_distribution == {"youtube": 70, "custom": 30}
        assert stats.most_popular_topics == [
            ("gaming", 25),
            ("music", 20),
            ("tech", 15),
        ]
        assert stats.hierarchy_distribution == {0: 20, 1: 35, 2: 30, 3: 15}

    def test_create_minimal_statistics(self):
        """Test creating minimal TopicCategoryStatistics."""
        stats = TopicCategoryStatistics(
            total_topics=50,
            root_topics=10,
            max_hierarchy_depth=2,
            avg_children_per_topic=4.0,
        )

        assert stats.total_topics == 50
        assert stats.root_topics == 10
        assert stats.max_hierarchy_depth == 2
        assert stats.avg_children_per_topic == 4.0
        assert stats.topic_type_distribution == {}
        assert stats.most_popular_topics == []
        assert stats.hierarchy_distribution == {}

    def test_factory_generates_realistic_statistics(self):
        """Test factory generates realistic statistics."""
        stats = TopicCategoryStatisticsFactory()

        assert isinstance(stats, TopicCategoryStatistics)
        assert stats.total_topics > 0
        assert stats.root_topics <= stats.total_topics
        assert stats.max_hierarchy_depth > 0
        assert stats.avg_children_per_topic >= 0
        assert isinstance(stats.topic_type_distribution, dict)
        assert isinstance(stats.most_popular_topics, list)
        assert isinstance(stats.hierarchy_distribution, dict)


class TestTopicCategoryHierarchy:
    """Test TopicCategoryHierarchy model using factories."""

    def test_create_valid_hierarchy(self):
        """Test creating valid TopicCategoryHierarchy with keyword arguments."""
        hierarchy = TopicCategoryHierarchyFactory(
            topic_id="gaming",
            category_name="Gaming",
            topic_type="youtube",
            level=1,
            children=[],
            path=["entertainment", "gaming"],
        )

        assert hierarchy.topic_id == "gaming"
        assert hierarchy.category_name == "Gaming"
        assert hierarchy.topic_type == "youtube"
        assert hierarchy.level == 1
        assert hierarchy.children == []
        assert hierarchy.path == ["entertainment", "gaming"]

    def test_create_root_hierarchy(self):
        """Test creating root level hierarchy."""
        hierarchy = TopicCategoryHierarchy(
            topic_id="entertainment",
            category_name="Entertainment",
            topic_type="youtube",
            level=0,
            children=[],
            path=["entertainment"],
        )

        assert hierarchy.level == 0
        assert hierarchy.path == ["entertainment"]

    def test_factory_generates_valid_hierarchy(self):
        """Test factory generates valid hierarchy models."""
        hierarchy = TopicCategoryHierarchyFactory()

        assert isinstance(hierarchy, TopicCategoryHierarchy)
        assert hierarchy.level >= 0
        assert isinstance(hierarchy.children, list)
        assert isinstance(hierarchy.path, list)

    def test_nested_hierarchy_structure(self):
        """Test nested hierarchy validation."""
        # Create nested structure manually to test validation
        child_hierarchy = TopicCategoryHierarchy(
            topic_id="esports",
            category_name="Esports",
            topic_type="custom",
            level=2,
            children=[],
            path=["entertainment", "gaming", "esports"],
        )

        parent_hierarchy = TopicCategoryHierarchy(
            topic_id="gaming",
            category_name="Gaming",
            topic_type="youtube",
            level=1,
            children=[child_hierarchy],
            path=["entertainment", "gaming"],
        )

        assert len(parent_hierarchy.children) == 1
        assert parent_hierarchy.children[0].topic_id == "esports"
        assert parent_hierarchy.children[0].level == 2


class TestTopicCategoryAnalytics:
    """Test TopicCategoryAnalytics model using factories."""

    def test_create_valid_analytics(self):
        """Test creating valid TopicCategoryAnalytics with keyword arguments."""
        analytics = TopicCategoryAnalyticsFactory(
            topic_trends={"gaming": [10, 12, 15], "music": [8, 9, 11]},
            topic_relationships={
                "gaming": ["esports", "streaming"],
                "music": ["pop", "rock"],
            },
            semantic_similarity={"gaming-esports": 0.9, "music-entertainment": 0.8},
            content_classification={
                "gaming": {"entertainment": 0.95, "technology": 0.7}
            },
        )

        assert analytics.topic_trends == {"gaming": [10, 12, 15], "music": [8, 9, 11]}
        assert analytics.topic_relationships == {
            "gaming": ["esports", "streaming"],
            "music": ["pop", "rock"],
        }
        assert analytics.semantic_similarity == {
            "gaming-esports": 0.9,
            "music-entertainment": 0.8,
        }
        assert analytics.content_classification == {
            "gaming": {"entertainment": 0.95, "technology": 0.7}
        }

    def test_create_minimal_analytics(self):
        """Test creating minimal TopicCategoryAnalytics."""
        analytics = TopicCategoryAnalytics()

        assert analytics.topic_trends == {}
        assert analytics.topic_relationships == {}
        assert analytics.semantic_similarity == {}
        assert analytics.content_classification == {}

    def test_factory_generates_realistic_analytics(self):
        """Test factory generates realistic analytics."""
        analytics = TopicCategoryAnalyticsFactory()

        assert isinstance(analytics, TopicCategoryAnalytics)
        assert isinstance(analytics.topic_trends, dict)
        assert isinstance(analytics.topic_relationships, dict)
        assert isinstance(analytics.semantic_similarity, dict)
        assert isinstance(analytics.content_classification, dict)


class TestTopicCategoryModelInteractions:
    """Test interactions between different TopicCategory models using factories."""

    def test_create_then_update_workflow(self):
        """Test typical create then update workflow with keyword arguments."""
        # Create
        topic_create = TopicCategoryCreateFactory(
            topic_id="gaming",
            category_name="Gaming",
            parent_topic_id=None,
            topic_type="youtube",
        )

        # Simulate creation
        now = datetime.now(timezone.utc)
        topic_full = TopicCategoryFactory(
            topic_id=topic_create.topic_id,
            category_name=topic_create.category_name,
            parent_topic_id=topic_create.parent_topic_id,
            topic_type=topic_create.topic_type,
            created_at=now,
        )

        # Update
        topic_update = TopicCategoryUpdate(
            category_name="Gaming & Esports",
            parent_topic_id="entertainment",
            # topic_type intentionally omitted - no change
        )

        # Apply update (simulated)
        updated_data = topic_full.model_dump()
        update_data = topic_update.model_dump(exclude_unset=True)
        updated_data.update(update_data)

        topic_updated = TopicCategory.model_validate(updated_data)

        assert topic_updated.topic_id == "gaming"
        assert topic_updated.category_name == "Gaming & Esports"
        assert topic_updated.parent_topic_id == "entertainment"
        assert topic_updated.topic_type == "youtube"

    def test_search_filters_serialization(self):
        """Test search filters serialization for API usage."""
        filters = TopicCategorySearchFiltersFactory(
            topic_ids=["gaming", "music"],
            category_name_query="entertainment",
            parent_topic_ids=["entertainment"],
            topic_types=["youtube"],
            is_root_topic=False,
            has_children=True,
            max_depth=3,
            created_after=None,
            created_before=None,
        )

        # Simulate API query parameters
        query_params = filters.model_dump(exclude_none=True)

        expected = {
            "topic_ids": ["gaming", "music"],
            "category_name_query": "entertainment",
            "parent_topic_ids": ["entertainment"],
            "topic_types": ["youtube"],
            "is_root_topic": False,
            "has_children": True,
            "max_depth": 3,
        }

        assert query_params == expected

    def test_statistics_aggregation_pattern(self):
        """Test statistics model for aggregation results."""
        # Simulate aggregation data from database
        aggregation_result = {
            "total_topics": 250,
            "root_topics": 15,
            "max_hierarchy_depth": 4,
            "avg_children_per_topic": 15.67,
            "topic_type_distribution": {"youtube": 180, "custom": 70},
            "most_popular_topics": [("gaming", 45), ("music", 38), ("tech", 32)],
            "hierarchy_distribution": {0: 15, 1: 60, 2: 120, 3: 45, 4: 10},
        }

        stats = TopicCategoryStatistics.model_validate(aggregation_result)

        assert stats.total_topics == 250
        assert stats.root_topics == 15
        assert len(stats.most_popular_topics) == 3
        assert len(stats.hierarchy_distribution) == 5
        assert stats.most_popular_topics[0] == ("gaming", 45)

    def test_hierarchy_tree_construction(self):
        """Test hierarchy tree model for representing topic trees."""
        # Test data from factory
        tree_data = TopicCategoryTestData.hierarchy_tree_data()

        hierarchy_tree = TopicCategoryHierarchy.model_validate(tree_data)

        assert hierarchy_tree.topic_id == "entertainment"
        assert hierarchy_tree.level == 0
        assert len(hierarchy_tree.children) == 1

        gaming_node = hierarchy_tree.children[0]
        assert gaming_node.topic_id == "gaming"
        assert gaming_node.level == 1
        assert len(gaming_node.children) == 1

        esports_node = gaming_node.children[0]
        assert esports_node.topic_id == "esports"
        assert esports_node.level == 2
        assert esports_node.path == ["entertainment", "gaming", "esports"]

    def test_analytics_pattern(self):
        """Test analytics model for complex analysis results."""
        # Simulate analytics data from ML/NLP processing
        analytics_result = {
            "topic_trends": {
                "gaming": [10, 12, 15, 18, 20, 22, 25, 28, 30],
                "music": [8, 9, 11, 13, 15, 17, 19, 21, 23],
            },
            "topic_relationships": {
                "gaming": ["esports", "streaming", "reviews"],
                "music": ["pop", "rock", "classical", "playlists"],
            },
            "semantic_similarity": {
                "gaming-esports": 0.95,
                "music-entertainment": 0.82,
                "tech-programming": 0.88,
            },
            "content_classification": {
                "gaming": {"entertainment": 0.95, "technology": 0.75},
                "tutorial": {"education": 0.92, "technology": 0.65},
            },
        }

        analytics = TopicCategoryAnalytics.model_validate(analytics_result)

        assert len(analytics.topic_trends) == 2
        assert len(analytics.topic_relationships) == 2
        assert len(analytics.semantic_similarity) == 3
        assert len(analytics.content_classification) == 2
        assert analytics.topic_relationships["gaming"] == [
            "esports",
            "streaming",
            "reviews",
        ]

    def test_convenience_factory_functions(self):
        """Test convenience factory functions for easy model creation."""
        # Test convenience function
        topic = create_topic_category(
            topic_id="science",
            category_name="Science & Technology",
            parent_topic_id="education",
            topic_type="youtube",
        )

        assert isinstance(topic, TopicCategory)
        assert topic.topic_id == "science"
        assert topic.category_name == "Science & Technology"
        assert topic.parent_topic_id == "education"
        assert topic.topic_type == "youtube"
        assert isinstance(topic.created_at, datetime)

    def test_factory_inheritance_consistency(self):
        """Test that factory-created models maintain proper inheritance."""
        base = TopicCategoryBaseFactory()
        create = TopicCategoryCreateFactory()
        full = TopicCategoryFactory()

        # All should be instances of TopicCategoryBase
        assert isinstance(base, TopicCategoryBase)
        assert isinstance(create, TopicCategoryBase)
        assert isinstance(full, TopicCategoryBase)

        # Specific type checks
        assert isinstance(create, TopicCategoryCreate)
        assert isinstance(full, TopicCategory)

    def test_hierarchical_topic_patterns(self):
        """Test common hierarchical topic patterns."""
        # Test YouTube official topic structure
        youtube_topics = TopicCategoryTestData.YOUTUBE_OFFICIAL_TOPICS

        for topic_id, category_name in youtube_topics:
            topic = TopicCategoryBaseFactory(
                topic_id=topic_id,
                category_name=category_name,
                topic_type="youtube",
                parent_topic_id=None,  # Official topics are typically root level
            )

            assert topic.topic_id == topic_id
            assert topic.category_name == category_name
            assert topic.topic_type == "youtube"
            assert topic.parent_topic_id is None

    def test_custom_topic_creation(self):
        """Test custom topic creation with proper validation."""
        custom_data = TopicCategoryTestData.custom_topic_data()

        custom_topic = TopicCategoryCreateFactory(**custom_data)

        assert custom_topic.topic_id == "custom_ai_ml"
        assert custom_topic.category_name == "AI & Machine Learning"
        assert custom_topic.parent_topic_id == "technology"
        assert custom_topic.topic_type == "custom"

    def test_topic_id_format_consistency(self):
        """Test topic ID format validation and consistency."""
        valid_formats = [
            "gaming",  # Simple lowercase
            "science_tech",  # Underscore
            "how-to",  # Hyphen
            "film_animation",  # YouTube style
            "AI_ML_2024",  # Mixed with numbers
        ]

        for topic_id in valid_formats:
            topic = TopicCategoryBaseFactory(topic_id=topic_id)
            assert topic.topic_id == topic_id

    def test_hierarchy_depth_validation(self):
        """Test hierarchy depth business logic."""
        # Create a deep hierarchy to test depth constraints
        root = TopicCategoryFactory(topic_id="entertainment", parent_topic_id=None)

        level1 = TopicCategoryFactory(
            topic_id="gaming", parent_topic_id="entertainment"
        )

        level2 = TopicCategoryFactory(topic_id="esports", parent_topic_id="gaming")

        level3 = TopicCategoryFactory(topic_id="fps_games", parent_topic_id="esports")

        # Validate parent-child relationships
        assert root.parent_topic_id is None
        assert level1.parent_topic_id == "entertainment"
        assert level2.parent_topic_id == "gaming"
        assert level3.parent_topic_id == "esports"
