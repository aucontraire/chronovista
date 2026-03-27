"""
Takeout Analysis Models

Pydantic models for analyzing patterns and relationships in Google Takeout data.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    """Represents a date range for analysis."""

    start_date: datetime = Field(..., description="Start of the date range")
    end_date: datetime = Field(..., description="End of the date range")
    total_days: int = Field(..., description="Total days in the range")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if "total_days" not in data:
            self.total_days = (self.end_date - self.start_date).days


class ChannelSummary(BaseModel):
    """Summary statistics for a channel based on takeout data."""

    channel_id: Optional[str] = Field(None, description="YouTube channel ID")
    channel_name: str = Field(..., description="Channel display name")
    channel_url: Optional[str] = Field(None, description="Channel URL")

    # Viewing statistics
    videos_watched: int = Field(
        0, description="Number of videos watched from this channel"
    )
    total_watch_time_minutes: Optional[int] = Field(
        None, description="Estimated total watch time"
    )
    first_watched: Optional[datetime] = Field(
        None, description="First video watched from channel"
    )
    last_watched: Optional[datetime] = Field(
        None, description="Most recent video watched"
    )

    # Engagement indicators
    videos_in_playlists: int = Field(
        0, description="Videos from this channel saved to playlists"
    )
    is_subscribed: bool = Field(
        False, description="Whether user is subscribed to this channel"
    )

    # Analysis scores
    engagement_score: float = Field(
        0.0, description="Calculated engagement score (0-1)"
    )
    consistency_score: float = Field(
        0.0, description="How consistently user watches this channel"
    )


class ContentGap(BaseModel):
    """Identifies content that lacks rich metadata and needs API enrichment."""

    video_id: str = Field(..., description="YouTube video ID")
    title: str = Field(..., description="Video title from takeout")
    channel_name: Optional[str] = Field(None, description="Channel name")

    missing_fields: List[str] = Field(
        default_factory=list, description="Fields that could be enriched from API"
    )
    priority_score: float = Field(0.0, description="Priority for API fetching (0-1)")

    # Context for prioritization
    in_playlists: int = Field(
        0, description="Number of playlists containing this video"
    )
    watch_count: int = Field(0, description="Number of times watched (if available)")
    last_watched: Optional[datetime] = Field(None, description="When last watched")


class PlaylistSuggestion(BaseModel):
    """Suggestion for creating new playlists based on content analysis."""

    suggested_name: str = Field(..., description="Suggested playlist name")
    reason: str = Field(..., description="Why this playlist is suggested")
    video_ids: List[str] = Field(
        ..., description="Videos that would fit in this playlist"
    )
    confidence_score: float = Field(
        ..., description="Confidence in this suggestion (0-1)"
    )

    # Supporting data
    common_themes: List[str] = Field(
        default_factory=list, description="Common themes among videos"
    )
    channel_overlap: Dict[str, int] = Field(
        default_factory=dict, description="Channels represented"
    )


class ViewingPatterns(BaseModel):
    """Analysis of user viewing patterns from takeout data."""

    # Temporal patterns
    peak_viewing_hours: List[int] = Field(
        default_factory=list, description="Hours of day with most activity"
    )
    peak_viewing_days: List[str] = Field(
        default_factory=list, description="Days of week with most activity"
    )
    viewing_frequency: float = Field(0.0, description="Average videos per day")

    # Content patterns
    top_channels: List[ChannelSummary] = Field(
        default_factory=list, description="Most watched channels"
    )
    channel_diversity: float = Field(
        0.0, description="How diverse channel watching is (0-1)"
    )
    content_categories: Dict[str, int] = Field(
        default_factory=dict, description="Estimated content categories"
    )

    # Engagement patterns
    playlist_usage: float = Field(
        0.0, description="Percentage of videos saved to playlists"
    )
    subscription_engagement: float = Field(
        0.0, description="How much user watches subscribed channels"
    )


class PlaylistAnalysis(BaseModel):
    """Analysis of playlist relationships and organization."""

    # Overlap analysis
    playlist_overlap_matrix: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Matrix showing video overlap between playlists",
    )
    overlap_percentages: Dict[str, Dict[str, float]] = Field(
        default_factory=dict, description="Percentage overlap between playlists"
    )

    # Organization insights
    orphaned_videos: List[str] = Field(
        default_factory=list, description="Video IDs that aren't in any playlist"
    )
    over_categorized_videos: List[str] = Field(
        default_factory=list,
        description="Videos that appear in many playlists (potential over-categorization)",
    )

    # Playlist quality metrics
    playlist_diversity_scores: Dict[str, float] = Field(
        default_factory=dict, description="Diversity score for each playlist (0-1)"
    )
    playlist_sizes: Dict[str, int] = Field(
        default_factory=dict, description="Number of videos in each playlist"
    )

    # Suggestions
    suggested_new_playlists: List[PlaylistSuggestion] = Field(
        default_factory=list,
        description="Suggestions for new playlists based on orphaned content",
    )
    merge_suggestions: List[Tuple[str, str, str]] = Field(
        default_factory=list,
        description="Playlist pairs that could be merged (playlist1, playlist2, reason)",
    )


class TakeoutAnalysis(BaseModel):
    """
    Comprehensive analysis of Google Takeout data.

    This is the main analysis result returned by TakeoutService analysis methods.
    """

    # Basic statistics
    total_videos_watched: int = Field(
        ..., description="Total unique videos in watch history"
    )
    unique_channels: int = Field(..., description="Number of unique channels watched")
    playlist_count: int = Field(..., description="Number of playlists")
    subscription_count: int = Field(..., description="Number of channel subscriptions")

    # Date information
    date_range: Optional[DateRange] = Field(
        None, description="Date range of available data"
    )
    data_completeness: float = Field(
        0.0, description="Estimated completeness of takeout data (0-1)"
    )

    # Detailed analysis
    viewing_patterns: ViewingPatterns = Field(
        ..., description="User viewing behavior analysis"
    )
    playlist_analysis: PlaylistAnalysis = Field(
        ..., description="Playlist organization analysis"
    )
    top_channels: List[ChannelSummary] = Field(
        ..., description="Most significant channels"
    )

    # Content gaps and opportunities
    content_gaps: List[ContentGap] = Field(
        default_factory=list,
        description="Content that would benefit from API enrichment",
    )
    high_priority_videos: List[str] = Field(
        default_factory=list,
        description="Video IDs that should be prioritized for API fetching",
    )

    # Language and diversity insights
    estimated_language_distribution: Dict[str, float] = Field(
        default_factory=dict,
        description="Estimated language distribution based on channel names",
    )
    content_diversity_score: float = Field(
        0.0, description="Overall content diversity (0-1)"
    )

    # Analysis metadata
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When this analysis was performed"
    )
    analysis_version: str = Field(
        "1.0", description="Version of analysis algorithm used"
    )

    def get_api_fetch_priorities(self, max_videos: int = 100) -> List[str]:
        """
        Get prioritized list of video IDs to fetch from API.

        Parameters
        ----------
        max_videos : int
            Maximum number of videos to return

        Returns
        -------
        List[str]
            Video IDs ordered by priority for API fetching
        """
        # Combine high priority videos and content gaps
        prioritized = []

        # Add high priority videos first
        prioritized.extend(self.high_priority_videos)

        # Add content gaps sorted by priority score
        gap_videos = sorted(
            self.content_gaps, key=lambda x: x.priority_score, reverse=True
        )
        prioritized.extend([gap.video_id for gap in gap_videos])

        # Remove duplicates while preserving order
        seen = set()
        unique_prioritized = []
        for video_id in prioritized:
            if video_id not in seen:
                seen.add(video_id)
                unique_prioritized.append(video_id)

        return unique_prioritized[:max_videos]

    def get_channel_fetch_priorities(self, max_channels: int = 20) -> List[str]:
        """
        Get prioritized list of channel IDs to fetch from API.

        Parameters
        ----------
        max_channels : int
            Maximum number of channels to return

        Returns
        -------
        List[str]
            Channel IDs ordered by priority for API fetching
        """
        # Sort channels by engagement score and video count
        sorted_channels = sorted(
            [ch for ch in self.top_channels if ch.channel_id],
            key=lambda x: (x.engagement_score, x.videos_watched),
            reverse=True,
        )

        return [
            ch.channel_id
            for ch in sorted_channels[:max_channels]
            if ch.channel_id is not None
        ]
