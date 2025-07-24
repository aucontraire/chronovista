"""
Tests for video tag Pydantic models.

Tests validation, keyword arguments, serialization, and model methods
for all VideoTag model variants using factory pattern for DRY.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.video_tag import (
    VideoTag,
    VideoTagBase,
    VideoTagCreate,
    VideoTagSearchFilters,
    VideoTagStatistics,
    VideoTagUpdate,
)
from tests.factories import (
    VideoTagBaseFactory,
    VideoTagCreateFactory,
    VideoTagFactory,
    VideoTagSearchFiltersFactory,
    VideoTagStatisticsFactory,
    VideoTagTestData,
    VideoTagUpdateFactory,
    create_video_tag,
)


class TestVideoTagBase:
    """Test VideoTagBase model using factories."""

    def test_create_valid_video_tag_base(self):
        """Test creating valid VideoTagBase with keyword arguments."""
        tag = VideoTagBaseFactory(video_id="dQw4w9WgXcQ", tag="music", tag_order=1)

        assert tag.video_id == "dQw4w9WgXcQ"
        assert tag.tag == "music"
        assert tag.tag_order == 1

    def test_create_video_tag_base_minimal(self):
        """Test creating VideoTagBase with minimal required fields."""
        tag = VideoTagBaseFactory(video_id="dQw4w9WgXcQ", tag="gaming", tag_order=None)

        assert tag.video_id == "dQw4w9WgXcQ"
        assert tag.tag == "gaming"
        assert tag.tag_order is None

    def test_factory_generates_valid_defaults(self):
        """Test that factory generates valid models with defaults."""
        tag = VideoTagBaseFactory()

        assert isinstance(tag, VideoTagBase)
        assert len(tag.video_id) >= 8
        assert len(tag.video_id) <= 20
        assert len(tag.tag) >= 1
        assert len(tag.tag) <= 100

    @pytest.mark.parametrize("invalid_video_id", VideoTagTestData.INVALID_VIDEO_IDS)
    def test_video_id_validation_invalid(self, invalid_video_id):
        """Test video_id validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            VideoTagBaseFactory(video_id=invalid_video_id)

    @pytest.mark.parametrize("valid_video_id", VideoTagTestData.VALID_VIDEO_IDS)
    def test_video_id_validation_valid(self, valid_video_id):
        """Test video_id validation with various valid inputs."""
        tag = VideoTagBaseFactory(video_id=valid_video_id)
        assert tag.video_id == valid_video_id

    @pytest.mark.parametrize("invalid_tag", VideoTagTestData.INVALID_TAGS)
    def test_tag_validation_invalid(self, invalid_tag):
        """Test tag validation with various invalid inputs."""
        with pytest.raises(ValidationError):
            VideoTagBaseFactory(tag=invalid_tag)

    @pytest.mark.parametrize("valid_tag", VideoTagTestData.VALID_TAGS)
    def test_tag_validation_valid(self, valid_tag):
        """Test tag validation with various valid inputs."""
        tag = VideoTagBaseFactory(tag=valid_tag)
        assert tag.tag == valid_tag

    def test_tag_order_validation_negative(self):
        """Test tag_order validation with negative value."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            VideoTagBaseFactory(tag_order=-1)

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        tag = VideoTagBaseFactory(video_id="dQw4w9WgXcQ", tag="music", tag_order=1)

        data = tag.model_dump()
        expected = {"video_id": "dQw4w9WgXcQ", "tag": "music", "tag_order": 1}

        assert data == expected

    def test_model_validate_functionality(self):
        """Test model_validate() method for deserialization."""
        data = VideoTagTestData.valid_video_tag_data()

        tag = VideoTagBase.model_validate(data)

        assert tag.video_id == data["video_id"]
        assert tag.tag == data["tag"]
        assert tag.tag_order == data["tag_order"]


class TestVideoTagCreate:
    """Test VideoTagCreate model using factories."""

    def test_create_valid_video_tag_create(self):
        """Test creating valid VideoTagCreate with keyword arguments."""
        tag = VideoTagCreateFactory(
            video_id="dQw4w9WgXcQ", tag="entertainment", tag_order=3
        )

        assert tag.video_id == "dQw4w9WgXcQ"
        assert tag.tag == "entertainment"
        assert tag.tag_order == 3

    def test_inherits_base_validation(self):
        """Test that VideoTagCreate inherits base validation."""
        with pytest.raises(ValidationError):
            VideoTagCreateFactory(video_id="   ")

    def test_factory_generates_valid_model(self):
        """Test factory generates valid VideoTagCreate models."""
        tag = VideoTagCreateFactory()

        assert isinstance(tag, VideoTagCreate)
        assert isinstance(tag, VideoTagBase)  # Inheritance check


class TestVideoTagUpdate:
    """Test VideoTagUpdate model using factories."""

    def test_create_valid_video_tag_update(self):
        """Test creating valid VideoTagUpdate with keyword arguments."""
        update = VideoTagUpdateFactory(tag_order=5)

        assert update.tag_order == 5

    def test_create_empty_video_tag_update(self):
        """Test creating empty VideoTagUpdate."""
        update = VideoTagUpdate()

        assert update.tag_order is None

    def test_tag_order_validation_negative(self):
        """Test tag_order validation with negative value."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            VideoTagUpdateFactory(tag_order=-1)

    def test_model_dump_excludes_none(self):
        """Test model_dump() excludes None values."""
        update = VideoTagUpdate()

        data = update.model_dump(exclude_none=True)

        assert data == {}

    def test_factory_generates_valid_updates(self):
        """Test factory generates valid update models."""
        update = VideoTagUpdateFactory()

        assert isinstance(update, VideoTagUpdate)
        assert update.tag_order >= 0


class TestVideoTag:
    """Test VideoTag full model using factories."""

    def test_create_valid_video_tag(self):
        """Test creating valid VideoTag with keyword arguments."""
        now = datetime.now(timezone.utc)
        tag = VideoTagFactory(
            video_id="dQw4w9WgXcQ", tag="tutorial", tag_order=1, created_at=now
        )

        assert tag.video_id == "dQw4w9WgXcQ"
        assert tag.tag == "tutorial"
        assert tag.tag_order == 1
        assert tag.created_at == now

    def test_from_attributes_compatibility(self):
        """Test ORM compatibility with from_attributes."""

        # Simulate SQLAlchemy model attributes
        class MockVideoTagDB:
            video_id = "dQw4w9WgXcQ"
            tag = "education"
            tag_order = 2
            created_at = datetime.now(timezone.utc)

        mock_db = MockVideoTagDB()
        tag = VideoTag.model_validate(mock_db, from_attributes=True)

        assert tag.video_id == "dQw4w9WgXcQ"
        assert tag.tag == "education"
        assert tag.tag_order == 2
        assert isinstance(tag.created_at, datetime)

    def test_factory_generates_full_model(self):
        """Test factory generates complete VideoTag models."""
        tag = VideoTagFactory()

        assert isinstance(tag, VideoTag)
        assert isinstance(tag, VideoTagBase)  # Inheritance
        assert isinstance(tag.created_at, datetime)
        assert tag.created_at.tzinfo is not None  # Has timezone


class TestVideoTagSearchFilters:
    """Test VideoTagSearchFilters model using factories."""

    def test_create_comprehensive_filters(self):
        """Test creating comprehensive search filters with keyword arguments."""
        data = VideoTagTestData.comprehensive_search_filters_data()
        filters = VideoTagSearchFiltersFactory(**data)

        assert filters.video_ids == data["video_ids"]
        assert filters.tags == data["tags"]
        assert filters.tag_pattern == data["tag_pattern"]
        assert filters.min_tag_order == data["min_tag_order"]
        assert filters.max_tag_order == data["max_tag_order"]
        assert filters.created_after == data["created_after"]
        assert filters.created_before == data["created_before"]

    def test_create_empty_filters(self):
        """Test creating empty search filters."""
        filters = VideoTagSearchFilters()

        assert filters.video_ids is None
        assert filters.tags is None
        assert filters.tag_pattern is None
        assert filters.min_tag_order is None
        assert filters.max_tag_order is None
        assert filters.created_after is None
        assert filters.created_before is None

    def test_factory_generates_valid_filters(self):
        """Test factory generates valid search filters."""
        filters = VideoTagSearchFiltersFactory()

        assert isinstance(filters, VideoTagSearchFilters)
        assert isinstance(filters.video_ids, list)
        assert isinstance(filters.tags, list)
        assert len(filters.video_ids) > 0
        assert len(filters.tags) > 0

    def test_tag_pattern_validation_empty(self):
        """Test tag_pattern validation with empty string."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            VideoTagSearchFilters(tag_pattern="")

    def test_min_tag_order_validation_negative(self):
        """Test min_tag_order validation with negative value."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            VideoTagSearchFilters(min_tag_order=-1)

    def test_max_tag_order_validation_negative(self):
        """Test max_tag_order validation with negative value."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            VideoTagSearchFilters(max_tag_order=-1)


class TestVideoTagStatistics:
    """Test VideoTagStatistics model using factories."""

    def test_create_valid_statistics(self):
        """Test creating valid VideoTagStatistics with keyword arguments."""
        stats = VideoTagStatisticsFactory(
            total_tags=100,
            unique_tags=75,
            avg_tags_per_video=2.5,
            most_common_tags=[("music", 15), ("gaming", 12)],
            tag_distribution={"music": 15, "gaming": 12, "tutorial": 8},
        )

        assert stats.total_tags == 100
        assert stats.unique_tags == 75
        assert stats.avg_tags_per_video == 2.5
        assert stats.most_common_tags == [("music", 15), ("gaming", 12)]
        assert stats.tag_distribution == {"music": 15, "gaming": 12, "tutorial": 8}

    def test_create_minimal_statistics(self):
        """Test creating minimal VideoTagStatistics."""
        stats = VideoTagStatistics(
            total_tags=50, unique_tags=30, avg_tags_per_video=1.8
        )

        assert stats.total_tags == 50
        assert stats.unique_tags == 30
        assert stats.avg_tags_per_video == 1.8
        assert stats.most_common_tags == []
        assert stats.tag_distribution == {}

    def test_factory_generates_realistic_statistics(self):
        """Test factory generates realistic statistics."""
        stats = VideoTagStatisticsFactory()

        assert isinstance(stats, VideoTagStatistics)
        assert stats.total_tags > 0
        assert stats.unique_tags <= stats.total_tags
        assert stats.avg_tags_per_video > 0
        assert isinstance(stats.most_common_tags, list)
        assert isinstance(stats.tag_distribution, dict)

    def test_model_dump_with_complex_types(self):
        """Test model_dump() with complex field types."""
        stats = VideoTagStatisticsFactory(
            total_tags=10,
            unique_tags=8,
            avg_tags_per_video=1.2,
            most_common_tags=[("tech", 5), ("review", 3)],
            tag_distribution={"tech": 5, "review": 3, "unboxing": 2},
        )

        data = stats.model_dump()

        assert isinstance(data["most_common_tags"], list)
        assert isinstance(data["tag_distribution"], dict)
        assert data["most_common_tags"] == [("tech", 5), ("review", 3)]


class TestVideoTagModelInteractions:
    """Test interactions between different VideoTag models using factories."""

    def test_create_then_update_workflow(self):
        """Test typical create then update workflow with keyword arguments."""
        # Create
        tag_create = VideoTagCreateFactory(
            video_id="dQw4w9WgXcQ", tag="original_tag", tag_order=None
        )

        # Simulate creation
        now = datetime.now(timezone.utc)
        tag_full = VideoTagFactory(
            video_id=tag_create.video_id,
            tag=tag_create.tag,
            tag_order=tag_create.tag_order,
            created_at=now,
        )

        # Update
        tag_update = VideoTagUpdateFactory(tag_order=5)

        # Apply update (simulated)
        updated_data = tag_full.model_dump()
        updated_data.update(tag_update.model_dump(exclude_none=True))

        tag_updated = VideoTag.model_validate(updated_data)

        assert tag_updated.video_id == "dQw4w9WgXcQ"
        assert tag_updated.tag == "original_tag"
        assert tag_updated.tag_order == 5

    def test_search_filters_serialization(self):
        """Test search filters serialization for API usage."""
        filters = VideoTagSearchFiltersFactory(
            video_ids=["dQw4w9WgXcQ"],
            tags=["music", "entertainment"],
            min_tag_order=1,
            max_tag_order=None,
            tag_pattern=None,
            created_after=None,
            created_before=None,
        )

        # Simulate API query parameters
        query_params = filters.model_dump(exclude_none=True)

        expected = {
            "video_ids": ["dQw4w9WgXcQ"],
            "tags": ["music", "entertainment"],
            "min_tag_order": 1,
        }

        assert query_params == expected

    def test_statistics_aggregation_pattern(self):
        """Test statistics model for aggregation results."""
        # Simulate aggregation data from database
        aggregation_result = {
            "total_tags": 500,
            "unique_tags": 150,
            "avg_tags_per_video": 3.2,
            "most_common_tags": [("music", 75), ("gaming", 50), ("tech", 40)],
            "tag_distribution": {
                "music": 75,
                "gaming": 50,
                "tech": 40,
                "education": 30,
                "entertainment": 25,
            },
        }

        stats = VideoTagStatistics.model_validate(aggregation_result)

        assert stats.total_tags == 500
        assert stats.unique_tags == 150
        assert len(stats.most_common_tags) == 3
        assert len(stats.tag_distribution) == 5
        assert stats.most_common_tags[0] == ("music", 75)

    def test_convenience_factory_functions(self):
        """Test convenience factory functions for easy model creation."""
        # Test convenience function
        tag = create_video_tag(video_id="dQw4w9WgXcQ", tag="convenience_test")

        assert isinstance(tag, VideoTag)
        assert tag.video_id == "dQw4w9WgXcQ"
        assert tag.tag == "convenience_test"
        assert isinstance(tag.created_at, datetime)

    def test_factory_inheritance_consistency(self):
        """Test that factory-created models maintain proper inheritance."""
        base = VideoTagBaseFactory()
        create = VideoTagCreateFactory()
        full = VideoTagFactory()

        # All should be instances of VideoTagBase
        assert isinstance(base, VideoTagBase)
        assert isinstance(create, VideoTagBase)
        assert isinstance(full, VideoTagBase)

        # Specific type checks
        assert isinstance(create, VideoTagCreate)
        assert isinstance(full, VideoTag)
