"""Playlist API response schemas.

This module defines Pydantic schemas for playlist API endpoints,
including list/detail responses and video position tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from chronovista.api.schemas.responses import PaginationMeta
from chronovista.api.schemas.videos import TranscriptSummary


class PlaylistListItem(BaseModel):
    """Playlist summary for list responses.

    The is_linked field is derived at runtime from the playlist_id prefix:
    - True if ID starts with PL, LL, WL, or HL (YouTube-linked)
    - False if ID starts with int_ (internal/unlinked)
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    playlist_id: str = Field(..., description="Playlist ID (YouTube, system, or internal)")
    title: str = Field(..., description="Playlist title")
    description: Optional[str] = Field(None, description="Playlist description")
    video_count: int = Field(0, description="Number of videos in playlist")
    privacy_status: str = Field(..., description="Privacy status: public, private, unlisted")
    is_linked: bool = Field(..., description="Whether playlist is linked to YouTube")

    @model_validator(mode="before")
    @classmethod
    def derive_is_linked(cls, data: Any) -> Any:
        """Derive is_linked from playlist_id prefix.

        Parameters
        ----------
        data : Any
            Input data (dict or ORM model).

        Returns
        -------
        Any
            Data with is_linked field populated.
        """
        if isinstance(data, dict):
            playlist_id = data.get("playlist_id", "")
            data["is_linked"] = playlist_id.startswith(("PL", "LL", "WL", "HL"))
        elif hasattr(data, "playlist_id"):
            # ORM model - convert to dict with is_linked
            playlist_id = getattr(data, "playlist_id", "")
            return {
                "playlist_id": playlist_id,
                "title": getattr(data, "title", ""),
                "description": getattr(data, "description", None),
                "video_count": getattr(data, "video_count", 0),
                "privacy_status": getattr(data, "privacy_status", "private"),
                "is_linked": playlist_id.startswith(("PL", "LL", "WL", "HL")),
            }
        return data


class PlaylistDetail(PlaylistListItem):
    """Full playlist details for single resource response.

    Extends PlaylistListItem with additional fields including
    channel ownership, timestamps, and playlist type.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    default_language: Optional[str] = Field(None, description="Default language code")
    channel_id: Optional[str] = Field(None, description="Owner channel ID")
    published_at: Optional[datetime] = Field(None, description="Playlist creation date")
    deleted_flag: bool = Field(False, description="Whether playlist is marked deleted")
    playlist_type: str = Field("regular", description="Playlist type")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    @model_validator(mode="before")
    @classmethod
    def derive_is_linked_detail(cls, data: Any) -> Any:
        """Derive is_linked from playlist_id prefix for detail view.

        Parameters
        ----------
        data : Any
            Input data (dict or ORM model).

        Returns
        -------
        Any
            Data with is_linked field populated.
        """
        if isinstance(data, dict):
            playlist_id = data.get("playlist_id", "")
            data["is_linked"] = playlist_id.startswith(("PL", "LL", "WL", "HL"))
        elif hasattr(data, "playlist_id"):
            # ORM model - convert to dict with all fields
            playlist_id = getattr(data, "playlist_id", "")
            return {
                "playlist_id": playlist_id,
                "title": getattr(data, "title", ""),
                "description": getattr(data, "description", None),
                "video_count": getattr(data, "video_count", 0),
                "privacy_status": getattr(data, "privacy_status", "private"),
                "is_linked": playlist_id.startswith(("PL", "LL", "WL", "HL")),
                "default_language": getattr(data, "default_language", None),
                "channel_id": getattr(data, "channel_id", None),
                "published_at": getattr(data, "published_at", None),
                "deleted_flag": getattr(data, "deleted_flag", False),
                "playlist_type": getattr(data, "playlist_type", "regular"),
                "created_at": getattr(data, "created_at"),
                "updated_at": getattr(data, "updated_at"),
            }
        return data


class PlaylistVideoListItem(BaseModel):
    """Video item in playlist context with position.

    Extends video information with playlist-specific position
    and includes availability_status to preserve position integrity.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    # Video fields (matching VideoListItem structure)
    video_id: str = Field(..., description="YouTube video ID (11 chars)")
    title: str = Field(..., description="Video title")
    channel_id: Optional[str] = Field(None, description="Channel ID (24 chars)")
    channel_title: Optional[str] = Field(None, description="Channel name")
    upload_date: datetime = Field(..., description="Video upload date")
    duration: int = Field(..., description="Duration in seconds")
    view_count: Optional[int] = Field(None, description="View count")
    transcript_summary: TranscriptSummary = Field(
        ..., description="Transcript availability summary"
    )

    # Playlist-specific fields
    position: int = Field(..., description="Position in playlist (0-indexed)")
    availability_status: str = Field(
        ...,
        description="Video availability status (included to preserve position integrity)",
    )


class PlaylistListResponse(BaseModel):
    """Response wrapper for playlist list."""

    model_config = ConfigDict(strict=True)

    data: List[PlaylistListItem]
    pagination: PaginationMeta


class PlaylistDetailResponse(BaseModel):
    """Response wrapper for single playlist."""

    model_config = ConfigDict(strict=True)

    data: PlaylistDetail


class PlaylistVideoListResponse(BaseModel):
    """Response wrapper for playlist video list."""

    model_config = ConfigDict(strict=True)

    data: List[PlaylistVideoListItem]
    pagination: PaginationMeta
