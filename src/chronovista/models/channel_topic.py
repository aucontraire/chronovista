"""
Channel topic models.

Defines Pydantic models for channel-topic relationships and content classification
with validation and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .youtube_types import ChannelId, TopicId


class ChannelTopicBase(BaseModel):
    """Base model for channel topics."""

    channel_id: ChannelId = Field(..., description="YouTube channel ID (validated)")
    topic_id: TopicId = Field(..., description="Topic identifier (validated)")

    # Note: channel_id and topic_id validation is now handled by respective types

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelTopicCreate(ChannelTopicBase):
    """Model for creating channel topics."""

    pass


class ChannelTopicUpdate(BaseModel):
    """Model for updating channel topics."""

    # Channel topics are typically static, but we keep this for consistency
    # and potential future enhancements
    pass

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelTopic(ChannelTopicBase):
    """Full channel topic model with timestamps."""

    created_at: datetime = Field(..., description="When the topic was created")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class ChannelTopicSearchFilters(BaseModel):
    """Filters for searching channel topics."""

    channel_ids: Optional[List[ChannelId]] = Field(
        default=None, description="Filter by channel IDs"
    )
    topic_ids: Optional[List[TopicId]] = Field(
        default=None, description="Filter by topic IDs"
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


class ChannelTopicStatistics(BaseModel):
    """Channel topic statistics."""

    total_channel_topics: int = Field(..., description="Total number of channel-topic relationships")
    unique_topics: int = Field(..., description="Number of unique topics")
    unique_channels: int = Field(..., description="Number of unique channels with topics")
    avg_topics_per_channel: float = Field(..., description="Average topics per channel")
    most_common_topics: List[tuple[str, int]] = Field(
        default_factory=list, description="Most common topics with counts"
    )
    topic_distribution: dict[str, int] = Field(
        default_factory=dict, description="Topic frequency distribution"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class ChannelTopicAnalytics(BaseModel):
    """Advanced channel topic analytics."""

    topic_trends: dict[str, List[int]] = Field(
        default_factory=dict, description="Topic usage trends over time"
    )
    channel_topic_clusters: dict[str, List[str]] = Field(
        default_factory=dict, description="Channel clusters by topic similarity"
    )
    topic_dominance: dict[str, List[tuple[str, float]]] = Field(
        default_factory=dict, description="Topic dominance patterns by channel"
    )
    cross_topic_analysis: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="Cross-topic analysis and relationships"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )