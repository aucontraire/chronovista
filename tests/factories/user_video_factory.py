"""
Factory definitions for user video models.

Provides factory-boy factories for creating test instances of user video models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, cast

import factory
from factory import LazyFunction

from chronovista.models.user_video import (
    GoogleTakeoutWatchHistoryItem,
    UserVideo,
    UserVideoBase,
    UserVideoCreate,
    UserVideoSearchFilters,
    UserVideoStatistics,
    UserVideoUpdate,
)


class UserVideoBaseFactory(factory.Factory):
    """Factory for UserVideoBase models."""

    class Meta:
        model = UserVideoBase

    user_id = factory.LazyFunction(lambda: "test_user_123")
    video_id = factory.LazyFunction(lambda: "dQw4w9WgXcQ")
    watched_at = factory.LazyFunction(
        lambda: datetime(2023, 12, 1, 10, 30, 0, tzinfo=timezone.utc)
    )
    watch_duration = factory.LazyFunction(lambda: 180)  # 3 minutes
    completion_percentage = factory.LazyFunction(lambda: 85.5)
    rewatch_count = factory.LazyFunction(lambda: 1)
    liked = factory.LazyFunction(lambda: True)
    disliked = factory.LazyFunction(lambda: False)
    saved_to_playlist = factory.LazyFunction(lambda: True)


class UserVideoCreateFactory(factory.Factory):
    """Factory for UserVideoCreate models."""

    class Meta:
        model = UserVideoCreate

    user_id = factory.LazyFunction(lambda: "test_user_456")
    video_id = factory.LazyFunction(lambda: "9bZkp7q19f0")
    watched_at = factory.LazyFunction(
        lambda: datetime(2023, 11, 15, 14, 20, 0, tzinfo=timezone.utc)
    )
    watch_duration = factory.LazyFunction(lambda: 240)  # 4 minutes
    completion_percentage = factory.LazyFunction(lambda: 75.0)
    rewatch_count = factory.LazyFunction(lambda: 0)
    liked = factory.LazyFunction(lambda: False)
    disliked = factory.LazyFunction(lambda: False)
    saved_to_playlist = factory.LazyFunction(lambda: False)


class UserVideoUpdateFactory(factory.Factory):
    """Factory for UserVideoUpdate models.

    Note: This factory respects the model's default values (None for all fields).
    For Update models, the default behavior should be an empty update (all None),
    with values only generated when explicitly requested.
    """

    class Meta:
        model = UserVideoUpdate

    # No default values - respects model defaults (None for all fields)
    # Values will only be generated when explicitly passed to build()


class UserVideoFactory(factory.Factory):
    """Factory for UserVideo models."""

    class Meta:
        model = UserVideo

    user_id = factory.LazyFunction(lambda: "test_user_789")
    video_id = factory.LazyFunction(lambda: "3tmd-ClpJxA")
    watched_at = factory.LazyFunction(
        lambda: datetime(2023, 10, 20, 9, 15, 0, tzinfo=timezone.utc)
    )
    watch_duration = factory.LazyFunction(lambda: 420)  # 7 minutes
    completion_percentage = factory.LazyFunction(lambda: 95.0)
    rewatch_count = factory.LazyFunction(lambda: 3)
    liked = factory.LazyFunction(lambda: True)
    disliked = factory.LazyFunction(lambda: False)
    saved_to_playlist = factory.LazyFunction(lambda: True)
    created_at = factory.LazyFunction(
        lambda: datetime(2023, 10, 20, 9, 15, 0, tzinfo=timezone.utc)
    )
    updated_at = factory.LazyFunction(
        lambda: datetime(2023, 12, 1, 10, 30, 0, tzinfo=timezone.utc)
    )


class GoogleTakeoutWatchHistoryItemFactory(factory.Factory):
    """Factory for GoogleTakeoutWatchHistoryItem models."""

    class Meta:
        model = GoogleTakeoutWatchHistoryItem

    header = factory.LazyFunction(lambda: "YouTube")
    title = factory.LazyFunction(
        lambda: "Watched Rick Astley - Never Gonna Give You Up (Official Video)"
    )
    titleUrl = factory.LazyFunction(
        lambda: "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    subtitles = factory.LazyFunction(
        lambda: [
            {
                "name": "Rick Astley",
                "url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            }
        ]
    )
    time = factory.LazyFunction(lambda: "2023-12-01T10:30:00Z")
    products = factory.LazyFunction(lambda: ["YouTube"])
    activityControls = factory.LazyFunction(lambda: ["YouTube watch history"])


class UserVideoSearchFiltersFactory(factory.Factory):
    """Factory for UserVideoSearchFilters models."""

    class Meta:
        model = UserVideoSearchFilters

    user_ids = factory.LazyFunction(lambda: ["user1", "user2", "user3"])
    video_ids = factory.LazyFunction(
        lambda: ["dQw4w9WgXcQ", "9bZkp7q19f0", "3tmd-ClpJxA"]
    )
    watched_after = factory.LazyFunction(
        lambda: datetime(2023, 1, 1, tzinfo=timezone.utc)
    )
    watched_before = factory.LazyFunction(
        lambda: datetime(2023, 12, 31, tzinfo=timezone.utc)
    )
    min_watch_duration = factory.LazyFunction(lambda: 60)  # 1 minute
    min_completion_percentage = factory.LazyFunction(lambda: 50.0)
    liked_only = factory.LazyFunction(lambda: True)
    disliked_only = factory.LazyFunction(lambda: False)
    playlist_saved_only = factory.LazyFunction(lambda: True)
    min_rewatch_count = factory.LazyFunction(lambda: 1)
    created_after = factory.LazyFunction(
        lambda: datetime(2023, 6, 1, tzinfo=timezone.utc)
    )
    created_before = factory.LazyFunction(
        lambda: datetime(2023, 12, 1, tzinfo=timezone.utc)
    )


class UserVideoStatisticsFactory(factory.Factory):
    """Factory for UserVideoStatistics models."""

    class Meta:
        model = UserVideoStatistics

    total_videos = factory.LazyFunction(lambda: 150)
    total_watch_time = factory.LazyFunction(lambda: 18000)  # 5 hours in seconds
    average_completion = factory.LazyFunction(lambda: 78.5)
    liked_count = factory.LazyFunction(lambda: 45)
    disliked_count = factory.LazyFunction(lambda: 8)
    playlist_saved_count = factory.LazyFunction(lambda: 32)
    rewatch_count = factory.LazyFunction(lambda: 25)
    unique_videos = factory.LazyFunction(lambda: 125)
    most_watched_date = factory.LazyFunction(
        lambda: datetime(2023, 11, 15, tzinfo=timezone.utc)
    )
    watch_streak_days = factory.LazyFunction(lambda: 14)


# Test data constants for validation testing
class UserVideoTestData:
    """Test data constants for user video models."""

    # Valid test data
    VALID_USER_IDS = ["user123", "test_user", "user_with_underscores", "a" * 50]
    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",
        "9bZkp7q19f0",
        "3tmd-ClpJxA",
        "abcdefghijk",
        "AAAAAAAAAAA",
    ]  # All 11 chars
    VALID_COMPLETION_PERCENTAGES = [0.0, 25.5, 50.0, 75.5, 100.0]
    VALID_REWATCH_COUNTS = [0, 1, 5, 10, 50]

    # Invalid test data
    INVALID_USER_IDS = ["", "   ", "\t\n"]
    INVALID_VIDEO_IDS = [
        "",
        "short",
        "a" * 21,
        "   ",
        "aaaaaaaa",
        "bbbbbbbbbbbbbbbbbbbb",
    ]  # Empty, too short, too long
    INVALID_COMPLETION_PERCENTAGES = [-0.1, -50.0, 100.1, 150.0]
    INVALID_REWATCH_COUNTS = [-1, -5]

    # Google Takeout test data
    VALID_YOUTUBE_URLS = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/9bZkp7q19f0",
        "https://www.youtube.com/embed/3tmd-ClpJxA",
    ]
    INVALID_YOUTUBE_URLS = [
        "https://example.com/video",
        "https://vimeo.com/123456789",
        "",
    ]

    # Valid takeout titles
    VALID_TAKEOUT_TITLES = [
        "Watched Rick Astley - Never Gonna Give You Up (Official Video)",
        "Viewed Python Tutorial for Beginners",
        "Visited Tech Conference 2023 Highlights",
    ]
    INVALID_TAKEOUT_TITLES = ["", "   ", "\t\n"]


# Convenience factory functions
def create_user_video_base(**kwargs) -> UserVideoBase:
    """Create a UserVideoBase with optional overrides."""
    return cast(UserVideoBase, UserVideoBaseFactory.build(**kwargs))


def create_user_video_create(**kwargs) -> UserVideoCreate:
    """Create a UserVideoCreate with optional overrides."""
    return cast(UserVideoCreate, UserVideoCreateFactory.build(**kwargs))


def create_user_video_update(**kwargs) -> UserVideoUpdate:
    """Create a UserVideoUpdate with optional overrides."""
    return cast(UserVideoUpdate, UserVideoUpdateFactory.build(**kwargs))


def create_user_video(**kwargs) -> UserVideo:
    """Create a UserVideo with optional overrides."""
    return cast(UserVideo, UserVideoFactory.build(**kwargs))


def create_google_takeout_item(**kwargs) -> GoogleTakeoutWatchHistoryItem:
    """Create a GoogleTakeoutWatchHistoryItem with optional overrides."""
    return cast(
        GoogleTakeoutWatchHistoryItem,
        GoogleTakeoutWatchHistoryItemFactory.build(**kwargs),
    )


def create_user_video_search_filters(**kwargs) -> UserVideoSearchFilters:
    """Create a UserVideoSearchFilters with optional overrides."""
    return cast(UserVideoSearchFilters, UserVideoSearchFiltersFactory.build(**kwargs))


def create_user_video_statistics(**kwargs) -> UserVideoStatistics:
    """Create a UserVideoStatistics with optional overrides."""
    return cast(UserVideoStatistics, UserVideoStatisticsFactory.build(**kwargs))


def create_batch_user_videos(count: int = 5) -> List[UserVideo]:
    """Create a batch of UserVideo instances for testing."""
    videos = []
    base_user_ids = ["user1", "user2", "user3"]
    base_video_ids = [
        "dQw4w9WgXcQ",
        "9bZkp7q19f0",
        "3tmd-ClpJxA",
        "jNQXAC9IVRw",
        "MejbOFk7H6c",
    ]

    for i in range(count):
        user_id = base_user_ids[i % len(base_user_ids)]
        video_id = base_video_ids[i % len(base_video_ids)]

        video = UserVideoFactory.build(
            user_id=user_id,
            video_id=video_id,
            completion_percentage=50.0 + (i * 10),
            rewatch_count=i % 3,
        )
        videos.append(video)

    return videos
