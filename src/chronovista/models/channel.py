"""
Channel models for YouTube channel management.

Defines Pydantic models for channel data with validation and serialization support.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import AvailabilityStatus, LanguageCode
from .youtube_types import ChannelId


class ChannelBase(BaseModel):
    """Base model for channel data."""

    channel_id: ChannelId = Field(..., description="YouTube channel ID (validated)")
    title: str = Field(..., min_length=1, max_length=255, description="Channel title")
    description: str | None = Field(default=None, description="Channel description")
    subscriber_count: int | None = Field(
        default=None, ge=0, description="Number of subscribers"
    )
    video_count: int | None = Field(
        default=None, ge=0, description="Number of videos"
    )
    default_language: LanguageCode | None = Field(
        default=None, description="Default language (BCP-47)"
    )
    country: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Country code (ISO 3166-1)",
    )
    thumbnail_url: str | None = Field(
        default=None, max_length=500, description="Channel thumbnail URL"
    )
    is_subscribed: bool = Field(
        default=False, description="Whether the user is subscribed to this channel"
    )

    # Availability and recovery tracking
    availability_status: AvailabilityStatus = Field(
        default=AvailabilityStatus.AVAILABLE,
        description="Current availability status on YouTube",
    )
    recovered_at: datetime | None = Field(
        default=None, description="When content was recovered"
    )
    recovery_source: str | None = Field(
        default=None, description="Source of recovery information"
    )
    unavailability_first_detected: datetime | None = Field(
        default=None, description="When unavailability was first detected"
    )

    # Channel ID validation now handled by ChannelId custom type

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str | None) -> str | None:
        """Validate country code format."""
        if v is not None:
            country = v.strip().upper()
            if len(country) != 2:
                raise ValueError(
                    "Country code must be exactly 2 characters (ISO 3166-1)"
                )
            return country
        return v

    # Note: Language validation is now handled by LanguageCode enum

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelCreate(ChannelBase):
    """Model for creating channels."""

    pass


class ChannelUpdate(BaseModel):
    """Model for updating channels."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    subscriber_count: int | None = Field(default=None, ge=0)
    video_count: int | None = Field(default=None, ge=0)
    default_language: LanguageCode | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    is_subscribed: bool | None = None
    availability_status: AvailabilityStatus | None = None
    recovered_at: datetime | None = None
    recovery_source: str | None = None
    unavailability_first_detected: datetime | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        """Validate title if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Title cannot be empty")
        return v.strip() if v else v

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str | None) -> str | None:
        """Validate country code format."""
        if v is not None:
            country = v.strip().upper()
            if len(country) != 2:
                raise ValueError(
                    "Country code must be exactly 2 characters (ISO 3166-1)"
                )
            return country
        return v

    # Note: Language validation is now handled by LanguageCode enum

    model_config = ConfigDict(
        validate_assignment=True,
    )


class Channel(ChannelBase):
    """Full channel model with timestamps."""

    created_at: datetime = Field(..., description="When the record was created")
    updated_at: datetime = Field(..., description="When the record was last updated")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class ChannelSearchFilters(BaseModel):
    """Filters for searching channels."""

    title_query: str | None = Field(default=None, description="Search in title")
    description_query: str | None = Field(
        default=None, description="Search in description"
    )
    language_codes: list[LanguageCode] | None = Field(
        default=None, description="Filter by languages"
    )
    countries: list[str] | None = Field(
        default=None, description="Filter by countries"
    )
    min_subscriber_count: int | None = Field(
        default=None, ge=0, description="Minimum subscribers"
    )
    max_subscriber_count: int | None = Field(
        default=None, ge=0, description="Maximum subscribers"
    )
    min_video_count: int | None = Field(
        default=None, ge=0, description="Minimum video count"
    )
    max_video_count: int | None = Field(
        default=None, ge=0, description="Maximum video count"
    )
    has_keywords: bool | None = Field(
        default=None, description="Filter channels with keywords"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelStatistics(BaseModel):
    """Channel statistics summary."""

    total_channels: int = Field(..., description="Total number of channels")
    total_subscribers: int = Field(
        ..., description="Total subscriber count across all channels"
    )
    total_videos: int = Field(..., description="Total video count across all channels")
    avg_subscribers_per_channel: float = Field(
        ..., description="Average subscribers per channel"
    )
    avg_videos_per_channel: float = Field(..., description="Average videos per channel")
    top_countries: list[tuple[str, int]] = Field(
        ..., description="Top countries by channel count"
    )
    top_languages: list[tuple[str, int]] = Field(
        ..., description="Top languages by channel count"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
