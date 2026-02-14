"""Search API response schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from chronovista.api.schemas.responses import ApiResponse


class SearchResultSegment(BaseModel):
    """Search result with video context."""

    model_config = ConfigDict(strict=True)

    segment_id: int
    video_id: str
    video_title: str
    channel_title: Optional[str]
    language_code: str
    text: str  # Matching segment text
    start_time: float
    end_time: float
    context_before: Optional[str]  # Previous segment text (up to 200 chars)
    context_after: Optional[str]  # Next segment text (up to 200 chars)
    match_count: int  # Number of query terms matched
    video_upload_date: datetime  # For client-side grouping
    availability_status: str = "available"


class SearchResponse(ApiResponse[List[SearchResultSegment]]):
    """Response for segment search endpoint."""

    model_config = ConfigDict(strict=True)

    available_languages: List[str]  # All unique languages in full result set


class TitleSearchResult(BaseModel):
    """Search result from matching video titles."""

    model_config = ConfigDict(strict=True)

    video_id: str
    title: str
    channel_title: Optional[str]
    upload_date: datetime
    availability_status: str = "available"


class TitleSearchResponse(BaseModel):
    """Response for title search endpoint."""

    model_config = ConfigDict(strict=True)

    data: List[TitleSearchResult]
    total_count: int


class DescriptionSearchResult(BaseModel):
    """Search result from matching video descriptions with snippet."""

    model_config = ConfigDict(strict=True)

    video_id: str
    title: str
    channel_title: Optional[str]
    upload_date: datetime
    snippet: str
    availability_status: str = "available"


class DescriptionSearchResponse(BaseModel):
    """Response for description search endpoint."""

    model_config = ConfigDict(strict=True)

    data: List[DescriptionSearchResult]
    total_count: int
