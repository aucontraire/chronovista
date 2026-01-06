"""
Video tag models.

Defines Pydantic models for video tagging and content analysis with validation
and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .youtube_types import VideoId


class VideoTagBase(BaseModel):
    """Base model for video tags."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    tag: str = Field(..., min_length=1, max_length=500, description="Tag content")
    tag_order: Optional[int] = Field(
        default=None, ge=0, description="Order of tag from YouTube API"
    )

    # Note: video_id validation is now handled by VideoId type

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        """Validate tag content."""
        if not v or not v.strip():
            raise ValueError("Tag cannot be empty")

        tag = v.strip()
        if len(tag) > 500:
            raise ValueError("Tag cannot exceed 500 characters")

        return tag

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoTagCreate(VideoTagBase):
    """Model for creating video tags."""

    pass


class VideoTagUpdate(BaseModel):
    """Model for updating video tags."""

    tag_order: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoTag(VideoTagBase):
    """Full video tag model with timestamps."""

    created_at: datetime = Field(..., description="When the tag was created")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class VideoTagSearchFilters(BaseModel):
    """Filters for searching video tags."""

    video_ids: Optional[List[VideoId]] = Field(
        default=None, description="Filter by video IDs"
    )
    tags: Optional[List[str]] = Field(
        default=None, description="Filter by specific tags"
    )
    tag_pattern: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Search tags by pattern (case-insensitive)",
    )
    min_tag_order: Optional[int] = Field(
        default=None, ge=0, description="Minimum tag order"
    )
    max_tag_order: Optional[int] = Field(
        default=None, ge=0, description="Maximum tag order"
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


class VideoTagStatistics(BaseModel):
    """Video tag statistics."""

    total_tags: int = Field(..., description="Total number of tags")
    unique_tags: int = Field(..., description="Number of unique tags")
    avg_tags_per_video: float = Field(..., description="Average tags per video")
    most_common_tags: List[tuple[str, int]] = Field(
        default_factory=list, description="Most common tags with counts"
    )
    tag_distribution: dict[str, int] = Field(
        default_factory=dict, description="Tag frequency distribution"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
