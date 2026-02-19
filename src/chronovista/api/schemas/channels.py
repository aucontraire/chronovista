"""Channel API response schemas.

This module defines Pydantic schemas for channel list and detail endpoints,
following the established pattern from videos.py with List/Detail separation
and response wrappers.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import ApiResponse, PaginationMeta


class ChannelListItem(BaseModel):
    """Channel summary for list responses.

    Provides minimal channel information for efficient list rendering.
    Fields are mapped directly from the Channel database model.

    Attributes
    ----------
    channel_id : str
        YouTube channel ID (24 characters).
    title : str
        Channel title.
    description : Optional[str]
        Channel description (may be truncated in list view).
    subscriber_count : Optional[int]
        Number of subscribers.
    video_count : Optional[int]
        Number of videos on the channel.
    thumbnail_url : Optional[str]
        URL to channel thumbnail image.
    custom_url : Optional[str]
        Custom channel URL (e.g., @username). Currently always None
        as this field is not yet persisted in the database.
    availability_status : str
        Channel availability status (available, deleted, terminated, suspended).
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    channel_id: str = Field(..., description="YouTube channel ID (24 chars)")
    title: str = Field(..., description="Channel title")
    description: Optional[str] = Field(None, description="Channel description")
    subscriber_count: Optional[int] = Field(None, description="Subscriber count")
    video_count: Optional[int] = Field(None, description="Number of videos")
    thumbnail_url: Optional[str] = Field(None, description="Channel thumbnail URL")
    custom_url: Optional[str] = Field(
        default=None,
        description="Custom channel URL (e.g., @username). Currently always None.",
    )
    availability_status: str = Field(..., description="Channel availability status")


class ChannelDetail(ChannelListItem):
    """Full channel details for single resource response.

    Extends ChannelListItem with additional metadata fields including
    language, country, subscription status, and timestamps.

    Attributes
    ----------
    default_language : Optional[str]
        Default language code for the channel (BCP-47).
    country : Optional[str]
        Country code (ISO 3166-1 alpha-2).
    is_subscribed : bool
        Whether the user is subscribed to this channel.
    created_at : datetime
        Record creation timestamp.
    updated_at : datetime
        Last update timestamp.
    availability_status : str
        Channel availability status (inherited from ChannelListItem).
    """

    default_language: Optional[str] = Field(None, description="Default language code")
    country: Optional[str] = Field(None, description="Country code (ISO 3166-1)")
    is_subscribed: bool = Field(False, description="Whether user is subscribed")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    recovered_at: Optional[datetime] = Field(None, description="Timestamp when metadata was recovered via Wayback Machine")
    recovery_source: Optional[str] = Field(None, description="Source used for metadata recovery (e.g., wayback_machine)")


class ChannelListResponse(BaseModel):
    """Response wrapper for channel list.

    Contains a list of channel items with pagination metadata.

    Attributes
    ----------
    data : List[ChannelListItem]
        List of channel summary items.
    pagination : PaginationMeta
        Pagination metadata (total, limit, offset, has_more).
    """

    model_config = ConfigDict(strict=True)

    data: List[ChannelListItem]
    pagination: PaginationMeta


class ChannelDetailResponse(BaseModel):
    """Response wrapper for single channel.

    Contains full channel details for a single resource.

    Attributes
    ----------
    data : ChannelDetail
        Full channel details.
    """

    model_config = ConfigDict(strict=True)

    data: ChannelDetail


class ChannelRecoveryResultData(BaseModel):
    """Recovery result data for a single channel recovery attempt.

    Mirrors VideoRecoveryResultData but uses channel_id instead of video_id
    and omits channel sub-recovery fields (since this IS the channel recovery).

    Attributes
    ----------
    channel_id : str
        YouTube channel ID (24 characters, starts with UC).
    success : bool
        Whether the recovery attempt succeeded.
    snapshot_used : Optional[str]
        CDX timestamp of the snapshot used for recovery.
    fields_recovered : List[str]
        Names of fields successfully recovered.
    fields_skipped : List[str]
        Names of fields that were skipped during recovery.
    snapshots_available : int
        Total number of CDX snapshots found.
    snapshots_tried : int
        Number of snapshots attempted before success or exhaustion.
    failure_reason : Optional[str]
        Reason for failure, if success is False.
    duration_seconds : float
        Wall-clock time for the recovery operation.
    """

    model_config = ConfigDict(strict=True)

    channel_id: str
    success: bool
    snapshot_used: Optional[str] = None
    fields_recovered: List[str] = Field(default_factory=list)
    fields_skipped: List[str] = Field(default_factory=list)
    snapshots_available: int = 0
    snapshots_tried: int = 0
    failure_reason: Optional[str] = None
    duration_seconds: float = 0.0


class ChannelRecoveryResponse(ApiResponse[ChannelRecoveryResultData]):
    """Response for channel recovery endpoint."""

    pass
