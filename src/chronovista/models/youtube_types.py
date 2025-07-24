"""
Custom validated types for YouTube API entities.

Provides strongly-typed wrappers for YouTube IDs that enforce format and length
constraints at the type level, improving type safety and preventing validation errors.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BeforeValidator, Field


def validate_playlist_id(v: str) -> str:
    """Validate YouTube Playlist ID format."""
    if not isinstance(v, str):
        raise TypeError("PlaylistId must be a string")

    # Check length
    if not (30 <= len(v) <= 34):
        raise ValueError(f"PlaylistId must be 30-34 characters long, got {len(v)}: {v}")

    # Check prefix
    if not v.startswith("PL"):
        raise ValueError(f'PlaylistId must start with "PL", got: {v}')

    # Check valid characters (alphanumeric, hyphens, underscores)
    if not re.match(r"^PL[A-Za-z0-9_-]+$", v):
        raise ValueError(f"PlaylistId contains invalid characters: {v}")

    return v


def validate_channel_id(v: str) -> str:
    """Validate YouTube Channel ID format."""
    if not isinstance(v, str):
        raise TypeError("ChannelId must be a string")

    # Check length
    if len(v) != 24:
        raise ValueError(
            f"ChannelId must be exactly 24 characters long, got {len(v)}: {v}"
        )

    # Check prefix
    if not v.startswith("UC"):
        raise ValueError(f'ChannelId must start with "UC", got: {v}')

    # Check valid characters (alphanumeric, hyphens, underscores)
    if not re.match(r"^UC[A-Za-z0-9_-]+$", v):
        raise ValueError(f"ChannelId contains invalid characters: {v}")

    return v


def validate_video_id(v: str) -> str:
    """Validate YouTube Video ID format."""
    if not isinstance(v, str):
        raise TypeError("VideoId must be a string")

    # Check length
    if len(v) != 11:
        raise ValueError(
            f"VideoId must be exactly 11 characters long, got {len(v)}: {v}"
        )

    # Check valid characters (alphanumeric, hyphens, underscores)
    if not re.match(r"^[A-Za-z0-9_-]+$", v):
        raise ValueError(f"VideoId contains invalid characters: {v}")

    return v


def validate_user_id(v: str) -> str:
    """Validate User ID format."""
    if not isinstance(v, str):
        raise TypeError("UserId must be a string")

    # Check not empty after stripping whitespace
    cleaned = v.strip()
    if not cleaned:
        raise ValueError("UserId cannot be empty or whitespace-only")

    # Check reasonable length limits (YouTube user IDs are typically channel IDs or email-like)
    if len(cleaned) > 255:
        raise ValueError(
            f"UserId too long (max 255 chars), got {len(cleaned)}: {cleaned[:50]}..."
        )

    return cleaned


def validate_topic_id(v: str) -> str:
    """Validate Topic ID format."""
    if not isinstance(v, str):
        raise TypeError("TopicId must be a string")

    # Check not empty after stripping whitespace
    cleaned = v.strip()
    if not cleaned:
        raise ValueError("TopicId cannot be empty or whitespace-only")

    # Check length limits (max 50 characters as per TopicCategory model)
    if len(cleaned) > 50:
        raise ValueError(
            f"TopicId too long (max 50 chars), got {len(cleaned)}: {cleaned}"
        )

    # Allow alphanumeric, hyphens, underscores (as per TopicCategory validation)
    if not re.match(r"^[a-zA-Z0-9_-]+$", cleaned):
        raise ValueError(
            f"TopicId can only contain letters, numbers, hyphens, and underscores: {cleaned}"
        )

    return cleaned


def validate_caption_id(v: str) -> str:
    """Validate Caption ID format."""
    if not isinstance(v, str):
        raise TypeError("CaptionId must be a string")

    # Check not empty after stripping whitespace
    cleaned = v.strip()
    if not cleaned:
        raise ValueError("CaptionId cannot be empty or whitespace-only")

    # Check reasonable length limits (YouTube caption IDs are typically 20-30 characters)
    if len(cleaned) > 100:
        raise ValueError(
            f"CaptionId too long (max 100 chars), got {len(cleaned)}: {cleaned}"
        )

    # Allow alphanumeric, hyphens, underscores (common in YouTube APIs)
    if not re.match(r"^[A-Za-z0-9_-]+$", cleaned):
        raise ValueError(
            f"CaptionId can only contain letters, numbers, hyphens, and underscores: {cleaned}"
        )

    return cleaned


# Type aliases for use in Pydantic models
PlaylistId = Annotated[
    str,
    BeforeValidator(validate_playlist_id),
    Field(description="YouTube Playlist ID (30-34 chars, starts with PL)"),
]

ChannelId = Annotated[
    str,
    BeforeValidator(validate_channel_id),
    Field(description="YouTube Channel ID (24 chars, starts with UC)"),
]

VideoId = Annotated[
    str,
    BeforeValidator(validate_video_id),
    Field(description="YouTube Video ID (11 chars, alphanumeric)"),
]

UserId = Annotated[
    str,
    BeforeValidator(validate_user_id),
    Field(description="User identifier (non-empty string, max 255 chars)"),
]

TopicId = Annotated[
    str,
    BeforeValidator(validate_topic_id),
    Field(
        description="Topic identifier (alphanumeric with hyphens/underscores, max 50 chars)"
    ),
]

CaptionId = Annotated[
    str,
    BeforeValidator(validate_caption_id),
    Field(
        description="Caption track identifier (alphanumeric with hyphens/underscores, max 100 chars)"
    ),
]


# Factory functions for creating valid test IDs
def create_test_playlist_id(suffix: str = "test") -> str:
    """
    Create a valid test playlist ID.

    Args:
        suffix: Custom suffix for the playlist ID

    Returns:
        Valid YouTube playlist ID string for testing
    """
    import time

    timestamp = str(int(time.time()))[-8:]  # Last 8 digits

    # Format: PLtest_{timestamp}_{suffix}_{padding}
    base = f"PLtest_{timestamp}_{suffix}_"
    padding_needed = 34 - len(base)
    padding = "x" * max(0, padding_needed)

    playlist_id = f"{base}{padding}"[:34]  # Ensure exactly 34 chars
    return validate_playlist_id(playlist_id)


def create_test_channel_id(suffix: str = "test") -> str:
    """
    Create a valid test channel ID.

    Args:
        suffix: Custom suffix for the channel ID

    Returns:
        Valid YouTube channel ID string for testing
    """
    import time

    timestamp = str(int(time.time()))[-6:]  # Last 6 digits

    # Format: UCtest_{timestamp}_{suffix}_{padding}
    base = f"UCtest_{timestamp}_{suffix}_"
    padding_needed = 24 - len(base)
    padding = "x" * max(0, padding_needed)

    channel_id = f"{base}{padding}"[:24]  # Ensure exactly 24 chars
    return validate_channel_id(channel_id)


def create_test_video_id(suffix: str = "test") -> str:
    """
    Create a valid test video ID.

    Args:
        suffix: Custom suffix for the video ID

    Returns:
        Valid YouTube video ID string for testing
    """
    import time

    timestamp = str(int(time.time()))[-4:]  # Last 4 digits

    # Format: {suffix}_{timestamp}_{padding} (11 chars total)
    base = f"{suffix}_{timestamp}_"
    padding_needed = 11 - len(base)
    padding = "x" * max(0, padding_needed)

    video_id = f"{base}{padding}"[:11]  # Ensure exactly 11 chars
    return validate_video_id(video_id)


def create_test_user_id(suffix: str = "test") -> str:
    """
    Create a valid test user ID.

    Args:
        suffix: Custom suffix for the user ID

    Returns:
        Valid user ID string for testing
    """
    import time

    timestamp = str(int(time.time()))[-8:]  # Last 8 digits

    # Format: user_{suffix}_{timestamp}
    user_id = f"user_{suffix}_{timestamp}"
    return validate_user_id(user_id)


def create_test_topic_id(suffix: str = "test") -> str:
    """
    Create a valid test topic ID.

    Args:
        suffix: Custom suffix for the topic ID

    Returns:
        Valid topic ID string for testing
    """
    import time

    timestamp = str(int(time.time()))[-6:]  # Last 6 digits

    # Format: topic_{suffix}_{timestamp} (max 50 chars)
    topic_id = f"topic_{suffix}_{timestamp}"
    return validate_topic_id(topic_id)


def create_test_caption_id(suffix: str = "test") -> str:
    """
    Create a valid test caption ID.

    Args:
        suffix: Custom suffix for the caption ID

    Returns:
        Valid caption ID string for testing
    """
    import time

    timestamp = str(int(time.time()))[-8:]  # Last 8 digits

    # Format: cap_{suffix}_{timestamp} (max 100 chars)
    caption_id = f"cap_{suffix}_{timestamp}"
    return validate_caption_id(caption_id)


# Example usage and testing
if __name__ == "__main__":
    # Test playlist ID creation
    try:
        # Valid playlist IDs
        playlist1 = validate_playlist_id("PLdU2XMVb99xOK9Ch9k0X9kWJwGQ3P5yZK")
        playlist2 = create_test_playlist_id("music")
        print(f"✅ Valid playlist IDs: {playlist1}, {playlist2}")

        # Invalid playlist ID (too short)
        validate_playlist_id("PLshort")
    except ValueError as e:
        print(f"❌ Expected validation error: {e}")

    # Test channel ID creation
    try:
        # Valid channel IDs
        channel1 = validate_channel_id("UCuAXFkgsw1L7xaCfnd5JJOw")
        channel2 = create_test_channel_id("rick")
        print(f"✅ Valid channel IDs: {channel1}, {channel2}")

        # Invalid channel ID (wrong prefix)
        validate_channel_id("PLuAXFkgsw1L7xaCfnd5JJOw")
    except ValueError as e:
        print(f"❌ Expected validation error: {e}")

    # Test video ID creation
    try:
        # Valid video IDs
        video1 = validate_video_id("dQw4w9WgXcQ")
        video2 = create_test_video_id("rick")
        print(f"✅ Valid video IDs: {video1}, {video2}")

        # Invalid video ID (too long)
        validate_video_id("dQw4w9WgXcQTooLong")
    except ValueError as e:
        print(f"❌ Expected validation error: {e}")

    # Test user ID creation
    try:
        # Valid user IDs
        user1 = validate_user_id("user_test_123")
        user2 = create_test_user_id("alice")
        print(f"✅ Valid user IDs: {user1}, {user2}")

        # Invalid user ID (empty)
        validate_user_id("   ")
    except ValueError as e:
        print(f"❌ Expected validation error: {e}")
