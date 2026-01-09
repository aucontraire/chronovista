"""
Factory definitions for takeout watch entry models.

Provides factory-boy factories for creating test instances of takeout watch entry models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Any, Dict, List, cast

import factory
from factory import LazyFunction

from chronovista.models.takeout.takeout_data import TakeoutWatchEntry


class TakeoutWatchEntryFactory(factory.Factory[TakeoutWatchEntry]):
    """Factory for TakeoutWatchEntry models."""

    class Meta:
        model = TakeoutWatchEntry

    # Required fields
    title: Any = factory.LazyFunction(
        lambda: "Watched Rick Astley - Never Gonna Give You Up (Official Video)"
    )
    title_url: Any = factory.LazyFunction(
        lambda: "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )

    # Optional fields with realistic defaults
    video_id: Any = factory.LazyFunction(lambda: "dQw4w9WgXcQ")
    channel_name: Any = factory.LazyFunction(lambda: "Rick Astley")
    channel_url: Any = factory.LazyFunction(
        lambda: "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
    )
    channel_id: Any = factory.LazyFunction(lambda: "UCuAXFkgsw1L7xaCfnd5JJOw")
    watched_at: Any = factory.LazyFunction(
        lambda: datetime(2023, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
    )
    raw_time: Any = factory.LazyFunction(lambda: "2023-06-15T14:30:00Z")


class TakeoutWatchEntryMinimalFactory(factory.Factory[TakeoutWatchEntry]):
    """Factory for TakeoutWatchEntry models with only required fields."""

    class Meta:
        model = TakeoutWatchEntry

    # Only required fields
    title: Any = factory.LazyFunction(lambda: "Watched Python Tutorial - Complete Course")
    title_url: Any = factory.LazyFunction(
        lambda: "https://www.youtube.com/watch?v=9bZkp7q19f0"
    )

    # Set optional fields explicitly to None
    video_id = None
    channel_name = None
    channel_url = None
    channel_id = None
    watched_at = None
    raw_time = None


class TakeoutWatchEntryWithTimeFactory(factory.Factory[TakeoutWatchEntry]):
    """Factory for TakeoutWatchEntry models with realistic time data."""

    class Meta:
        model = TakeoutWatchEntry

    title: Any = factory.LazyFunction(
        lambda: "Watched The Late Show with Stephen Colbert - Best Moments 2023"
    )
    title_url: Any = factory.LazyFunction(
        lambda: "https://www.youtube.com/watch?v=3tmd-ClpJxA"
    )
    video_id: Any = factory.LazyFunction(lambda: "3tmd-ClpJxA")
    channel_name: Any = factory.LazyFunction(lambda: "The Late Show with Stephen Colbert")
    channel_url: Any = factory.LazyFunction(
        lambda: "https://www.youtube.com/channel/UCMtFAi84ehTSYSE9XoHefig"
    )
    channel_id: Any = factory.LazyFunction(lambda: "UCMtFAi84ehTSYSE9XoHefig")
    watched_at: Any = factory.LazyFunction(
        lambda: datetime(2023, 12, 15, 23, 35, 0, tzinfo=timezone.utc)
    )
    raw_time: Any = factory.LazyFunction(lambda: "2023-12-15T23:35:00Z")


class TakeoutWatchEntryTechFactory(factory.Factory[TakeoutWatchEntry]):
    """Factory for TakeoutWatchEntry models with tech content."""

    class Meta:
        model = TakeoutWatchEntry

    title: Any = factory.LazyFunction(
        lambda: "Watched Google I/O 2023: What's new in Machine Learning"
    )
    title_url: Any = factory.LazyFunction(
        lambda: "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    )
    video_id: Any = factory.LazyFunction(lambda: "jNQXAC9IVRw")
    channel_name: Any = factory.LazyFunction(lambda: "Google Developers")
    channel_url: Any = factory.LazyFunction(
        lambda: "https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw"
    )
    channel_id: Any = factory.LazyFunction(lambda: "UC_x5XG1OV2P6uZZ5FSM9Ttw")
    watched_at: Any = factory.LazyFunction(
        lambda: datetime(2023, 5, 10, 17, 0, 0, tzinfo=timezone.utc)
    )
    raw_time: Any = factory.LazyFunction(lambda: "2023-05-10T17:00:00Z")


# Test data constants for validation testing
class TakeoutWatchEntryTestData:
    """Test data constants for takeout watch entry models."""

    # Valid test data
    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",  # Rick Astley (11 chars)
        "9bZkp7q19f0",  # Tech video (11 chars)
        "3tmd-ClpJxA",  # Late Show (11 chars)
        "jNQXAC9IVRw",  # Google I/O (11 chars)
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
        "Watched Rick Astley - Never Gonna Give You Up",
        "Watched Python Programming Tutorial",
        "Watched A",  # Min meaningful length after 'Watched '
        "Watched " + "A" * 1000,  # Long title
    ]

    VALID_URLS = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123s",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLtest&index=1",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",  # Without www
        "http://www.youtube.com/watch?v=dQw4w9WgXcQ",  # HTTP
    ]

    VALID_CHANNEL_NAMES = [
        "Rick Astley",
        "Google Developers",
        "The Late Show with Stephen Colbert",
        "Marques Brownlee",
        "TestChannel",
        "A",  # Min length
        "A" * 200,  # Long channel name
    ]

    VALID_CHANNEL_URLS = [
        "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "https://youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "http://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "https://www.youtube.com/c/RickAstleyYT",  # Custom URL
        "https://www.youtube.com/@rickastley",  # Handle URL
    ]

    VALID_RAW_TIMES = [
        "2023-06-15T14:30:00Z",
        "2023-06-15T14:30:00+00:00",
        "2023-06-15T14:30:00-05:00",
        "2023-12-31T23:59:59Z",
        "2020-01-01T00:00:00Z",
    ]

    # Invalid test data
    INVALID_TITLES = ["", "   ", "\t\n", "Watched"]  # Empty, whitespace, no content
    INVALID_URLS = [
        "",
        "   ",
        "not-a-url",
        "https://example.com",
        "youtube.com/watch",  # Missing protocol
        "https://www.youtube.com/channel/UCtest",  # Channel URL not watch URL
    ]
    INVALID_VIDEO_IDS = [
        "",
        "   ",
        "\t\n",
        "a" * 21,  # Too long
        "short",  # Too short
        "toolongvideoid123456789",  # Way too long
    ]
    INVALID_CHANNEL_IDS = [
        "",
        "   ",
        "\t\n",
        "a" * 25,  # Too long
        "UCshort",  # Too short
        "PLnotachannel123456789012",  # Wrong prefix
        "notachannel",  # No UC prefix
    ]
    INVALID_RAW_TIMES = [
        "",
        "   ",
        "not-a-date",
        "2023-13-01T00:00:00Z",  # Invalid month
        "2023-06-32T00:00:00Z",  # Invalid day
        "2023-06-15T25:00:00Z",  # Invalid hour
    ]


# Convenience factory functions
def create_takeout_watch_entry(**kwargs: Any) -> TakeoutWatchEntry:
    """Create a TakeoutWatchEntry with optional overrides."""
    result = TakeoutWatchEntryFactory.build(**kwargs)
    assert isinstance(result, TakeoutWatchEntry)
    return result


def create_minimal_takeout_watch_entry(**kwargs: Any) -> TakeoutWatchEntry:
    """Create a minimal TakeoutWatchEntry with only required fields."""
    result = TakeoutWatchEntryMinimalFactory.build(**kwargs)
    assert isinstance(result, TakeoutWatchEntry)
    return result


def create_takeout_watch_entry_with_time(**kwargs: Any) -> TakeoutWatchEntry:
    """Create a TakeoutWatchEntry with realistic time data."""
    result = TakeoutWatchEntryWithTimeFactory.build(**kwargs)
    assert isinstance(result, TakeoutWatchEntry)
    return result


def create_tech_takeout_watch_entry(**kwargs: Any) -> TakeoutWatchEntry:
    """Create a TakeoutWatchEntry with tech content."""
    result = TakeoutWatchEntryTechFactory.build(**kwargs)
    assert isinstance(result, TakeoutWatchEntry)
    return result


def create_batch_takeout_watch_entries(count: int = 5) -> List[TakeoutWatchEntry]:
    """Create a batch of TakeoutWatchEntry instances for testing."""
    entries = []
    base_video_ids = [
        "dQw4w9WgXcQ",
        "9bZkp7q19f0",
        "3tmd-ClpJxA",
        "jNQXAC9IVRw",
        "MejbOFk7H6c",
    ]
    base_titles = [
        "Never Gonna Give You Up",
        "Python Programming Tutorial",
        "Late Show Best Moments",
        "Google I/O Highlights",
        "Tech Review Video",
    ]
    base_channels = [
        ("Rick Astley", "UCuAXFkgsw1L7xaCfnd5JJOw"),
        ("Python Tutorials", "UC_x5XG1OV2P6uZZ5FSM9Ttw"),
        ("The Late Show", "UCMtFAi84ehTSYSE9XoHefig"),
        ("Google Developers", "UCBJycsmduvYEL83R_U4JriQ"),
        ("Tech Channel", "UCTestChannel12345678901"),
    ]

    for i in range(count):
        video_id = base_video_ids[i % len(base_video_ids)]
        title = f"Watched {base_titles[i % len(base_titles)]}"
        channel_name, channel_id = base_channels[i % len(base_channels)]

        # Create progressive timestamps
        timestamp = datetime(2023, 1, 1, tzinfo=timezone.utc)
        timestamp = timestamp.replace(day=1 + (i % 28), hour=10 + (i % 12))

        entry = TakeoutWatchEntryFactory.build(
            video_id=video_id,
            title=title,
            title_url=f"https://www.youtube.com/watch?v={video_id}",
            channel_name=channel_name,
            channel_id=channel_id,
            channel_url=f"https://www.youtube.com/channel/{channel_id}",
            watched_at=timestamp,
            raw_time=timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        entries.append(entry)

    return entries
