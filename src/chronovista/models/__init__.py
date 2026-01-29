"""
Data models module for chronovista.

Defines Pydantic models for representing YouTube data including videos,
playlists, annotations, and metadata with full type safety and validation.

Includes YouTube API response models for type-safe API parsing (FR-005, FR-006, FR-007).
"""

from __future__ import annotations

from .api_responses import (
    # Base
    BaseYouTubeModel,
    # Supporting models
    LocalizedString,
    PageInfo,
    RegionRestriction,
    RelatedPlaylists,
    ResourceId,
    Thumbnail,
    TopicDetails,
    # Snippet models
    CaptionSnippet,
    CategorySnippet,
    ChannelSnippet,
    PlaylistItemSnippet,
    PlaylistSnippet,
    SearchSnippet,
    SubscriptionSnippet,
    VideoSnippet,
    # Statistics models
    ChannelStatisticsResponse,
    VideoStatisticsResponse,
    # ContentDetails models
    ChannelContentDetails,
    PlaylistContentDetails,
    PlaylistItemContentDetails,
    VideoContentDetails,
    # Status models
    ChannelStatus,
    PlaylistStatus,
    VideoStatus,
    # Root response models
    YouTubeCaptionResponse,
    YouTubeChannelResponse,
    YouTubeListResponseMetadata,
    YouTubePlaylistItemResponse,
    YouTubePlaylistResponse,
    YouTubeSearchResponse,
    YouTubeSubscriptionResponse,
    YouTubeVideoCategoryResponse,
    YouTubeVideoResponse,
)
from .channel import (
    Channel,
    ChannelBase,
    ChannelCreate,
    ChannelSearchFilters,
    ChannelStatistics,
    ChannelUpdate,
)
from .channel_keyword import (
    ChannelKeyword,
    ChannelKeywordAnalytics,
    ChannelKeywordBase,
    ChannelKeywordCreate,
    ChannelKeywordSearchFilters,
    ChannelKeywordStatistics,
    ChannelKeywordUpdate,
)
from .channel_topic import (
    ChannelTopic,
    ChannelTopicAnalytics,
    ChannelTopicBase,
    ChannelTopicCreate,
    ChannelTopicSearchFilters,
    ChannelTopicStatistics,
    ChannelTopicUpdate,
)
from .enrichment_report import (
    EnrichmentDetail,
    EnrichmentReport,
    EnrichmentSummary,
)
from .enums import DownloadReason, LanguagePreferenceType, TrackKind, TranscriptType
from .playlist import (
    Playlist,
    PlaylistAnalytics,
    PlaylistBase,
    PlaylistCreate,
    PlaylistSearchFilters,
    PlaylistStatistics,
    PlaylistUpdate,
)
from .topic_category import (
    TopicCategory,
    TopicCategoryAnalytics,
    TopicCategoryBase,
    TopicCategoryCreate,
    TopicCategoryHierarchy,
    TopicCategorySearchFilters,
    TopicCategoryStatistics,
    TopicCategoryUpdate,
)
from .video_category import (
    VideoCategory,
    VideoCategoryBase,
    VideoCategoryCreate,
    VideoCategoryUpdate,
)
from .user_language_preference import (
    UserLanguagePreference,
    UserLanguagePreferenceBase,
    UserLanguagePreferenceCreate,
    UserLanguagePreferenceUpdate,
)
from .user_video import (
    GoogleTakeoutWatchHistoryItem,
    UserVideo,
    UserVideoBase,
    UserVideoCreate,
    UserVideoSearchFilters,
    UserVideoStatistics,
    UserVideoUpdate,
)
from .video import (
    Video,
    VideoBase,
    VideoCreate,
    VideoSearchFilters,
    VideoStatistics,
    VideoUpdate,
    VideoWithChannel,
)
from .video_localization import (
    VideoLocalization,
    VideoLocalizationBase,
    VideoLocalizationCreate,
    VideoLocalizationSearchFilters,
    VideoLocalizationStatistics,
    VideoLocalizationUpdate,
)
from .video_tag import (
    VideoTag,
    VideoTagBase,
    VideoTagCreate,
    VideoTagSearchFilters,
    VideoTagStatistics,
    VideoTagUpdate,
)
from .video_topic import (
    VideoTopic,
    VideoTopicAnalytics,
    VideoTopicBase,
    VideoTopicCreate,
    VideoTopicSearchFilters,
    VideoTopicStatistics,
    VideoTopicUpdate,
)
from .video_transcript import (
    TranscriptSearchFilters,
    VideoTranscript,
    VideoTranscriptBase,
    VideoTranscriptCreate,
    VideoTranscriptUpdate,
    VideoTranscriptWithQuality,
)
from .transcript_segment import (
    TranscriptSegmentBase,
    TranscriptSegmentCreate,
    TranscriptSegment,
    TranscriptSegmentResponse,
)

__all__ = [
    # YouTube API Response Models (FR-005, FR-006, FR-007)
    # Base
    "BaseYouTubeModel",
    # Supporting models
    "Thumbnail",
    "LocalizedString",
    "ResourceId",
    "RegionRestriction",
    "TopicDetails",
    "RelatedPlaylists",
    "PageInfo",
    # Snippet models
    "VideoSnippet",
    "ChannelSnippet",
    "PlaylistSnippet",
    "PlaylistItemSnippet",
    "SearchSnippet",
    "CaptionSnippet",
    "SubscriptionSnippet",
    "CategorySnippet",
    # Statistics models (API responses)
    "VideoStatisticsResponse",
    "ChannelStatisticsResponse",
    # ContentDetails models
    "VideoContentDetails",
    "ChannelContentDetails",
    "PlaylistContentDetails",
    "PlaylistItemContentDetails",
    # Status models
    "VideoStatus",
    "PlaylistStatus",
    "ChannelStatus",
    # Root response models
    "YouTubeVideoResponse",
    "YouTubeChannelResponse",
    "YouTubePlaylistResponse",
    "YouTubePlaylistItemResponse",
    "YouTubeSearchResponse",
    "YouTubeCaptionResponse",
    "YouTubeSubscriptionResponse",
    "YouTubeVideoCategoryResponse",
    "YouTubeListResponseMetadata",
    # Enums
    "LanguagePreferenceType",
    "TranscriptType",
    "DownloadReason",
    "TrackKind",
    # User Language Preferences
    "UserLanguagePreference",
    "UserLanguagePreferenceCreate",
    "UserLanguagePreferenceUpdate",
    "UserLanguagePreferenceBase",
    # Video Transcripts
    "VideoTranscript",
    "VideoTranscriptCreate",
    "VideoTranscriptUpdate",
    "VideoTranscriptBase",
    "VideoTranscriptWithQuality",
    "TranscriptSearchFilters",
    # Transcript Segments
    "TranscriptSegmentBase",
    "TranscriptSegmentCreate",
    "TranscriptSegment",
    "TranscriptSegmentResponse",
    # User Videos
    "UserVideo",
    "UserVideoCreate",
    "UserVideoUpdate",
    "UserVideoBase",
    "GoogleTakeoutWatchHistoryItem",
    "UserVideoSearchFilters",
    "UserVideoStatistics",
    # Channels
    "Channel",
    "ChannelCreate",
    "ChannelUpdate",
    "ChannelBase",
    "ChannelSearchFilters",
    "ChannelStatistics",
    # Videos
    "Video",
    "VideoCreate",
    "VideoUpdate",
    "VideoBase",
    "VideoSearchFilters",
    "VideoStatistics",
    "VideoWithChannel",
    # Video Tags
    "VideoTag",
    "VideoTagCreate",
    "VideoTagUpdate",
    "VideoTagBase",
    "VideoTagSearchFilters",
    "VideoTagStatistics",
    # Video Topics
    "VideoTopic",
    "VideoTopicCreate",
    "VideoTopicUpdate",
    "VideoTopicBase",
    "VideoTopicSearchFilters",
    "VideoTopicStatistics",
    "VideoTopicAnalytics",
    # Video Localizations
    "VideoLocalization",
    "VideoLocalizationCreate",
    "VideoLocalizationUpdate",
    "VideoLocalizationBase",
    "VideoLocalizationSearchFilters",
    "VideoLocalizationStatistics",
    # Channel Keywords
    "ChannelKeyword",
    "ChannelKeywordCreate",
    "ChannelKeywordUpdate",
    "ChannelKeywordBase",
    "ChannelKeywordSearchFilters",
    "ChannelKeywordStatistics",
    "ChannelKeywordAnalytics",
    # Channel Topics
    "ChannelTopic",
    "ChannelTopicCreate",
    "ChannelTopicUpdate",
    "ChannelTopicBase",
    "ChannelTopicSearchFilters",
    "ChannelTopicStatistics",
    "ChannelTopicAnalytics",
    # Topic Categories
    "TopicCategory",
    "TopicCategoryCreate",
    "TopicCategoryUpdate",
    "TopicCategoryBase",
    "TopicCategorySearchFilters",
    "TopicCategoryStatistics",
    "TopicCategoryHierarchy",
    "TopicCategoryAnalytics",
    # Playlists
    "Playlist",
    "PlaylistCreate",
    "PlaylistUpdate",
    "PlaylistBase",
    "PlaylistSearchFilters",
    "PlaylistStatistics",
    "PlaylistAnalytics",
    # Video Categories
    "VideoCategory",
    "VideoCategoryCreate",
    "VideoCategoryUpdate",
    "VideoCategoryBase",
    # Enrichment Reports
    "EnrichmentReport",
    "EnrichmentSummary",
    "EnrichmentDetail",
    # Utility functions
    "get_model_count",
]


def get_model_count() -> int:
    """Get the number of available models."""
    return len(__all__) - 1  # Subtract 1 for the function itself
