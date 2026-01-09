"""
Factory definitions for channel models.

Provides factory-boy factories for creating test instances of channel models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, cast

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


class ChannelBaseFactory(factory.Factory[ChannelBase]):
    """Factory for ChannelBase models."""

    class Meta:
        model = ChannelBase

    channel_id: Any = factory.LazyFunction(lambda: "UCuAXFkgsw1L7xaCfnd5JJOw")
    title: Any = factory.LazyFunction(lambda: "Rick Astley")
    description: Any = factory.LazyFunction(
        lambda: "The official Rick Astley YouTube channel. Home of the legendary Never Gonna Give You Up music video."
    )
    subscriber_count: Any = factory.LazyFunction(lambda: 3500000)
    video_count: Any = factory.LazyFunction(lambda: 125)
    default_language: Any = factory.LazyFunction(lambda: "en")
    country: Any = factory.LazyFunction(lambda: "GB")
    thumbnail_url: Any = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/ytc/AKedOLSxvZ8QH9z4jO8jOdPNMDG7q9vPGnl_4iF8gQ=s240-c-k-c0x00ffffff-no-rj"
    )


class ChannelCreateFactory(factory.Factory[ChannelCreate]):
    """Factory for ChannelCreate models."""

    class Meta:
        model = ChannelCreate

    channel_id: Any = factory.LazyFunction(lambda: "UC_x5XG1OV2P6uZZ5FSM9Ttw")
    title: Any = factory.LazyFunction(lambda: "Google Developers")
    description: Any = factory.LazyFunction(
        lambda: "The Google Developers channel features talks from events, educational series, best practices, tips, and the latest updates across our products and platforms."
    )
    subscriber_count: Any = factory.LazyFunction(lambda: 2100000)
    video_count: Any = factory.LazyFunction(lambda: 8500)
    default_language: Any = factory.LazyFunction(lambda: "en-US")
    country: Any = factory.LazyFunction(lambda: "US")
    thumbnail_url: Any = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/ytc/AKedOLTHj8QH9z4jO8jOdPNMDG7q9vPGnl_4iF8gQ=s240-c-k-c0x00ffffff-no-rj"
    )


class ChannelUpdateFactory(factory.Factory[ChannelUpdate]):
    """Factory for ChannelUpdate models."""

    class Meta:
        model = ChannelUpdate

    title: Any = factory.LazyFunction(lambda: "Updated Channel Title")
    description: Any = factory.LazyFunction(
        lambda: "This is an updated channel description with new content."
    )
    subscriber_count: Any = factory.LazyFunction(lambda: 5000000)
    video_count: Any = factory.LazyFunction(lambda: 200)
    default_language: Any = factory.LazyFunction(lambda: "es")
    country: Any = factory.LazyFunction(lambda: "ES")
    thumbnail_url: Any = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/updated-thumbnail-url=s240-c-k-c0x00ffffff-no-rj"
    )


class ChannelFactory(factory.Factory[Channel]):
    """Factory for Channel models."""

    class Meta:
        model = Channel

    channel_id: Any = factory.LazyFunction(lambda: "UCMtFAi84ehTSYSE9XoHefig")
    title: Any = factory.LazyFunction(lambda: "The Late Show with Stephen Colbert")
    description: Any = factory.LazyFunction(
        lambda: "The Late Show with Stephen Colbert brings you late-night laughs with a healthy dose of current events and celebrity guests."
    )
    subscriber_count: Any = factory.LazyFunction(lambda: 4800000)
    video_count: Any = factory.LazyFunction(lambda: 3200)
    default_language: Any = factory.LazyFunction(lambda: "en")
    country: Any = factory.LazyFunction(lambda: "US")
    thumbnail_url: Any = factory.LazyFunction(
        lambda: "https://yt3.ggpht.com/ytc/AKedOLStephenColbert=s240-c-k-c0x00ffffff-no-rj"
    )
    created_at: Any = factory.LazyFunction(
        lambda: datetime(2023, 10, 15, 9, 30, 0, tzinfo=timezone.utc)
    )
    updated_at: Any = factory.LazyFunction(
        lambda: datetime(2023, 12, 1, 14, 45, 0, tzinfo=timezone.utc)
    )


class ChannelSearchFiltersFactory(factory.Factory[ChannelSearchFilters]):
    """Factory for ChannelSearchFilters models.

    When called with no arguments, generates realistic test data.
    When called with specific arguments, only those fields are set,
    leaving others as None (respecting model defaults).
    """

    class Meta:
        model = ChannelSearchFilters

    title_query: Any = factory.LazyFunction(lambda: "programming")
    description_query: Any = factory.LazyFunction(lambda: "tutorial")
    language_codes: Any = factory.LazyFunction(lambda: ["en", "en-US", "es"])
    countries: Any = factory.LazyFunction(lambda: ["US", "GB", "CA"])
    min_subscriber_count: Any = factory.LazyFunction(lambda: 10000)
    max_subscriber_count: Any = factory.LazyFunction(lambda: 10000000)
    min_video_count: Any = factory.LazyFunction(lambda: 50)
    max_video_count: Any = factory.LazyFunction(lambda: 5000)
    has_keywords: Any = factory.LazyFunction(lambda: True)


class ChannelStatisticsFactory(factory.Factory[ChannelStatistics]):
    """Factory for ChannelStatistics models."""

    class Meta:
        model = ChannelStatistics

    total_channels: Any = factory.LazyFunction(lambda: 150)
    total_subscribers: Any = factory.LazyFunction(lambda: 25000000)
    total_videos: Any = factory.LazyFunction(lambda: 12500)
    avg_subscribers_per_channel: Any = factory.LazyFunction(lambda: 166666.67)
    avg_videos_per_channel: Any = factory.LazyFunction(lambda: 83.33)
    top_countries: Any = factory.LazyFunction(
        lambda: [("US", 65), ("GB", 25), ("CA", 20), ("AU", 15), ("DE", 10)]
    )
    top_languages: Any = factory.LazyFunction(
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
def create_channel_base(**kwargs: Any) -> ChannelBase:
    """Create a ChannelBase with optional overrides."""
    result = ChannelBaseFactory.build(**kwargs)
    assert isinstance(result, ChannelBase)
    return result


def create_channel_create(**kwargs: Any) -> ChannelCreate:
    """Create a ChannelCreate with optional overrides."""
    result = ChannelCreateFactory.build(**kwargs)
    assert isinstance(result, ChannelCreate)
    return result


def create_channel_update(**kwargs: Any) -> ChannelUpdate:
    """Create a ChannelUpdate with optional overrides."""
    result = ChannelUpdateFactory.build(**kwargs)
    assert isinstance(result, ChannelUpdate)
    return result


def create_channel(**kwargs: Any) -> Channel:
    """Create a Channel with optional overrides."""
    result = ChannelFactory.build(**kwargs)
    assert isinstance(result, Channel)
    return result


def create_channel_search_filters(**kwargs: Any) -> ChannelSearchFilters:
    """Create a ChannelSearchFilters with optional overrides."""
    result = ChannelSearchFiltersFactory.build(**kwargs)
    assert isinstance(result, ChannelSearchFilters)
    return result


def create_channel_statistics(**kwargs: Any) -> ChannelStatistics:
    """Create a ChannelStatistics with optional overrides."""
    result = ChannelStatisticsFactory.build(**kwargs)
    assert isinstance(result, ChannelStatistics)
    return result


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
