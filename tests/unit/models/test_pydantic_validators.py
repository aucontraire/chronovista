"""
Tests for Pydantic model validators across all models.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.channel import ChannelCreate, ChannelUpdate
from chronovista.models.enums import (
    DownloadReason,
    LanguageCode,
    LanguagePreferenceType,
    TranscriptType,
)
from chronovista.models.user_language_preference import UserLanguagePreferenceCreate
from chronovista.models.user_video import GoogleTakeoutWatchHistoryItem, UserVideoCreate
from chronovista.models.video import VideoCreate, VideoUpdate
from chronovista.models.video_transcript import VideoTranscriptCreate


class TestChannelValidators:
    """Test Channel model validators."""

    def test_channel_id_validation_empty(self):
        """Test channel ID validation with empty values."""
        with pytest.raises(
            ValidationError, match="ChannelId must be exactly 24 characters long"
        ):
            ChannelCreate(channel_id="", title="Test Channel")

        with pytest.raises(
            ValidationError, match="ChannelId must be exactly 24 characters long"
        ):
            ChannelCreate(channel_id="   ", title="Test Channel")

    def test_channel_id_validation_length(self):
        """Test channel ID validation with invalid lengths."""
        with pytest.raises(
            ValidationError, match="ChannelId must be exactly 24 characters long"
        ):
            ChannelCreate(channel_id="x" * 25, title="Test Channel")

    def test_channel_id_validation_valid(self):
        """Test channel ID validation with valid values."""
        # Use valid 24-char channel ID with UC prefix
        valid_channel_id = "UCtest123456789012345678"
        channel = ChannelCreate(channel_id=valid_channel_id, title="Test Channel")
        assert channel.channel_id == valid_channel_id

        # Valid channel ID should work normally (trimming handled by BeforeValidator)
        channel = ChannelCreate(channel_id=valid_channel_id, title="Test Channel")
        assert channel.channel_id == valid_channel_id

    def test_title_validation_empty(self):
        """Test title validation with empty values."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            ChannelCreate(channel_id="UCtest123456789012345678", title="")

        with pytest.raises(ValidationError, match="Title cannot be empty"):
            ChannelCreate(channel_id="UCtest123456789012345678", title="   ")

    def test_title_validation_valid(self):
        """Test title validation with valid values."""
        channel = ChannelCreate(
            channel_id="UCtest123456789012345678", title="Test Channel"
        )
        assert channel.title == "Test Channel"

        # Test trimming
        channel = ChannelCreate(
            channel_id="UCtest123456789012345678", title="  Test Channel  "
        )
        assert channel.title == "Test Channel"

    def test_country_validation_invalid_length(self):
        """Test country validation with invalid lengths."""
        with pytest.raises(
            ValidationError, match="String should have at most 2 characters"
        ):
            ChannelCreate(
                channel_id="UCtest123456789012345678", title="Test", country="USA"
            )

        with pytest.raises(
            ValidationError, match="String should have at least 2 characters"
        ):
            ChannelCreate(
                channel_id="UCtest123456789012345678", title="Test", country="U"
            )

    def test_country_validation_valid(self):
        """Test country validation with valid values."""
        channel = ChannelCreate(
            channel_id="UCtest123456789012345678", title="Test", country="US"
        )
        assert channel.country == "US"

        # Test None
        channel = ChannelCreate(
            channel_id="UCtest123456789012345678", title="Test", country=None
        )
        assert channel.country is None

    def test_subscriber_count_validation_negative(self):
        """Test subscriber count validation with negative values."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            ChannelCreate(
                channel_id="UCtest123456789012345678", title="Test", subscriber_count=-1
            )

    def test_subscriber_count_validation_valid(self):
        """Test subscriber count validation with valid values."""
        channel = ChannelCreate(
            channel_id="UCtest123456789012345678", title="Test", subscriber_count=1000
        )
        assert channel.subscriber_count == 1000

        channel = ChannelCreate(
            channel_id="UCtest123456789012345678", title="Test", subscriber_count=0
        )
        assert channel.subscriber_count == 0


class TestVideoValidators:
    """Test Video model validators."""

    def test_video_id_validation_empty(self):
        """Test video ID validation with empty values."""
        with pytest.raises(
            ValidationError, match="VideoId must be exactly 11 characters long"
        ):
            VideoCreate(
                video_id="",
                channel_id="UCtest123456789012345678",
                title="Test",
                upload_date=datetime.now(timezone.utc),
                duration=120,
            )

        with pytest.raises(
            ValidationError, match="VideoId must be exactly 11 characters long"
        ):
            VideoCreate(
                video_id="   ",
                channel_id="UCtest123456789012345678",
                title="Test",
                upload_date=datetime.now(timezone.utc),
                duration=120,
            )

    def test_video_id_validation_length(self):
        """Test video ID validation with invalid lengths."""
        with pytest.raises(
            ValidationError, match="VideoId must be exactly 11 characters long"
        ):
            VideoCreate(
                video_id="x" * 21,
                channel_id="UCtest123456789012345678",
                title="Test",
                upload_date=datetime.now(timezone.utc),
                duration=120,
            )

        with pytest.raises(
            ValidationError, match="VideoId must be exactly 11 characters long"
        ):
            VideoCreate(
                video_id="x" * 22,
                channel_id="UCtest123456789012345678",
                title="Test",
                upload_date=datetime.now(timezone.utc),
                duration=120,
            )

    def test_video_id_validation_valid(self):
        """Test video ID validation with valid values."""
        video = VideoCreate(
            video_id="dQw4w9WgXcQ",
            channel_id="UCtest123456789012345678",
            title="Test",
            upload_date=datetime.now(timezone.utc),
            duration=120,
        )
        assert video.video_id == "dQw4w9WgXcQ"

    def test_channel_id_validation_empty(self):
        """Test channel ID validation with empty values."""
        with pytest.raises(
            ValidationError, match="ChannelId must be exactly 24 characters long"
        ):
            VideoCreate(
                video_id="dQw4w9WgXcQ",
                channel_id="",
                title="Test",
                upload_date=datetime.now(timezone.utc),
                duration=120,
            )

    def test_title_validation_empty(self):
        """Test title validation with empty values."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            VideoCreate(
                video_id="dQw4w9WgXcQ",
                channel_id="UCtest1234567890123456787",
                title="",
                upload_date=datetime.now(timezone.utc),
                duration=120,
            )

    def test_duration_validation_negative(self):
        """Test duration validation with negative values."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            VideoCreate(
                video_id="dQw4w9WgXcQ",
                channel_id="UCtest1234567890123456787",
                title="Test",
                upload_date=datetime.now(timezone.utc),
                duration=-1,
            )

    def test_duration_validation_valid(self):
        """Test duration validation with valid values."""
        video = VideoCreate(
            video_id="dQw4w9WgXcQ",
            channel_id="UCtest123456789012345678",
            title="Test",
            upload_date=datetime.now(timezone.utc),
            duration=212,
        )
        assert video.duration == 212


class TestUserVideoValidators:
    """Test UserVideo model validators."""

    def test_user_id_validation_empty(self):
        """Test user ID validation with empty values."""
        with pytest.raises(
            ValidationError, match="UserId cannot be empty or whitespace-only"
        ):
            UserVideoCreate(
                user_id="",
                video_id="dQw4w9WgXcQ",
                watched_at=datetime.now(timezone.utc),
            )

    def test_video_id_validation_empty(self):
        """Test video ID validation with empty values."""
        with pytest.raises(
            ValidationError, match="VideoId must be exactly 11 characters long"
        ):
            UserVideoCreate(
                user_id="test_user", video_id="", watched_at=datetime.now(timezone.utc)
            )

    def test_rewatch_count_validation_negative(self):
        """Test rewatch count validation with negative values."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            UserVideoCreate(
                user_id="test_user",
                video_id="dQw4w9WgXcQ",
                watched_at=datetime.now(timezone.utc),
                rewatch_count=-1,
            )

class TestGoogleTakeoutValidators:
    """Test Google Takeout model validators."""

    def test_takeout_item_video_id_extraction(self):
        """Test video ID extraction from takeout items."""
        item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Test Video",
            titleUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            time="2023-12-01T10:30:00Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        video_id = item.extract_video_id()
        assert video_id == "dQw4w9WgXcQ"

    def test_takeout_item_invalid_url(self):
        """Test video ID extraction with invalid URL."""
        item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Invalid Video",
            titleUrl="https://www.youtube.com/playlist?list=invalid",
            time="2023-12-01T10:30:00Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        video_id = item.extract_video_id()
        assert video_id is None

    def test_takeout_to_user_video_create_valid(self):
        """Test conversion from takeout item to UserVideoCreate."""
        item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Test Video",
            titleUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            time="2023-12-01T10:30:00Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        user_video = item.to_user_video_create("test_user")

        assert user_video is not None
        assert user_video.user_id == "test_user"
        assert user_video.video_id == "dQw4w9WgXcQ"
        assert user_video.rewatch_count == 0

    def test_takeout_to_user_video_create_invalid(self):
        """Test conversion with invalid video URL."""
        item = GoogleTakeoutWatchHistoryItem(
            header="YouTube",
            title="Watched Invalid Video",
            titleUrl="https://www.youtube.com/playlist?list=invalid",
            time="2023-12-01T10:30:00Z",
            products=["YouTube"],
            activityControls=["YouTube watch history"],
        )

        user_video = item.to_user_video_create("test_user")
        assert user_video is None


class TestUserLanguagePreferenceValidators:
    """Test UserLanguagePreference model validators."""

    def test_user_id_validation_empty(self):
        """Test user ID validation with empty values."""
        with pytest.raises(
            ValidationError, match="UserId cannot be empty or whitespace-only"
        ):
            UserLanguagePreferenceCreate(
                user_id="",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
            )

    def test_language_code_validation_empty(self):
        """Test language code validation with empty values."""
        with pytest.raises(ValidationError, match="Input should be 'en', 'en-US'"):
            UserLanguagePreferenceCreate(
                user_id="test_user",
                language_code="",  # type: ignore[arg-type] # Testing validation error
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
            )

    def test_priority_validation_negative(self):
        """Test priority validation with negative values."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 1"
        ):
            UserLanguagePreferenceCreate(
                user_id="test_user",
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=-1,
            )


class TestVideoTranscriptValidators:
    """Test VideoTranscript model validators."""

    def test_video_id_validation_empty(self):
        """Test video ID validation with empty values."""
        with pytest.raises(
            ValidationError, match="VideoId must be exactly 11 characters long"
        ):
            VideoTranscriptCreate(
                video_id="",
                language_code=LanguageCode.ENGLISH,
                transcript_text="Test transcript",
                transcript_type=TranscriptType.AUTO,
                download_reason=DownloadReason.USER_REQUEST,
            )

    def test_language_code_validation_empty(self):
        """Test language code validation with empty values."""
        with pytest.raises(ValidationError, match="Input should be 'en', 'en-US'"):
            VideoTranscriptCreate(
                video_id="dQw4w9WgXcQ",
                language_code="",  # type: ignore[arg-type] # Testing validation error
                transcript_text="Test transcript",
                transcript_type=TranscriptType.AUTO,
                download_reason=DownloadReason.USER_REQUEST,
            )

    def test_content_validation_empty(self):
        """Test content validation with empty values."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            VideoTranscriptCreate(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH,
                transcript_text="",
                transcript_type=TranscriptType.AUTO,
                download_reason=DownloadReason.USER_REQUEST,
            )

    def test_confidence_score_validation_negative(self):
        """Test confidence score validation with negative values."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            VideoTranscriptCreate(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH,
                transcript_text="Test transcript",
                transcript_type=TranscriptType.AUTO,
                download_reason=DownloadReason.USER_REQUEST,
                confidence_score=-0.1,
            )

    def test_confidence_score_validation_over_one(self):
        """Test confidence score validation with values over 1.0."""
        with pytest.raises(
            ValidationError, match="Input should be less than or equal to 1"
        ):
            VideoTranscriptCreate(
                video_id="dQw4w9WgXcQ",
                language_code=LanguageCode.ENGLISH,
                transcript_text="Test transcript",
                transcript_type=TranscriptType.AUTO,
                download_reason=DownloadReason.USER_REQUEST,
                confidence_score=1.1,
            )

    def test_confidence_score_validation_valid(self):
        """Test confidence score validation with valid values."""
        transcript = VideoTranscriptCreate(
            video_id="dQw4w9WgXcQ",
            language_code=LanguageCode.ENGLISH,
            transcript_text="Test transcript",
            transcript_type=TranscriptType.AUTO,
            download_reason=DownloadReason.USER_REQUEST,
            confidence_score=0.95,
        )
        assert transcript.confidence_score == 0.95
