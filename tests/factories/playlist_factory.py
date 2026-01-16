"""
Factory for Playlist models using factory_boy.

Provides reusable test data factories for all Playlist model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, cast

import factory
from factory import Faker, LazyAttribute

from chronovista.models.playlist import (
    Playlist,
    PlaylistBase,
    PlaylistCreate,
    PlaylistSearchFilters,
    PlaylistStatistics,
    PlaylistUpdate,
)


class PlaylistBaseFactory(factory.Factory[PlaylistBase]):
    """Factory for PlaylistBase models."""

    class Meta:
        model = PlaylistBase

    playlist_id: Any = factory.LazyAttribute(
        lambda obj: f"int_{hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()}"
    )  # Generate int_ prefixed internal playlist ID (36 chars total, normalized to lowercase)
    youtube_id: Any = None  # Optional YouTube playlist ID (None by default)
    title: Any = Faker("sentence", nb_words=4)
    description: Any = Faker("text", max_nb_chars=200)
    default_language: Any = Faker("random_element", elements=["en", "es", "fr", "de", "ja"])
    privacy_status: Any = Faker("random_element", elements=["private", "public", "unlisted"])
    channel_id: Any = factory.LazyFunction(
        lambda: "UCuAXFkgsw1L7xaCfnd5JJOw"
    )  # Use fixed valid channel ID
    video_count: Any = Faker("random_int", min=0, max=100)


class PlaylistCreateFactory(PlaylistBaseFactory):
    """Factory for PlaylistCreate models."""

    class Meta:
        model = PlaylistCreate


class PlaylistUpdateFactory(factory.Factory[PlaylistUpdate]):
    """Factory for PlaylistUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = PlaylistUpdate

    # No default values - respects model defaults (None for all fields)
    # Values will only be generated when explicitly passed to build()


class PlaylistFactory(PlaylistBaseFactory):
    """Factory for full Playlist models."""

    class Meta:
        model = Playlist

    created_at: Any = Faker("date_time", tzinfo=timezone.utc)
    updated_at: Any = Faker("date_time", tzinfo=timezone.utc)

    @classmethod
    def with_youtube_id(cls, youtube_id: str | None = None, **kwargs: Any) -> Playlist:
        """Create a playlist with a valid YouTube ID.

        Parameters
        ----------
        youtube_id : str | None, optional
            The YouTube playlist ID to use (PL-prefixed, 30-34 chars).
            If None, generates a valid PL-prefixed ID automatically.
        **kwargs : Any
            Additional keyword arguments to pass to the factory.

        Returns
        -------
        Playlist
            A Playlist instance with youtube_id set.
        """
        if youtube_id is None:
            # Generate valid PL-prefixed YouTube playlist ID (34 chars total)
            youtube_id = f"PL{hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()}"

        result = cls.build(youtube_id=youtube_id, **kwargs)
        assert isinstance(result, Playlist)
        return result


class PlaylistSearchFiltersFactory(factory.Factory[PlaylistSearchFilters]):
    """Factory for PlaylistSearchFilters models."""

    class Meta:
        model = PlaylistSearchFilters

    playlist_ids: Any = factory.LazyFunction(
        lambda: [
            generate_internal_playlist_id(),
            generate_internal_playlist_id(),
        ]
    )
    channel_ids: Any = factory.LazyFunction(
        lambda: ["UCuAXFkgsw1L7xaCfnd5JJOw", "UC-lHJZR3Gqxm24_Vd_AJ5Yw"]
    )
    title_query: Any = Faker("word")
    description_query: Any = Faker("word")
    language_codes: Any = factory.LazyFunction(lambda: ["en", "es", "fr"])
    privacy_statuses: Any = factory.LazyFunction(lambda: ["public", "unlisted"])
    min_video_count: Any = Faker("random_int", min=1, max=10)
    max_video_count: Any = Faker("random_int", min=11, max=100)
    has_description: Any = Faker("boolean")
    created_after: Any = Faker("date_time", tzinfo=timezone.utc)
    created_before: Any = Faker("date_time", tzinfo=timezone.utc)
    updated_after: Any = Faker("date_time", tzinfo=timezone.utc)
    updated_before: Any = Faker("date_time", tzinfo=timezone.utc)


class PlaylistStatisticsFactory(factory.Factory[PlaylistStatistics]):
    """Factory for PlaylistStatistics models."""

    class Meta:
        model = PlaylistStatistics

    total_playlists: Any = Faker("random_int", min=50, max=500)
    total_videos: Any = LazyAttribute(
        lambda obj: int(obj.total_playlists * 15)
    )  # ~15 videos per playlist average
    avg_videos_per_playlist: Any = LazyAttribute(
        lambda obj: round(obj.total_videos / obj.total_playlists, 2)
    )
    unique_channels: Any = LazyAttribute(
        lambda obj: int(obj.total_playlists * 0.7)
    )  # 70% unique channels
    privacy_distribution: Any = factory.LazyFunction(
        lambda: {"public": 180, "unlisted": 120, "private": 100}
    )
    language_distribution: Any = factory.LazyFunction(
        lambda: {"en": 200, "es": 100, "fr": 80, "de": 60, "ja": 50, "ko": 40}
    )
    top_channels_by_playlists: Any = factory.LazyFunction(
        lambda: [
            ("UCuAXFkgsw1L7xaCfnd5JJOw", 25),
            ("UC-lHJZR3Gqxm24_Vd_AJ5Yw", 20),
            ("UCBJycsmduvYEL83R_U4JriQ", 18),
        ]
    )
    playlist_size_distribution: Any = factory.LazyFunction(
        lambda: {
            "1-5 videos": 120,
            "6-20 videos": 180,
            "21-50 videos": 150,
            "50+ videos": 80,
        }
    )
    playlists_with_descriptions: Any = LazyAttribute(
        lambda obj: int(obj.total_playlists * 0.75)
    )  # 75% have descriptions


# Helper functions for ID generation
def generate_youtube_playlist_id() -> str:
    """Generate a valid YouTube playlist ID (PL-prefixed, 34 chars total).

    Returns
    -------
    str
        A valid YouTube playlist ID with PL prefix and 32 hex characters.
    """
    return f"PL{hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()}"


def generate_internal_playlist_id() -> str:
    """Generate a valid internal playlist ID (int_-prefixed, 36 chars total).

    Returns
    -------
    str
        A valid internal playlist ID with int_ prefix (lowercase) and 32 lowercase hex characters.
        The lowercase prefix matches the normalization behavior of the validator.
    """
    return f"int_{hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()}"


# Convenience factory methods
def create_playlist(**kwargs: Any) -> Playlist:
    """Create a Playlist with keyword arguments."""
    result = PlaylistFactory.build(**kwargs)
    assert isinstance(result, Playlist)
    return result


def create_playlist_create(**kwargs: Any) -> PlaylistCreate:
    """Create a PlaylistCreate with keyword arguments."""
    result = PlaylistCreateFactory.build(**kwargs)
    assert isinstance(result, PlaylistCreate)
    return result


def create_playlist_update(**kwargs: Any) -> PlaylistUpdate:
    """Create a PlaylistUpdate with keyword arguments."""
    result = PlaylistUpdateFactory.build(**kwargs)
    assert isinstance(result, PlaylistUpdate)
    return result


def create_playlist_filters(**kwargs: Any) -> PlaylistSearchFilters:
    """Create PlaylistSearchFilters with keyword arguments."""
    result = PlaylistSearchFiltersFactory.build(**kwargs)
    assert isinstance(result, PlaylistSearchFilters)
    return result


def create_playlist_statistics(**kwargs: Any) -> PlaylistStatistics:
    """Create PlaylistStatistics with keyword arguments."""
    result = PlaylistStatisticsFactory.build(**kwargs)
    assert isinstance(result, PlaylistStatistics)
    return result


# Common test data patterns
class PlaylistTestData:
    """Common test data patterns for Playlist models."""

    # Internal playlist IDs (int_ prefix, 36 chars - normalized to lowercase)
    VALID_INTERNAL_PLAYLIST_IDS = [
        "int_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        "int_f7abe60f8c123456789abcdef0123456",
        "int_1234567890abcdef1234567890abcdef",
        "int_deadbeefcafebabedeadbeefcafebabe",
        "int_0123456789abcdef0123456789abcdef",
    ]

    # YouTube playlist IDs (PL prefix, 30-50 chars)
    VALID_YOUTUBE_PLAYLIST_IDS = [
        "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
        "PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg",
        "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo",
        "PLMYEtPqzjdeev14J_RpAU_RQKyeaROB8T",
        "PLillGF-RfqbY0pq_LLo8BSfP_iDnODx36",
    ]

    # Combined valid playlist IDs (both internal and YouTube)
    VALID_PLAYLIST_IDS = VALID_INTERNAL_PLAYLIST_IDS + VALID_YOUTUBE_PLAYLIST_IDS

    VALID_TITLES = [
        "Learn Python Programming",
        "Best of Jazz Music",
        "Cooking with Julia",
        "Travel Adventures 2024",
        "Tech Reviews & Unboxings",
        "Gaming Highlights",
        "Educational Content",
        "Music Mix Collection",
        "Tutorial Series",
        "Documentary Playlist",
    ]

    VALID_DESCRIPTIONS = [
        "A comprehensive playlist for learning Python programming from basics to advanced.",
        "Collection of the best jazz music tracks from legendary artists.",
        "Cooking tutorials and recipes from Julia's kitchen.",
        "Amazing travel adventures and destinations around the world.",
        "Latest technology reviews and unboxing videos.",
        None,  # Some playlists don't have descriptions
        "Educational content for students and lifelong learners.",
        "Curated music mix for different moods and occasions.",
        "Step-by-step tutorial series for various topics.",
        "High-quality documentaries on science and nature.",
    ]

    VALID_CHANNEL_IDS = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",
        "UC-lHJZR3Gqxm24_Vd_AJ5Yw",
        "UCBJycsmduvYEL83R_U4JriQ",
        "UCsXVk37bltHxD1rDPwtNM8Q",
        "UCYCvGbr7chpyTgFpgUOVjjw",
    ]

    VALID_LANGUAGE_CODES = [
        "en",  # English
        "es",  # Spanish
        "fr",  # French
        "de",  # German
        "ja",  # Japanese
        "ko",  # Korean
        "zh-CN",  # Chinese Simplified (not zh alone)
        "pt",  # Portuguese
        "en-US",  # English (US)
        "en-GB",  # English (UK)
        "es-ES",  # Spanish (Spain)
        "fr-FR",  # French (France)
    ]

    PRIVACY_STATUSES = ["private", "public", "unlisted"]

    INVALID_PLAYLIST_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short
        "x" * 35,  # Too long
        "invalidformat123456",  # Invalid format
        "12345678901234567890",  # Numbers only
    ]

    INVALID_TITLES = [
        "",  # Empty
        "   ",  # Whitespace
        "x" * 256,  # Too long
    ]

    INVALID_DESCRIPTIONS = [
        "x" * 50001,  # Too long (over 50,000 chars)
    ]

    INVALID_CHANNEL_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short
        "x" * 25,  # Too long
        "invalidformat",  # Invalid format
        "12345678901234567890",  # Numbers only
    ]

    INVALID_LANGUAGE_CODES = [
        "",  # Empty
        "x",  # Too short
        "toolongcode",  # Too long
        "123",  # Numbers only
        "en-",  # Incomplete
        "en-123456",  # Invalid region format
    ]

    @classmethod
    def valid_playlist_data(cls) -> dict[str, Any]:
        """Get valid playlist data with internal ID."""
        return {
            "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[0],
            "youtube_id": None,
            "title": cls.VALID_TITLES[0],
            "description": cls.VALID_DESCRIPTIONS[0],
            "default_language": cls.VALID_LANGUAGE_CODES[0],
            "privacy_status": "public",
            "channel_id": cls.VALID_CHANNEL_IDS[0],
            "video_count": 25,
        }

    @classmethod
    def minimal_playlist_data(cls) -> dict[str, Any]:
        """Get minimal valid playlist data with internal ID."""
        return {
            "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[1],
            "youtube_id": None,
            "title": cls.VALID_TITLES[1],
            "channel_id": cls.VALID_CHANNEL_IDS[1],
        }

    @classmethod
    def youtube_playlist_data(cls) -> dict[str, Any]:
        """Get playlist data linked to a YouTube playlist."""
        return {
            "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[0],
            "youtube_id": cls.VALID_YOUTUBE_PLAYLIST_IDS[0],
            "title": "Learn Python Programming - Complete Course",
            "description": "Complete Python programming course from beginner to advanced level with hands-on examples.",
            "default_language": "en",
            "privacy_status": "public",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "video_count": 50,
        }

    @classmethod
    def private_playlist_data(cls) -> dict[str, Any]:
        """Get private playlist data with internal ID."""
        return {
            "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[2],
            "youtube_id": None,
            "title": "My Private Music Collection",
            "description": "Personal music collection for private listening.",
            "default_language": "en",
            "privacy_status": "private",
            "channel_id": "UC-lHJZR3Gqxm24_Vd_AJ5Yw",
            "video_count": 30,
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict[str, Any]:
        """Get comprehensive search filters data."""
        return {
            "playlist_ids": cls.VALID_INTERNAL_PLAYLIST_IDS[:2],
            "channel_ids": cls.VALID_CHANNEL_IDS[:2],
            "title_query": "python",
            "description_query": "tutorial",
            "language_codes": cls.VALID_LANGUAGE_CODES[:3],
            "privacy_statuses": ["public", "unlisted"],
            "min_video_count": 5,
            "max_video_count": 100,
            "has_description": True,
            "created_after": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "created_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
            "updated_after": datetime(2023, 6, 1, tzinfo=timezone.utc),
            "updated_before": datetime(2023, 12, 31, tzinfo=timezone.utc),
        }

    @classmethod
    def multilingual_playlists_data(cls) -> list[dict[str, Any]]:
        """Get multilingual playlist test data with internal IDs."""
        return [
            {
                "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[0],
                "youtube_id": None,
                "title": "Learn Python Programming",
                "description": "Complete Python course",
                "default_language": "en",
                "privacy_status": "public",
            },
            {
                "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[1],
                "youtube_id": None,
                "title": "Aprende Programación Python",
                "description": "Curso completo de Python",
                "default_language": "es",
                "privacy_status": "public",
            },
            {
                "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[2],
                "youtube_id": None,
                "title": "Apprendre la Programmation Python",
                "description": "Cours complet de Python",
                "default_language": "fr",
                "privacy_status": "public",
            },
            {
                "playlist_id": cls.VALID_INTERNAL_PLAYLIST_IDS[3],
                "youtube_id": None,
                "title": "Pythonプログラミング学習",
                "description": "Python完全コース",
                "default_language": "ja",
                "privacy_status": "public",
            },
        ]
