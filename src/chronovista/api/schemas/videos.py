"""Video API response schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from chronovista.api.schemas.responses import ApiResponse


class TranscriptSummary(BaseModel):
    """Transcript availability summary for a video."""

    model_config = ConfigDict(strict=True)

    count: int  # Number of transcripts
    languages: List[str]  # Available language codes (BCP-47)
    has_manual: bool  # Any manual/CC transcripts?


class VideoListItem(BaseModel):
    """Video summary for list view."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    video_id: str  # 11-char YouTube ID
    title: str
    channel_id: Optional[str]  # 24-char channel ID (can be null for orphaned)
    channel_title: Optional[str]  # Channel name
    upload_date: datetime
    duration: int  # Seconds
    view_count: Optional[int]
    transcript_summary: TranscriptSummary


class VideoListResponse(ApiResponse[List[VideoListItem]]):
    """Response for video list endpoint."""

    pass


class VideoDetail(BaseModel):
    """Full video details."""

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
    default_language: Optional[str]
    made_for_kids: bool
    transcript_summary: TranscriptSummary


class VideoDetailResponse(ApiResponse[VideoDetail]):
    """Response for video detail endpoint."""

    pass
