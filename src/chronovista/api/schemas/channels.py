"""Channel API response schemas.

This module defines Pydantic schemas for channel list and detail endpoints,
following the established pattern from videos.py with List/Detail separation
and response wrappers.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import PaginationMeta


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
    """

    default_language: Optional[str] = Field(None, description="Default language code")
    country: Optional[str] = Field(None, description="Country code (ISO 3166-1)")
    is_subscribed: bool = Field(False, description="Whether user is subscribed")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


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
