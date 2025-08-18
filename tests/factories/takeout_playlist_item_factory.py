"""
Factory definitions for takeout playlist item models.

Provides factory-boy factories for creating test instances of takeout playlist item models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, cast

import factory

from chronovista.models.takeout.takeout_data import TakeoutPlaylistItem


class TakeoutPlaylistItemFactory(factory.Factory):
    """Factory for TakeoutPlaylistItem models."""

    class Meta:
        model = TakeoutPlaylistItem

    # Required fields
    video_id = factory.LazyFunction(lambda: "dQw4w9WgXcQ")

    # Optional fields with realistic defaults
    creation_timestamp = factory.LazyFunction(
        lambda: datetime(2023, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
    )
    raw_timestamp = factory.LazyFunction(lambda: "2023-06-15T14:30:00+00:00")


class TakeoutPlaylistItemMinimalFactory(factory.Factory):
    """Factory for TakeoutPlaylistItem models with only required fields."""

    class Meta:
        model = TakeoutPlaylistItem

    # Only required field
    video_id = factory.LazyFunction(lambda: "9bZkp7q19f0")

    # Set optional fields explicitly to None
    creation_timestamp = None
    raw_timestamp = None


class TakeoutPlaylistItemRecentFactory(factory.Factory):
    """Factory for TakeoutPlaylistItem models with recent timestamps."""

    class Meta:
        model = TakeoutPlaylistItem

    video_id = factory.LazyFunction(lambda: "3tmd-ClpJxA")
    creation_timestamp = factory.LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    )
    raw_timestamp = factory.LazyFunction(lambda: "2024-01-15T10:00:00+00:00")


class TakeoutPlaylistItemOldFactory(factory.Factory):
    """Factory for TakeoutPlaylistItem models with old timestamps."""

    class Meta:
        model = TakeoutPlaylistItem

    video_id = factory.LazyFunction(lambda: "jNQXAC9IVRw")
    creation_timestamp = factory.LazyFunction(
        lambda: datetime(2020, 5, 10, 16, 45, 0, tzinfo=timezone.utc)
    )
    raw_timestamp = factory.LazyFunction(lambda: "2020-05-10T16:45:00+00:00")


# Test data constants for validation testing
class TakeoutPlaylistItemTestData:
    """Test data constants for takeout playlist item models."""

    # Valid test data
    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",  # Rick Astley (11 chars)
        "9bZkp7q19f0",  # Tech video (11 chars)
        "3tmd-ClpJxA",  # Late Show (11 chars)
        "jNQXAC9IVRw",  # Google I/O (11 chars)
        "MejbOFk7H6c",  # Tech review (11 chars)
    ]

    VALID_RAW_TIMESTAMPS = [
        "2023-06-15T14:30:00+00:00",
        "2023-06-15T14:30:00Z",
        "2023-12-31T23:59:59Z",
        "2020-01-01T00:00:00+00:00",
        "2024-07-04T12:00:00-05:00",
    ]

    # Invalid test data
    INVALID_VIDEO_IDS = [
        "",
        "   ",
        "\t\n",
        "a" * 21,  # Too long
        "short",  # Too short
        "toolongvideoid123456789",  # Way too long
    ]

    INVALID_RAW_TIMESTAMPS = [
        "",
        "   ",
        "not-a-date",
        "2023-13-01T00:00:00Z",  # Invalid month
        "2023-06-32T00:00:00Z",  # Invalid day
        "2023-06-15T25:00:00Z",  # Invalid hour
    ]


# Convenience factory functions
def create_takeout_playlist_item(**kwargs: Any) -> TakeoutPlaylistItem:
    """Create a TakeoutPlaylistItem with optional overrides."""
    return cast(TakeoutPlaylistItem, TakeoutPlaylistItemFactory.build(**kwargs))


def create_minimal_takeout_playlist_item(**kwargs: Any) -> TakeoutPlaylistItem:
    """Create a minimal TakeoutPlaylistItem with only required fields."""
    return cast(TakeoutPlaylistItem, TakeoutPlaylistItemMinimalFactory.build(**kwargs))


def create_recent_takeout_playlist_item(**kwargs: Any) -> TakeoutPlaylistItem:
    """Create a TakeoutPlaylistItem with recent timestamp."""
    return cast(TakeoutPlaylistItem, TakeoutPlaylistItemRecentFactory.build(**kwargs))


def create_old_takeout_playlist_item(**kwargs: Any) -> TakeoutPlaylistItem:
    """Create a TakeoutPlaylistItem with old timestamp."""
    return cast(TakeoutPlaylistItem, TakeoutPlaylistItemOldFactory.build(**kwargs))


def create_batch_takeout_playlist_items(count: int = 5) -> List[TakeoutPlaylistItem]:
    """Create a batch of TakeoutPlaylistItem instances for testing."""
    items = []
    base_video_ids = [
        "dQw4w9WgXcQ",
        "9bZkp7q19f0",
        "3tmd-ClpJxA",
        "jNQXAC9IVRw",
        "MejbOFk7H6c",
    ]

    for i in range(count):
        video_id = base_video_ids[i % len(base_video_ids)]

        # Create progressive timestamps
        timestamp = datetime(2023, 1, 1, tzinfo=timezone.utc)
        timestamp = timestamp.replace(day=1 + (i % 28), hour=10 + (i % 12))

        item = TakeoutPlaylistItemFactory.build(
            video_id=video_id,
            creation_timestamp=timestamp,
            raw_timestamp=timestamp.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        )
        items.append(item)

    return items
