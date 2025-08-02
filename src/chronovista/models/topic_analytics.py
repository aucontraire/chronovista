"""
Topic analytics models.

Defines Pydantic models for topic analytics results including popularity rankings,
relationship analysis, and statistical data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .youtube_types import TopicId


class TopicPopularity(BaseModel):
    """Model for topic popularity analysis results."""

    model_config = ConfigDict(frozen=True)

    topic_id: TopicId = Field(..., description="Topic identifier")
    category_name: str = Field(..., description="Human-readable topic name")
    video_count: int = Field(0, description="Number of videos in this topic")
    channel_count: int = Field(
        0, description="Number of channels associated with this topic"
    )
    total_content_count: int = Field(
        0, description="Total content items (videos + channels)"
    )
    video_percentage: Decimal = Field(
        Decimal("0.0"), description="Percentage of total videos"
    )
    channel_percentage: Decimal = Field(
        Decimal("0.0"), description="Percentage of total channels"
    )
    popularity_score: Decimal = Field(
        Decimal("0.0"), description="Combined popularity score"
    )
    rank: int = Field(0, description="Ranking position (1 = most popular)")


class TopicRelationship(BaseModel):
    """Model for topic relationship analysis."""

    model_config = ConfigDict(frozen=True)

    topic_id: TopicId = Field(..., description="Related topic identifier")
    category_name: str = Field(..., description="Related topic name")
    shared_videos: int = Field(0, description="Number of shared videos")
    shared_channels: int = Field(0, description="Number of shared channels")
    total_shared: int = Field(0, description="Total shared content items")
    confidence_score: Decimal = Field(
        Decimal("0.0"), description="Relationship confidence (0.0-1.0)"
    )
    lift_score: Decimal = Field(Decimal("0.0"), description="Association lift score")
    relationship_type: str = Field(
        "related", description="Type of relationship (related, similar, overlapping)"
    )


class TopicRelationships(BaseModel):
    """Model for complete topic relationship analysis."""

    model_config = ConfigDict(frozen=True)

    source_topic_id: TopicId = Field(..., description="Source topic identifier")
    source_category_name: str = Field(..., description="Source topic name")
    total_videos: int = Field(0, description="Total videos in source topic")
    total_channels: int = Field(0, description="Total channels in source topic")
    relationships: List[TopicRelationship] = Field(
        default_factory=list, description="Related topics"
    )
    analysis_date: str = Field(..., description="Date of analysis (ISO format)")


class TopicOverlap(BaseModel):
    """Model for topic overlap analysis between two topics."""

    model_config = ConfigDict(frozen=True)

    topic1_id: TopicId = Field(..., description="First topic identifier")
    topic1_name: str = Field(..., description="First topic name")
    topic2_id: TopicId = Field(..., description="Second topic identifier")
    topic2_name: str = Field(..., description="Second topic name")

    # Video overlap
    topic1_videos: int = Field(0, description="Total videos in topic 1")
    topic2_videos: int = Field(0, description="Total videos in topic 2")
    shared_videos: int = Field(0, description="Videos shared between topics")
    video_overlap_percentage: Decimal = Field(
        Decimal("0.0"), description="Percentage of video overlap"
    )

    # Channel overlap
    topic1_channels: int = Field(0, description="Total channels in topic 1")
    topic2_channels: int = Field(0, description="Total channels in topic 2")
    shared_channels: int = Field(0, description="Channels shared between topics")
    channel_overlap_percentage: Decimal = Field(
        Decimal("0.0"), description="Percentage of channel overlap"
    )

    # Overall metrics
    jaccard_similarity: Decimal = Field(
        Decimal("0.0"), description="Jaccard similarity coefficient"
    )
    overlap_strength: str = Field(
        "none",
        description="Qualitative overlap strength (none, weak, moderate, strong)",
    )


class TopicStats(BaseModel):
    """Model for general topic statistics."""

    model_config = ConfigDict(frozen=True)

    topic_id: TopicId = Field(..., description="Topic identifier")
    category_name: str = Field(..., description="Topic name")
    video_count: int = Field(0, description="Number of videos")
    channel_count: int = Field(0, description="Number of channels")
    avg_views: Optional[Decimal] = Field(None, description="Average views per video")
    avg_likes: Optional[Decimal] = Field(None, description="Average likes per video")
    total_duration: Optional[int] = Field(None, description="Total duration in seconds")


class TopicTrend(BaseModel):
    """Model for topic trends over time."""

    model_config = ConfigDict(frozen=True)

    topic_id: TopicId = Field(..., description="Topic identifier")
    category_name: str = Field(..., description="Topic name")
    period: str = Field(..., description="Time period (e.g., '2024-01', 'Q1-2024')")
    video_count: int = Field(0, description="Videos added in this period")
    channel_count: int = Field(0, description="Channels added in this period")
    growth_rate: Decimal = Field(
        Decimal("0.0"), description="Growth rate compared to previous period"
    )
    trend_direction: str = Field(
        "stable", description="Trend direction (growing, declining, stable)"
    )


class TopicDiscoveryPath(BaseModel):
    """Model for topic discovery pathway analysis."""

    model_config = ConfigDict(frozen=True)

    discovery_method: str = Field(
        ..., description="How topic was discovered (liked, watched, recommended)"
    )
    topic_id: TopicId = Field(..., description="Topic identifier")
    category_name: str = Field(..., description="Topic name")
    discovery_count: int = Field(0, description="Number of times discovered this way")
    avg_engagement: Decimal = Field(
        Decimal("0.0"), description="Average engagement score (completion rate, likes)"
    )
    retention_rate: Decimal = Field(
        Decimal("0.0"), description="Percentage who continue consuming this topic"
    )


class TopicDiscoveryAnalysis(BaseModel):
    """Model for comprehensive topic discovery analysis."""

    model_config = ConfigDict(frozen=True)

    total_users: int = Field(0, description="Total users analyzed")
    total_discoveries: int = Field(0, description="Total discovery events")
    discovery_paths: List[TopicDiscoveryPath] = Field(
        default_factory=list, description="Topic discovery pathways"
    )
    top_entry_topics: List[TopicPopularity] = Field(
        default_factory=list, description="Topics most often discovered first"
    )
    high_retention_topics: List[TopicPopularity] = Field(
        default_factory=list, description="Topics with highest retention rates"
    )
    analysis_date: str = Field(..., description="Analysis date (ISO format)")


class TopicInsight(BaseModel):
    """Model for personalized topic insights and recommendations."""

    model_config = ConfigDict(frozen=True)

    topic_id: TopicId = Field(..., description="Topic identifier")
    category_name: str = Field(..., description="Topic name")
    insight_type: str = Field(
        ..., description="Type of insight (emerging, dominant, underexplored, similar)"
    )
    confidence_score: Decimal = Field(
        Decimal("0.0"), description="Confidence in insight (0.0-1.0)"
    )

    # User-specific metrics
    user_engagement: Decimal = Field(
        Decimal("0.0"), description="User's engagement level with this topic"
    )
    watch_time_hours: Decimal = Field(
        Decimal("0.0"), description="Total hours watched in this topic"
    )
    completion_rate: Decimal = Field(
        Decimal("0.0"), description="Average completion rate for topic videos"
    )

    # Recommendation context
    recommendation_reason: str = Field(..., description="Why this is recommended")
    potential_interest_score: Decimal = Field(
        Decimal("0.0"), description="Predicted interest level"
    )
    suggested_content_count: int = Field(
        0, description="Number of suggested videos/channels"
    )

    # Comparative metrics
    vs_average_engagement: Decimal = Field(
        Decimal("0.0"), description="Engagement vs. user's average"
    )
    growth_potential: str = Field(
        "medium", description="Growth potential (low, medium, high)"
    )


class TopicInsightCollection(BaseModel):
    """Model for complete topic insights analysis."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="User identifier")
    total_watched_hours: Decimal = Field(
        Decimal("0.0"), description="Total hours watched"
    )
    topics_explored: int = Field(0, description="Number of unique topics explored")

    # Insight categories
    emerging_interests: List[TopicInsight] = Field(
        default_factory=list, description="Newly emerging topic interests"
    )
    dominant_interests: List[TopicInsight] = Field(
        default_factory=list, description="Primary topic interests"
    )
    underexplored_topics: List[TopicInsight] = Field(
        default_factory=list, description="Topics to explore more"
    )
    similar_recommendations: List[TopicInsight] = Field(
        default_factory=list, description="Similar topic recommendations"
    )

    # Summary insights
    diversity_score: Decimal = Field(
        Decimal("0.0"), description="Topic diversity in viewing (0.0-1.0)"
    )
    exploration_trend: str = Field(
        "stable", description="Exploration trend (expanding, stable, narrowing)"
    )
    analysis_date: str = Field(..., description="Analysis date (ISO format)")


class TopicAnalyticsSummary(BaseModel):
    """Model for overall topic analytics summary."""

    model_config = ConfigDict(frozen=True)

    total_topics: int = Field(0, description="Total number of topics")
    total_videos: int = Field(0, description="Total number of videos with topics")
    total_channels: int = Field(0, description="Total number of channels with topics")
    most_popular_topics: List[TopicPopularity] = Field(
        default_factory=list, description="Top 5 popular topics"
    )
    topic_distribution: Dict[str, int] = Field(
        default_factory=dict, description="Topic distribution counts"
    )
    analysis_date: str = Field(..., description="Analysis date (ISO format)")
    coverage_percentage: Decimal = Field(
        Decimal("0.0"), description="Percentage of content with topic data"
    )
