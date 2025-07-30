"""
ID Factory for generating valid YouTube IDs.

Provides factory methods to generate valid YouTube channel IDs, video IDs,
playlist IDs, and user IDs that meet all validation requirements.
"""

import hashlib
import random
import string
from typing import Optional


class YouTubeIdFactory:
    """Factory for generating valid YouTube IDs."""

    @staticmethod
    def create_channel_id(seed: Optional[str] = None) -> str:
        """
        Create a valid 24-character YouTube channel ID starting with 'UC'.

        Parameters
        ----------
        seed : Optional[str]
            Optional seed for deterministic ID generation

        Returns
        -------
        str
            Valid 24-character channel ID starting with 'UC'
        """
        if seed:
            # Use hash for deterministic generation
            hash_value = hashlib.md5(seed.encode()).hexdigest()[:22]
        else:
            # Generate random 22 characters
            hash_value = "".join(
                random.choices(string.ascii_letters + string.digits, k=22)
            )

        return f"UC{hash_value}"

    @staticmethod
    def create_video_id(seed: Optional[str] = None) -> str:
        """
        Create a valid 11-character YouTube video ID.

        Parameters
        ----------
        seed : Optional[str]
            Optional seed for deterministic ID generation

        Returns
        -------
        str
            Valid 11-character video ID
        """
        if seed:
            # Use hash for deterministic generation
            hash_value = hashlib.md5(seed.encode()).hexdigest()[:11]
        else:
            # Generate random 11 characters (YouTube uses base64-like chars)
            chars = string.ascii_letters + string.digits + "-_"
            hash_value = "".join(random.choices(chars, k=11))

        return hash_value

    @staticmethod
    def create_playlist_id(seed: Optional[str] = None) -> str:
        """
        Create a valid 30-34 character YouTube playlist ID starting with 'PL'.

        Parameters
        ----------
        seed : Optional[str]
            Optional seed for deterministic ID generation

        Returns
        -------
        str
            Valid 30-34 character playlist ID starting with 'PL'
        """
        if seed:
            # Use hash for deterministic generation, make it 32 chars total
            hash_value = hashlib.md5(seed.encode()).hexdigest()[:32]
        else:
            # Generate random 32 characters (34 chars total with 'PL' prefix)
            chars = string.ascii_letters + string.digits + "-_"
            hash_value = "".join(random.choices(chars, k=32))

        return f"PL{hash_value}"

    @staticmethod
    def create_user_id(seed: Optional[str] = None) -> str:
        """
        Create a valid user ID.

        Parameters
        ----------
        seed : Optional[str]
            Optional seed for deterministic ID generation

        Returns
        -------
        str
            Valid user ID
        """
        if seed:
            return f"user_{hashlib.md5(seed.encode()).hexdigest()[:16]}"
        else:
            return f"user_{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}"

    @staticmethod
    def create_topic_id(seed: Optional[str] = None) -> str:
        """
        Create a valid topic ID.

        Parameters
        ----------
        seed : Optional[str]
            Optional seed for deterministic ID generation

        Returns
        -------
        str
            Valid topic ID (up to 50 characters)
        """
        if seed:
            # Use hash for deterministic generation
            hash_value = hashlib.md5(seed.encode()).hexdigest()
            return f"topic_{hash_value[:32]}"  # 38 chars total, well under 50
        else:
            # Generate random topic ID
            suffix = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=16)
            )
            return f"topic_{suffix}"


# Convenience functions for easy access
def channel_id(seed: Optional[str] = None) -> str:
    """Generate a valid channel ID."""
    return YouTubeIdFactory.create_channel_id(seed)


def video_id(seed: Optional[str] = None) -> str:
    """Generate a valid video ID."""
    return YouTubeIdFactory.create_video_id(seed)


def playlist_id(seed: Optional[str] = None) -> str:
    """Generate a valid playlist ID."""
    return YouTubeIdFactory.create_playlist_id(seed)


def user_id(seed: Optional[str] = None) -> str:
    """Generate a valid user ID."""
    return YouTubeIdFactory.create_user_id(seed)


def topic_id(seed: Optional[str] = None) -> str:
    """Generate a valid topic ID."""
    return YouTubeIdFactory.create_topic_id(seed)


# Predefined IDs for consistent testing
class TestIds:
    """Predefined valid IDs for consistent testing."""

    # Channels
    RICK_ASTLEY_CHANNEL = YouTubeIdFactory.create_channel_id("rick_astley")
    TEST_CHANNEL_1 = YouTubeIdFactory.create_channel_id("test_channel_1")
    TEST_CHANNEL_2 = YouTubeIdFactory.create_channel_id("test_channel_2")
    USER_CHANNEL = YouTubeIdFactory.create_channel_id("user_channel")

    # Videos
    NEVER_GONNA_GIVE_YOU_UP = YouTubeIdFactory.create_video_id(
        "never_gonna_give_you_up"
    )
    TEST_VIDEO_1 = YouTubeIdFactory.create_video_id("test_video_1")
    TEST_VIDEO_2 = YouTubeIdFactory.create_video_id("test_video_2")
    DELETED_VIDEO = YouTubeIdFactory.create_video_id("deleted_video")

    # Playlists
    FAVORITES_PLAYLIST = YouTubeIdFactory.create_playlist_id("my_favorites")
    WATCH_LATER_PLAYLIST = YouTubeIdFactory.create_playlist_id("watch_later")
    TEST_PLAYLIST = YouTubeIdFactory.create_playlist_id("test_playlist")
    TEST_PLAYLIST_1 = YouTubeIdFactory.create_playlist_id("test_playlist_1")
    TEST_PLAYLIST_2 = YouTubeIdFactory.create_playlist_id("test_playlist_2")

    # Users
    TEST_USER = YouTubeIdFactory.create_user_id("test_user")
    TAKEOUT_USER = YouTubeIdFactory.create_user_id("takeout_user")

    # Topics
    MUSIC_TOPIC = YouTubeIdFactory.create_topic_id("music")
    GAMING_TOPIC = YouTubeIdFactory.create_topic_id("gaming")
    EDUCATION_TOPIC = YouTubeIdFactory.create_topic_id("education")
    ENTERTAINMENT_TOPIC = YouTubeIdFactory.create_topic_id("entertainment")
