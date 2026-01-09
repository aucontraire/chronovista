"""
Factory definitions for takeout playlist models.

Provides factory-boy factories for creating test instances of takeout playlist models
with realistic and consistent test data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Any, List, cast

import factory

from chronovista.models.takeout.takeout_data import TakeoutPlaylist
from tests.factories.takeout_playlist_item_factory import (
    TakeoutPlaylistItemFactory,
    create_batch_takeout_playlist_items,
)


class TakeoutPlaylistFactory(factory.Factory[TakeoutPlaylist]):
    """Factory for TakeoutPlaylist models."""

    class Meta:
        model = TakeoutPlaylist

    # Required fields
    name: Any = factory.LazyFunction(lambda: "Liked videos")
    file_path: Any = factory.LazyFunction(
        lambda: Path("/tmp/takeout/playlists/liked-videos.csv")
    )

    # Optional fields with realistic defaults
    videos: Any = factory.LazyFunction(lambda: create_batch_takeout_playlist_items(3))
    video_count = 0  # Will be calculated automatically


class TakeoutPlaylistMinimalFactory(factory.Factory[TakeoutPlaylist]):
    """Factory for TakeoutPlaylist models with only required fields."""

    class Meta:
        model = TakeoutPlaylist

    # Only required fields
    name: Any = factory.LazyFunction(lambda: "Watch later")
    file_path: Any = factory.LazyFunction(
        lambda: Path("/tmp/takeout/playlists/watch-later.csv")
    )

    # Set optional fields to minimal values
    videos: Any = factory.LazyFunction(list)  # Empty list
    video_count = 0


class TakeoutPlaylistLargeFactory(factory.Factory[TakeoutPlaylist]):
    """Factory for TakeoutPlaylist models with many videos."""

    class Meta:
        model = TakeoutPlaylist

    name: Any = factory.LazyFunction(lambda: "My Favorites")
    file_path: Any = factory.LazyFunction(
        lambda: Path("/tmp/takeout/playlists/my-favorites.csv")
    )
    videos: Any = factory.LazyFunction(lambda: create_batch_takeout_playlist_items(25))
    video_count = 0  # Will be calculated automatically


class TakeoutPlaylistMusicFactory(factory.Factory[TakeoutPlaylist]):
    """Factory for TakeoutPlaylist models with music content."""

    class Meta:
        model = TakeoutPlaylist

    name: Any = factory.LazyFunction(lambda: "Music Playlist")
    file_path: Any = factory.LazyFunction(
        lambda: Path("/tmp/takeout/playlists/music-playlist.csv")
    )
    videos: Any = factory.LazyFunction(
        lambda: [
            TakeoutPlaylistItemFactory(
                video_id="dQw4w9WgXcQ"
            ),  # Never Gonna Give You Up
            TakeoutPlaylistItemFactory(video_id="fJ9rUzIMcZQ"),  # Bohemian Rhapsody
            TakeoutPlaylistItemFactory(video_id="9jK-NcRmVcw"),  # Europa
        ]
    )
    video_count = 0


class TakeoutPlaylistTechFactory(factory.Factory[TakeoutPlaylist]):
    """Factory for TakeoutPlaylist models with tech content."""

    class Meta:
        model = TakeoutPlaylist

    name: Any = factory.LazyFunction(lambda: "Tech Tutorials")
    file_path: Any = factory.LazyFunction(
        lambda: Path("/tmp/takeout/playlists/tech-tutorials.csv")
    )
    videos: Any = factory.LazyFunction(
        lambda: [
            TakeoutPlaylistItemFactory(video_id="9bZkp7q19f0"),  # Python tutorial
            TakeoutPlaylistItemFactory(video_id="jNQXAC9IVRw"),  # Google I/O
            TakeoutPlaylistItemFactory(video_id="3tmd-ClpJxA"),  # Tech review
        ]
    )
    video_count = 0


# Test data constants for validation testing
class TakeoutPlaylistTestData:
    """Test data constants for takeout playlist models."""

    # Valid test data
    VALID_NAMES = [
        "Liked videos",
        "Watch later",
        "My Favorites",
        "Music Playlist",
        "Tech Tutorials",
        "A",  # Min length
        "A" * 200,  # Long playlist name
    ]

    VALID_FILE_PATHS = [
        Path("/tmp/takeout/playlists/liked-videos.csv"),
        Path("/tmp/takeout/playlists/watch-later.csv"),
        Path("/tmp/takeout/playlists/my-favorites.csv"),
        Path("/tmp/takeout/playlists/music-playlist.csv"),
        Path("/tmp/takeout/playlists/tech-tutorials.csv"),
        Path("/tmp/test.csv"),
        Path("relative/path/playlist.csv"),
    ]

    # Invalid test data
    INVALID_NAMES = ["", "   ", "\t\n"]  # Empty, whitespace

    INVALID_FILE_PATHS: list[str] = []  # Pathlib.Path can handle most strings


# Convenience factory functions
def create_takeout_playlist(**kwargs: Any) -> TakeoutPlaylist:
    """Create a TakeoutPlaylist with optional overrides."""
    result = TakeoutPlaylistFactory.build(**kwargs)
    assert isinstance(result, TakeoutPlaylist)
    return result


def create_minimal_takeout_playlist(**kwargs: Any) -> TakeoutPlaylist:
    """Create a minimal TakeoutPlaylist with only required fields."""
    result = TakeoutPlaylistMinimalFactory.build(**kwargs)
    assert isinstance(result, TakeoutPlaylist)
    return result


def create_large_takeout_playlist(**kwargs: Any) -> TakeoutPlaylist:
    """Create a TakeoutPlaylist with many videos."""
    result = TakeoutPlaylistLargeFactory.build(**kwargs)
    assert isinstance(result, TakeoutPlaylist)
    return result


def create_music_takeout_playlist(**kwargs: Any) -> TakeoutPlaylist:
    """Create a TakeoutPlaylist with music content."""
    result = TakeoutPlaylistMusicFactory.build(**kwargs)
    assert isinstance(result, TakeoutPlaylist)
    return result


def create_tech_takeout_playlist(**kwargs: Any) -> TakeoutPlaylist:
    """Create a TakeoutPlaylist with tech content."""
    result = TakeoutPlaylistTechFactory.build(**kwargs)
    assert isinstance(result, TakeoutPlaylist)
    return result


def create_batch_takeout_playlists(count: int = 3) -> List[TakeoutPlaylist]:
    """Create a batch of TakeoutPlaylist instances for testing."""
    playlists = []
    base_names = [
        "Liked videos",
        "Watch later",
        "My Favorites",
        "Music Playlist",
        "Tech Tutorials",
    ]

    for i in range(count):
        name = base_names[i % len(base_names)]
        if i >= len(base_names):
            name = f"{name} {i + 1}"

        file_path = Path(f"/tmp/takeout/playlists/{name.lower().replace(' ', '-')}.csv")
        video_count = (i % 5) + 1  # 1-5 videos per playlist

        playlist = TakeoutPlaylistFactory.build(
            name=name,
            file_path=file_path,
            videos=create_batch_takeout_playlist_items(video_count),
            video_count=0,  # Will be calculated automatically
        )
        playlists.append(playlist)

    return playlists
