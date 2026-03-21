"""API schema exports.

This module provides a centralized export of all API schemas for convenient
imports throughout the application.
"""

from chronovista.api.schemas.batch_corrections import (
    BatchApplyRequest,
    BatchApplyResult,
    BatchPreviewMatch,
    BatchPreviewRequest,
    BatchPreviewResponse,
    BatchRebuildRequest,
    BatchRebuildResult,
)
from chronovista.api.schemas.categories import (
    CategoryDetail,
    CategoryDetailResponse,
    CategoryListItem,
    CategoryListResponse,
)
from chronovista.api.schemas.entity_mentions import (
    EntityVideoResponse,
    EntityVideoResult,
    MentionPreview,
    VideoEntitiesResponse,
    VideoEntitySummary,
)
from chronovista.api.schemas.channels import (
    ChannelDetail,
    ChannelDetailResponse,
    ChannelListItem,
    ChannelListResponse,
)
from chronovista.api.schemas.onboarding import (
    OnboardingCounts,
    OnboardingStatus,
    PipelineStep,
)
from chronovista.api.schemas.filters import (
    ErrorTypeURI,
    FILTER_LIMITS,
    FilterType,
    FilterWarning,
    FilterWarningCode,
    ProblemDetails,
    VideoFilterParams,
)
from chronovista.api.schemas.playlists import (
    PlaylistDetail,
    PlaylistDetailResponse,
    PlaylistListItem,
    PlaylistListResponse,
    PlaylistVideoListItem,
    PlaylistVideoListResponse,
)
from chronovista.api.schemas.settings import (
    AppInfoResponse,
    CachePurgeResponse,
    CacheStatusResponse,
    DatabaseStats,
    MultiTranscriptDownloadResponse,
    SupportedLanguage,
    TranscriptDownloadResult,
)
from chronovista.api.schemas.responses import (
    ApiError,
    ApiResponse,
    ErrorCode,
    ErrorResponse,
    PaginationMeta,
)
from chronovista.api.schemas.sorting import SortOrder
from chronovista.api.schemas.tasks import (
    BackgroundTask,
    TaskCreate,
)
from chronovista.api.schemas.tags import (
    TagDetail,
    TagDetailResponse,
    TagListItem,
    TagListResponse,
)
from chronovista.api.schemas.topics import (
    TopicDetail,
    TopicDetailResponse,
    TopicListItem,
    TopicListResponse,
)
from chronovista.api.schemas.videos import (
    TranscriptSummary,
    VideoDetail,
    VideoDetailResponse,
    VideoListItem,
    VideoListResponse,
)

__all__ = [
    # Batch Corrections
    "BatchApplyRequest",
    "BatchApplyResult",
    "BatchPreviewMatch",
    "BatchPreviewRequest",
    "BatchPreviewResponse",
    "BatchRebuildRequest",
    "BatchRebuildResult",
    # Categories
    "CategoryDetail",
    "CategoryDetailResponse",
    "CategoryListItem",
    "CategoryListResponse",
    # Entity Mentions (Feature 038)
    "EntityVideoResponse",
    "EntityVideoResult",
    "MentionPreview",
    "VideoEntitiesResponse",
    "VideoEntitySummary",
    # Channels
    "ChannelDetail",
    "ChannelDetailResponse",
    "ChannelListItem",
    "ChannelListResponse",
    # Onboarding (Feature 047)
    "OnboardingCounts",
    "OnboardingStatus",
    "PipelineStep",
    # Filters (Feature 020)
    "ErrorTypeURI",
    "FILTER_LIMITS",
    "FilterType",
    "FilterWarning",
    "FilterWarningCode",
    "ProblemDetails",
    "VideoFilterParams",
    # Playlists
    "PlaylistDetail",
    "PlaylistDetailResponse",
    "PlaylistListItem",
    "PlaylistListResponse",
    "PlaylistVideoListItem",
    "PlaylistVideoListResponse",
    # Settings (Feature 049)
    "AppInfoResponse",
    "CachePurgeResponse",
    "CacheStatusResponse",
    "DatabaseStats",
    "MultiTranscriptDownloadResponse",
    "SupportedLanguage",
    "TranscriptDownloadResult",
    # Responses
    "ApiError",
    "ApiResponse",
    "ErrorCode",
    "ErrorResponse",
    "PaginationMeta",
    # Sorting
    "SortOrder",
    # Tasks (Feature 047)
    "BackgroundTask",
    "TaskCreate",
    # Tags
    "TagDetail",
    "TagDetailResponse",
    "TagListItem",
    "TagListResponse",
    # Topics
    "TopicDetail",
    "TopicDetailResponse",
    "TopicListItem",
    "TopicListResponse",
    # Videos
    "TranscriptSummary",
    "VideoDetail",
    "VideoDetailResponse",
    "VideoListItem",
    "VideoListResponse",
]
