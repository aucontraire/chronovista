"""
Takeout Data Models

Pydantic models for parsing and analyzing Google Takeout data.
These models are designed for local analysis without API calls.
"""

from .recovery import (
    CHANNEL_PLACEHOLDER_PREFIX,
    UNKNOWN_CHANNEL_PREFIX,
    VIDEO_PLACEHOLDER_PREFIX,
    ChannelRecoveryAction,
    HistoricalTakeout,
    RecoveredChannelMetadata,
    RecoveredVideoMetadata,
    RecoveryCandidate,
    RecoveryOptions,
    RecoveryResult,
    VideoRecoveryAction,
    extract_video_id_from_placeholder,
    is_placeholder_channel_name,
    is_placeholder_video_title,
)
from .takeout_analysis import (
    ChannelSummary,
    ContentGap,
    DateRange,
    PlaylistAnalysis,
    PlaylistSuggestion,
    TakeoutAnalysis,
    ViewingPatterns,
)
from .takeout_data import (
    TakeoutData,
    TakeoutPlaylist,
    TakeoutPlaylistItem,
    TakeoutSubscription,
    TakeoutWatchEntry,
)

__all__ = [
    # Core data models
    "TakeoutWatchEntry",
    "TakeoutPlaylist",
    "TakeoutPlaylistItem",
    "TakeoutSubscription",
    "TakeoutData",
    # Analysis models
    "TakeoutAnalysis",
    "PlaylistAnalysis",
    "ViewingPatterns",
    "ChannelSummary",
    "ContentGap",
    "DateRange",
    "PlaylistSuggestion",
    # Recovery models
    "HistoricalTakeout",
    "RecoveredVideoMetadata",
    "RecoveredChannelMetadata",
    "RecoveryCandidate",
    "VideoRecoveryAction",
    "ChannelRecoveryAction",
    "RecoveryResult",
    "RecoveryOptions",
    # Recovery utilities
    "VIDEO_PLACEHOLDER_PREFIX",
    "CHANNEL_PLACEHOLDER_PREFIX",
    "UNKNOWN_CHANNEL_PREFIX",
    "is_placeholder_video_title",
    "is_placeholder_channel_name",
    "extract_video_id_from_placeholder",
]
