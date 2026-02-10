"""API schema exports.

This module provides a centralized export of all API schemas for convenient
imports throughout the application.
"""

from chronovista.api.schemas.categories import (
    CategoryDetail,
    CategoryDetailResponse,
    CategoryListItem,
    CategoryListResponse,
)
from chronovista.api.schemas.channels import (
    ChannelDetail,
    ChannelDetailResponse,
    ChannelListItem,
    ChannelListResponse,
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
from chronovista.api.schemas.responses import (
    ApiError,
    ApiResponse,
    ErrorCode,
    ErrorResponse,
    PaginationMeta,
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
    # Categories
    "CategoryDetail",
    "CategoryDetailResponse",
    "CategoryListItem",
    "CategoryListResponse",
    # Channels
    "ChannelDetail",
    "ChannelDetailResponse",
    "ChannelListItem",
    "ChannelListResponse",
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
    # Responses
    "ApiError",
    "ApiResponse",
    "ErrorCode",
    "ErrorResponse",
    "PaginationMeta",
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
