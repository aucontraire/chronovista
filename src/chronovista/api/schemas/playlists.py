"""Playlist API response schemas.

This module defines Pydantic schemas for playlist API endpoints,
including list/detail responses and video position tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

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

    playlist_id: str = Field(
        ..., description="Playlist ID (YouTube, system, or internal)"
    )
    title: str = Field(..., description="Playlist title")
    description: str | None = Field(None, description="Playlist description")
    video_count: int = Field(0, description="Number of videos in playlist")
    privacy_status: str = Field(
        ..., description="Privacy status: public, private, unlisted"
    )
    is_linked: bool = Field(..., description="Whether playlist is linked to YouTube")
    playlist_type: str = Field(
        "regular",
        description="Playlist type: regular, liked, watch_later, history, favorites",
    )

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
                "playlist_type": getattr(data, "playlist_type", "regular"),
            }
        return data


class PlaylistDetail(PlaylistListItem):
    """Full playlist details for single resource response.

    Extends PlaylistListItem with additional fields including
    channel ownership, timestamps, and playlist type.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    default_language: str | None = Field(None, description="Default language code")
    channel_id: str | None = Field(None, description="Owner channel ID")
    published_at: datetime | None = Field(None, description="Playlist creation date")
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
                "created_at": data.created_at,
                "updated_at": data.updated_at,
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
    channel_id: str | None = Field(None, description="Channel ID (24 chars)")
    channel_title: str | None = Field(None, description="Channel name")
    upload_date: datetime = Field(..., description="Video upload date")
    duration: int = Field(..., description="Duration in seconds")
    view_count: int | None = Field(None, description="View count")
    transcript_summary: TranscriptSummary = Field(
        ..., description="Transcript availability summary"
    )

    # Playlist-specific fields
    position: int = Field(..., description="Position in playlist (0-indexed)")
    availability_status: str = Field(
        ...,
        description="Video availability status (included to preserve position integrity)",
    )
    watched: bool = Field(
        ...,
        description=(
            "Whether a watch-history record exists for this video. Derived from "
            "watch history, never from playlist membership."
        ),
    )


class PlaylistListResponse(BaseModel):
    """Response wrapper for playlist list."""

    model_config = ConfigDict(strict=True)

    data: list[PlaylistListItem]
    pagination: PaginationMeta


class PlaylistDetailResponse(BaseModel):
    """Response wrapper for single playlist."""

    model_config = ConfigDict(strict=True)

    data: PlaylistDetail


class HiddenPlaylistItem(PlaylistListItem):
    """A playlist hidden from every other view by ``deleted_flag`` (#149).

    Carries ``hidden_at_approx`` rather than a real deletion timestamp: no
    column records when a playlist was hidden, so this is the row's
    last-modified time. For a hidden playlist that *is* when it was hidden,
    because nothing writes to one afterwards — enrichment selects only live
    rows. The name says "approx" because that is a property of current
    behaviour, not a guarantee, and a consumer must not treat it as an audit
    record.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    hidden_at_approx: datetime = Field(
        ...,
        description=(
            "Row last-modified time, which for a hidden playlist approximates "
            "when it was hidden. Not an audit timestamp."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def derive_is_linked(cls, data: Any) -> Any:
        """Map an ORM row to this schema's fields.

        Written standalone rather than delegating to the parent's validator:
        that attribute is a Pydantic descriptor proxy, and calling it through
        the class is not a supported, type-checkable call even though it
        happens to resolve at runtime. The parent also drops ``updated_at``
        when it builds its dict, so there would be nothing left to read the
        hidden time from afterwards.
        """
        if isinstance(data, dict):
            playlist_id = data.get("playlist_id", "")
            data["is_linked"] = playlist_id.startswith(("PL", "LL", "WL", "HL"))
            return data
        if hasattr(data, "playlist_id"):
            playlist_id = getattr(data, "playlist_id", "")
            return {
                "playlist_id": playlist_id,
                "title": getattr(data, "title", ""),
                "description": getattr(data, "description", None),
                "video_count": getattr(data, "video_count", 0),
                "privacy_status": getattr(data, "privacy_status", "private"),
                "is_linked": playlist_id.startswith(("PL", "LL", "WL", "HL")),
                "playlist_type": getattr(data, "playlist_type", "regular"),
                "hidden_at_approx": getattr(data, "updated_at", None),
            }
        return data


class HiddenPlaylistListResponse(BaseModel):
    """Response wrapper for the hidden-playlist list."""

    model_config = ConfigDict(strict=True)

    data: list[HiddenPlaylistItem]
    total: int = Field(..., description="Number of hidden playlists")


class PlaylistRestoreRequest(BaseModel):
    """Playlists to un-hide.

    ``playlist_ids`` is required and must be non-empty: there is deliberately
    no "restore everything" request shape, because an empty body is exactly
    what an accidental POST sends, and un-hiding the whole library must be an
    explicit act. A caller wanting all of them lists them from
    ``GET /playlists/hidden`` first.
    """

    model_config = ConfigDict(strict=True)

    playlist_ids: list[str] = Field(
        ..., min_length=1, description="Playlist IDs to restore"
    )


class PlaylistRestoreResponse(BaseModel):
    """Outcome of a restore request."""

    model_config = ConfigDict(strict=True)

    restored: int = Field(..., description="Number of playlists actually un-hidden")
    skipped: list[str] = Field(
        default_factory=list,
        description="Requested IDs that were not hidden (already visible or unknown)",
    )


class PlaylistWatchStats(BaseModel):
    """Watched/unwatched breakdown for one playlist (Feature 061).

    The field is named ``playlist_total`` rather than ``total`` on purpose. The
    same response also carries ``pagination.total``, which is the **result
    count** — the number of videos in the current view — and the two differ
    whenever the watched filter is not ``all``. Under ``watched_status=unwatched``
    on a 4,973-video Watch Later, ``playlist_total`` is 4,973 while
    ``pagination.total`` is 2,392. Distinct names make that impossible to
    conflate in code.
    """

    model_config = ConfigDict(strict=True)

    playlist_total: int = Field(
        ..., description="Distinct videos in the playlist under the current filters"
    )
    watched: int = Field(
        ..., description="Of those, distinct videos with a watch-history record"
    )
    unwatched: int = Field(
        ..., description="Of those, distinct videos with no watch-history record"
    )


class PlaylistVideoListResponse(BaseModel):
    """Response wrapper for playlist video list."""

    model_config = ConfigDict(strict=True)

    data: list[PlaylistVideoListItem]
    pagination: PaginationMeta
    stats: PlaylistWatchStats
