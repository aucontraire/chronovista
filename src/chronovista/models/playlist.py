"""
Playlist models.

Defines Pydantic models for enhanced playlists with multi-language support,
validation and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LanguageCode, PlaylistType, PrivacyStatus
from .youtube_types import ChannelId, PlaylistId


class PlaylistBase(BaseModel):
    """Base model for playlists."""

    playlist_id: PlaylistId = Field(
        ...,
        description="Playlist ID - either YouTube ID (PL prefix, LL, WL, HL) or internal (int_ prefix)",
    )
    title: str = Field(..., min_length=1, max_length=255, description="Playlist title")
    description: str | None = Field(default=None, description="Playlist description")
    default_language: LanguageCode | None = Field(
        default=None, description="BCP-47 language code"
    )
    privacy_status: PrivacyStatus = Field(
        default=PrivacyStatus.PRIVATE, description="Playlist privacy setting"
    )
    channel_id: ChannelId | None = Field(
        default=None,
        description="Channel ID that owns the playlist. NULL for user playlists from Takeout until linked via OAuth.",
    )
    video_count: int = Field(
        default=0, ge=0, description="Number of videos in playlist"
    )
    published_at: datetime | None = Field(
        default=None, description="When the playlist was created on YouTube"
    )
    deleted_flag: bool = Field(
        default=False, description="Whether the playlist is deleted/private"
    )

    # Playlist type (for system playlist handling)
    playlist_type: PlaylistType = Field(
        default=PlaylistType.REGULAR,
        description="Type of playlist: regular, liked, watch_later, history, favorites",
    )

    # Playlist ID validation now handled by PlaylistId custom type

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate playlist title."""
        if not v or not v.strip():
            raise ValueError("Playlist title cannot be empty")

        title = v.strip()
        if len(title) > 255:
            raise ValueError("Playlist title cannot exceed 255 characters")

        return title

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        """Validate playlist description."""
        if v is None:
            return v

        description = v.strip() if v else ""
        if not description:
            return None

        if len(description) > 50000:  # YouTube's description limit
            raise ValueError("Playlist description cannot exceed 50,000 characters")

        return description

    # Note: Language validation is now handled by LanguageCode enum

    # Channel ID validation now handled by ChannelId custom type

    model_config = ConfigDict(
        validate_assignment=True,
    )


class PlaylistCreate(PlaylistBase):
    """Model for creating playlists."""

    pass


class PlaylistUpdate(BaseModel):
    """Model for updating playlists."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    default_language: LanguageCode | None = None
    privacy_status: PrivacyStatus | None = None
    channel_id: ChannelId | None = Field(
        default=None,
        description="Channel ID to link playlist to after OAuth authentication",
    )
    video_count: int | None = Field(None, ge=0)
    published_at: datetime | None = None
    deleted_flag: bool | None = None

    # Playlist type (for system playlist handling)
    playlist_type: PlaylistType | None = Field(
        default=None,
        description="Type of playlist: regular, liked, watch_later, history, favorites",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        """Validate playlist title."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Playlist title cannot be empty")

        title = v.strip()
        if len(title) > 255:
            raise ValueError("Playlist title cannot exceed 255 characters")

        return title

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        """Validate playlist description."""
        if v is None:
            return v

        description = v.strip() if v else ""
        if not description:
            return None

        if len(description) > 50000:
            raise ValueError("Playlist description cannot exceed 50,000 characters")

        return description

    # Note: Language validation is now handled by LanguageCode enum

    model_config = ConfigDict(
        validate_assignment=True,
    )


class Playlist(PlaylistBase):
    """Full playlist model with timestamps."""

    created_at: datetime = Field(..., description="When the playlist was created")
    updated_at: datetime = Field(..., description="When the playlist was last updated")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class PlaylistSearchFilters(BaseModel):
    """Filters for searching playlists."""

    playlist_ids: list[PlaylistId] | None = Field(
        default=None, description="Filter by specific playlist IDs"
    )
    channel_ids: list[ChannelId] | None = Field(
        default=None, description="Filter by channel IDs"
    )
    title_query: str | None = Field(
        default=None, min_length=1, description="Search in playlist titles"
    )
    description_query: str | None = Field(
        default=None, min_length=1, description="Search in playlist descriptions"
    )
    language_codes: list[LanguageCode] | None = Field(
        default=None, description="Filter by language codes"
    )
    privacy_statuses: list[PrivacyStatus] | None = Field(
        default=None, description="Filter by privacy status"
    )
    min_video_count: int | None = Field(
        default=None, ge=0, description="Minimum number of videos"
    )
    max_video_count: int | None = Field(
        default=None, ge=0, description="Maximum number of videos"
    )
    has_description: bool | None = Field(
        default=None, description="Filter by presence of description"
    )
    created_after: datetime | None = Field(
        default=None, description="Filter by creation date"
    )
    created_before: datetime | None = Field(
        default=None, description="Filter by creation date"
    )
    updated_after: datetime | None = Field(
        default=None, description="Filter by update date"
    )
    updated_before: datetime | None = Field(
        default=None, description="Filter by update date"
    )
    linked_status: Literal["linked", "unlinked", "all"] | None = Field(
        default="all",
        description="Filter by YouTube ID link status",
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class PlaylistStatistics(BaseModel):
    """Playlist statistics."""

    total_playlists: int = Field(..., description="Total number of playlists")
    total_videos: int = Field(..., description="Total videos across all playlists")
    avg_videos_per_playlist: float = Field(
        ..., description="Average videos per playlist"
    )
    unique_channels: int = Field(..., description="Number of channels with playlists")
    privacy_distribution: dict[PrivacyStatus, int] = Field(
        default_factory=dict, description="Distribution by privacy status"
    )
    language_distribution: dict[str, int] = Field(
        default_factory=dict, description="Distribution by language"
    )
    top_channels_by_playlists: list[tuple[str, int]] = Field(
        default_factory=list, description="Channels with most playlists"
    )
    playlist_size_distribution: dict[str, int] = Field(
        default_factory=dict, description="Distribution by playlist size ranges"
    )
    playlists_with_descriptions: int = Field(
        ..., description="Playlists with descriptions"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class PlaylistAnalytics(BaseModel):
    """Advanced playlist analytics."""

    creation_trends: dict[str, list[int]] = Field(
        default_factory=dict, description="Playlist creation trends over time"
    )
    content_analysis: dict[str, Any] = Field(
        default_factory=dict, description="Content analysis results"
    )
    engagement_metrics: dict[str, float] = Field(
        default_factory=dict, description="Playlist engagement metrics"
    )
    similarity_clusters: list[dict[str, Any]] = Field(
        default_factory=list, description="Similar playlists clustered together"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
