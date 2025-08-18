"""
Tests for VideoTopic model classes.

Tests for VideoTopic, VideoTopicCreate, VideoTopicUpdate models
including validation, field validation, and edge cases.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.video_topic import (
    VideoTopic,
    VideoTopicCreate,
    VideoTopicSearchFilters,
    VideoTopicStatistics,
    VideoTopicUpdate,
)
from tests.factories.id_factory import TestIds


class TestVideoTopicCreate:
    """Test VideoTopicCreate model."""

    def test_video_topic_create_valid(self):
        """Test VideoTopicCreate with valid data."""
        video_topic = VideoTopicCreate(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.MUSIC_TOPIC,
            relevance_type="primary",
        )

        assert video_topic.video_id == TestIds.TEST_VIDEO_1
        assert video_topic.topic_id == TestIds.MUSIC_TOPIC
        assert video_topic.relevance_type == "primary"

    def test_video_topic_create_relevance_type_validation(self):
        """Test relevance_type validation in VideoTopicCreate."""
        # Valid values should work
        for valid_type in ["primary", "relevant", "suggested"]:
            video_topic = VideoTopicCreate(
                video_id=TestIds.TEST_VIDEO_1,
                topic_id=TestIds.MUSIC_TOPIC,
                relevance_type=valid_type,
            )
            assert video_topic.relevance_type == valid_type

    def test_video_topic_create_relevance_type_normalization(self):
        """Test relevance_type normalization (whitespace and case)."""
        video_topic = VideoTopicCreate(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.MUSIC_TOPIC,
            relevance_type="  PRIMARY  ",  # Mixed case with whitespace
        )
        assert video_topic.relevance_type == "primary"

    def test_video_topic_create_invalid_relevance_type(self):
        """Test VideoTopicCreate with invalid relevance_type."""
        with pytest.raises(ValidationError) as exc_info:
            VideoTopicCreate(
                video_id=TestIds.TEST_VIDEO_1,
                topic_id=TestIds.MUSIC_TOPIC,
                relevance_type="invalid_type",
            )

        error = exc_info.value.errors()[0]
        assert "Relevance type must be one of:" in str(error)

    def test_video_topic_create_empty_relevance_type(self):
        """Test VideoTopicCreate with empty relevance_type."""
        with pytest.raises(ValidationError) as exc_info:
            VideoTopicCreate(
                video_id=TestIds.TEST_VIDEO_1,
                topic_id=TestIds.MUSIC_TOPIC,
                relevance_type="",
            )

        error = exc_info.value.errors()[0]
        assert "Relevance type cannot be empty" in str(error)

    def test_video_topic_create_whitespace_only_relevance_type(self):
        """Test VideoTopicCreate with whitespace-only relevance_type."""
        with pytest.raises(ValidationError) as exc_info:
            VideoTopicCreate(
                video_id=TestIds.TEST_VIDEO_1,
                topic_id=TestIds.MUSIC_TOPIC,
                relevance_type="   ",
            )

        error = exc_info.value.errors()[0]
        assert "Relevance type cannot be empty" in str(error)


class TestVideoTopicUpdate:
    """Test VideoTopicUpdate model."""

    def test_video_topic_update_valid(self):
        """Test VideoTopicUpdate with valid data."""
        update = VideoTopicUpdate(relevance_type="relevant")
        assert update.relevance_type == "relevant"

    def test_video_topic_update_none_relevance_type(self):
        """Test VideoTopicUpdate with None relevance_type."""
        update = VideoTopicUpdate(relevance_type=None)
        assert update.relevance_type is None

    def test_video_topic_update_relevance_type_validation(self):
        """Test relevance_type validation in VideoTopicUpdate."""
        # Valid values should work
        for valid_type in ["primary", "relevant", "suggested"]:
            update = VideoTopicUpdate(relevance_type=valid_type)
            assert update.relevance_type == valid_type

    def test_video_topic_update_invalid_relevance_type(self):
        """Test VideoTopicUpdate with invalid relevance_type."""
        with pytest.raises(ValidationError) as exc_info:
            VideoTopicUpdate(relevance_type="invalid_type")

        error = exc_info.value.errors()[0]
        assert "Relevance type must be one of:" in str(error)

    def test_video_topic_update_empty_relevance_type(self):
        """Test VideoTopicUpdate with empty relevance_type."""
        with pytest.raises(ValidationError) as exc_info:
            VideoTopicUpdate(relevance_type="")

        error = exc_info.value.errors()[0]
        assert "Relevance type cannot be empty" in str(error)


class TestVideoTopicSearchFilters:
    """Test VideoTopicSearchFilters model."""

    def test_video_topic_search_filters_empty(self):
        """Test VideoTopicSearchFilters with no filters."""
        filters = VideoTopicSearchFilters()

        assert filters.video_ids is None
        assert filters.topic_ids is None
        assert filters.relevance_types is None
        assert filters.created_after is None
        assert filters.created_before is None

    def test_video_topic_search_filters_with_data(self):
        """Test VideoTopicSearchFilters with filter data."""
        now = datetime.now(timezone.utc)
        filters = VideoTopicSearchFilters(
            video_ids=[TestIds.TEST_VIDEO_1, TestIds.TEST_VIDEO_2],
            topic_ids=[TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC],
            relevance_types=["primary", "relevant"],
            created_after=now,
            created_before=now,
        )

        assert filters.video_ids == [TestIds.TEST_VIDEO_1, TestIds.TEST_VIDEO_2]
        assert filters.topic_ids == [TestIds.MUSIC_TOPIC, TestIds.GAMING_TOPIC]
        assert filters.relevance_types == ["primary", "relevant"]
        assert filters.created_after == now
        assert filters.created_before == now


class TestVideoTopicStatistics:
    """Test VideoTopicStatistics model."""

    def test_video_topic_statistics_valid(self):
        """Test VideoTopicStatistics with valid data."""
        stats = VideoTopicStatistics(
            total_video_topics=100,
            unique_topics=25,
            unique_videos=50,
            avg_topics_per_video=2.5,
            most_common_topics=[(TestIds.MUSIC_TOPIC, 30), (TestIds.GAMING_TOPIC, 20)],
            relevance_type_distribution={"primary": 60, "relevant": 40},
        )

        assert stats.total_video_topics == 100
        assert stats.unique_topics == 25
        assert stats.unique_videos == 50
        assert stats.avg_topics_per_video == 2.5
        assert len(stats.most_common_topics) == 2
        assert stats.most_common_topics[0] == (TestIds.MUSIC_TOPIC, 30)
        assert stats.relevance_type_distribution["primary"] == 60

    def test_video_topic_statistics_empty(self):
        """Test VideoTopicStatistics with empty/zero values."""
        stats = VideoTopicStatistics(
            total_video_topics=0,
            unique_topics=0,
            unique_videos=0,
            avg_topics_per_video=0.0,
            most_common_topics=[],
            relevance_type_distribution={},
        )

        assert stats.total_video_topics == 0
        assert stats.unique_topics == 0
        assert stats.unique_videos == 0
        assert stats.avg_topics_per_video == 0.0
        assert stats.most_common_topics == []
        assert stats.relevance_type_distribution == {}


class TestVideoTopic:
    """Test VideoTopic model (read model)."""

    def test_video_topic_from_dict(self):
        """Test VideoTopic creation from dictionary (as from database)."""
        now = datetime.now(timezone.utc)

        video_topic = VideoTopic(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.MUSIC_TOPIC,
            relevance_type="primary",
            created_at=now,
        )

        assert video_topic.video_id == TestIds.TEST_VIDEO_1
        assert video_topic.topic_id == TestIds.MUSIC_TOPIC
        assert video_topic.relevance_type == "primary"
        assert video_topic.created_at == now

    def test_video_topic_model_config(self):
        """Test VideoTopic model configuration."""
        # Test that validate_assignment is enabled
        video_topic = VideoTopic(
            video_id=TestIds.TEST_VIDEO_1,
            topic_id=TestIds.MUSIC_TOPIC,
            relevance_type="primary",
            created_at=datetime.now(timezone.utc),
        )

        # Should validate when assigning new values
        with pytest.raises(ValidationError):
            video_topic.relevance_type = "invalid_type"
