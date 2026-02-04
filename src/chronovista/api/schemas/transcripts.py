"""Transcript API response schemas."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict

from chronovista.api.schemas.responses import ApiResponse


class TranscriptLanguage(BaseModel):
    """Available transcript language."""

    model_config = ConfigDict(strict=True)

    language_code: str  # BCP-47 code (e.g., "en-US")
    language_name: str  # Human name (e.g., "English (US)")
    transcript_type: str  # "manual", "auto_synced", "auto_generated"
    is_translatable: bool  # Can be translated
    downloaded_at: datetime


class TranscriptLanguagesResponse(ApiResponse[List[TranscriptLanguage]]):
    """Response for transcript languages endpoint."""

    pass


class TranscriptFull(BaseModel):
    """Full transcript with metadata."""

    model_config = ConfigDict(strict=True)

    video_id: str
    language_code: str
    transcript_type: str
    full_text: str  # Concatenated segment text
    segment_count: int
    downloaded_at: datetime


class TranscriptResponse(ApiResponse[TranscriptFull]):
    """Response for full transcript endpoint."""

    pass


class TranscriptSegment(BaseModel):
    """Single transcript segment."""

    model_config = ConfigDict(strict=True)

    id: int  # Segment ID
    text: str  # Segment text
    start_time: float  # Start time in seconds
    end_time: float  # End time in seconds
    duration: float  # Segment duration


class SegmentListResponse(ApiResponse[List[TranscriptSegment]]):
    """Response for transcript segments endpoint."""

    pass
