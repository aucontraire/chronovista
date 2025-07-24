"""
Channel keyword models.

Defines Pydantic models for channel keyword analysis and topic extraction
with validation and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .youtube_types import ChannelId


class ChannelKeywordBase(BaseModel):
    """Base model for channel keywords."""

    channel_id: ChannelId = Field(..., description="YouTube channel ID (validated)")
    keyword: str = Field(
        ..., min_length=1, max_length=100, description="Keyword content"
    )
    keyword_order: Optional[int] = Field(
        default=None, ge=0, description="Order of keyword from channel branding"
    )

    # Note: channel_id validation is now handled by ChannelId type

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v: str) -> str:
        """Validate keyword content."""
        if not v or not v.strip():
            raise ValueError("Keyword cannot be empty")

        keyword = v.strip()
        if len(keyword) > 100:
            raise ValueError("Keyword cannot exceed 100 characters")

        # Remove excessive whitespace
        keyword = " ".join(keyword.split())

        return keyword

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelKeywordCreate(ChannelKeywordBase):
    """Model for creating channel keywords."""

    pass


class ChannelKeywordUpdate(BaseModel):
    """Model for updating channel keywords."""

    keyword_order: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelKeyword(ChannelKeywordBase):
    """Full channel keyword model with timestamps."""

    created_at: datetime = Field(..., description="When the keyword was created")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class ChannelKeywordSearchFilters(BaseModel):
    """Filters for searching channel keywords."""

    channel_ids: Optional[List[ChannelId]] = Field(
        default=None, description="Filter by channel IDs"
    )
    keywords: Optional[List[str]] = Field(
        default=None, description="Filter by specific keywords"
    )
    keyword_pattern: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Search keywords by pattern (case-insensitive)",
    )
    min_keyword_order: Optional[int] = Field(
        default=None, ge=0, description="Minimum keyword order"
    )
    max_keyword_order: Optional[int] = Field(
        default=None, ge=0, description="Maximum keyword order"
    )
    has_order: Optional[bool] = Field(
        default=None, description="Filter by presence of keyword order"
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


class ChannelKeywordStatistics(BaseModel):
    """Channel keyword statistics."""

    total_keywords: int = Field(..., description="Total number of keywords")
    unique_keywords: int = Field(..., description="Number of unique keywords")
    unique_channels: int = Field(..., description="Number of channels with keywords")
    avg_keywords_per_channel: float = Field(
        ..., description="Average keywords per channel"
    )
    most_common_keywords: List[tuple[str, int]] = Field(
        default_factory=list, description="Most common keywords with counts"
    )
    keyword_distribution: dict[str, int] = Field(
        default_factory=dict, description="Keyword frequency distribution"
    )
    channels_with_ordered_keywords: int = Field(
        ..., description="Channels with ordered keywords"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelKeywordAnalytics(BaseModel):
    """Advanced channel keyword analytics."""

    keyword_trends: dict[str, List[int]] = Field(
        default_factory=dict, description="Keyword usage trends over time"
    )
    semantic_clusters: List[dict[str, Any]] = Field(
        default_factory=list, description="Semantic keyword clusters"
    )
    topic_keywords: dict[str, List[str]] = Field(
        default_factory=dict, description="Keywords grouped by topics"
    )
    keyword_similarity: dict[str, float] = Field(
        default_factory=dict, description="Keyword similarity scores"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
