"""
Factory definitions for takeout data models.

Provides factory-boy factories for creating test instances of takeout data models
with realistic and consistent test data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Any, List, Optional, Tuple, cast

import factory

from chronovista.models.takeout.takeout_data import TakeoutData
from tests.factories.takeout_playlist_factory import create_batch_takeout_playlists
from tests.factories.takeout_subscription_factory import (
    create_batch_takeout_subscriptions,
)
from tests.factories.takeout_watch_entry_factory import (
    create_batch_takeout_watch_entries,
)


class TakeoutDataFactory(factory.Factory[TakeoutData]):
    """Factory for TakeoutData models."""

    class Meta:
        model = TakeoutData

    # Required fields
    takeout_path: Any = factory.LazyFunction(lambda: Path("/tmp/takeout"))

    # Optional fields with realistic defaults
    watch_history: Any = factory.LazyFunction(lambda: create_batch_takeout_watch_entries(10))
    playlists: Any = factory.LazyFunction(lambda: create_batch_takeout_playlists(3))
    subscriptions: Any = factory.LazyFunction(lambda: create_batch_takeout_subscriptions(5))
    parsed_at: Any = factory.LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    )

    # These will be calculated automatically from the data
    total_videos_watched = 0
    total_playlists = 0
    total_subscriptions = 0
    date_range = None


class TakeoutDataMinimalFactory(factory.Factory[TakeoutData]):
    """Factory for TakeoutData models with only required fields."""

    class Meta:
        model = TakeoutData

    # Only required field
    takeout_path: Any = factory.LazyFunction(lambda: Path("/tmp/minimal-takeout"))

    # Set optional fields to empty/default values
    watch_history: Any = factory.LazyFunction(list)  # Empty list
    playlists: Any = factory.LazyFunction(list)  # Empty list
    subscriptions: Any = factory.LazyFunction(list)  # Empty list
    parsed_at: Any = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    total_videos_watched = 0
    total_playlists = 0
    total_subscriptions = 0
    date_range = None


class TakeoutDataLargeFactory(factory.Factory[TakeoutData]):
    """Factory for TakeoutData models with large amounts of data."""

    class Meta:
        model = TakeoutData

    takeout_path: Any = factory.LazyFunction(lambda: Path("/tmp/large-takeout"))
    watch_history: Any = factory.LazyFunction(
        lambda: create_batch_takeout_watch_entries(100)
    )
    playlists: Any = factory.LazyFunction(lambda: create_batch_takeout_playlists(15))
    subscriptions: Any = factory.LazyFunction(lambda: create_batch_takeout_subscriptions(50))
    parsed_at: Any = factory.LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    )
    total_videos_watched = 0
    total_playlists = 0
    total_subscriptions = 0
    date_range = None


class TakeoutDataHistoricalFactory(factory.Factory[TakeoutData]):
    """Factory for TakeoutData models with historical data (older timestamps)."""

    class Meta:
        model = TakeoutData

    takeout_path: Any = factory.LazyFunction(lambda: Path("/tmp/historical-takeout"))
    watch_history: Any = factory.LazyFunction(lambda: create_batch_takeout_watch_entries(20))
    playlists: Any = factory.LazyFunction(lambda: create_batch_takeout_playlists(5))
    subscriptions: Any = factory.LazyFunction(lambda: create_batch_takeout_subscriptions(10))
    parsed_at: Any = factory.LazyFunction(
        lambda: datetime(2020, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    )
    total_videos_watched = 0
    total_playlists = 0
    total_subscriptions = 0
    date_range = None


class TakeoutDataWithExplicitTotalsFactory(factory.Factory[TakeoutData]):
    """Factory for TakeoutData models with explicitly set totals (not auto-calculated)."""

    class Meta:
        model = TakeoutData

    takeout_path: Any = factory.LazyFunction(lambda: Path("/tmp/explicit-takeout"))
    watch_history: Any = factory.LazyFunction(lambda: create_batch_takeout_watch_entries(5))
    playlists: Any = factory.LazyFunction(lambda: create_batch_takeout_playlists(2))
    subscriptions: Any = factory.LazyFunction(lambda: create_batch_takeout_subscriptions(3))
    parsed_at: Any = factory.LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    )

    # Explicitly set totals (won't be auto-calculated)
    total_videos_watched = 100
    total_playlists = 20
    total_subscriptions = 50
    date_range: Any = factory.LazyFunction(
        lambda: (
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
    )


# Test data constants for validation testing
class TakeoutDataTestData:
    """Test data constants for takeout data models."""

    # Valid test data
    VALID_TAKEOUT_PATHS = [
        Path("/tmp/takeout"),
        Path("/tmp/minimal-takeout"),
        Path("/tmp/large-takeout"),
        Path("/tmp/historical-takeout"),
        Path("/tmp/explicit-takeout"),
        Path("relative/takeout/path"),
        Path("/Users/user/Downloads/Takeout"),
    ]

    VALID_PARSED_AT_TIMESTAMPS = [
        datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        datetime(2020, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        datetime.now(timezone.utc),
    ]

    VALID_DATE_RANGES = [
        (
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        (
            datetime(2023, 1, 1, tzinfo=timezone.utc),
            datetime(2023, 12, 31, tzinfo=timezone.utc),
        ),
        None,  # Can be None
    ]

    # Invalid test data (minimal since Path is very forgiving)
    INVALID_TOTALS = [-1, -100]  # Negative counts don't make sense


# Convenience factory functions
def create_takeout_data(**kwargs: Any) -> TakeoutData:
    """Create a TakeoutData with optional overrides."""
    result = TakeoutDataFactory.build(**kwargs)
    assert isinstance(result, TakeoutData)
    return result


def create_minimal_takeout_data(**kwargs: Any) -> TakeoutData:
    """Create a minimal TakeoutData with only required fields."""
    result = TakeoutDataMinimalFactory.build(**kwargs)
    assert isinstance(result, TakeoutData)
    return result


def create_large_takeout_data(**kwargs: Any) -> TakeoutData:
    """Create a TakeoutData with large amounts of data."""
    result = TakeoutDataLargeFactory.build(**kwargs)
    assert isinstance(result, TakeoutData)
    return result


def create_historical_takeout_data(**kwargs: Any) -> TakeoutData:
    """Create a TakeoutData with historical data."""
    result = TakeoutDataHistoricalFactory.build(**kwargs)
    assert isinstance(result, TakeoutData)
    return result


def create_takeout_data_with_explicit_totals(**kwargs: Any) -> TakeoutData:
    """Create a TakeoutData with explicitly set totals."""
    result = TakeoutDataWithExplicitTotalsFactory.build(**kwargs)
    assert isinstance(result, TakeoutData)
    return result


def create_empty_takeout_data(takeout_path: Optional[Path] = None) -> TakeoutData:
    """Create a TakeoutData with no watch history, playlists, or subscriptions."""
    if takeout_path is None:
        takeout_path = Path("/tmp/empty-takeout")

    result = TakeoutDataMinimalFactory.build(takeout_path=takeout_path)
    assert isinstance(result, TakeoutData)
    return result


def create_takeout_data_with_counts(
    video_count: int = 10,
    playlist_count: int = 3,
    subscription_count: int = 5,
    **kwargs: Any,
) -> TakeoutData:
    """Create a TakeoutData with specific counts of each data type."""
    watch_history = create_batch_takeout_watch_entries(video_count)
    playlists = create_batch_takeout_playlists(playlist_count)
    subscriptions = create_batch_takeout_subscriptions(subscription_count)

    result = TakeoutDataFactory.build(
            watch_history=watch_history,
            playlists=playlists,
            subscriptions=subscriptions,
            **kwargs,
        )
    assert isinstance(result, TakeoutData)
    return result


def create_batch_takeout_data(count: int = 3) -> List[TakeoutData]:
    """Create a batch of TakeoutData instances for testing."""
    takeout_data_list = []

    for i in range(count):
        takeout_path = Path(f"/tmp/takeout-batch-{i}")
        video_count = (i + 1) * 5  # 5, 10, 15, etc.
        playlist_count = i + 1  # 1, 2, 3, etc.
        subscription_count = (i + 1) * 2  # 2, 4, 6, etc.

        parsed_at = datetime(2024, 1, 1 + i, 10, 0, 0, tzinfo=timezone.utc)

        takeout_data = create_takeout_data_with_counts(
            video_count=video_count,
            playlist_count=playlist_count,
            subscription_count=subscription_count,
            takeout_path=takeout_path,
            parsed_at=parsed_at,
        )
        takeout_data_list.append(takeout_data)

    return takeout_data_list
