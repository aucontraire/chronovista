"""
Factory for Playlist models using factory_boy.

Provides reusable test data factories for all Playlist model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


class PlaylistBaseFactory(factory.Factory):
    """Factory for PlaylistBase models."""

    class Meta:
        model = PlaylistBase

    playlist_id = factory.LazyFunction(
        lambda: "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f"
    )  # Use fixed valid playlist ID
    title = Faker("sentence", nb_words=4)
    description = Faker("text", max_nb_chars=200)
    default_language = Faker("random_element", elements=["en", "es", "fr", "de", "ja"])
    privacy_status = Faker("random_element", elements=["private", "public", "unlisted"])
    channel_id = factory.LazyFunction(
        lambda: "UCuAXFkgsw1L7xaCfnd5JJOw"
    )  # Use fixed valid channel ID
    video_count = Faker("random_int", min=0, max=100)


class PlaylistCreateFactory(PlaylistBaseFactory):
    """Factory for PlaylistCreate models."""

    class Meta:
        model = PlaylistCreate


class PlaylistUpdateFactory(factory.Factory):
    """Factory for PlaylistUpdate models."""

    class Meta:
        model = PlaylistUpdate

    title = Faker("sentence", nb_words=3)
    description = Faker("text", max_nb_chars=150)
    default_language = Faker("random_element", elements=["en", "es", "fr"])
    privacy_status = Faker("random_element", elements=["private", "public", "unlisted"])
    video_count = Faker("random_int", min=0, max=50)


class PlaylistFactory(PlaylistBaseFactory):
    """Factory for full Playlist models."""

    class Meta:
        model = Playlist

    created_at = Faker("date_time", tzinfo=timezone.utc)
    updated_at = Faker("date_time", tzinfo=timezone.utc)


class PlaylistSearchFiltersFactory(factory.Factory):
    """Factory for PlaylistSearchFilters models."""

    class Meta:
        model = PlaylistSearchFilters

    playlist_ids = factory.LazyFunction(
        lambda: [
            "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
            "PLs9ACwy3uKTOT2q_test123456789ABC",
        ]
    )
    channel_ids = factory.LazyFunction(
        lambda: ["UCuAXFkgsw1L7xaCfnd5JJOw", "UC-lHJZR3Gqxm24_Vd_AJ5Yw"]
    )
    title_query = Faker("word")
    description_query = Faker("word")
    language_codes = factory.LazyFunction(lambda: ["en", "es", "fr"])
    privacy_statuses = factory.LazyFunction(lambda: ["public", "unlisted"])
    min_video_count = Faker("random_int", min=1, max=10)
    max_video_count = Faker("random_int", min=11, max=100)
    has_description = Faker("boolean")
    created_after = Faker("date_time", tzinfo=timezone.utc)
    created_before = Faker("date_time", tzinfo=timezone.utc)
    updated_after = Faker("date_time", tzinfo=timezone.utc)
    updated_before = Faker("date_time", tzinfo=timezone.utc)


class PlaylistStatisticsFactory(factory.Factory):
    """Factory for PlaylistStatistics models."""

    class Meta:
        model = PlaylistStatistics

    total_playlists = Faker("random_int", min=50, max=500)
    total_videos = LazyAttribute(
        lambda obj: int(obj.total_playlists * 15)
    )  # ~15 videos per playlist average
    avg_videos_per_playlist = LazyAttribute(
        lambda obj: round(obj.total_videos / obj.total_playlists, 2)
    )
    unique_channels = LazyAttribute(
        lambda obj: int(obj.total_playlists * 0.7)
    )  # 70% unique channels
    privacy_distribution = factory.LazyFunction(
        lambda: {"public": 180, "unlisted": 120, "private": 100}
    )
    language_distribution = factory.LazyFunction(
        lambda: {"en": 200, "es": 100, "fr": 80, "de": 60, "ja": 50, "ko": 40}
    )
    top_channels_by_playlists = factory.LazyFunction(
        lambda: [
            ("UCuAXFkgsw1L7xaCfnd5JJOw", 25),
            ("UC-lHJZR3Gqxm24_Vd_AJ5Yw", 20),
            ("UCBJycsmduvYEL83R_U4JriQ", 18),
        ]
    )
    playlist_size_distribution = factory.LazyFunction(
        lambda: {
            "1-5 videos": 120,
            "6-20 videos": 180,
            "21-50 videos": 150,
            "50+ videos": 80,
        }
    )
    playlists_with_descriptions = LazyAttribute(
        lambda obj: int(obj.total_playlists * 0.75)
    )  # 75% have descriptions


# Convenience factory methods
def create_playlist(**kwargs) -> Playlist:
    """Create a Playlist with keyword arguments."""
    return PlaylistFactory(**kwargs)


def create_playlist_create(**kwargs) -> PlaylistCreate:
    """Create a PlaylistCreate with keyword arguments."""
    return PlaylistCreateFactory(**kwargs)


def create_playlist_update(**kwargs) -> PlaylistUpdate:
    """Create a PlaylistUpdate with keyword arguments."""
    return PlaylistUpdateFactory(**kwargs)


def create_playlist_filters(**kwargs) -> PlaylistSearchFilters:
    """Create PlaylistSearchFilters with keyword arguments."""
    return PlaylistSearchFiltersFactory(**kwargs)


def create_playlist_statistics(**kwargs) -> PlaylistStatistics:
    """Create PlaylistStatistics with keyword arguments."""
    return PlaylistStatisticsFactory(**kwargs)


# Common test data patterns
class PlaylistTestData:
    """Common test data patterns for Playlist models."""

    VALID_PLAYLIST_IDS = [
        "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
        "PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg",
        "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo",
        "PLMYEtPqzjdeev14J_RpAU_RQKyeaROB8T",
        "PLillGF-RfqbY0pq_LLo8BSfP_iDnODx36",
    ]

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
    def valid_playlist_data(cls) -> dict:
        """Get valid playlist data."""
        return {
            "playlist_id": cls.VALID_PLAYLIST_IDS[0],
            "title": cls.VALID_TITLES[0],
            "description": cls.VALID_DESCRIPTIONS[0],
            "default_language": cls.VALID_LANGUAGE_CODES[0],
            "privacy_status": "public",
            "channel_id": cls.VALID_CHANNEL_IDS[0],
            "video_count": 25,
        }

    @classmethod
    def minimal_playlist_data(cls) -> dict:
        """Get minimal valid playlist data."""
        return {
            "playlist_id": cls.VALID_PLAYLIST_IDS[1],
            "title": cls.VALID_TITLES[1],
            "channel_id": cls.VALID_CHANNEL_IDS[1],
        }

    @classmethod
    def youtube_playlist_data(cls) -> dict:
        """Get typical YouTube playlist data."""
        return {
            "playlist_id": "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
            "title": "Learn Python Programming - Complete Course",
            "description": "Complete Python programming course from beginner to advanced level with hands-on examples.",
            "default_language": "en",
            "privacy_status": "public",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "video_count": 50,
        }

    @classmethod
    def private_playlist_data(cls) -> dict:
        """Get private playlist data."""
        return {
            "playlist_id": "PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg",
            "title": "My Private Music Collection",
            "description": "Personal music collection for private listening.",
            "default_language": "en",
            "privacy_status": "private",
            "channel_id": "UC-lHJZR3Gqxm24_Vd_AJ5Yw",
            "video_count": 30,
        }

    @classmethod
    def comprehensive_search_filters_data(cls) -> dict:
        """Get comprehensive search filters data."""
        return {
            "playlist_ids": cls.VALID_PLAYLIST_IDS[:2],
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
    def multilingual_playlists_data(cls) -> list[dict]:
        """Get multilingual playlist test data."""
        return [
            {
                "playlist_id": "PLrAXtmRdnEQy3roZQD5TZuDCU5x-X4V8f",
                "title": "Learn Python Programming",
                "description": "Complete Python course",
                "default_language": "en",
                "privacy_status": "public",
            },
            {
                "playlist_id": "PLs9ACwy3uKTOT2q9gLKUvyqPOjLXUlAWg",
                "title": "Aprende Programación Python",
                "description": "Curso completo de Python",
                "default_language": "es",
                "privacy_status": "public",
            },
            {
                "playlist_id": "PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo",
                "title": "Apprendre la Programmation Python",
                "description": "Cours complet de Python",
                "default_language": "fr",
                "privacy_status": "public",
            },
            {
                "playlist_id": "PLMYEtPqzjdeev14J_RpAU_RQKyeaROB8T",
                "title": "Pythonプログラミング学習",
                "description": "Python完全コース",
                "default_language": "ja",
                "privacy_status": "public",
            },
        ]
