"""
Factory definitions for video models.

Provides factory-boy factories for creating test instances of video models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import factory
from factory import LazyFunction

from chronovista.models.enums import LanguageCode
from chronovista.models.video import (
    Video,
    VideoBase,
    VideoCreate,
    VideoSearchFilters,
    VideoStatistics,
    VideoUpdate,
    VideoWithChannel,
)


class VideoBaseFactory(factory.Factory):
    """Factory for VideoBase models."""

    class Meta:
        model = VideoBase

    video_id = factory.LazyFunction(lambda: "dQw4w9WgXcQ")
    channel_id = factory.LazyFunction(lambda: "UCuAXFkgsw1L7xaCfnd5JJOw")
    title = factory.LazyFunction(
        lambda: "Rick Astley - Never Gonna Give You Up (Official Video)"
    )
    description = factory.LazyFunction(
        lambda: "The official video for 'Never Gonna Give You Up' by Rick Astley. A timeless classic that has become an internet phenomenon."
    )
    upload_date = factory.LazyFunction(
        lambda: datetime(2009, 10, 25, 8, 15, 0, tzinfo=timezone.utc)
    )
    duration = factory.LazyFunction(lambda: 213)  # 3:33 in seconds
    made_for_kids = factory.LazyFunction(lambda: False)
    self_declared_made_for_kids = factory.LazyFunction(lambda: False)
    default_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH)
    default_audio_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH)
    available_languages = factory.LazyFunction(
        lambda: {"en": "English", "es": "Spanish", "fr": "French"}
    )
    region_restriction = factory.LazyFunction(
        lambda: {"blocked": ["CN"], "allowed": ["US", "GB", "CA"]}
    )
    content_rating = factory.LazyFunction(
        lambda: {"mpaaRating": "G", "ytRating": "ytAgeRestricted"}
    )
    like_count = factory.LazyFunction(lambda: 1200000)
    view_count = factory.LazyFunction(lambda: 1400000000)
    comment_count = factory.LazyFunction(lambda: 2800000)
    deleted_flag = factory.LazyFunction(lambda: False)


class VideoCreateFactory(factory.Factory):
    """Factory for VideoCreate models."""

    class Meta:
        model = VideoCreate

    video_id = factory.LazyFunction(lambda: "9bZkp7q19f0")
    channel_id = factory.LazyFunction(lambda: "UC_x5XG1OV2P6uZZ5FSM9Ttw")
    title = factory.LazyFunction(
        lambda: "Google I/O 2023: What's new in Machine Learning"
    )
    description = factory.LazyFunction(
        lambda: "Join us for an overview of the latest ML developments from Google, including new tools, frameworks, and research breakthroughs."
    )
    upload_date = factory.LazyFunction(
        lambda: datetime(2023, 5, 10, 17, 0, 0, tzinfo=timezone.utc)
    )
    duration = factory.LazyFunction(lambda: 2760)  # 46 minutes
    made_for_kids = factory.LazyFunction(lambda: False)
    self_declared_made_for_kids = factory.LazyFunction(lambda: False)
    default_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    default_audio_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    available_languages = factory.LazyFunction(
        lambda: {"en": "English", "zh": "Chinese", "ja": "Japanese"}
    )
    region_restriction = factory.LazyFunction(lambda: None)
    content_rating = factory.LazyFunction(lambda: {"ytRating": "ytAgeAppropriate"})
    like_count = factory.LazyFunction(lambda: 85000)
    view_count = factory.LazyFunction(lambda: 2500000)
    comment_count = factory.LazyFunction(lambda: 12000)
    deleted_flag = factory.LazyFunction(lambda: False)


class VideoUpdateFactory(factory.Factory):
    """Factory for VideoUpdate models."""

    class Meta:
        model = VideoUpdate

    title = factory.LazyFunction(
        lambda: "Updated: Advanced Python Programming Tutorial"
    )
    description = factory.LazyFunction(
        lambda: "This is an updated description with new content and corrections."
    )
    duration = factory.LazyFunction(lambda: 1800)  # 30 minutes
    made_for_kids = factory.LazyFunction(lambda: False)
    self_declared_made_for_kids = factory.LazyFunction(lambda: False)
    default_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH)
    default_audio_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH)
    available_languages = factory.LazyFunction(
        lambda: {"en": "English", "es": "Spanish"}
    )
    region_restriction = factory.LazyFunction(
        lambda: {"blocked": [], "allowed": ["US", "CA", "GB", "AU"]}
    )
    content_rating = factory.LazyFunction(lambda: {"ytRating": "ytAgeAppropriate"})
    like_count = factory.LazyFunction(lambda: 45000)
    view_count = factory.LazyFunction(lambda: 750000)
    comment_count = factory.LazyFunction(lambda: 3200)
    deleted_flag = factory.LazyFunction(lambda: False)


class VideoFactory(factory.Factory):
    """Factory for Video models."""

    class Meta:
        model = Video

    video_id = factory.LazyFunction(lambda: "3tmd-ClpJxA")
    channel_id = factory.LazyFunction(lambda: "UCMtFAi84ehTSYSE9XoHefig")
    title = factory.LazyFunction(
        lambda: "The Late Show with Stephen Colbert - Best Moments 2023"
    )
    description = factory.LazyFunction(
        lambda: "A compilation of the funniest and most memorable moments from The Late Show with Stephen Colbert in 2023."
    )
    upload_date = factory.LazyFunction(
        lambda: datetime(2023, 12, 15, 23, 35, 0, tzinfo=timezone.utc)
    )
    duration = factory.LazyFunction(lambda: 1440)  # 24 minutes
    made_for_kids = factory.LazyFunction(lambda: False)
    self_declared_made_for_kids = factory.LazyFunction(lambda: False)
    default_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    default_audio_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    available_languages = factory.LazyFunction(
        lambda: {"en": "English", "es": "Spanish", "pt": "Portuguese"}
    )
    region_restriction = factory.LazyFunction(lambda: None)
    content_rating = factory.LazyFunction(lambda: {"ytRating": "ytAgeAppropriate"})
    like_count = factory.LazyFunction(lambda: 125000)
    view_count = factory.LazyFunction(lambda: 3200000)
    comment_count = factory.LazyFunction(lambda: 8500)
    deleted_flag = factory.LazyFunction(lambda: False)
    created_at = factory.LazyFunction(
        lambda: datetime(2023, 12, 15, 23, 35, 0, tzinfo=timezone.utc)
    )
    updated_at = factory.LazyFunction(
        lambda: datetime(2023, 12, 16, 10, 20, 0, tzinfo=timezone.utc)
    )


class VideoSearchFiltersFactory(factory.Factory):
    """Factory for VideoSearchFilters models."""

    class Meta:
        model = VideoSearchFilters

    channel_ids = factory.LazyFunction(
        lambda: ["UCuAXFkgsw1L7xaCfnd5JJOw", "UC_x5XG1OV2P6uZZ5FSM9Ttw"]
    )
    title_query = factory.LazyFunction(lambda: "python tutorial")
    description_query = factory.LazyFunction(lambda: "programming")
    language_codes = factory.LazyFunction(
        lambda: [LanguageCode.ENGLISH, LanguageCode.ENGLISH_US, LanguageCode.SPANISH]
    )
    upload_after = factory.LazyFunction(
        lambda: datetime(2023, 1, 1, tzinfo=timezone.utc)
    )
    upload_before = factory.LazyFunction(
        lambda: datetime(2023, 12, 31, tzinfo=timezone.utc)
    )
    min_duration = factory.LazyFunction(lambda: 300)  # 5 minutes
    max_duration = factory.LazyFunction(lambda: 3600)  # 1 hour
    min_view_count = factory.LazyFunction(lambda: 1000)
    max_view_count = factory.LazyFunction(lambda: 10000000)
    min_like_count = factory.LazyFunction(lambda: 100)
    kids_friendly_only = factory.LazyFunction(lambda: False)
    exclude_deleted = factory.LazyFunction(lambda: True)
    has_transcripts = factory.LazyFunction(lambda: True)


class VideoStatisticsFactory(factory.Factory):
    """Factory for VideoStatistics models."""

    class Meta:
        model = VideoStatistics

    total_videos = factory.LazyFunction(lambda: 1250)
    total_duration = factory.LazyFunction(
        lambda: 2250000
    )  # Total seconds across all videos
    avg_duration = factory.LazyFunction(lambda: 1800.0)  # Average 30 minutes
    total_views = factory.LazyFunction(lambda: 50000000)
    total_likes = factory.LazyFunction(lambda: 2500000)
    total_comments = factory.LazyFunction(lambda: 125000)
    avg_views_per_video = factory.LazyFunction(lambda: 40000.0)
    avg_likes_per_video = factory.LazyFunction(lambda: 2000.0)
    deleted_video_count = factory.LazyFunction(lambda: 25)
    kids_friendly_count = factory.LazyFunction(lambda: 150)
    top_languages = factory.LazyFunction(
        lambda: [("en", 800), ("es", 200), ("fr", 150), ("de", 100)]
    )
    upload_trend = factory.LazyFunction(
        lambda: {"2023-01": 95, "2023-02": 88, "2023-03": 102, "2023-04": 96}
    )


class VideoWithChannelFactory(factory.Factory):
    """Factory for VideoWithChannel models."""

    class Meta:
        model = VideoWithChannel

    video_id = factory.LazyFunction(lambda: "jNQXAC9IVRw")
    channel_id = factory.LazyFunction(lambda: "UCBJycsmduvYEL83R_U4JriQ")
    title = factory.LazyFunction(lambda: "Marques Brownlee - iPhone 15 Pro Max Review!")
    description = factory.LazyFunction(
        lambda: "The most comprehensive review of Apple's latest flagship iPhone with detailed testing and comparisons."
    )
    upload_date = factory.LazyFunction(
        lambda: datetime(2023, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    )
    duration = factory.LazyFunction(lambda: 1260)  # 21 minutes
    made_for_kids = factory.LazyFunction(lambda: False)
    self_declared_made_for_kids = factory.LazyFunction(lambda: False)
    default_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    default_audio_language = factory.LazyFunction(lambda: LanguageCode.ENGLISH_US)
    available_languages = factory.LazyFunction(lambda: {"en": "English"})
    region_restriction = factory.LazyFunction(lambda: None)
    content_rating = factory.LazyFunction(lambda: {"ytRating": "ytAgeAppropriate"})
    like_count = factory.LazyFunction(lambda: 450000)
    view_count = factory.LazyFunction(lambda: 12000000)
    comment_count = factory.LazyFunction(lambda: 35000)
    deleted_flag = factory.LazyFunction(lambda: False)
    created_at = factory.LazyFunction(
        lambda: datetime(2023, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    )
    updated_at = factory.LazyFunction(
        lambda: datetime(2023, 9, 22, 15, 30, 0, tzinfo=timezone.utc)
    )
    channel_title = factory.LazyFunction(lambda: "Marques Brownlee")
    channel_subscriber_count = factory.LazyFunction(lambda: 17800000)


# Test data constants for validation testing
class VideoTestData:
    """Test data constants for video models."""

    # Valid test data
    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",  # Rick Astley (11 chars)
        "9bZkp7q19f0",  # Tech video (11 chars)
        "3tmd-ClpJxA",  # Late Show (11 chars)
        "jNQXAC9IVRw",  # MKBHD (11 chars)
        "abcdefghijk",  # Exactly 11 chars
    ]

    VALID_CHANNEL_IDS = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",  # Rick Astley (24 chars)
        "UC_x5XG1OV2P6uZZ5FSM9Ttw",  # Google Developers (24 chars)
        "UCMtFAi84ehTSYSE9XoHefig",  # Stephen Colbert (24 chars)
        "UCBJycsmduvYEL83R_U4JriQ",  # MKBHD (24 chars)
        "UC1234567890123456789012",  # Exactly 24 chars
    ]

    VALID_TITLES = [
        "Rick Astley - Never Gonna Give You Up",
        "Python Programming Tutorial",
        "A",  # Min length
        "A" * 1000,  # Long title
    ]

    VALID_LANGUAGES = [
        LanguageCode.ENGLISH,
        LanguageCode.ENGLISH_US,
        LanguageCode.SPANISH,
        LanguageCode.FRENCH,
        LanguageCode.GERMAN,
        LanguageCode.ITALIAN,
        LanguageCode.JAPANESE,
        LanguageCode.KOREAN,
        LanguageCode.PORTUGUESE_BR,
        LanguageCode.CHINESE_SIMPLIFIED,
    ]
    VALID_DURATIONS = [0, 1, 60, 300, 1800, 3600, 7200, 21600]  # 0 to 6 hours
    VALID_COUNTS = [0, 1, 100, 1000, 100000, 1000000, 1000000000]

    # Invalid test data
    INVALID_VIDEO_IDS = [
        "",
        "   ",
        "\t\n",
        "a" * 21,
        "short",
        "toolongvideoid123",
        "aaaaaaaa",
        "bbbbbbbbbbbbbbbbbbbb",
    ]  # Empty, whitespace, too long, wrong length
    INVALID_CHANNEL_IDS = [
        "",
        "   ",
        "\t\n",
        "a" * 25,
        "UCshort",
        "UC123456789012345678901",
        "PLnotachannel123456789012",
        "U",
        "aaaaaaaaaaaaaaaaaaaaaaaa",
    ]  # Empty, whitespace, too long, wrong length, wrong prefix
    INVALID_TITLES = ["", "   ", "\t\n"]  # Empty, whitespace
    INVALID_LANGUAGES = ["", "A", "a" * 11]  # Too short, too long
    INVALID_DURATIONS = [-1, -100, -3600]  # Negative values
    INVALID_COUNTS = [-1, -100, -1000]  # Negative values

    # YouTube data structures
    VALID_AVAILABLE_LANGUAGES = [
        {"en": "English", "es": "Spanish"},
        {"en": "English", "fr": "French", "de": "German"},
        {"ja": "Japanese", "ko": "Korean", "zh": "Chinese"},
    ]

    VALID_REGION_RESTRICTIONS = [
        {"blocked": ["CN"], "allowed": ["US", "GB", "CA"]},
        {"blocked": [], "allowed": ["US", "CA", "GB", "AU", "NZ"]},
        None,  # No restrictions
    ]

    VALID_CONTENT_RATINGS = [
        {"ytRating": "ytAgeAppropriate"},
        {"ytRating": "ytAgeRestricted"},
        {"mpaaRating": "G", "ytRating": "ytAgeAppropriate"},
        {"mpaaRating": "PG-13", "ytRating": "ytAgeRestricted"},
    ]


# Convenience factory functions
def create_video_base(**kwargs) -> VideoBase:
    """Create a VideoBase with optional overrides."""
    return VideoBaseFactory(**kwargs)


def create_video_create(**kwargs) -> VideoCreate:
    """Create a VideoCreate with optional overrides."""
    return VideoCreateFactory(**kwargs)


def create_video_update(**kwargs) -> VideoUpdate:
    """Create a VideoUpdate with optional overrides."""
    return VideoUpdateFactory(**kwargs)


def create_video(**kwargs) -> Video:
    """Create a Video with optional overrides."""
    return VideoFactory(**kwargs)


def create_video_search_filters(**kwargs) -> VideoSearchFilters:
    """Create a VideoSearchFilters with optional overrides."""
    return VideoSearchFiltersFactory(**kwargs)


def create_video_statistics(**kwargs) -> VideoStatistics:
    """Create a VideoStatistics with optional overrides."""
    return VideoStatisticsFactory(**kwargs)


def create_video_with_channel(**kwargs) -> VideoWithChannel:
    """Create a VideoWithChannel with optional overrides."""
    return VideoWithChannelFactory(**kwargs)


def create_batch_videos(count: int = 5) -> List[Video]:
    """Create a batch of Video instances for testing."""
    videos = []
    base_video_ids = [
        "dQw4w9WgXcQ",
        "9bZkp7q19f0",
        "3tmd-ClpJxA",
        "jNQXAC9IVRw",
        "MejbOFk7H6c",
    ]
    base_channel_ids = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",
        "UC_x5XG1OV2P6uZZ5FSM9Ttw",
        "UCMtFAi84ehTSYSE9XoHefig",
        "UCBJycsmduvYEL83R_U4JriQ",
        "UCTestChannel12345678901",
    ]
    base_titles = [
        "Never Gonna Give You Up",
        "Google I/O Highlights",
        "Late Show Best Moments",
        "iPhone Review",
        "Test Video Content",
    ]

    for i in range(count):
        video_id = base_video_ids[i % len(base_video_ids)]
        channel_id = base_channel_ids[i % len(base_channel_ids)]
        title = base_titles[i % len(base_titles)]

        video = VideoFactory(
            video_id=video_id,
            channel_id=channel_id,
            title=title,
            duration=300 + (i * 120),  # Varying durations
            view_count=10000 + (i * 50000),
            like_count=500 + (i * 250),
        )
        videos.append(video)

    return videos
