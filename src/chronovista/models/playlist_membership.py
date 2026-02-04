"""
Playlist membership models for chronovista.

Pydantic models for playlist-video relationships with position tracking
and metadata from Google Takeout data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .youtube_types import PlaylistId, VideoId

from .playlist import Playlist
from .video import Video


class PlaylistMembershipBase(BaseModel):
    """Base playlist membership model with shared fields."""

    playlist_id: PlaylistId = Field(
        ...,
        description="Playlist ID (INT_ internal 36 chars or PL YouTube 30-50 chars)",
    )
    video_id: VideoId = Field(
        ...,
        description="YouTube video ID (11 characters)",
    )
    position: int = Field(
        ..., ge=0, description="Position of video in playlist (0-based)"
    )
    added_at: Optional[datetime] = Field(
        None, description="When video was added to playlist (from takeout data)"
    )


class PlaylistMembershipCreate(PlaylistMembershipBase):
    """Create model for playlist membership."""

    pass


class PlaylistMembershipUpdate(BaseModel):
    """Update model for playlist membership."""

    position: Optional[int] = Field(
        None, ge=0, description="New position of video in playlist"
    )
    added_at: Optional[datetime] = Field(
        None, description="Updated timestamp when video was added"
    )


class PlaylistMembershipRead(PlaylistMembershipBase):
    """Read model for playlist membership with timestamps."""

    created_at: datetime = Field(
        ..., description="When this membership record was created in database"
    )

    model_config = {"from_attributes": True}


class PlaylistMembershipReadWithVideo(PlaylistMembershipRead):
    """Read model for playlist membership with video details."""

    video: Video = Field(..., description="Video details for this playlist membership")


class PlaylistMembershipReadWithPlaylist(PlaylistMembershipRead):
    """Read model for playlist membership with playlist details."""

    playlist: Playlist = Field(..., description="Playlist details for this membership")


# Export all models
__all__ = [
    "PlaylistMembershipBase",
    "PlaylistMembershipCreate",
    "PlaylistMembershipUpdate",
    "PlaylistMembershipRead",
    "PlaylistMembershipReadWithVideo",
    "PlaylistMembershipReadWithPlaylist",
]
