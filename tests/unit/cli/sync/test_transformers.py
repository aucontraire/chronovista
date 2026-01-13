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
    PlaylistContentDetails,
    PlaylistItemContentDetails,
    PlaylistItemSnippet,
    PlaylistSnippet,
    PlaylistStatus,
    Thumbnail,
    TopicDetails,
    VideoContentDetails,
    VideoSnippet,
    VideoStatus,
    YouTubeChannelResponse,
    YouTubePlaylistItemResponse,
    YouTubePlaylistResponse,
    YouTubeVideoCategoryResponse,
    YouTubeVideoResponse,
)
from chronovista.models.enums import LanguageCode, PrivacyStatus, TopicType


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


class TestExtractPlaylistCreate:
    """Tests for extract_playlist_create method."""

    # Valid 24-char channel ID (UC + 22 chars = 24 total)
    VALID_CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxxxxxx"
    # Valid 34-char playlist ID (PL + 32 chars = 34 total)
    VALID_PLAYLIST_ID = "PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    def test_extract_playlist_create_valid_response(self) -> None:
        """Test extracting playlist with full valid response."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="My Test Playlist",
            description="A comprehensive test playlist",
            channel_title="Test Channel",
            default_language="en",
        )
        content_details = PlaylistContentDetails(
            item_count=25,
        )
        status = PlaylistStatus(
            privacy_status="public",
        )
        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=snippet,
            content_details=content_details,
            status=status,
        )

        result = DataTransformers.extract_playlist_create(playlist)

        assert result.playlist_id == self.VALID_PLAYLIST_ID
        assert result.title == "My Test Playlist"
        assert result.description == "A comprehensive test playlist"
        assert result.default_language == LanguageCode.ENGLISH
        assert result.privacy_status == PrivacyStatus.PUBLIC
        assert result.channel_id == self.VALID_CHANNEL_ID
        assert result.video_count == 25
        assert result.published_at == published

    def test_extract_playlist_create_missing_snippet(self) -> None:
        """Test extracting playlist without snippet raises validation error.

        When snippet is None, title defaults to "" which doesn't pass the
        min_length=1 validation. This is expected - callers should ensure
        they have valid data.
        """
        from pydantic import ValidationError

        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=None,
            content_details=None,
            status=None,
        )

        with pytest.raises(ValidationError):
            DataTransformers.extract_playlist_create(playlist)

    def test_extract_playlist_create_with_language(self) -> None:
        """Test extracting playlist with different language codes."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Mi Lista de Reproducción",
            description="Una lista en español",
            channel_title="Test Channel",
            default_language="es",
        )
        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=snippet,
        )

        result = DataTransformers.extract_playlist_create(playlist)

        assert result.default_language == LanguageCode.SPANISH

    def test_extract_playlist_create_invalid_language_defaults_to_none(self) -> None:
        """Test extracting playlist with invalid language code defaults to None."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Test Playlist",
            description="Test",
            channel_title="Test Channel",
            default_language="invalid_lang",
        )
        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=snippet,
        )

        result = DataTransformers.extract_playlist_create(playlist)

        assert result.default_language is None

    def test_extract_playlist_create_private_status(self) -> None:
        """Test extracting playlist with private status."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Private Playlist",
            description="",
            channel_title="Test Channel",
        )
        status = PlaylistStatus(
            privacy_status="private",
        )
        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=snippet,
            status=status,
        )

        result = DataTransformers.extract_playlist_create(playlist)

        assert result.privacy_status == PrivacyStatus.PRIVATE

    def test_extract_playlist_create_unlisted_status(self) -> None:
        """Test extracting playlist with unlisted status."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Unlisted Playlist",
            description="",
            channel_title="Test Channel",
        )
        status = PlaylistStatus(
            privacy_status="unlisted",
        )
        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=snippet,
            status=status,
        )

        result = DataTransformers.extract_playlist_create(playlist)

        assert result.privacy_status == PrivacyStatus.UNLISTED

    def test_extract_playlist_create_invalid_privacy_defaults_to_private(self) -> None:
        """Test extracting playlist with invalid privacy status defaults to private."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Test Playlist",
            description="",
            channel_title="Test Channel",
        )
        status = PlaylistStatus(
            privacy_status="invalid_status",
        )
        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=snippet,
            status=status,
        )

        result = DataTransformers.extract_playlist_create(playlist)

        assert result.privacy_status == PrivacyStatus.PRIVATE

    def test_extract_playlist_create_no_content_details(self) -> None:
        """Test extracting playlist without content details defaults video_count to 0."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Empty Playlist",
            description="No videos yet",
            channel_title="Test Channel",
        )
        playlist = YouTubePlaylistResponse(
            kind="youtube#playlist",
            etag="xyz123",
            id=self.VALID_PLAYLIST_ID,
            snippet=snippet,
            content_details=None,
        )

        result = DataTransformers.extract_playlist_create(playlist)

        assert result.video_count == 0


class TestExtractPlaylistMembershipCreate:
    """Tests for extract_playlist_membership_create method."""

    # Valid 34-char playlist ID (PL + 32 chars = 34 total)
    VALID_PLAYLIST_ID = "PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    # Valid 11-char video ID for tests
    VALID_VIDEO_ID = "dQw4w9WgXcQ"
    # Valid 24-char channel ID (UC + 22 chars = 24 total)
    VALID_CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxxxxxx"

    def test_extract_playlist_membership_create_valid(self) -> None:
        """Test extracting playlist membership with valid data."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistItemSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Test Video",
            description="A test video",
            channel_title="Test Channel",
            playlist_id=self.VALID_PLAYLIST_ID,
            position=5,
            resource_id={
                "kind": "youtube#video",
                "videoId": self.VALID_VIDEO_ID,
            },
        )
        content_details = PlaylistItemContentDetails(
            video_id=self.VALID_VIDEO_ID,
        )
        item = YouTubePlaylistItemResponse(
            kind="youtube#playlistItem",
            etag="abc123",
            id="UExxxx",
            snippet=snippet,
            content_details=content_details,
        )

        result = DataTransformers.extract_playlist_membership_create(item)

        assert result is not None
        assert result.playlist_id == self.VALID_PLAYLIST_ID
        assert result.video_id == self.VALID_VIDEO_ID
        assert result.position == 5
        assert result.added_at == published

    def test_extract_playlist_membership_create_missing_snippet(self) -> None:
        """Test extracting playlist membership without snippet returns None."""
        content_details = PlaylistItemContentDetails(
            video_id=self.VALID_VIDEO_ID,
        )
        item = YouTubePlaylistItemResponse(
            kind="youtube#playlistItem",
            etag="abc123",
            id="UExxxx",
            snippet=None,
            content_details=content_details,
        )

        result = DataTransformers.extract_playlist_membership_create(item)

        assert result is None

    def test_extract_playlist_membership_create_missing_content_details(self) -> None:
        """Test extracting playlist membership without content_details returns None."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistItemSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Test Video",
            description="A test video",
            channel_title="Test Channel",
            playlist_id=self.VALID_PLAYLIST_ID,
            position=5,
            resource_id={
                "kind": "youtube#video",
                "videoId": self.VALID_VIDEO_ID,
            },
        )
        item = YouTubePlaylistItemResponse(
            kind="youtube#playlistItem",
            etag="abc123",
            id="UExxxx",
            snippet=snippet,
            content_details=None,
        )

        result = DataTransformers.extract_playlist_membership_create(item)

        assert result is None

    def test_extract_playlist_membership_create_missing_video_id(self) -> None:
        """Test extracting playlist membership without video_id returns None."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistItemSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="Test Video",
            description="A test video",
            channel_title="Test Channel",
            playlist_id=self.VALID_PLAYLIST_ID,
            position=5,
            resource_id={
                "kind": "youtube#video",
                "videoId": self.VALID_VIDEO_ID,
            },
        )
        # Create content_details without video_id by using empty string
        content_details = PlaylistItemContentDetails(
            video_id="",  # Empty video_id should cause None to be returned
        )
        item = YouTubePlaylistItemResponse(
            kind="youtube#playlistItem",
            etag="abc123",
            id="UExxxx",
            snippet=snippet,
            content_details=content_details,
        )

        result = DataTransformers.extract_playlist_membership_create(item)

        assert result is None

    def test_extract_playlist_membership_create_position_zero(self) -> None:
        """Test extracting playlist membership with position 0 (first item)."""
        published = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        snippet = PlaylistItemSnippet(
            published_at=published,
            channel_id=self.VALID_CHANNEL_ID,
            title="First Video",
            description="The first video in playlist",
            channel_title="Test Channel",
            playlist_id=self.VALID_PLAYLIST_ID,
            position=0,
            resource_id={
                "kind": "youtube#video",
                "videoId": self.VALID_VIDEO_ID,
            },
        )
        content_details = PlaylistItemContentDetails(
            video_id=self.VALID_VIDEO_ID,
        )
        item = YouTubePlaylistItemResponse(
            kind="youtube#playlistItem",
            etag="abc123",
            id="UExxxx",
            snippet=snippet,
            content_details=content_details,
        )

        result = DataTransformers.extract_playlist_membership_create(item)

        assert result is not None
        assert result.position == 0
