"""
Tests for sync command data transformers.

Tests DataTransformers utility class.

Note: Pydantic models use camelCase aliases (via alias_generator=to_camel) but
accept snake_case field names at runtime thanks to populate_by_name=True.
Mypy doesn't understand this, so we ignore call-arg errors in this file.
"""

# mypy: disable-error-code="call-arg"

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from chronovista.cli.sync.transformers import DataTransformers
from chronovista.models.api_responses import (
    CategorySnippet,
    ChannelSnippet,
    ChannelStatisticsResponse,
    Thumbnail,
    TopicDetails,
    VideoContentDetails,
    VideoSnippet,
    VideoStatus,
    YouTubeChannelResponse,
    YouTubeVideoCategoryResponse,
    YouTubeVideoResponse,
)
from chronovista.models.enums import LanguageCode, TopicType


class TestParseDuration:
    """Tests for parse_duration method."""

    def test_parse_hours_minutes_seconds(self) -> None:
        """Test parsing full duration with hours, minutes, seconds."""
        assert DataTransformers.parse_duration("PT1H2M3S") == 3723

    def test_parse_hours_only(self) -> None:
        """Test parsing duration with hours only."""
        assert DataTransformers.parse_duration("PT2H") == 7200

    def test_parse_minutes_only(self) -> None:
        """Test parsing duration with minutes only."""
        assert DataTransformers.parse_duration("PT30M") == 1800

    def test_parse_seconds_only(self) -> None:
        """Test parsing duration with seconds only."""
        assert DataTransformers.parse_duration("PT45S") == 45

    def test_parse_minutes_seconds(self) -> None:
        """Test parsing duration with minutes and seconds."""
        assert DataTransformers.parse_duration("PT5M30S") == 330

    def test_parse_hours_seconds(self) -> None:
        """Test parsing duration with hours and seconds."""
        assert DataTransformers.parse_duration("PT1H30S") == 3630

    def test_parse_none(self) -> None:
        """Test parsing None returns 0."""
        assert DataTransformers.parse_duration(None) == 0

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string returns 0."""
        assert DataTransformers.parse_duration("") == 0

    def test_parse_invalid_format(self) -> None:
        """Test parsing invalid format returns 0."""
        assert DataTransformers.parse_duration("invalid") == 0

    def test_parse_no_pt_prefix(self) -> None:
        """Test parsing without PT prefix returns 0."""
        assert DataTransformers.parse_duration("1H2M3S") == 0


class TestCastLanguageCode:
    """Tests for cast_language_code method."""

    def test_cast_valid_language_code(self) -> None:
        """Test casting valid language code."""
        result = DataTransformers.cast_language_code("en")
        assert result == LanguageCode.ENGLISH

    def test_cast_another_valid_code(self) -> None:
        """Test casting another valid language code."""
        result = DataTransformers.cast_language_code("es")
        assert result == LanguageCode.SPANISH

    def test_cast_invalid_code(self) -> None:
        """Test casting invalid language code returns None."""
        result = DataTransformers.cast_language_code("xyz")
        assert result is None

    def test_cast_none(self) -> None:
        """Test casting None returns None."""
        result = DataTransformers.cast_language_code(None)
        assert result is None

    def test_cast_empty_string(self) -> None:
        """Test casting empty string returns None."""
        result = DataTransformers.cast_language_code("")
        assert result is None


class TestExtractTopicCategoryCreate:
    """Tests for extract_topic_category_create method."""

    def test_extract_with_snippet(self) -> None:
        """Test extracting topic category with full snippet."""
        snippet = CategorySnippet(
            channel_id="UCWX3X",
            title="Music",
            assignable=True,
        )
        category = YouTubeVideoCategoryResponse(
            kind="youtube#videoCategory",
            etag="abc123",
            id="10",
            snippet=snippet,
        )

        result = DataTransformers.extract_topic_category_create(category)

        assert result.topic_id == "10"
        assert result.category_name == "Music"
        assert result.parent_topic_id is None
        assert result.topic_type == TopicType.YOUTUBE

    def test_extract_without_snippet_raises_validation_error(self) -> None:
        """Test extracting topic category without snippet raises validation error.

        When snippet is None, category_name defaults to "" which doesn't pass
        the min_length=1 validation. This is expected - callers should ensure
        they have valid category data.
        """
        from pydantic import ValidationError

        category = YouTubeVideoCategoryResponse(
            kind="youtube#videoCategory",
            etag="abc123",
            id="15",
            snippet=None,
        )

        with pytest.raises(ValidationError):
            DataTransformers.extract_topic_category_create(category)


class TestExtractChannelCreate:
    """Tests for extract_channel_create method."""

    # Valid 24-char channel ID for tests (UC + 22 chars = 24 total)
    VALID_CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxxxxxx"

    def test_extract_full_channel(self) -> None:
        """Test extracting channel with all fields."""
        snippet = ChannelSnippet(
            title="Test Channel",
            description="A test channel",
            custom_url="@testchannel",
            published_at=datetime.now(timezone.utc),
            thumbnails={
                "high": Thumbnail(
                    url="https://example.com/thumb.jpg",
                    width=800,
                    height=800,
                )
            },
            default_language="en",
            country="US",
        )
        statistics = ChannelStatisticsResponse(
            view_count=1000,
            subscriber_count=500,
            video_count=50,
        )
        channel = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="xyz",
            id=self.VALID_CHANNEL_ID,
            snippet=snippet,
            statistics=statistics,
        )

        result = DataTransformers.extract_channel_create(channel)

        assert result.channel_id == self.VALID_CHANNEL_ID
        assert result.title == "Test Channel"
        assert result.description == "A test channel"
        assert result.subscriber_count == 500
        assert result.video_count == 50
        assert result.default_language == LanguageCode.ENGLISH
        assert result.country == "US"
        assert result.thumbnail_url == "https://example.com/thumb.jpg"

    def test_extract_channel_minimal_raises_validation_error(self) -> None:
        """Test extracting channel with minimal fields raises validation error.

        When snippet is None, title defaults to "" which doesn't pass the
        min_length=1 validation. This is expected - callers should ensure
        they have valid data before creating channels.
        """
        from pydantic import ValidationError

        channel = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="xyz",
            id=self.VALID_CHANNEL_ID,
            snippet=None,
            statistics=None,
        )

        with pytest.raises(ValidationError):
            DataTransformers.extract_channel_create(channel)

    def test_extract_channel_invalid_language(self) -> None:
        """Test extracting channel with invalid language code."""
        snippet = ChannelSnippet(
            title="Test Channel",
            description="",
            published_at=datetime.now(timezone.utc),
            default_language="invalid_lang",
        )
        channel = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="xyz",
            id=self.VALID_CHANNEL_ID,
            snippet=snippet,
        )

        result = DataTransformers.extract_channel_create(channel)

        assert result.default_language is None


class TestExtractVideoCreate:
    """Tests for extract_video_create method."""

    # Valid 24-char channel ID for tests (UC + 22 chars = 24 total)
    VALID_CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxxxxxx"
    # Valid 11-char video ID for tests
    VALID_VIDEO_ID = "dQw4w9WgXcQ"

    def test_extract_full_video(self) -> None:
        """Test extracting video with all fields."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = VideoSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Test Video",
            description="A test video",
            category_id="10",
            default_language="en",
        )
        content_details = VideoContentDetails(
            duration="PT10M30S",
            dimension="2d",
            definition="hd",
            caption="true",
        )
        status = VideoStatus(
            upload_status="processed",
            privacy_status="public",
            made_for_kids=False,
            self_declared_made_for_kids=False,
        )
        video = YouTubeVideoResponse(
            kind="youtube#video",
            etag="abc",
            id=self.VALID_VIDEO_ID,
            snippet=snippet,
            content_details=content_details,
            status=status,
        )

        result = DataTransformers.extract_video_create(video)

        assert result.video_id == self.VALID_VIDEO_ID
        assert result.channel_id == self.VALID_CHANNEL_ID
        assert result.title == "Test Video"
        assert result.description == "A test video"
        assert result.duration == 630  # 10*60 + 30
        assert result.category_id == "10"
        assert result.default_language == LanguageCode.ENGLISH
        assert result.made_for_kids is False
        assert result.self_declared_made_for_kids is False
        assert result.upload_date == published

    def test_extract_video_minimal_raises_validation_error(self) -> None:
        """Test extracting video with minimal fields raises validation error.

        When snippet is None, channel_id defaults to "UNKNOWN" which doesn't
        pass the 24-char validation. This is expected - callers should ensure
        they have valid data before creating videos.
        """
        from pydantic import ValidationError

        video = YouTubeVideoResponse(
            kind="youtube#video",
            etag="abc",
            id=self.VALID_VIDEO_ID,
            snippet=None,
            content_details=None,
            status=None,
        )

        with pytest.raises(ValidationError):
            DataTransformers.extract_video_create(video)

    def test_extract_video_with_channel_override(self) -> None:
        """Test extracting video with channel_id override."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = VideoSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Test Video",
        )
        video = YouTubeVideoResponse(
            kind="youtube#video",
            etag="abc",
            id=self.VALID_VIDEO_ID,
            snippet=snippet,
        )

        # Use a valid 24-char override (UC + 22 chars = 24 total)
        override_channel = "UCyyyyyyyyyyyyyyyyyyyyyy"
        result = DataTransformers.extract_video_create(video, channel_id=override_channel)

        assert result.channel_id == override_channel


class TestExtractTopicIds:
    """Tests for extract_topic_ids method."""

    # Valid 24-char channel ID for tests (UC + 22 chars = 24 total)
    VALID_CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxxxxxx"
    # Valid 11-char video ID for tests
    VALID_VIDEO_ID = "dQw4w9WgXcQ"

    def test_extract_from_channel_with_topics(self) -> None:
        """Test extracting topic IDs from channel with topics."""
        topic_details = TopicDetails(
            topic_ids=["topic1", "topic2", "topic3"],
            topic_categories=[],
        )
        channel = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="xyz",
            id=self.VALID_CHANNEL_ID,
            topic_details=topic_details,
        )

        result = DataTransformers.extract_topic_ids(channel)

        assert result == ["topic1", "topic2", "topic3"]

    def test_extract_from_channel_without_topics(self) -> None:
        """Test extracting topic IDs from channel without topics."""
        channel = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="xyz",
            id=self.VALID_CHANNEL_ID,
            topic_details=None,
        )

        result = DataTransformers.extract_topic_ids(channel)

        assert result == []

    def test_extract_from_video_with_topics(self) -> None:
        """Test extracting topic IDs from video with topics."""
        topic_details = TopicDetails(
            topic_ids=["music", "entertainment"],
            topic_categories=[],
        )
        video = YouTubeVideoResponse(
            kind="youtube#video",
            etag="abc",
            id=self.VALID_VIDEO_ID,
            topic_details=topic_details,
        )

        result = DataTransformers.extract_topic_ids(video)

        assert result == ["music", "entertainment"]

    def test_extract_with_empty_topic_ids(self) -> None:
        """Test extracting when topic_ids is empty list."""
        topic_details = TopicDetails(
            topic_ids=[],
            topic_categories=[],
        )
        channel = YouTubeChannelResponse(
            kind="youtube#channel",
            etag="xyz",
            id=self.VALID_CHANNEL_ID,
            topic_details=topic_details,
        )

        result = DataTransformers.extract_topic_ids(channel)

        assert result == []
