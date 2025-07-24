"""
User video interaction models.

Defines Pydantic models for user-video interactions including watch history
from Google Takeout data with validation and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .youtube_types import UserId, VideoId


class UserVideoBase(BaseModel):
    """Base model for user-video interactions."""

    user_id: UserId = Field(..., description="User identifier (validated)")
    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    watched_at: Optional[datetime] = Field(
        default=None, description="When the video was watched"
    )
    watch_duration: Optional[int] = Field(
        default=None, ge=0, description="Duration watched in seconds"
    )
    completion_percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Percentage of video watched (0-100)",
    )
    rewatch_count: int = Field(default=0, ge=0, description="Number of times rewatched")
    liked: bool = Field(default=False, description="Whether user liked the video")
    disliked: bool = Field(default=False, description="Whether user disliked the video")
    saved_to_playlist: bool = Field(
        default=False, description="Whether saved to playlist"
    )

    # Note: user_id validation is now handled by UserId type
    # Note: video_id validation is now handled by VideoId type

    @field_validator("completion_percentage")
    @classmethod
    def validate_completion_percentage(cls, v: Optional[float]) -> Optional[float]:
        """Validate completion percentage is within valid range."""
        if v is not None and (v < 0.0 or v > 100.0):
            raise ValueError("Completion percentage must be between 0.0 and 100.0")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
    )


class UserVideoCreate(UserVideoBase):
    """Model for creating user-video interactions."""

    pass


class UserVideoUpdate(BaseModel):
    """Model for updating user-video interactions."""

    watched_at: Optional[datetime] = None
    watch_duration: Optional[int] = Field(None, ge=0)
    completion_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    rewatch_count: Optional[int] = Field(None, ge=0)
    liked: Optional[bool] = None
    disliked: Optional[bool] = None
    saved_to_playlist: Optional[bool] = None

    @field_validator("completion_percentage")
    @classmethod
    def validate_completion_percentage(cls, v: Optional[float]) -> Optional[float]:
        """Validate completion percentage if provided."""
        if v is not None and (v < 0.0 or v > 100.0):
            raise ValueError("Completion percentage must be between 0.0 and 100.0")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
    )


class UserVideo(UserVideoBase):
    """Full user-video interaction model with timestamps."""

    created_at: datetime = Field(..., description="When the record was created")
    updated_at: datetime = Field(..., description="When the record was last updated")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class GoogleTakeoutWatchHistoryItem(BaseModel):
    """Model for parsing Google Takeout watch history items."""

    header: str = Field(..., description="Source header (usually 'YouTube')")
    title: str = Field(..., description="Full title from Takeout including action")
    titleUrl: str = Field(..., description="YouTube URL for the video")
    subtitles: List[dict] = Field(default_factory=list, description="Channel info")
    time: str = Field(..., description="ISO timestamp string from Takeout")
    products: List[str] = Field(default_factory=list, description="Google products")
    activityControls: List[str] = Field(
        default_factory=list, description="Activity controls"
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

    @field_validator("titleUrl")
    @classmethod
    def validate_title_url(cls, v: str) -> str:
        """Validate URL is a valid YouTube URL."""
        if not v:
            raise ValueError("Title URL cannot be empty")

        if "youtube.com" not in v and "youtu.be" not in v:
            raise ValueError("URL must be a YouTube URL")

        return v

    def extract_video_id(self) -> Optional[str]:
        """
        Extract video ID from YouTube URL.

        Returns
        -------
        Optional[str]
            Video ID if extractable, None otherwise
        """
        try:
            parsed_url = urlparse(self.titleUrl)

            # Handle youtube.com/watch?v= URLs
            if "youtube.com" in parsed_url.netloc and parsed_url.path == "/watch":
                query_params = parse_qs(parsed_url.query)
                return query_params.get("v", [None])[0]

            # Handle youtu.be/ URLs
            if "youtu.be" in parsed_url.netloc:
                return parsed_url.path.lstrip("/")

            # Handle youtube.com/embed/ URLs
            if "youtube.com" in parsed_url.netloc and parsed_url.path.startswith(
                "/embed/"
            ):
                return parsed_url.path.split("/embed/")[1]

            return None
        except Exception:
            return None

    def extract_channel_info(self) -> Optional[dict]:
        """
        Extract channel information from subtitles.

        Returns
        -------
        Optional[dict]
            Channel info with name and URL if available
        """
        if not self.subtitles:
            return None

        channel = self.subtitles[0]  # First subtitle is usually the channel
        return {
            "name": channel.get("name"),
            "url": channel.get("url"),
        }

    def extract_channel_id(self) -> Optional[str]:
        """
        Extract channel ID from channel URL.

        Returns
        -------
        Optional[str]
            Channel ID if extractable, None otherwise
        """
        channel_info = self.extract_channel_info()
        if not channel_info or not channel_info.get("url"):
            return None

        try:
            parsed_url = urlparse(channel_info["url"])
            if "youtube.com" in parsed_url.netloc and parsed_url.path.startswith(
                "/channel/"
            ):
                channel_id = parsed_url.path.split("/channel/")[1]
                return channel_id if channel_id else None
            return None
        except Exception:
            return None

    def get_watch_action(self) -> str:
        """
        Extract the action type from the title.

        Returns
        -------
        str
            Action type: 'watched', 'viewed', 'visited', etc.
        """
        title_lower = self.title.lower()
        if title_lower.startswith("watched"):
            return "watched"
        elif title_lower.startswith("viewed"):
            return "viewed"
        elif title_lower.startswith("visited"):
            return "visited"
        else:
            return "unknown"

    def get_video_title(self) -> str:
        """
        Extract the actual video title (removing action prefix).

        Returns
        -------
        str
            Clean video title
        """
        # Remove action prefix like "Watched " or "Viewed "
        title = self.title
        for prefix in ["Watched ", "Viewed ", "Visited "]:
            if title.startswith(prefix):
                title = title[len(prefix) :]
                break
        return title.strip()

    def to_user_video_create(self, user_id: UserId) -> Optional[UserVideoCreate]:
        """
        Convert to UserVideoCreate model.

        Parameters
        ----------
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        Optional[UserVideoCreate]
            UserVideoCreate instance if video ID is extractable
        """
        video_id = self.extract_video_id()
        if not video_id:
            return None

        # Parse timestamp
        try:
            watched_at = datetime.fromisoformat(self.time.replace("Z", "+00:00"))
        except ValueError:
            watched_at = None

        return UserVideoCreate(
            user_id=user_id,
            video_id=video_id,
            watched_at=watched_at,
            # Note: Google Takeout doesn't provide duration/completion data
            watch_duration=None,
            completion_percentage=None,
            rewatch_count=0,  # Default, will be incremented if video appears multiple times
        )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class UserVideoSearchFilters(BaseModel):
    """Filters for searching user video interactions."""

    user_ids: Optional[List[UserId]] = Field(
        default=None, description="Filter by validated user IDs"
    )
    video_ids: Optional[List[VideoId]] = Field(
        default=None, description="Filter by video IDs"
    )
    watched_after: Optional[datetime] = Field(
        default=None, description="Filter by watch date"
    )
    watched_before: Optional[datetime] = Field(
        default=None, description="Filter by watch date"
    )
    min_watch_duration: Optional[int] = Field(
        default=None, ge=0, description="Minimum watch duration"
    )
    min_completion_percentage: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description="Minimum completion"
    )
    liked_only: Optional[bool] = Field(
        default=None, description="Filter for liked videos only"
    )
    disliked_only: Optional[bool] = Field(
        default=None, description="Filter for disliked videos only"
    )
    playlist_saved_only: Optional[bool] = Field(
        default=None, description="Filter for playlist-saved videos"
    )
    min_rewatch_count: Optional[int] = Field(
        default=None, ge=0, description="Minimum rewatch count"
    )
    created_after: Optional[datetime] = Field(
        default=None, description="Filter by creation date"
    )
    created_before: Optional[datetime] = Field(
        default=None, description="Filter by creation date"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class UserVideoStatistics(BaseModel):
    """User video interaction statistics."""

    total_videos: int = Field(..., description="Total number of videos watched")
    total_watch_time: int = Field(..., description="Total watch time in seconds")
    average_completion: float = Field(..., description="Average completion percentage")
    liked_count: int = Field(..., description="Number of liked videos")
    disliked_count: int = Field(..., description="Number of disliked videos")
    playlist_saved_count: int = Field(
        ..., description="Number of videos saved to playlists"
    )
    rewatch_count: int = Field(..., description="Number of rewatched videos")
    unique_videos: int = Field(..., description="Number of unique videos")
    most_watched_date: Optional[datetime] = Field(
        default=None, description="Date with most activity"
    )
    watch_streak_days: int = Field(
        default=0, description="Current consecutive days watching"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
