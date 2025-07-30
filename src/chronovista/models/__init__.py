"""
Data models module for chronovista.

Defines Pydantic models for representing YouTube data including videos,
playlists, annotations, and metadata with full type safety and validation.
"""

from __future__ import annotations

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

__all__ = [
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
    # Utility functions
    "get_model_count",
]


def get_model_count() -> int:
    """Get the number of available models."""
    return len(__all__) - 1  # Subtract 1 for the function itself
