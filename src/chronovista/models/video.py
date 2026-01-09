"""
Video models for YouTube video management.

Defines Pydantic models for video data with multi-language support,
content restrictions, and engagement metrics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LanguageCode
from .youtube_types import ChannelId, VideoId


class VideoBase(BaseModel):
    """Base model for video data."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    channel_id: ChannelId = Field(
        ..., description="Channel ID (foreign key, validated)"
    )
    title: str = Field(..., min_length=1, description="Video title")
    description: Optional[str] = Field(default=None, description="Video description")
    upload_date: datetime = Field(..., description="Video upload date and time")
    duration: int = Field(..., ge=0, description="Video duration in seconds")

    # Content restrictions
    made_for_kids: bool = Field(
        default=False, description="Whether video is made for kids"
    )
    self_declared_made_for_kids: bool = Field(
        default=False, description="Self-declared made for kids"
    )

    # Language support
    default_language: Optional[LanguageCode] = Field(
        default=None, description="Default language (BCP-47)"
    )
    default_audio_language: Optional[LanguageCode] = Field(
        default=None, description="Default audio language (BCP-47)"
    )
    available_languages: Optional[Dict[str, Any]] = Field(
        default=None, description="Available languages data"
    )

    # Regional and content restrictions
    region_restriction: Optional[Dict[str, Any]] = Field(
        default=None, description="Regional restrictions"
    )
    content_rating: Optional[Dict[str, Any]] = Field(
        default=None, description="Content rating information"
    )

    # Category
    category_id: Optional[str] = Field(
        default=None,
        max_length=10,
        description="YouTube category ID (numeric string)",
    )

    # Engagement metrics
    like_count: Optional[int] = Field(default=None, ge=0, description="Number of likes")
    view_count: Optional[int] = Field(default=None, ge=0, description="Number of views")
    comment_count: Optional[int] = Field(
        default=None, ge=0, description="Number of comments"
    )

    # Status tracking
    deleted_flag: bool = Field(
        default=False, description="Whether video is marked as deleted"
    )

    @field_validator("video_id")
    @classmethod
    def validate_video_id(cls, v: str) -> str:
        """Validate video ID format."""
        if not v or not v.strip():
            raise ValueError("Video ID cannot be empty")

        video_id = v.strip()
        if len(video_id) < 1 or len(video_id) > 20:
            raise ValueError("Video ID must be between 1-20 characters")

        return video_id

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        """Validate channel ID format."""
        if not v or not v.strip():
            raise ValueError("Channel ID cannot be empty")

        channel_id = v.strip()
        if len(channel_id) < 1 or len(channel_id) > 24:
            raise ValueError("Channel ID must be between 1-24 characters")

        return channel_id

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

    # Note: Language validation is now handled by LanguageCode enum

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        """Validate duration is positive."""
        if v < 0:
            raise ValueError("Duration must be non-negative")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoCreate(VideoBase):
    """Model for creating videos."""

    pass


class VideoUpdate(BaseModel):
    """Model for updating videos."""

    title: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    duration: Optional[int] = Field(default=None, ge=0)
    made_for_kids: Optional[bool] = None
    self_declared_made_for_kids: Optional[bool] = None
    default_language: Optional[LanguageCode] = None
    default_audio_language: Optional[LanguageCode] = None
    available_languages: Optional[Dict[str, Any]] = None
    region_restriction: Optional[Dict[str, Any]] = None
    content_rating: Optional[Dict[str, Any]] = None
    category_id: Optional[str] = Field(default=None, max_length=10)
    like_count: Optional[int] = Field(default=None, ge=0)
    view_count: Optional[int] = Field(default=None, ge=0)
    comment_count: Optional[int] = Field(default=None, ge=0)
    deleted_flag: Optional[bool] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        """Validate title if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Title cannot be empty")
        return v.strip() if v else v

    # Note: Language validation is now handled by LanguageCode enum

    model_config = ConfigDict(
        validate_assignment=True,
    )


class Video(VideoBase):
    """Full video model with timestamps."""

    created_at: datetime = Field(..., description="When the record was created")
    updated_at: datetime = Field(..., description="When the record was last updated")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class VideoSearchFilters(BaseModel):
    """Filters for searching videos."""

    channel_ids: Optional[List[ChannelId]] = Field(
        default=None, description="Filter by channel IDs"
    )
    title_query: Optional[str] = Field(default=None, description="Search in title")
    description_query: Optional[str] = Field(
        default=None, description="Search in description"
    )
    language_codes: Optional[List[LanguageCode]] = Field(
        default=None, description="Filter by languages"
    )
    upload_after: Optional[datetime] = Field(
        default=None, description="Videos uploaded after date"
    )
    upload_before: Optional[datetime] = Field(
        default=None, description="Videos uploaded before date"
    )
    min_duration: Optional[int] = Field(
        default=None, ge=0, description="Minimum duration in seconds"
    )
    max_duration: Optional[int] = Field(
        default=None, ge=0, description="Maximum duration in seconds"
    )
    min_view_count: Optional[int] = Field(
        default=None, ge=0, description="Minimum view count"
    )
    max_view_count: Optional[int] = Field(
        default=None, ge=0, description="Maximum view count"
    )
    min_like_count: Optional[int] = Field(
        default=None, ge=0, description="Minimum like count"
    )
    kids_friendly_only: Optional[bool] = Field(
        default=None, description="Filter for kids-friendly content"
    )
    exclude_deleted: bool = Field(default=True, description="Exclude deleted videos")
    has_transcripts: Optional[bool] = Field(
        default=None, description="Filter videos with transcripts"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoStatistics(BaseModel):
    """Video statistics summary."""

    total_videos: int = Field(..., description="Total number of videos")
    total_duration: int = Field(..., description="Total duration in seconds")
    avg_duration: float = Field(..., description="Average duration in seconds")
    total_views: int = Field(..., description="Total view count across all videos")
    total_likes: int = Field(..., description="Total like count across all videos")
    total_comments: int = Field(
        ..., description="Total comment count across all videos"
    )
    avg_views_per_video: float = Field(..., description="Average views per video")
    avg_likes_per_video: float = Field(..., description="Average likes per video")
    deleted_video_count: int = Field(..., description="Number of deleted videos")
    kids_friendly_count: int = Field(..., description="Number of kids-friendly videos")
    top_languages: List[tuple[str, int]] = Field(
        ..., description="Top languages by video count"
    )
    upload_trend: Dict[str, int] = Field(..., description="Upload counts by month/year")

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoWithChannel(Video):
    """Video model with channel information included."""

    channel_title: Optional[str] = Field(default=None, description="Channel title")
    channel_subscriber_count: Optional[int] = Field(
        default=None, description="Channel subscriber count"
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
