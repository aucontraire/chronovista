"""Video API response schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.filters import FilterWarning
from chronovista.api.schemas.responses import ApiResponse, PaginationMeta
from chronovista.api.schemas.topics import TopicSummary


class TranscriptSummary(BaseModel):
    """Transcript availability summary for a video."""

    model_config = ConfigDict(strict=True)

    count: int  # Number of transcripts
    languages: List[str]  # Available language codes (BCP-47)
    has_manual: bool  # Any manual/CC transcripts?


class VideoListItem(BaseModel):
    """Video summary for list view.

    Extended with classification fields for filter display (Feature 020).

    Attributes
    ----------
    video_id : str
        11-character YouTube video ID.
    title : str
        Video title.
    channel_id : str | None
        24-character channel ID (null for orphaned videos).
    channel_title : str | None
        Channel name for display.
    upload_date : datetime
        Video upload date.
    duration : int
        Video duration in seconds.
    view_count : int | None
        View count if available.
    transcript_summary : TranscriptSummary
        Summary of available transcripts.
    tags : List[str]
        Video tags from YouTube.
    category_id : str | None
        YouTube category ID.
    category_name : str | None
        Human-readable category name.
    topics : List[TopicSummary]
        Associated topics with hierarchy info.
    availability_status : str
        Video availability status (available, deleted, private, unavailable).
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    video_id: str  # 11-char YouTube ID
    title: str
    channel_id: Optional[str]  # 24-char channel ID (can be null for orphaned)
    channel_title: Optional[str]  # Channel name
    upload_date: datetime
    duration: int  # Seconds
    view_count: Optional[int]
    transcript_summary: TranscriptSummary

    # Classification fields (Feature 020 - Video Classification Filters)
    tags: List[str] = Field(default_factory=list, description="Video tags")
    category_id: Optional[str] = Field(None, description="YouTube category ID")
    category_name: Optional[str] = Field(None, description="Human-readable category")
    topics: List["TopicSummary"] = Field(
        default_factory=list, description="Associated topics"
    )
    availability_status: str = Field(..., description="Video availability status")


class VideoListResponse(ApiResponse[List[VideoListItem]]):
    """Response for video list endpoint."""

    pass


class VideoListResponseWithWarnings(BaseModel):
    """Response for video list endpoint with optional warnings (FR-049, FR-050).

    Used when some filter values are invalid but the request can still return
    partial results. Includes a warnings array indicating which filters failed.

    Attributes
    ----------
    data : List[VideoListItem]
        The list of videos matching the valid filters.
    pagination : PaginationMeta
        Pagination metadata.
    warnings : List[FilterWarning]
        Warnings for invalid filter values that were ignored.
    """

    model_config = ConfigDict(strict=True)

    data: List[VideoListItem]
    pagination: PaginationMeta
    warnings: List[FilterWarning] = Field(
        default_factory=list,
        description="Warnings for invalid filter values that were ignored",
    )


class VideoDetail(BaseModel):
    """Full video details.

    Includes classification data (tags, category, topics) for display.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    video_id: str
    title: str
    description: Optional[str]
    channel_id: Optional[str]
    channel_title: Optional[str]
    upload_date: datetime
    duration: int
    view_count: Optional[int]
    like_count: Optional[int]
    comment_count: Optional[int]
    tags: List[str]
    category_id: Optional[str]
    category_name: Optional[str]  # Human-readable category name
    default_language: Optional[str]
    made_for_kids: bool
    transcript_summary: TranscriptSummary
    topics: List[TopicSummary] = Field(default_factory=list)  # Associated topics
    availability_status: str = Field(..., description="Video availability status")
    alternative_url: Optional[str] = Field(None, description="Alternative URL for deleted/unavailable content")


class VideoDetailResponse(ApiResponse[VideoDetail]):
    """Response for video detail endpoint."""

    pass


class VideoPlaylistMembership(BaseModel):
    """Playlist membership info for a specific video."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    playlist_id: str  # YouTube playlist ID
    title: str  # Playlist title
    position: int  # Video position in playlist (0-indexed)
    is_linked: bool  # Whether playlist is YouTube-linked
    privacy_status: str  # Playlist privacy status


class VideoPlaylistsResponse(BaseModel):
    """Response wrapper for video's playlists."""

    model_config = ConfigDict(strict=True)

    data: List[VideoPlaylistMembership]


class AlternativeUrlRequest(BaseModel):
    """Request body for setting an alternative URL on a video."""

    model_config = ConfigDict(strict=True)

    alternative_url: Optional[str] = Field(
        None,
        max_length=500,
        description="Alternative URL for unavailable video (max 500 characters). Set to null to clear.",
    )


# Rebuild models to resolve forward references
# This is required for Pydantic V2 with TYPE_CHECKING imports
def _rebuild_models() -> None:
    """Rebuild models after all imports are resolved."""
    from chronovista.api.schemas.topics import TopicSummary

    VideoListItem.model_rebuild()


_rebuild_models()
