"""
Video localization models.

Defines Pydantic models for multi-language video content with validation
and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LanguageCode
from .youtube_types import VideoId


class VideoLocalizationBase(BaseModel):
    """Base model for video localizations."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    language_code: LanguageCode = Field(..., description="BCP-47 language code")
    localized_title: str = Field(..., min_length=1, description="Localized video title")
    localized_description: Optional[str] = Field(
        default=None, description="Localized video description"
    )

    # Note: video_id validation is now handled by VideoId type
    # Note: Language validation is now handled by LanguageCode enum

    @field_validator("localized_title")
    @classmethod
    def validate_localized_title(cls, v: str) -> str:
        """Validate localized title."""
        if not v or not v.strip():
            raise ValueError("Localized title cannot be empty")

        title = v.strip()
        if len(title) > 1000:  # Reasonable limit for video titles
            raise ValueError("Localized title cannot exceed 1000 characters")

        return title

    @field_validator("localized_description")
    @classmethod
    def validate_localized_description(cls, v: Optional[str]) -> Optional[str]:
        """Validate localized description."""
        if v is None:
            return v

        description = v.strip() if v else ""
        if not description:
            return None

        if len(description) > 50000:  # YouTube's description limit
            raise ValueError("Localized description cannot exceed 50,000 characters")

        return description

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoLocalizationCreate(VideoLocalizationBase):
    """Model for creating video localizations."""

    pass


class VideoLocalizationUpdate(BaseModel):
    """Model for updating video localizations."""

    localized_title: Optional[str] = Field(None, min_length=1)
    localized_description: Optional[str] = None

    @field_validator("localized_title")
    @classmethod
    def validate_localized_title(cls, v: Optional[str]) -> Optional[str]:
        """Validate localized title."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Localized title cannot be empty")

        title = v.strip()
        if len(title) > 1000:
            raise ValueError("Localized title cannot exceed 1000 characters")

        return title

    @field_validator("localized_description")
    @classmethod
    def validate_localized_description(cls, v: Optional[str]) -> Optional[str]:
        """Validate localized description."""
        if v is None:
            return v

        description = v.strip() if v else ""
        if not description:
            return None

        if len(description) > 50000:
            raise ValueError("Localized description cannot exceed 50,000 characters")

        return description

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoLocalization(VideoLocalizationBase):
    """Full video localization model with timestamps."""

    created_at: datetime = Field(..., description="When the localization was created")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class VideoLocalizationSearchFilters(BaseModel):
    """Filters for searching video localizations."""

    video_ids: Optional[List[VideoId]] = Field(
        default=None, description="Filter by video IDs"
    )
    language_codes: Optional[List[str]] = Field(
        default=None, description="Filter by language codes"
    )
    title_query: Optional[str] = Field(
        default=None, min_length=1, description="Search in localized titles"
    )
    description_query: Optional[str] = Field(
        default=None, min_length=1, description="Search in localized descriptions"
    )
    has_description: Optional[bool] = Field(
        default=None, description="Filter by presence of localized description"
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


class VideoLocalizationStatistics(BaseModel):
    """Video localization statistics."""

    total_localizations: int = Field(..., description="Total number of localizations")
    unique_videos: int = Field(..., description="Number of videos with localizations")
    unique_languages: int = Field(..., description="Number of supported languages")
    avg_localizations_per_video: float = Field(
        ..., description="Average localizations per video"
    )
    top_languages: List[tuple[str, int]] = Field(
        default_factory=list, description="Most common languages with counts"
    )
    localization_coverage: dict[str, int] = Field(
        default_factory=dict, description="Language coverage distribution"
    )
    videos_with_descriptions: int = Field(
        ..., description="Videos with localized descriptions"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
