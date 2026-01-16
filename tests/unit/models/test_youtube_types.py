"""
Tests for YouTube validated types.

Comprehensive test coverage for YouTube ID validation functions and type aliases.
"""

import re
from typing import Any

import pytest

from chronovista.models.youtube_types import (  # Validation functions; Type aliases (for testing type annotations); Factory functions
    CaptionId,
    ChannelId,
    PlaylistId,
    TopicId,
    UserId,
    VideoId,
    create_test_caption_id,
    create_test_channel_id,
    create_test_playlist_id,
    create_test_topic_id,
    create_test_user_id,
    create_test_video_id,
    is_internal_playlist_id,
    is_youtube_playlist_id,
    validate_caption_id,
    validate_channel_id,
    validate_playlist_id,
    validate_topic_id,
    validate_user_id,
    validate_video_id,
    validate_youtube_id_format,
)


class TestValidatePlaylistId:
    """Tests for playlist ID validation."""

    def test_valid_playlist_ids(self):
        """Test valid playlist ID formats."""
        valid_ids = [
            "PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",  # Real YouTube playlist ID
            "PLtest_123456_music_xxxxxxxxxx",  # Test format
            "PL" + "x" * 32,  # Minimum valid length (34 chars)
            "PL" + "a" * 28,  # 30 chars (minimum)
        ]

        for playlist_id in valid_ids:
            result = validate_playlist_id(playlist_id)
            assert result == playlist_id
            assert result.startswith("PL")
            assert 30 <= len(result) <= 34

    def test_invalid_playlist_id_type(self):
        """Test playlist ID validation with wrong type."""
        with pytest.raises(TypeError, match="PlaylistId must be a string"):
            validate_playlist_id(123)  # type: ignore

        with pytest.raises(TypeError, match="PlaylistId must be a string"):
            validate_playlist_id(None)  # type: ignore

    def test_invalid_playlist_id_length(self):
        """Test playlist ID validation with invalid lengths."""
        # Too short
        with pytest.raises(
            ValueError, match="YouTube PlaylistId must be 30-50 chars"
        ):
            validate_playlist_id("PLshort")

        # Too long
        long_id = "PL" + "x" * 49  # 51 chars
        with pytest.raises(
            ValueError, match="YouTube PlaylistId must be 30-50 chars"
        ):
            validate_playlist_id(long_id)

    def test_invalid_playlist_id_prefix(self):
        """Test playlist ID validation with wrong prefix."""
        with pytest.raises(ValueError, match='PlaylistId must start with "INT_" or "PL"'):
            validate_playlist_id(
                "UCdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK"
            )  # Channel ID format

        with pytest.raises(ValueError, match='PlaylistId must start with "INT_" or "PL"'):
            validate_playlist_id("XLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK")  # Wrong prefix

    def test_invalid_playlist_id_characters(self):
        """Test playlist ID validation with invalid characters."""
        with pytest.raises(ValueError, match="PlaylistId contains invalid characters"):
            validate_playlist_id("PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5y@K")  # Contains @

        with pytest.raises(ValueError, match="PlaylistId contains invalid characters"):
            validate_playlist_id("PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5y K")  # Contains space


class TestValidateChannelId:
    """Tests for channel ID validation."""

    def test_valid_channel_ids(self):
        """Test valid channel ID formats."""
        valid_ids = [
            "UCuAXFkgsw1L7xaCfnd5JJOw",  # Real YouTube channel ID
            "UCtest_123456_rick_xxxxx",  # Test format (24 chars)
            "UC" + "x" * 22,  # Exactly 24 chars
            "UC" + "a" * 22,  # With letters
        ]

        for channel_id in valid_ids:
            result = validate_channel_id(channel_id)
            assert result == channel_id
            assert result.startswith("UC")
            assert len(result) == 24

    def test_invalid_channel_id_type(self):
        """Test channel ID validation with wrong type."""
        with pytest.raises(TypeError, match="ChannelId must be a string"):
            validate_channel_id(123)  # type: ignore

        with pytest.raises(TypeError, match="ChannelId must be a string"):
            validate_channel_id([])  # type: ignore

    def test_invalid_channel_id_length(self):
        """Test channel ID validation with invalid lengths."""
        # Too short
        with pytest.raises(
            ValueError, match="ChannelId must be exactly 24 characters long"
        ):
            validate_channel_id("UCshort")

        # Too long
        with pytest.raises(
            ValueError, match="ChannelId must be exactly 24 characters long"
        ):
            validate_channel_id("UCuAXFkgsw1L7xaCfnd5JJOwTooLong")

    def test_invalid_channel_id_prefix(self):
        """Test channel ID validation with wrong prefix."""
        with pytest.raises(ValueError, match='ChannelId must start with "UC"'):
            validate_channel_id("PLuAXFkgsw1L7xaCfnd5JJOw")  # Playlist ID format

        with pytest.raises(ValueError, match='ChannelId must start with "UC"'):
            validate_channel_id("XCuAXFkgsw1L7xaCfnd5JJOw")  # Wrong prefix

    def test_invalid_channel_id_characters(self):
        """Test channel ID validation with invalid characters."""
        with pytest.raises(ValueError, match="ChannelId contains invalid characters"):
            validate_channel_id("UCuAXFkgsw1L7xaCfnd5JJO@")  # Contains @

        with pytest.raises(ValueError, match="ChannelId contains invalid characters"):
            validate_channel_id("UCuAXFkgsw1L7xaCfnd5JJO ")  # Contains space


class TestValidateVideoId:
    """Tests for video ID validation."""

    def test_valid_video_ids(self):
        """Test valid video ID formats."""
        valid_ids = [
            "dQw4w9WgXcQ",  # Real YouTube video ID (Rick Roll)
            "test_123456",  # Test format
            "x" * 11,  # All x's
            "a1b2c3d4e5f",  # Mix of letters and numbers
            "A-B_C-D_E-F",  # With hyphens and underscores
        ]

        for video_id in valid_ids:
            result = validate_video_id(video_id)
            assert result == video_id
            assert len(result) == 11

    def test_invalid_video_id_type(self):
        """Test video ID validation with wrong type."""
        with pytest.raises(TypeError, match="VideoId must be a string"):
            validate_video_id(123)  # type: ignore

        with pytest.raises(TypeError, match="VideoId must be a string"):
            validate_video_id(None)  # type: ignore

    def test_invalid_video_id_length(self):
        """Test video ID validation with invalid lengths."""
        # Too short
        with pytest.raises(
            ValueError, match="VideoId must be exactly 11 characters long"
        ):
            validate_video_id("short")

        # Too long
        with pytest.raises(
            ValueError, match="VideoId must be exactly 11 characters long"
        ):
            validate_video_id("dQw4w9WgXcQTooLong")

    def test_invalid_video_id_characters(self):
        """Test video ID validation with invalid characters."""
        with pytest.raises(ValueError, match="VideoId contains invalid characters"):
            validate_video_id("dQw4w9WgX@Q")  # Contains @

        with pytest.raises(ValueError, match="VideoId contains invalid characters"):
            validate_video_id("dQw4w9WgX Q")  # Contains space

        with pytest.raises(ValueError, match="VideoId contains invalid characters"):
            validate_video_id("dQw4w9WgX.Q")  # Contains dot


class TestValidateUserId:
    """Tests for user ID validation."""

    def test_valid_user_ids(self):
        """Test valid user ID formats."""
        valid_ids = [
            "user_test_12345678",
            "simple_user",
            "user@example.com",  # Email-like format
            "UCuAXFkgsw1L7xaCfnd5JJOw",  # Channel ID format
            "a",  # Single character
            "x" * 255,  # Maximum length
        ]

        for user_id in valid_ids:
            result = validate_user_id(user_id)
            assert result == user_id.strip()
            assert len(result) <= 255
            assert result  # Not empty

    def test_valid_user_id_with_whitespace(self):
        """Test user ID validation strips whitespace."""
        user_id_with_spaces = "  user_test_123  "
        result = validate_user_id(user_id_with_spaces)
        assert result == "user_test_123"

    def test_invalid_user_id_type(self):
        """Test user ID validation with wrong type."""
        with pytest.raises(TypeError, match="UserId must be a string"):
            validate_user_id(123)  # type: ignore

        with pytest.raises(TypeError, match="UserId must be a string"):
            validate_user_id({})  # type: ignore

    def test_invalid_user_id_empty(self):
        """Test user ID validation with empty or whitespace-only strings."""
        with pytest.raises(
            ValueError, match="UserId cannot be empty or whitespace-only"
        ):
            validate_user_id("")

        with pytest.raises(
            ValueError, match="UserId cannot be empty or whitespace-only"
        ):
            validate_user_id("   ")  # Only whitespace

        with pytest.raises(
            ValueError, match="UserId cannot be empty or whitespace-only"
        ):
            validate_user_id("\t\n ")  # Various whitespace

    def test_invalid_user_id_too_long(self):
        """Test user ID validation with strings that are too long."""
        long_id = "x" * 256  # 256 chars
        with pytest.raises(ValueError, match="UserId too long \\(max 255 chars\\)"):
            validate_user_id(long_id)


class TestValidateTopicId:
    """Tests for topic ID validation."""

    def test_valid_topic_ids(self):
        """Test valid topic ID formats."""
        valid_ids = [
            "topic_test_123456",  # Alphanumeric with underscores
            "music-rock",  # With hyphens
            "/m/019_rr",  # Knowledge graph ID (music)
            "/g/1234567890",  # Knowledge graph ID (general)
            "simple",  # Simple alphanumeric
            "a" * 50,  # Maximum length
        ]

        for topic_id in valid_ids:
            result = validate_topic_id(topic_id)
            assert result == topic_id.strip()
            assert len(result) <= 50
            assert result  # Not empty

    def test_valid_topic_id_with_whitespace(self):
        """Test topic ID validation strips whitespace."""
        topic_id_with_spaces = "  music-rock  "
        result = validate_topic_id(topic_id_with_spaces)
        assert result == "music-rock"

    def test_invalid_topic_id_type(self):
        """Test topic ID validation with wrong type."""
        with pytest.raises(TypeError, match="TopicId must be a string"):
            validate_topic_id(123)  # type: ignore

        with pytest.raises(TypeError, match="TopicId must be a string"):
            validate_topic_id([])  # type: ignore

    def test_invalid_topic_id_empty(self):
        """Test topic ID validation with empty or whitespace-only strings."""
        with pytest.raises(
            ValueError, match="TopicId cannot be empty or whitespace-only"
        ):
            validate_topic_id("")

        with pytest.raises(
            ValueError, match="TopicId cannot be empty or whitespace-only"
        ):
            validate_topic_id("   ")

    def test_invalid_topic_id_too_long(self):
        """Test topic ID validation with strings that are too long."""
        long_id = "x" * 51  # 51 chars
        with pytest.raises(ValueError, match="TopicId too long \\(max 50 chars\\)"):
            validate_topic_id(long_id)

    def test_invalid_topic_id_characters(self):
        """Test topic ID validation with invalid characters."""
        with pytest.raises(ValueError, match="TopicId must be a knowledge graph ID"):
            validate_topic_id("topic@invalid")  # Contains @

        with pytest.raises(ValueError, match="TopicId must be a knowledge graph ID"):
            validate_topic_id("topic invalid")  # Contains space

        with pytest.raises(ValueError, match="TopicId must be a knowledge graph ID"):
            validate_topic_id("/invalid/path")  # Invalid knowledge graph format


class TestValidateCaptionId:
    """Tests for caption ID validation."""

    def test_valid_caption_ids(self):
        """Test valid caption ID formats."""
        valid_ids = [
            "cap_test_12345678",  # Test format
            "en_US",  # Language code format
            "auto-generated",  # With hyphens
            "manual_captions_v1",  # With underscores
            "a" * 100,  # Maximum length
        ]

        for caption_id in valid_ids:
            result = validate_caption_id(caption_id)
            assert result == caption_id.strip()
            assert len(result) <= 100
            assert result  # Not empty

    def test_valid_caption_id_with_whitespace(self):
        """Test caption ID validation strips whitespace."""
        caption_id_with_spaces = "  en_US  "
        result = validate_caption_id(caption_id_with_spaces)
        assert result == "en_US"

    def test_invalid_caption_id_type(self):
        """Test caption ID validation with wrong type."""
        with pytest.raises(TypeError, match="CaptionId must be a string"):
            validate_caption_id(123)  # type: ignore

        with pytest.raises(TypeError, match="CaptionId must be a string"):
            validate_caption_id(None)  # type: ignore

    def test_invalid_caption_id_empty(self):
        """Test caption ID validation with empty or whitespace-only strings."""
        with pytest.raises(
            ValueError, match="CaptionId cannot be empty or whitespace-only"
        ):
            validate_caption_id("")

        with pytest.raises(
            ValueError, match="CaptionId cannot be empty or whitespace-only"
        ):
            validate_caption_id("   ")

    def test_invalid_caption_id_too_long(self):
        """Test caption ID validation with strings that are too long."""
        long_id = "x" * 101  # 101 chars
        with pytest.raises(ValueError, match="CaptionId too long \\(max 100 chars\\)"):
            validate_caption_id(long_id)

    def test_invalid_caption_id_characters(self):
        """Test caption ID validation with invalid characters."""
        with pytest.raises(
            ValueError,
            match="CaptionId can only contain letters, numbers, hyphens, and underscores",
        ):
            validate_caption_id("cap@invalid")  # Contains @

        with pytest.raises(
            ValueError,
            match="CaptionId can only contain letters, numbers, hyphens, and underscores",
        ):
            validate_caption_id("cap invalid")  # Contains space

        with pytest.raises(
            ValueError,
            match="CaptionId can only contain letters, numbers, hyphens, and underscores",
        ):
            validate_caption_id("cap.invalid")  # Contains dot


class TestCreateTestPlaylistId:
    """Tests for test playlist ID factory function."""

    def test_create_test_playlist_id_default(self):
        """Test creating test playlist ID with default suffix."""
        playlist_id = create_test_playlist_id()

        # Should be valid
        validate_playlist_id(playlist_id)

        # Should follow expected format
        assert playlist_id.startswith("PLtest_")
        assert len(playlist_id) == 34
        assert "test" in playlist_id

    def test_create_test_playlist_id_custom_suffix(self):
        """Test creating test playlist ID with custom suffix."""
        playlist_id = create_test_playlist_id("music")

        # Should be valid
        validate_playlist_id(playlist_id)

        # Should contain custom suffix
        assert "music" in playlist_id
        assert len(playlist_id) == 34

    def test_create_test_playlist_id_different_calls(self):
        """Test that different calls create different IDs."""
        id1 = create_test_playlist_id("first")
        id2 = create_test_playlist_id("second")

        assert id1 != id2
        assert "first" in id1
        assert "second" in id2

    def test_create_test_playlist_id_long_suffix(self):
        """Test creating test playlist ID with very long suffix."""
        long_suffix = "very_long_suffix_that_might_exceed_limits"
        playlist_id = create_test_playlist_id(long_suffix)

        # Should still be valid and exactly 34 chars
        validate_playlist_id(playlist_id)
        assert len(playlist_id) == 34


class TestCreateTestChannelId:
    """Tests for test channel ID factory function."""

    def test_create_test_channel_id_default(self):
        """Test creating test channel ID with default suffix."""
        channel_id = create_test_channel_id()

        # Should be valid
        validate_channel_id(channel_id)

        # Should follow expected format
        assert channel_id.startswith("UCtest_")
        assert len(channel_id) == 24
        assert "test" in channel_id

    def test_create_test_channel_id_custom_suffix(self):
        """Test creating test channel ID with custom suffix."""
        channel_id = create_test_channel_id("rick")

        # Should be valid
        validate_channel_id(channel_id)

        # Should contain custom suffix
        assert "rick" in channel_id
        assert len(channel_id) == 24

    def test_create_test_channel_id_different_calls(self):
        """Test that different calls create different IDs."""
        id1 = create_test_channel_id("first")
        id2 = create_test_channel_id("second")

        assert id1 != id2

    def test_create_test_channel_id_long_suffix(self):
        """Test creating test channel ID with very long suffix."""
        long_suffix = "very_long_suffix"
        channel_id = create_test_channel_id(long_suffix)

        # Should still be valid and exactly 24 chars
        validate_channel_id(channel_id)
        assert len(channel_id) == 24


class TestCreateTestVideoId:
    """Tests for test video ID factory function."""

    def test_create_test_video_id_default(self):
        """Test creating test video ID with default suffix."""
        video_id = create_test_video_id()

        # Should be valid
        validate_video_id(video_id)

        # Should follow expected format
        assert len(video_id) == 11
        assert "test" in video_id

    def test_create_test_video_id_custom_suffix(self):
        """Test creating test video ID with custom suffix."""
        video_id = create_test_video_id("vid")

        # Should be valid
        validate_video_id(video_id)

        # Should contain custom suffix
        assert "vid" in video_id
        assert len(video_id) == 11

    def test_create_test_video_id_different_calls(self):
        """Test that different calls create different IDs."""
        id1 = create_test_video_id("a")
        id2 = create_test_video_id("b")

        assert id1 != id2

    def test_create_test_video_id_long_suffix(self):
        """Test creating test video ID with very long suffix."""
        long_suffix = "verylongname"
        video_id = create_test_video_id(long_suffix)

        # Should still be valid and exactly 11 chars
        validate_video_id(video_id)
        assert len(video_id) == 11


class TestCreateTestUserId:
    """Tests for test user ID factory function."""

    def test_create_test_user_id_default(self):
        """Test creating test user ID with default suffix."""
        user_id = create_test_user_id()

        # Should be valid
        validate_user_id(user_id)

        # Should follow expected format
        assert user_id.startswith("user_test_")
        assert len(user_id) <= 255

    def test_create_test_user_id_custom_suffix(self):
        """Test creating test user ID with custom suffix."""
        user_id = create_test_user_id("admin")

        # Should be valid
        validate_user_id(user_id)

        # Should contain custom suffix
        assert "admin" in user_id

    def test_create_test_user_id_different_calls(self):
        """Test that different calls create different IDs."""
        id1 = create_test_user_id("first")
        id2 = create_test_user_id("second")

        assert id1 != id2

    def test_create_test_user_id_long_suffix(self):
        """Test creating test user ID with very long suffix."""
        long_suffix = "very_long_user_name_that_is_quite_extensive"
        user_id = create_test_user_id(long_suffix)

        # Should still be valid
        validate_user_id(user_id)


class TestCreateTestTopicId:
    """Tests for test topic ID factory function."""

    def test_create_test_topic_id_default(self):
        """Test creating test topic ID with default suffix."""
        topic_id = create_test_topic_id()

        # Should be valid
        validate_topic_id(topic_id)

        # Should follow expected format
        assert topic_id.startswith("topic_test_")
        assert len(topic_id) <= 50

    def test_create_test_topic_id_custom_suffix(self):
        """Test creating test topic ID with custom suffix."""
        topic_id = create_test_topic_id("music")

        # Should be valid
        validate_topic_id(topic_id)

        # Should contain custom suffix
        assert "music" in topic_id

    def test_create_test_topic_id_different_calls(self):
        """Test that different calls create different IDs."""
        id1 = create_test_topic_id("first")
        id2 = create_test_topic_id("second")

        assert id1 != id2

    def test_create_test_topic_id_long_suffix(self):
        """Test creating test topic ID with very long suffix."""
        long_suffix = "very_long_topic_name"
        topic_id = create_test_topic_id(long_suffix)

        # Should still be valid and within limits
        validate_topic_id(topic_id)
        assert len(topic_id) <= 50


class TestCreateTestCaptionId:
    """Tests for test caption ID factory function."""

    def test_create_test_caption_id_default(self):
        """Test creating test caption ID with default suffix."""
        caption_id = create_test_caption_id()

        # Should be valid
        validate_caption_id(caption_id)

        # Should follow expected format
        assert caption_id.startswith("cap_test_")
        assert len(caption_id) <= 100

    def test_create_test_caption_id_custom_suffix(self):
        """Test creating test caption ID with custom suffix."""
        caption_id = create_test_caption_id("en")

        # Should be valid
        validate_caption_id(caption_id)

        # Should contain custom suffix
        assert "en" in caption_id

    def test_create_test_caption_id_different_calls(self):
        """Test that different calls create different IDs."""
        id1 = create_test_caption_id("first")
        id2 = create_test_caption_id("second")

        assert id1 != id2

    def test_create_test_caption_id_long_suffix(self):
        """Test creating test caption ID with very long suffix."""
        long_suffix = "very_long_caption_identifier"
        caption_id = create_test_caption_id(long_suffix)

        # Should still be valid and within limits
        validate_caption_id(caption_id)
        assert len(caption_id) <= 100


class TestPydanticIntegration:
    """Tests for Pydantic type integration."""

    def test_type_alias_usage(self):
        """Test that type aliases work with Pydantic."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            playlist_id: PlaylistId
            channel_id: ChannelId
            video_id: VideoId
            user_id: UserId
            topic_id: TopicId
            caption_id: CaptionId

        # Valid data should work
        valid_data = {
            "playlist_id": "PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "video_id": "dQw4w9WgXcQ",
            "user_id": "test_user",
            "topic_id": "music-rock",
            "caption_id": "en_US",
        }

        model = TestModel(**valid_data)
        assert model.playlist_id == valid_data["playlist_id"]
        assert model.channel_id == valid_data["channel_id"]
        assert model.video_id == valid_data["video_id"]
        assert model.user_id == valid_data["user_id"]
        assert model.topic_id == valid_data["topic_id"]
        assert model.caption_id == valid_data["caption_id"]

    def test_type_alias_validation_errors(self):
        """Test that type aliases validate correctly in Pydantic."""
        from pydantic import BaseModel, ValidationError

        class TestModel(BaseModel):
            playlist_id: PlaylistId

        # Invalid playlist ID should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            TestModel(playlist_id="invalid")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "playlist_id" in str(errors[0])


class TestInternalPlaylistIdHelpers:
    """Tests for INT_ prefix validation and helper functions (T035)."""

    def test_is_internal_playlist_id_true_for_int_prefix(self):
        """Test is_internal_playlist_id returns True for INT_ prefix."""
        assert is_internal_playlist_id("int_f7abe60f1234567890abcdef12345678")
        assert is_internal_playlist_id("INT_F7ABE60F1234567890ABCDEF12345678")
        assert is_internal_playlist_id("InT_MixedCase1234567890abcdef123456")

    def test_is_internal_playlist_id_false_for_pl_prefix(self):
        """Test is_internal_playlist_id returns False for PL prefix."""
        assert not is_internal_playlist_id("PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK")
        assert not is_internal_playlist_id("PLtest_123456_music_xxxxxxxxxx")

    def test_is_internal_playlist_id_false_for_invalid(self):
        """Test is_internal_playlist_id returns False for invalid inputs."""
        assert not is_internal_playlist_id("")
        assert not is_internal_playlist_id(None)
        assert not is_internal_playlist_id(123)
        assert not is_internal_playlist_id("random_string")

    def test_is_youtube_playlist_id_true_for_pl_prefix(self):
        """Test is_youtube_playlist_id returns True for PL prefix."""
        assert is_youtube_playlist_id("PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK")
        assert is_youtube_playlist_id("PLtest_123456_music_xxxxxxxxxx")

    def test_is_youtube_playlist_id_false_for_int_prefix(self):
        """Test is_youtube_playlist_id returns False for INT_ prefix."""
        assert not is_youtube_playlist_id("int_f7abe60f1234567890abcdef12345678")
        assert not is_youtube_playlist_id("INT_F7ABE60F1234567890ABCDEF12345678")

    def test_is_youtube_playlist_id_false_for_invalid(self):
        """Test is_youtube_playlist_id returns False for invalid inputs."""
        assert not is_youtube_playlist_id("")
        assert not is_youtube_playlist_id(None)
        assert not is_youtube_playlist_id(123)
        assert not is_youtube_playlist_id("random_string")

    def test_validate_youtube_id_format_accepts_valid_pl(self):
        """Test validate_youtube_id_format accepts valid PL IDs."""
        # Valid PL IDs (30-50 chars)
        valid_ids = [
            "PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK",  # 34 chars
            "PL" + "a" * 28,  # 30 chars (minimum)
            "PL" + "Z" * 48,  # 50 chars (maximum)
            "PLtest_123-ABC_xyz-012_padding",  # With hyphens and underscores (30 chars)
        ]
        for playlist_id in valid_ids:
            result = validate_youtube_id_format(playlist_id)
            assert result == playlist_id

    def test_validate_youtube_id_format_rejects_invalid_prefix(self):
        """Test validate_youtube_id_format rejects wrong prefix."""
        with pytest.raises(ValueError, match='must start with "PL"'):
            validate_youtube_id_format("INT_f7abe60f1234567890abcdef12345678")

        with pytest.raises(ValueError, match='must start with "PL"'):
            validate_youtube_id_format("UCuAXFkgsw1L7xaCfnd5JJOw")

    def test_validate_youtube_id_format_rejects_invalid_length(self):
        """Test validate_youtube_id_format rejects wrong length."""
        # Too short (29 chars)
        with pytest.raises(ValueError, match="must be 30-50 chars"):
            validate_youtube_id_format("PL" + "x" * 27)

        # Too long (51 chars)
        with pytest.raises(ValueError, match="must be 30-50 chars"):
            validate_youtube_id_format("PL" + "x" * 49)

    def test_validate_youtube_id_format_rejects_invalid_characters(self):
        """Test validate_youtube_id_format rejects bad characters."""
        with pytest.raises(ValueError, match="contains invalid characters"):
            validate_youtube_id_format("PL" + "x" * 28 + "@")

        with pytest.raises(ValueError, match="contains invalid characters"):
            validate_youtube_id_format("PL" + "x" * 28 + " ")

    def test_validate_playlist_id_accepts_int_prefix(self):
        """Test PlaylistId validator accepts INT_ prefix (36 chars)."""
        # Valid INT_ IDs
        int_id = "int_f7abe60f1234567890abcdef12345678"
        result = validate_playlist_id(int_id)
        assert result == int_id
        assert len(result) == 36

    def test_validate_playlist_id_accepts_pl_prefix(self):
        """Test PlaylistId validator accepts PL prefix (30-50 chars)."""
        pl_id = "PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK"
        result = validate_playlist_id(pl_id)
        assert result == pl_id
        assert 30 <= len(result) <= 50

    def test_int_normalization_uppercase_to_lowercase(self):
        """Test INT_ normalization: uppercase becomes lowercase."""
        uppercase_int = "INT_F7ABE60F1234567890ABCDEF12345678"
        result = validate_playlist_id(uppercase_int)
        assert result == "int_f7abe60f1234567890abcdef12345678"
        assert result.islower()

    def test_pl_case_preservation(self):
        """Test PL case preservation: mixed case stays as-is."""
        mixed_case_pl = "PLaBc123_DeF456_GhI789_JkL012xyz"
        result = validate_playlist_id(mixed_case_pl)
        assert result == mixed_case_pl  # Case preserved

    def test_boundary_int_35_chars_rejected(self):
        """Test boundary: 35-char INT_ ID rejected."""
        # INT_ (4 chars) + 31 hex chars = 35 chars (should be 36)
        invalid_int = "INT_" + "a" * 31
        with pytest.raises(ValueError, match="must be 36 characters"):
            validate_playlist_id(invalid_int)

    def test_boundary_pl_29_chars_rejected(self):
        """Test boundary: 29-char PL ID rejected."""
        invalid_pl = "PL" + "x" * 27  # 29 chars
        with pytest.raises(ValueError, match="must be 30-50 chars"):
            validate_playlist_id(invalid_pl)

    def test_boundary_pl_51_chars_rejected(self):
        """Test boundary: 51-char PL ID rejected."""
        invalid_pl = "PL" + "x" * 49  # 51 chars
        with pytest.raises(ValueError, match="must be 30-50 chars"):
            validate_playlist_id(invalid_pl)

    def test_fail_fast_validation_order_format_first(self):
        """Test fail-fast: format checked before length."""
        # Wrong prefix, wrong length - should fail on prefix first
        with pytest.raises(ValueError, match='must start with "INT_" or "PL"'):
            validate_playlist_id("XY" + "x" * 10)

    def test_fail_fast_validation_order_length_second(self):
        """Test fail-fast: length checked before characters."""
        # Valid prefix (PL), wrong length, invalid chars - should fail on length
        with pytest.raises(ValueError, match="must be 30-50 chars"):
            validate_playlist_id("PL@#$%")

    def test_fail_fast_validation_order_characters_last(self):
        """Test fail-fast: characters checked last."""
        # Valid prefix, valid length (30 chars), invalid chars
        with pytest.raises(ValueError, match="contains invalid characters"):
            validate_playlist_id("PL" + "x" * 27 + "@")


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_regex_patterns(self):
        """Test that regex patterns work correctly."""
        # Test playlist ID pattern
        assert re.match(r"^PL[A-Za-z0-9_-]+$", "PLtest_123-abc_XYZ")
        assert not re.match(r"^PL[A-Za-z0-9_-]+$", "PLtest@invalid")

        # Test channel ID pattern
        assert re.match(r"^UC[A-Za-z0-9_-]+$", "UCtest_123-abc_XYZ")
        assert not re.match(r"^UC[A-Za-z0-9_-]+$", "UCtest@invalid")

        # Test video ID pattern
        assert re.match(r"^[A-Za-z0-9_-]+$", "test_123-abc")
        assert not re.match(r"^[A-Za-z0-9_-]+$", "test@invalid")

        # Test topic ID pattern
        assert re.match(r"^(/[mg]/[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+)$", "/m/019_rr")
        assert re.match(r"^(/[mg]/[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+)$", "music-rock")
        assert not re.match(r"^(/[mg]/[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+)$", "/invalid/path")

    def test_boundary_lengths(self):
        """Test boundary length conditions."""
        # Playlist ID: 30-34 chars
        assert validate_playlist_id("PL" + "x" * 28)  # 30 chars
        assert validate_playlist_id("PL" + "x" * 32)  # 34 chars

        # Channel ID: exactly 24 chars
        assert validate_channel_id("UC" + "x" * 22)  # 24 chars

        # Video ID: exactly 11 chars
        assert validate_video_id("x" * 11)  # 11 chars

        # User ID: max 255 chars
        assert validate_user_id("x" * 255)  # 255 chars

        # Topic ID: max 50 chars
        assert validate_topic_id("x" * 50)  # 50 chars

        # Caption ID: max 100 chars
        assert validate_caption_id("x" * 100)  # 100 chars

    def test_unicode_handling(self):
        """Test handling of unicode characters."""
        # Most validators should reject unicode
        with pytest.raises(ValueError):
            validate_playlist_id("PLtest_unicode_café_xxxxx")

        with pytest.raises(ValueError):
            validate_channel_id("UCtest_unicode_café_xx")

        with pytest.raises(ValueError):
            validate_video_id("café_test12")

        # But user_id should accept unicode since it's more flexible
        user_id = validate_user_id("user_café_test")
        assert "café" in user_id

    def test_whitespace_normalization(self):
        """Test whitespace handling and normalization."""
        # User ID normalizes whitespace
        assert validate_user_id("  test_user  ") == "test_user"

        # Topic ID normalizes whitespace
        assert validate_topic_id("  music-rock  ") == "music-rock"

        # Caption ID normalizes whitespace
        assert validate_caption_id("  en_US  ") == "en_US"

        # But IDs with fixed formats don't accept leading/trailing whitespace
        with pytest.raises(ValueError):
            validate_playlist_id("  PLtest_123456_music_xxxxxxxxxx  ")
