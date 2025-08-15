"""
Factory definitions for channel models.

Provides factory-boy factories for creating test instances of channel models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, cast

import factory
from factory import LazyFunction

from chronovista.models.channel import (
    Channel,
    ChannelBase,
    ChannelCreate,
    ChannelSearchFilters,
    ChannelStatistics,
    ChannelUpdate,
)


class ChannelBaseFactory(factory.Factory):
    """Factory for ChannelBase models."""

    class Meta:
        model = ChannelBase

    channel_id = factory.LazyFunction(lambda: "UCuAXFkgsw1L7xaCfnd5JJOw")
    title = factory.LazyFunction(lambda: "Rick Astley")
    description = factory.LazyFunction(
        lambda: "The official Rick Astley YouTube channel. Home of the legendary Never Gonna Give You Up music video."
    )
    subscriber_count = factory.LazyFunction(lambda: 3500000)
    video_count = factory.LazyFunction(lambda: 125)
    default_language = factory.LazyFunction(lambda: "en")
    country = factory.LazyFunction(lambda: "GB")
    thumbnail_url = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/ytc/AKedOLSxvZ8QH9z4jO8jOdPNMDG7q9vPGnl_4iF8gQ=s240-c-k-c0x00ffffff-no-rj"
    )


class ChannelCreateFactory(factory.Factory):
    """Factory for ChannelCreate models."""

    class Meta:
        model = ChannelCreate

    channel_id = factory.LazyFunction(lambda: "UC_x5XG1OV2P6uZZ5FSM9Ttw")
    title = factory.LazyFunction(lambda: "Google Developers")
    description = factory.LazyFunction(
        lambda: "The Google Developers channel features talks from events, educational series, best practices, tips, and the latest updates across our products and platforms."
    )
    subscriber_count = factory.LazyFunction(lambda: 2100000)
    video_count = factory.LazyFunction(lambda: 8500)
    default_language = factory.LazyFunction(lambda: "en-US")
    country = factory.LazyFunction(lambda: "US")
    thumbnail_url = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/ytc/AKedOLTHj8QH9z4jO8jOdPNMDG7q9vPGnl_4iF8gQ=s240-c-k-c0x00ffffff-no-rj"
    )


class ChannelUpdateFactory(factory.Factory):
    """Factory for ChannelUpdate models."""

    class Meta:
        model = ChannelUpdate

    title = factory.LazyFunction(lambda: "Updated Channel Title")
    description = factory.LazyFunction(
        lambda: "This is an updated channel description with new content."
    )
    subscriber_count = factory.LazyFunction(lambda: 5000000)
    video_count = factory.LazyFunction(lambda: 200)
    default_language = factory.LazyFunction(lambda: "es")
    country = factory.LazyFunction(lambda: "ES")
    thumbnail_url = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/updated-thumbnail-url=s240-c-k-c0x00ffffff-no-rj"
    )


class ChannelFactory(factory.Factory):
    """Factory for Channel models."""

    class Meta:
        model = Channel

    channel_id = factory.LazyFunction(lambda: "UCMtFAi84ehTSYSE9XoHefig")
    title = factory.LazyFunction(lambda: "The Late Show with Stephen Colbert")
    description = factory.LazyFunction(
        lambda: "The Late Show with Stephen Colbert brings you late-night laughs with a healthy dose of current events and celebrity guests."
    )
    subscriber_count = factory.LazyFunction(lambda: 4800000)
    video_count = factory.LazyFunction(lambda: 3200)
    default_language = factory.LazyFunction(lambda: "en")
    country = factory.LazyFunction(lambda: "US")
    thumbnail_url = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/ytc/AKedOLStephenColbert=s240-c-k-c0x00ffffff-no-rj"
    )
    created_at = factory.LazyFunction(
        lambda: datetime(2023, 10, 15, 9, 30, 0, tzinfo=timezone.utc)
    )
    updated_at = factory.LazyFunction(
        lambda: datetime(2023, 12, 1, 14, 45, 0, tzinfo=timezone.utc)
    )


class ChannelSearchFiltersFactory(factory.Factory):
    """Factory for ChannelSearchFilters models.
    
    When called with no arguments, generates realistic test data.
    When called with specific arguments, only those fields are set,
    leaving others as None (respecting model defaults).
    """

    class Meta:
        model = ChannelSearchFilters

    title_query = factory.LazyFunction(lambda: "programming")
    description_query = factory.LazyFunction(lambda: "tutorial")
    language_codes = factory.LazyFunction(lambda: ["en", "en-US", "es"])
    countries = factory.LazyFunction(lambda: ["US", "GB", "CA"])
    min_subscriber_count = factory.LazyFunction(lambda: 10000)
    max_subscriber_count = factory.LazyFunction(lambda: 10000000)
    min_video_count = factory.LazyFunction(lambda: 50)
    max_video_count = factory.LazyFunction(lambda: 5000)
    has_keywords = factory.LazyFunction(lambda: True)


class ChannelStatisticsFactory(factory.Factory):
    """Factory for ChannelStatistics models."""

    class Meta:
        model = ChannelStatistics

    total_channels = factory.LazyFunction(lambda: 150)
    total_subscribers = factory.LazyFunction(lambda: 25000000)
    total_videos = factory.LazyFunction(lambda: 12500)
    avg_subscribers_per_channel = factory.LazyFunction(lambda: 166666.67)
    avg_videos_per_channel = factory.LazyFunction(lambda: 83.33)
    top_countries = factory.LazyFunction(
        lambda: [("US", 65), ("GB", 25), ("CA", 20), ("AU", 15), ("DE", 10)]
    )
    top_languages = factory.LazyFunction(
        lambda: [("en", 85), ("en-US", 45), ("es", 12), ("fr", 8), ("de", 5)]
    )


# Test data constants for validation testing
class ChannelTestData:
    """Test data constants for channel models."""

    # Valid test data
    VALID_CHANNEL_IDS = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",  # Rick Astley
        "UC_x5XG1OV2P6uZZ5FSM9Ttw",  # Google Developers
        "UCMtFAi84ehTSYSE9XoHefig",  # Stephen Colbert
        "UC1234567890123456789012",  # Exactly 24 chars with UC prefix
        "UCabcdefghijklmnopqrstuv",  # Another valid 24-char ID
    ]

    VALID_TITLES = [
        "Rick Astley",
        "Google Developers",
        "The Late Show with Stephen Colbert",
        "A" * 255,  # Max length
        "A",  # Min length
    ]

    VALID_COUNTRIES = ["US", "GB", "CA", "AU", "DE", "FR", "ES", "IT", "JP", "KR"]
    VALID_LANGUAGES = ["en", "en-US", "es", "fr", "de", "it", "ja", "ko", "pt-BR"]
    VALID_SUBSCRIBER_COUNTS = [0, 1000, 100000, 1000000, 10000000]
    VALID_VIDEO_COUNTS = [0, 1, 50, 500, 5000]

    # Invalid test data
    INVALID_CHANNEL_IDS = [
        "",
        "   ",
        "\t\n",
        "a" * 25,
        "UC123456789012345678901",
        "UCshort",
        "PLnotachannel123456789012",
    ]  # Empty, whitespace, too long, wrong length, wrong prefix
    INVALID_TITLES = ["", "   ", "\t\n", "a" * 256]  # Empty, whitespace, too long
    INVALID_COUNTRIES = ["", "A", "ABC", "123"]  # Wrong length, invalid format
    INVALID_LANGUAGES = ["", "A", "a" * 11]  # Too short, too long
    INVALID_SUBSCRIBER_COUNTS = [-1, -100]  # Negative values
    INVALID_VIDEO_COUNTS = [-1, -50]  # Negative values

    # Valid YouTube URLs for testing
    VALID_THUMBNAIL_URLS = [
        "https://yt3.ggpht.com/ytc/AKedOLSxvZ8QH9z4jO8jOdPNMDG7q9vPGnl_4iF8gQ=s240-c-k-c0x00ffffff-no-rj",
        "https://yt3.ggpht.com/a/AATXAJzKmqCDM-bV-4B3QE0BvNqxOcG9H3g=s100-c-k-c0xffffffff-no-rj-mo",
        "https://yt3.ggpht.com/ytc/shorter-url",
        "a" * 500,  # Max length
    ]

    INVALID_THUMBNAIL_URLS = ["a" * 501]  # Too long


# Convenience factory functions
def create_channel_base(**kwargs) -> ChannelBase:
    """Create a ChannelBase with optional overrides."""
    return cast(ChannelBase, ChannelBaseFactory.build(**kwargs))


def create_channel_create(**kwargs) -> ChannelCreate:
    """Create a ChannelCreate with optional overrides."""
    return cast(ChannelCreate, ChannelCreateFactory.build(**kwargs))


def create_channel_update(**kwargs) -> ChannelUpdate:
    """Create a ChannelUpdate with optional overrides."""
    return cast(ChannelUpdate, ChannelUpdateFactory.build(**kwargs))


def create_channel(**kwargs) -> Channel:
    """Create a Channel with optional overrides."""
    return cast(Channel, ChannelFactory.build(**kwargs))


def create_channel_search_filters(**kwargs) -> ChannelSearchFilters:
    """Create a ChannelSearchFilters with optional overrides."""
    return cast(ChannelSearchFilters, ChannelSearchFiltersFactory.build(**kwargs))


def create_channel_statistics(**kwargs) -> ChannelStatistics:
    """Create a ChannelStatistics with optional overrides."""
    return cast(ChannelStatistics, ChannelStatisticsFactory.build(**kwargs))


def create_batch_channels(count: int = 5) -> List[Channel]:
    """Create a batch of Channel instances for testing."""
    channels = []
    base_channel_ids = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",
        "UC_x5XG1OV2P6uZZ5FSM9Ttw",
        "UCMtFAi84ehTSYSE9XoHefig",
        "UC123456789Test1234567890",
        "UC987654321Test0987654321",
    ]
    base_titles = [
        "Rick Astley",
        "Google Developers",
        "Stephen Colbert",
        "Test Channel Alpha",
        "Test Channel Beta",
    ]

    for i in range(count):
        channel_id = base_channel_ids[i % len(base_channel_ids)]
        title = base_titles[i % len(base_titles)]

        channel = ChannelFactory.build(
            channel_id=channel_id,
            title=title,
            subscriber_count=100000 + (i * 50000),
            video_count=100 + (i * 25),
        )
        channels.append(channel)

    return channels
