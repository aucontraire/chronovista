"""
Recovery Models for Historical Takeout Data

Pydantic models for recovering metadata from historical Google Takeout exports.
These models support the gap-fill functionality that enriches placeholder videos
with real metadata from historical takeout data.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class HistoricalTakeout(BaseModel):
    """
    Represents a discovered historical takeout directory.

    Historical takeouts are identified by directory naming pattern:
    'YouTube and YouTube Music YYYY-MM-DD'
    """

    path: Path = Field(..., description="Full path to the takeout directory")
    export_date: datetime = Field(
        ..., description="Export date parsed from directory name"
    )
    has_watch_history: bool = Field(
        default=False, description="Whether watch-history.json exists"
    )
    has_playlists: bool = Field(default=False, description="Whether playlists directory exists")
    has_subscriptions: bool = Field(
        default=False, description="Whether subscriptions.csv exists"
    )


class RecoveredVideoMetadata(BaseModel):
    """
    Metadata recovered for a single video from historical takeout.

    Contains the video information extracted from watch-history.json
    in a historical takeout export.
    """

    video_id: str = Field(..., description="YouTube video ID")
    title: str = Field(..., description="Video title from historical takeout")
    channel_name: Optional[str] = Field(default=None, description="Channel name from takeout")
    channel_id: Optional[str] = Field(default=None, description="Channel ID if available")
    channel_url: Optional[str] = Field(default=None, description="Channel URL from takeout")
    watched_at: Optional[datetime] = Field(default=None, description="When the video was watched")
    source_takeout: Path = Field(..., description="Path to source takeout directory")
    source_date: datetime = Field(
        ..., description="Export date of source takeout"
    )


class RecoveredChannelMetadata(BaseModel):
    """
    Metadata recovered for a channel from historical takeout.

    Contains channel information extracted from watch-history.json
    entries in historical takeout exports.
    """

    channel_id: str = Field(..., description="YouTube channel ID")
    channel_name: str = Field(..., description="Channel name from takeout")
    channel_url: Optional[str] = Field(default=None, description="Channel URL from takeout")
    source_takeout: Path = Field(..., description="Path to source takeout directory")
    source_date: datetime = Field(
        ..., description="Export date of source takeout"
    )
    video_count: int = Field(
        default=0, description="Number of videos from this channel in takeout"
    )


class RecoveryCandidate(BaseModel):
    """
    A video in the database that is a candidate for recovery.

    Identifies placeholder videos that may have real metadata
    available in historical takeout exports.
    """

    video_id: str = Field(..., description="YouTube video ID")
    current_title: str = Field(
        ..., description="Current title in database (may be placeholder)"
    )
    is_placeholder: bool = Field(
        default=False, description="Whether current title is a placeholder"
    )
    channel_id: Optional[str] = Field(default=None, description="Current channel ID if known")
    channel_is_placeholder: bool = Field(
        default=False, description="Whether channel is a placeholder"
    )


class VideoRecoveryAction(BaseModel):
    """
    Represents a recovery action for a video.

    Describes what metadata will be updated for a video from
    historical takeout data.
    """

    video_id: str = Field(..., description="YouTube video ID")
    old_title: str = Field(..., description="Current placeholder title")
    new_title: str = Field(..., description="Recovered actual title")
    old_channel_id: Optional[str] = Field(default=None, description="Current channel ID")
    new_channel_id: Optional[str] = Field(default=None, description="Recovered channel ID")
    channel_name: Optional[str] = Field(default=None, description="Recovered channel name")
    source_date: datetime = Field(
        ..., description="Date of source takeout"
    )
    action_type: str = Field(
        default="update_title", description="Type of action: update_title, update_channel, both"
    )


class ChannelRecoveryAction(BaseModel):
    """
    Represents a recovery action for a channel.

    Describes a channel that needs to be created or updated
    based on historical takeout data.
    """

    channel_id: str = Field(..., description="YouTube channel ID")
    channel_name: str = Field(..., description="Channel name from takeout")
    channel_url: Optional[str] = Field(default=None, description="Channel URL from takeout")
    action_type: str = Field(
        default="create", description="Type of action: create, update_name"
    )
    source_date: datetime = Field(
        ..., description="Date of source takeout"
    )


class RecoveryResult(BaseModel):
    """
    Result of a recovery operation.

    Contains statistics and details about what was recovered
    from historical takeout data.
    """

    # Summary statistics
    videos_recovered: int = Field(default=0, description="Number of videos with recovered metadata")
    videos_still_missing: int = Field(
        default=0, description="Number of videos still without metadata"
    )
    channels_created: int = Field(
        default=0, description="Number of new channels created"
    )
    channels_updated: int = Field(
        default=0, description="Number of channels with updated names"
    )

    # Historical takeout info
    takeouts_scanned: int = Field(
        default=0, description="Number of historical takeouts scanned"
    )
    oldest_takeout_date: Optional[datetime] = Field(
        default=None, description="Date of oldest takeout found"
    )
    newest_takeout_date: Optional[datetime] = Field(
        default=None, description="Date of newest takeout found"
    )

    # Detailed actions (for verbose output or dry-run)
    video_actions: List[VideoRecoveryAction] = Field(
        default_factory=list, description="List of video recovery actions"
    )
    channel_actions: List[ChannelRecoveryAction] = Field(
        default_factory=list, description="List of channel recovery actions"
    )
    videos_not_recovered: List[str] = Field(
        default_factory=list, description="Video IDs that could not be recovered"
    )

    # Processing metadata
    dry_run: bool = Field(default=False, description="Whether this was a dry run")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When recovery started",
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="When recovery completed"
    )
    errors: List[str] = Field(
        default_factory=list, description="Any errors encountered during recovery"
    )

    def mark_complete(self) -> None:
        """Mark the recovery operation as complete."""
        self.completed_at = datetime.now(timezone.utc)

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)


class RecoveryOptions(BaseModel):
    """
    Options for controlling the recovery process.
    """

    dry_run: bool = Field(
        default=False, description="Preview changes without applying them"
    )
    verbose: bool = Field(
        default=False, description="Show detailed progress for each video"
    )
    process_oldest_first: bool = Field(
        default=False,
        description="Process oldest takeouts first (allows newer to overwrite)",
    )
    update_channels: bool = Field(
        default=True, description="Create/update channels from historical data"
    )
    batch_size: int = Field(
        default=100, description="Number of videos to process in each batch"
    )


# Constants for placeholder detection
VIDEO_PLACEHOLDER_PREFIX = "[Placeholder] Video "
CHANNEL_PLACEHOLDER_PREFIX = "[Placeholder]"
UNKNOWN_CHANNEL_PREFIX = "[Unknown"


def is_placeholder_video_title(title: str) -> bool:
    """
    Check if a video title is a placeholder.

    Parameters
    ----------
    title : str
        The video title to check

    Returns
    -------
    bool
        True if the title is a placeholder pattern
    """
    return title.startswith(VIDEO_PLACEHOLDER_PREFIX)


def is_placeholder_channel_name(name: str) -> bool:
    """
    Check if a channel name is a placeholder.

    Parameters
    ----------
    name : str
        The channel name to check

    Returns
    -------
    bool
        True if the name is a placeholder pattern
    """
    return name.startswith(CHANNEL_PLACEHOLDER_PREFIX) or name.startswith(
        UNKNOWN_CHANNEL_PREFIX
    )


def extract_video_id_from_placeholder(title: str) -> Optional[str]:
    """
    Extract video ID from a placeholder title.

    Parameters
    ----------
    title : str
        The placeholder title (e.g., "[Placeholder] Video ABC123")

    Returns
    -------
    Optional[str]
        The extracted video ID, or None if not a placeholder
    """
    if title.startswith(VIDEO_PLACEHOLDER_PREFIX):
        return title[len(VIDEO_PLACEHOLDER_PREFIX) :].strip()
    return None
