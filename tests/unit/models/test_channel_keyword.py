"""
Tests for channel keyword Pydantic models.

Tests validation, keyword arguments, serialization, and model methods
for all ChannelKeyword model variants using factory pattern for DRY.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.channel_keyword import (
    ChannelKeyword,
    ChannelKeywordAnalytics,
    ChannelKeywordBase,
    ChannelKeywordCreate,
    ChannelKeywordSearchFilters,
    ChannelKeywordStatistics,
    ChannelKeywordUpdate,
)
from tests.factories.channel_keyword_factory import (
    ChannelKeywordAnalyticsFactory,
    ChannelKeywordBaseFactory,
    ChannelKeywordCreateFactory,
    ChannelKeywordFactory,
    ChannelKeywordSearchFiltersFactory,
    ChannelKeywordStatisticsFactory,
    ChannelKeywordTestData,
    ChannelKeywordUpdateFactory,
    create_channel_keyword,
)


class TestChannelKeywordBase:
    """Test ChannelKeywordBase model using factories."""

    def test_create_valid_channel_keyword_base(self):
        """Test creating valid ChannelKeywordBase with keyword arguments."""
        keyword = ChannelKeywordBaseFactory(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw", keyword="gaming", keyword_order=1
        )

        assert keyword.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert keyword.keyword == "gaming"
        assert keyword.keyword_order == 1

    def test_create_channel_keyword_base_minimal(self):
        """Test creating ChannelKeywordBase with minimal required fields."""
        keyword = ChannelKeywordBaseFactory(
            channel_id="UC-lHJZR3Gqxm24_Vd_AJ5Yw",
            keyword="technology",
            keyword_order=None,
        )

        assert keyword.channel_id == "UC-lHJZR3Gqxm24_Vd_AJ5Yw"
        assert keyword.keyword == "technology"
        assert keyword.keyword_order is None

    def test_factory_generates_valid_defaults(self):
        """Test that factory generates valid models with defaults."""
        keyword = ChannelKeywordBaseFactory()

        assert isinstance(keyword, ChannelKeywordBase)
        assert len(keyword.channel_id) >= 20
        assert len(keyword.channel_id) <= 24
        assert len(keyword.keyword) >= 1
        assert len(keyword.keyword) <= 100
        assert keyword.keyword_order is not None
        assert keyword.keyword_order >= 0

    @pytest.mark.parametrize(
        "invalid_channel_id", ChannelKeywordTestData.INVALID_CHANNEL_IDS
    )
    def test_channel_id_validation_invalid(self, invalid_channel_id):
        """Test channel_id validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            ChannelKeywordBaseFactory(channel_id=invalid_channel_id)

    @pytest.mark.parametrize(
        "valid_channel_id", ChannelKeywordTestData.VALID_CHANNEL_IDS
    )
    def test_channel_id_validation_valid(self, valid_channel_id):
        """Test channel_id validation with various valid inputs."""
        keyword = ChannelKeywordBaseFactory(channel_id=valid_channel_id)
        assert keyword.channel_id == valid_channel_id

    @pytest.mark.parametrize("invalid_keyword", ChannelKeywordTestData.INVALID_KEYWORDS)
    def test_keyword_validation_invalid(self, invalid_keyword):
        """Test keyword validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            ChannelKeywordBaseFactory(keyword=invalid_keyword)

    @pytest.mark.parametrize("valid_keyword", ChannelKeywordTestData.VALID_KEYWORDS)
    def test_keyword_validation_valid(self, valid_keyword):
        """Test keyword validation with various valid inputs."""
        keyword = ChannelKeywordBaseFactory(keyword=valid_keyword)
        assert keyword.keyword == valid_keyword

    def test_keyword_order_validation(self):
        """Test keyword_order validation."""
        # Valid values
        keyword = ChannelKeywordBaseFactory(keyword_order=0)
        assert keyword.keyword_order == 0

        keyword = ChannelKeywordBaseFactory(keyword_order=50)
        assert keyword.keyword_order == 50

        keyword = ChannelKeywordBaseFactory(keyword_order=None)
        assert keyword.keyword_order is None

        # Invalid values
        with pytest.raises(ValidationError):
            ChannelKeywordBaseFactory(keyword_order=-1)

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        keyword = ChannelKeywordBaseFactory(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw", keyword="tutorial", keyword_order=5
        )

        data = keyword.model_dump()
        expected = {
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "keyword": "tutorial",
            "keyword_order": 5,
        }

        assert data == expected

    def test_model_validate_functionality(self):
        """Test model_validate() method for deserialization."""
        data = ChannelKeywordTestData.valid_channel_keyword_data()

        keyword = ChannelKeywordBase.model_validate(data)

        assert keyword.channel_id == data["channel_id"]
        assert keyword.keyword == data["keyword"]
        assert keyword.keyword_order == data["keyword_order"]


class TestChannelKeywordCreate:
    """Test ChannelKeywordCreate model using factories."""

    def test_create_valid_channel_keyword_create(self):
        """Test creating valid ChannelKeywordCreate with keyword arguments."""
        keyword = ChannelKeywordCreateFactory(
            channel_id="UCBJycsmduvYEL83R_U4JriQ", keyword="review", keyword_order=3
        )

        assert keyword.channel_id == "UCBJycsmduvYEL83R_U4JriQ"
        assert keyword.keyword == "review"
        assert keyword.keyword_order == 3

    def test_inherits_base_validation(self):
        """Test that ChannelKeywordCreate inherits base validation."""
        with pytest.raises(ValidationError):
            ChannelKeywordCreateFactory(channel_id="   ")

    def test_factory_generates_valid_model(self):
        """Test factory generates valid ChannelKeywordCreate models."""
        keyword = ChannelKeywordCreateFactory()

        assert isinstance(keyword, ChannelKeywordCreate)
        assert isinstance(keyword, ChannelKeywordBase)  # Inheritance check


class TestChannelKeywordUpdate:
    """Test ChannelKeywordUpdate model using factories."""

    def test_create_valid_channel_keyword_update(self):
        """Test creating valid ChannelKeywordUpdate with keyword arguments."""
        update = ChannelKeywordUpdateFactory(keyword_order=10)

        assert update.keyword_order == 10

    def test_create_empty_channel_keyword_update(self):
        """Test creating empty ChannelKeywordUpdate."""
        update = ChannelKeywordUpdate()

        assert update.keyword_order is None

    def test_keyword_order_validation_in_update(self):
        """Test keyword_order validation in update model."""
        with pytest.raises(ValidationError):
            ChannelKeywordUpdateFactory(keyword_order=-5)

    def test_model_dump_excludes_none(self):
        """Test model_dump() excludes None values."""
        update = ChannelKeywordUpdate()

        data = update.model_dump(exclude_none=True)

        assert data == {}

    def test_factory_generates_valid_updates(self):
        """Test factory generates valid update models."""
        update = ChannelKeywordUpdateFactory()

        assert isinstance(update, ChannelKeywordUpdate)
        assert update.keyword_order is not None


class TestChannelKeyword:
    """Test ChannelKeyword full model using factories."""

    def test_create_valid_channel_keyword(self):
        """Test creating valid ChannelKeyword with keyword arguments."""
        now = datetime.now(timezone.utc)
        keyword = ChannelKeywordFactory(
            channel_id="UCsXVk37bltHxD1rDPwtNM8Q",
            keyword="programming",
            keyword_order=2,
            created_at=now,
        )

        assert keyword.channel_id == "UCsXVk37bltHxD1rDPwtNM8Q"
        assert keyword.keyword == "programming"
        assert keyword.keyword_order == 2
        assert keyword.created_at == now

    def test_from_attributes_compatibility(self):
        """Test ORM compatibility with from_attributes."""

        # Simulate SQLAlchemy model attributes
        class MockChannelKeywordDB:
            channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
            keyword = "unboxing"
            keyword_order = 7
            created_at = datetime.now(timezone.utc)

        mock_db = MockChannelKeywordDB()
        keyword = ChannelKeyword.model_validate(mock_db, from_attributes=True)

        assert keyword.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert keyword.keyword == "unboxing"
        assert keyword.keyword_order == 7
        assert isinstance(keyword.created_at, datetime)

    def test_factory_generates_full_model(self):
        """Test factory generates complete ChannelKeyword models."""
        keyword = ChannelKeywordFactory()

        assert isinstance(keyword, ChannelKeyword)
        assert isinstance(keyword, ChannelKeywordBase)  # Inheritance
        assert isinstance(keyword.created_at, datetime)
        assert keyword.created_at.tzinfo is not None  # Has timezone


class TestChannelKeywordSearchFilters:
    """Test ChannelKeywordSearchFilters model using factories."""

    def test_create_comprehensive_filters(self):
        """Test creating comprehensive search filters with keyword arguments."""
        data = ChannelKeywordTestData.comprehensive_search_filters_data()
        filters = ChannelKeywordSearchFiltersFactory(**data)

        assert filters.channel_ids == data["channel_ids"]
        assert filters.keywords == data["keywords"]
        assert filters.keyword_pattern == data["keyword_pattern"]
        assert filters.min_keyword_order == data["min_keyword_order"]
        assert filters.max_keyword_order == data["max_keyword_order"]
        assert filters.has_order == data["has_order"]
        assert filters.created_after == data["created_after"]
        assert filters.created_before == data["created_before"]

    def test_create_empty_filters(self):
        """Test creating empty search filters."""
        filters = ChannelKeywordSearchFilters()

        assert filters.channel_ids is None
        assert filters.keywords is None
        assert filters.keyword_pattern is None
        assert filters.min_keyword_order is None
        assert filters.max_keyword_order is None
        assert filters.has_order is None
        assert filters.created_after is None
        assert filters.created_before is None

    def test_factory_generates_valid_filters(self):
        """Test factory generates valid search filters."""
        filters = ChannelKeywordSearchFiltersFactory()

        assert isinstance(filters, ChannelKeywordSearchFilters)
        assert isinstance(filters.channel_ids, list)
        assert isinstance(filters.keywords, list)
        assert len(filters.channel_ids) > 0
        assert len(filters.keywords) > 0

    def test_query_validation_empty_string(self):
        """Test query validation with empty strings."""
        with pytest.raises(ValidationError):
            ChannelKeywordSearchFiltersFactory(keyword_pattern="")

    def test_keyword_order_range_validation(self):
        """Test keyword order range validation."""
        # Valid ranges
        filters = ChannelKeywordSearchFiltersFactory(
            min_keyword_order=1, max_keyword_order=10
        )
        assert filters.min_keyword_order == 1
        assert filters.max_keyword_order == 10

        # Invalid ranges
        with pytest.raises(ValidationError):
            ChannelKeywordSearchFiltersFactory(min_keyword_order=-1)

        with pytest.raises(ValidationError):
            ChannelKeywordSearchFiltersFactory(max_keyword_order=-1)


class TestChannelKeywordStatistics:
    """Test ChannelKeywordStatistics model using factories."""

    def test_create_valid_statistics(self):
        """Test creating valid ChannelKeywordStatistics with keyword arguments."""
        stats = ChannelKeywordStatisticsFactory(
            total_keywords=2000,
            unique_keywords=1600,
            unique_channels=200,
            avg_keywords_per_channel=10.0,
            most_common_keywords=[("gaming", 150), ("tech", 120), ("tutorial", 100)],
            keyword_distribution={"gaming": 150, "tech": 120, "tutorial": 100},
            channels_with_ordered_keywords=120,
        )

        assert stats.total_keywords == 2000
        assert stats.unique_keywords == 1600
        assert stats.unique_channels == 200
        assert stats.avg_keywords_per_channel == 10.0
        assert stats.most_common_keywords == [
            ("gaming", 150),
            ("tech", 120),
            ("tutorial", 100),
        ]
        assert stats.keyword_distribution == {
            "gaming": 150,
            "tech": 120,
            "tutorial": 100,
        }
        assert stats.channels_with_ordered_keywords == 120

    def test_create_minimal_statistics(self):
        """Test creating minimal ChannelKeywordStatistics."""
        stats = ChannelKeywordStatistics(
            total_keywords=100,
            unique_keywords=80,
            unique_channels=20,
            avg_keywords_per_channel=5.0,
            channels_with_ordered_keywords=12,
        )

        assert stats.total_keywords == 100
        assert stats.unique_keywords == 80
        assert stats.unique_channels == 20
        assert stats.channels_with_ordered_keywords == 12
        assert stats.most_common_keywords == []
        assert stats.keyword_distribution == {}

    def test_factory_generates_realistic_statistics(self):
        """Test factory generates realistic statistics."""
        stats = ChannelKeywordStatisticsFactory()

        assert isinstance(stats, ChannelKeywordStatistics)
        assert stats.total_keywords > 0
        assert stats.unique_keywords <= stats.total_keywords
        assert stats.unique_channels > 0
        assert stats.avg_keywords_per_channel > 0
        assert stats.channels_with_ordered_keywords <= stats.unique_channels
        assert isinstance(stats.most_common_keywords, list)
        assert isinstance(stats.keyword_distribution, dict)


class TestChannelKeywordAnalytics:
    """Test ChannelKeywordAnalytics model using factories."""

    def test_create_valid_analytics(self):
        """Test creating valid ChannelKeywordAnalytics with keyword arguments."""
        analytics = ChannelKeywordAnalyticsFactory(
            keyword_trends={"gaming": [10, 12, 15, 18], "tech": [8, 9, 11, 13]},
            semantic_clusters=[
                {"cluster_id": 0, "keywords": ["gaming", "esports"], "similarity": 0.9}
            ],
            topic_keywords={
                "entertainment": ["gaming", "music"],
                "education": ["tutorial", "science"],
            },
            keyword_similarity={"gaming-esports": 0.85, "tech-programming": 0.78},
        )

        assert analytics.keyword_trends == {
            "gaming": [10, 12, 15, 18],
            "tech": [8, 9, 11, 13],
        }
        assert len(analytics.semantic_clusters) == 1
        assert analytics.semantic_clusters[0]["cluster_id"] == 0
        assert analytics.topic_keywords == {
            "entertainment": ["gaming", "music"],
            "education": ["tutorial", "science"],
        }
        assert analytics.keyword_similarity == {
            "gaming-esports": 0.85,
            "tech-programming": 0.78,
        }

    def test_create_minimal_analytics(self):
        """Test creating minimal ChannelKeywordAnalytics."""
        analytics = ChannelKeywordAnalytics()

        assert analytics.keyword_trends == {}
        assert analytics.semantic_clusters == []
        assert analytics.topic_keywords == {}
        assert analytics.keyword_similarity == {}

    def test_factory_generates_realistic_analytics(self):
        """Test factory generates realistic analytics."""
        analytics = ChannelKeywordAnalyticsFactory()

        assert isinstance(analytics, ChannelKeywordAnalytics)
        assert isinstance(analytics.keyword_trends, dict)
        assert isinstance(analytics.semantic_clusters, list)
        assert isinstance(analytics.topic_keywords, dict)
        assert isinstance(analytics.keyword_similarity, dict)

        # Check semantic clusters structure
        if analytics.semantic_clusters:
            cluster = analytics.semantic_clusters[0]
            assert "cluster_id" in cluster
            assert "keywords" in cluster
            assert "similarity" in cluster
            assert isinstance(cluster["keywords"], list)
            assert isinstance(cluster["similarity"], float)


class TestChannelKeywordModelInteractions:
    """Test interactions between different ChannelKeyword models using factories."""

    def test_create_then_update_workflow(self):
        """Test typical create then update workflow with keyword arguments."""
        # Create
        keyword_create = ChannelKeywordCreateFactory(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw", keyword="gaming", keyword_order=1
        )

        # Simulate creation
        now = datetime.now(timezone.utc)
        keyword_full = ChannelKeywordFactory(
            channel_id=keyword_create.channel_id,
            keyword=keyword_create.keyword,
            keyword_order=keyword_create.keyword_order,
            created_at=now,
        )

        # Update
        keyword_update = ChannelKeywordUpdateFactory(keyword_order=5)

        # Apply update (simulated)
        updated_data = keyword_full.model_dump()
        update_data = keyword_update.model_dump(exclude_unset=True)
        updated_data.update(update_data)

        keyword_updated = ChannelKeyword.model_validate(updated_data)

        assert keyword_updated.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert keyword_updated.keyword == "gaming"
        assert keyword_updated.keyword_order == 5

    def test_search_filters_serialization(self):
        """Test search filters serialization for API usage."""
        filters = ChannelKeywordSearchFiltersFactory(
            channel_ids=["UCuAXFkgsw1L7xaCfnd5JJOw"],
            keywords=["gaming", "tech"],
            keyword_pattern="game",
            min_keyword_order=1,
            max_keyword_order=10,
            has_order=True,
            created_after=None,
            created_before=None,
        )

        # Simulate API query parameters
        query_params = filters.model_dump(exclude_none=True)

        expected = {
            "channel_ids": ["UCuAXFkgsw1L7xaCfnd5JJOw"],
            "keywords": ["gaming", "tech"],
            "keyword_pattern": "game",
            "min_keyword_order": 1,
            "max_keyword_order": 10,
            "has_order": True,
        }

        assert query_params == expected

    def test_statistics_aggregation_pattern(self):
        """Test statistics model for aggregation results."""
        # Simulate aggregation data from database
        aggregation_result = {
            "total_keywords": 5000,
            "unique_keywords": 4000,
            "unique_channels": 500,
            "avg_keywords_per_channel": 10.0,
            "most_common_keywords": [("gaming", 300), ("tech", 250), ("tutorial", 200)],
            "keyword_distribution": {
                "gaming": 300,
                "tech": 250,
                "tutorial": 200,
                "review": 150,
                "music": 100,
            },
            "channels_with_ordered_keywords": 300,
        }

        stats = ChannelKeywordStatistics.model_validate(aggregation_result)

        assert stats.total_keywords == 5000
        assert stats.unique_keywords == 4000
        assert len(stats.most_common_keywords) == 3
        assert len(stats.keyword_distribution) == 5
        assert stats.most_common_keywords[0] == ("gaming", 300)
        assert stats.channels_with_ordered_keywords == 300

    def test_analytics_pattern(self):
        """Test analytics model for complex analysis results."""
        # Simulate analytics data from ML/NLP processing
        analytics_result = {
            "keyword_trends": {
                "gaming": [10, 12, 15, 18, 20, 22, 25, 28, 30, 32, 35, 38],
                "tech": [8, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29],
            },
            "semantic_clusters": [
                {
                    "cluster_id": 0,
                    "keywords": ["gaming", "esports", "streaming"],
                    "similarity": 0.92,
                },
                {
                    "cluster_id": 1,
                    "keywords": ["tech", "programming", "software"],
                    "similarity": 0.85,
                },
            ],
            "topic_keywords": {
                "entertainment": ["gaming", "music", "comedy", "vlogs"],
                "education": ["tutorial", "science", "math", "language"],
                "technology": ["programming", "software", "hardware", "AI"],
            },
            "keyword_similarity": {
                "gaming-esports": 0.95,
                "tech-programming": 0.88,
                "tutorial-education": 0.82,
            },
        }

        analytics = ChannelKeywordAnalytics.model_validate(analytics_result)

        assert len(analytics.keyword_trends) == 2
        assert len(analytics.semantic_clusters) == 2
        assert len(analytics.topic_keywords) == 3
        assert len(analytics.keyword_similarity) == 3
        assert analytics.semantic_clusters[0]["similarity"] == 0.92

    def test_convenience_factory_functions(self):
        """Test convenience factory functions for easy model creation."""
        # Test convenience function
        keyword = create_channel_keyword(
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw", keyword="DIY", keyword_order=3
        )

        assert isinstance(keyword, ChannelKeyword)
        assert keyword.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert keyword.keyword == "DIY"
        assert keyword.keyword_order == 3
        assert isinstance(keyword.created_at, datetime)

    def test_factory_inheritance_consistency(self):
        """Test that factory-created models maintain proper inheritance."""
        base = ChannelKeywordBaseFactory()
        create = ChannelKeywordCreateFactory()
        full = ChannelKeywordFactory()

        # All should be instances of ChannelKeywordBase
        assert isinstance(base, ChannelKeywordBase)
        assert isinstance(create, ChannelKeywordBase)
        assert isinstance(full, ChannelKeywordBase)

        # Specific type checks
        assert isinstance(create, ChannelKeywordCreate)
        assert isinstance(full, ChannelKeyword)

    def test_channel_id_format_validation(self):
        """Test specific YouTube channel ID format validation."""
        # Test various valid YouTube channel ID formats (all UC prefix, 24 chars)
        valid_channel_ids = [
            "UCuAXFkgsw1L7xaCfnd5JJOw",  # Standard UC format
            "UC-lHJZR3Gqxm24_Vd_AJ5Yw",  # UC with hyphen
            "UCBJycsmduvYEL83R_U4JriQ",  # Another UC format
            "UCsXVk37bltHxD1rDPwtNM8Q",  # UC format variant
        ]

        for channel_id in valid_channel_ids:
            keyword = ChannelKeywordBaseFactory(channel_id=channel_id)
            assert keyword.channel_id == channel_id

    def test_keyword_content_validation(self):
        """Test keyword content validation and normalization."""
        # Test various keyword formats
        test_cases = [
            ("Gaming", "Gaming"),  # Capitalized
            ("programming", "programming"),  # Lowercase
            ("How-To", "How-To"),  # Hyphenated
            ("AI/ML", "AI/ML"),  # With special characters
            ("tech 2024", "tech 2024"),  # With numbers
        ]

        for input_keyword, expected_keyword in test_cases:
            keyword = ChannelKeywordBaseFactory(keyword=input_keyword)
            assert keyword.keyword == expected_keyword

    def test_keyword_order_business_logic(self):
        """Test business logic around keyword ordering."""
        # Test that keyword order represents priority/importance
        high_priority = ChannelKeywordBaseFactory(keyword_order=1)
        medium_priority = ChannelKeywordBaseFactory(keyword_order=5)
        low_priority = ChannelKeywordBaseFactory(keyword_order=10)
        no_priority = ChannelKeywordBaseFactory(keyword_order=None)

        # Higher priority should have lower numbers
        assert high_priority.keyword_order < medium_priority.keyword_order
        assert medium_priority.keyword_order < low_priority.keyword_order
        assert no_priority.keyword_order is None
