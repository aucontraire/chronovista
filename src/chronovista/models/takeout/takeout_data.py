"""
Core Takeout Data Models

Pydantic models for parsing Google Takeout data files.
- Watch History: JSON format (user must select JSON option during download)
- Playlists: CSV format (individual files per playlist)
- Subscriptions: CSV format
- Other data: Various CSV formats
"""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, model_validator


class TakeoutWatchEntry(BaseModel):
    """
    Represents a single watch history entry from Google Takeout.

    Parsed from watch-history.json entries.
    """

    # Required fields first
    title: str = Field(..., description="Video title (with 'Watched ' prefix removed)")
    title_url: str = Field(..., description="Original YouTube URL")

    # Optional fields second
    video_id: str | None = Field(
        default=None, description="YouTube video ID extracted from URL"
    )
    channel_name: str | None = Field(default=None, description="Channel name from subtitles")
    channel_url: str | None = Field(default=None, description="Channel URL from subtitles")
    channel_id: str | None = Field(default=None, description="Channel ID extracted from URL")
    watched_at: datetime | None = Field(
        default=None, description="When the video was watched"
    )
    raw_time: str | None = Field(
        default=None, description="Original time string from takeout"
    )

    @model_validator(mode="after")
    def extract_video_id(self) -> "TakeoutWatchEntry":
        """Extract video ID from title_url if not provided."""
        if not self.video_id and self.title_url:
            try:
                # First, replace Unicode escapes manually
                decoded_url = self.title_url.replace("\\u003d", "=").replace(
                    "\\u0026", "&"
                )

                # Extract video ID from URL - try multiple methods
                if "v=" in decoded_url:
                    # Simple string parsing for YouTube URLs
                    video_id = decoded_url.split("v=")[1].split("&")[0]
                    self.video_id = video_id
                else:
                    # Fallback to URL parsing
                    parsed_url = urlparse(decoded_url)
                    video_ids = parse_qs(parsed_url.query).get("v", [])
                    if video_ids and isinstance(video_ids[0], str):
                        self.video_id = video_ids[0]
            except Exception:
                # If all parsing fails, try direct regex as last resort
                import re

                match = re.search(r"[?&]v=([^&]+)", self.title_url)
                if match:
                    self.video_id = match.group(1)
        return self

    @model_validator(mode="after")
    def extract_channel_id_from_url(self) -> "TakeoutWatchEntry":
        """Extract channel ID from channel_url if not provided."""
        if not self.channel_id and self.channel_url:
            if isinstance(self.channel_url, str) and "/channel/" in self.channel_url:
                parts = self.channel_url.split("/channel/")
                if len(parts) > 1:
                    self.channel_id = parts[-1]
        return self

    @model_validator(mode="after")
    def parse_watched_at(self) -> "TakeoutWatchEntry":
        """Parse watched_at from raw_time string."""
        if self.watched_at is not None:
            return self

        if self.raw_time:
            try:
                # Handle various Google Takeout date formats
                if self.raw_time.endswith("Z"):
                    self.watched_at = datetime.fromisoformat(
                        self.raw_time.replace("Z", "+00:00")
                    )
                else:
                    self.watched_at = datetime.fromisoformat(self.raw_time)
            except ValueError:
                # If parsing fails, leave as None
                pass
        return self


class TakeoutPlaylistItem(BaseModel):
    """Represents a single video in a takeout playlist."""

    video_id: str = Field(..., description="YouTube video ID from CSV")
    creation_timestamp: datetime | None = Field(
        default=None, description="When video was added to playlist"
    )
    raw_timestamp: str | None = Field(
        default=None, description="Original timestamp string from CSV"
    )

    @model_validator(mode="after")
    def parse_timestamp_from_raw(self) -> "TakeoutPlaylistItem":
        """Parse creation_timestamp from raw_timestamp if needed."""
        if self.creation_timestamp is None and self.raw_timestamp:
            try:
                # Handle ISO format with timezone: 2017-11-07T13:29:55+00:00
                self.creation_timestamp = datetime.fromisoformat(self.raw_timestamp)
            except ValueError:
                # If parsing fails, leave as None
                pass
        return self


class TakeoutPlaylist(BaseModel):
    """
    Represents a playlist from Google Takeout.

    Parsed from individual playlist CSV files. The youtube_id is extracted
    from playlists.csv which maps playlist titles to their YouTube IDs.
    """

    name: str = Field(..., description="Playlist name (derived from filename)")
    file_path: Path = Field(..., description="Path to the playlist CSV file")
    videos: list[TakeoutPlaylistItem] = Field(
        default_factory=list, description="Videos in the playlist"
    )
    video_count: int = Field(default=0, description="Number of videos in playlist")
    youtube_id: str | None = Field(
        default=None,
        description="YouTube playlist ID from playlists.csv (PL prefix, LL, WL, or HL)",
    )
    created_at: datetime | None = Field(
        default=None,
        description="Playlist creation timestamp from playlists.csv",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Playlist update timestamp from playlists.csv",
    )
    visibility: str | None = Field(
        default=None,
        description="Playlist visibility (Private/Public/Unlisted) from playlists.csv",
    )

    @model_validator(mode="after")
    def set_video_count(self) -> "TakeoutPlaylist":
        """Set video count based on videos list."""
        if self.video_count == 0:  # Only calculate if not explicitly set
            self.video_count = len(self.videos)
        return self


class TakeoutSubscription(BaseModel):
    """
    Represents a channel subscription from Google Takeout.

    Parsed from subscriptions.csv.
    """

    channel_id: str | None = Field(default=None, description="YouTube channel ID")
    channel_title: str = Field(..., description="Channel name/title")
    channel_url: str = Field(..., description="Channel URL")

    @model_validator(mode="after")
    def extract_channel_id_from_url(self) -> "TakeoutSubscription":
        """Extract channel ID from channel_url if not provided."""
        if not self.channel_id and self.channel_url:
            if isinstance(self.channel_url, str):
                if "/channel/" in self.channel_url:
                    parts = self.channel_url.split("/channel/")
                    if len(parts) > 1:
                        self.channel_id = parts[-1]
                elif "/c/" in self.channel_url:
                    # Handle custom channel URLs - these need API resolution
                    self.channel_id = None
        return self


class TakeoutData(BaseModel):
    """
    Container for all parsed Google Takeout data.

    This is the main data structure returned by TakeoutService.
    """

    takeout_path: Path = Field(..., description="Path to the takeout directory")
    watch_history: list[TakeoutWatchEntry] = Field(
        default_factory=list, description="Watch history entries"
    )
    playlists: list[TakeoutPlaylist] = Field(
        default_factory=list, description="User playlists"
    )
    subscriptions: list[TakeoutSubscription] = Field(
        default_factory=list, description="Channel subscriptions"
    )

    # Metadata
    parsed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When this data was parsed"
    )
    total_videos_watched: int = Field(
        default=0, description="Total unique videos in watch history"
    )
    total_playlists: int = Field(default=0, description="Total playlists found")
    total_subscriptions: int = Field(default=0, description="Total channel subscriptions")
    date_range: tuple[datetime, datetime] | None = Field(
        default=None, description="Date range of watch history"
    )

    @model_validator(mode="after")
    def calculate_totals(self) -> "TakeoutData":
        """Calculate total counts from the data."""
        # Count unique videos in watch history
        if self.total_videos_watched == 0:  # Only calculate if not explicitly set
            unique_video_ids = {
                entry.video_id for entry in self.watch_history if entry.video_id
            }
            self.total_videos_watched = len(unique_video_ids)

        # Count total playlists
        if self.total_playlists == 0:  # Only calculate if not explicitly set
            self.total_playlists = len(self.playlists)

        # Count total subscriptions
        if self.total_subscriptions == 0:  # Only calculate if not explicitly set
            self.total_subscriptions = len(self.subscriptions)

        return self

    @model_validator(mode="after")
    def calculate_date_range(self) -> "TakeoutData":
        """Calculate date range from watch history."""
        if self.date_range is not None:
            return self

        dates = [entry.watched_at for entry in self.watch_history if entry.watched_at]

        if dates:
            self.date_range = (min(dates), max(dates))
        return self

    def get_unique_video_ids(self) -> set[str]:
        """Get set of all unique video IDs across all data sources."""
        video_ids = set()

        # From watch history
        video_ids.update(
            {entry.video_id for entry in self.watch_history if entry.video_id}
        )

        # From playlists
        for playlist in self.playlists:
            video_ids.update(
                {video.video_id for video in playlist.videos if video.video_id}
            )

        return video_ids

    def get_unique_channel_ids(self) -> set[str]:
        """Get set of all unique channel IDs across all data sources."""
        channel_ids = set()

        # From watch history
        channel_ids.update(
            {entry.channel_id for entry in self.watch_history if entry.channel_id}
        )

        # From subscriptions
        channel_ids.update(
            {sub.channel_id for sub in self.subscriptions if sub.channel_id}
        )

        return channel_ids
