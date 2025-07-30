"""
Video topic models.

Defines Pydantic models for video-topic relationships and content classification
with validation and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .youtube_types import TopicId, VideoId


class VideoTopicBase(BaseModel):
    """Base model for video topics."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    topic_id: TopicId = Field(..., description="Topic identifier (validated)")
    relevance_type: str = Field(
        default="primary", description="Relevance type: primary, relevant, suggested"
    )

    # Note: video_id and topic_id validation is now handled by respective types

    @field_validator("relevance_type")
    @classmethod
    def validate_relevance_type(cls, v: str) -> str:
        """Validate relevance type."""
        if not v or not v.strip():
            raise ValueError("Relevance type cannot be empty")

        relevance_type = v.strip().lower()
        allowed_types = {"primary", "relevant", "suggested"}

        if relevance_type not in allowed_types:
            raise ValueError(
                f"Relevance type must be one of: {', '.join(allowed_types)}"
            )

        return relevance_type

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoTopicCreate(VideoTopicBase):
    """Model for creating video topics."""

    pass


class VideoTopicUpdate(BaseModel):
    """Model for updating video topics."""

    relevance_type: Optional[str] = Field(
        None, description="Relevance type: primary, relevant, suggested"
    )

    @field_validator("relevance_type")
    @classmethod
    def validate_relevance_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate relevance type."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Relevance type cannot be empty")

        relevance_type = v.strip().lower()
        allowed_types = {"primary", "relevant", "suggested"}

        if relevance_type not in allowed_types:
            raise ValueError(
                f"Relevance type must be one of: {', '.join(allowed_types)}"
            )

        return relevance_type

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoTopic(VideoTopicBase):
    """Full video topic model with timestamps."""

    created_at: datetime = Field(..., description="When the topic was created")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class VideoTopicSearchFilters(BaseModel):
    """Filters for searching video topics."""

    video_ids: Optional[List[VideoId]] = Field(
        default=None, description="Filter by video IDs"
    )
    topic_ids: Optional[List[TopicId]] = Field(
        default=None, description="Filter by topic IDs"
    )
    relevance_types: Optional[List[str]] = Field(
        default=None, description="Filter by relevance types"
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


class VideoTopicStatistics(BaseModel):
    """Video topic statistics."""

    total_video_topics: int = Field(
        ..., description="Total number of video-topic relationships"
    )
    unique_topics: int = Field(..., description="Number of unique topics")
    unique_videos: int = Field(..., description="Number of unique videos with topics")
    avg_topics_per_video: float = Field(..., description="Average topics per video")
    most_common_topics: List[tuple[str, int]] = Field(
        default_factory=list, description="Most common topics with counts"
    )
    relevance_type_distribution: dict[str, int] = Field(
        default_factory=dict, description="Distribution by relevance type"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoTopicAnalytics(BaseModel):
    """Advanced video topic analytics."""

    topic_trends: dict[str, List[int]] = Field(
        default_factory=dict, description="Topic usage trends over time"
    )
    video_topic_clusters: dict[str, List[str]] = Field(
        default_factory=dict, description="Video clusters by topic similarity"
    )
    topic_co_occurrence: dict[str, List[tuple[str, float]]] = Field(
        default_factory=dict, description="Topic co-occurrence patterns"
    )
    relevance_scores: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="Relevance scores by video and topic"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
