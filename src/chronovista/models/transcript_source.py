"""
Transcript source models for handling different transcript API responses.

This module defines models for handling transcript data from different sources:
- Third-party APIs (like youtube-transcript-api)
- Official YouTube Data API v3 caption downloads
- Unified internal representation
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LanguageCode
from .youtube_types import CaptionId, VideoId


class TranscriptSource(str, Enum):
    """Sources for transcript data."""

    YOUTUBE_TRANSCRIPT_API = "youtube_transcript_api"  # Third-party library
    YOUTUBE_DATA_API_V3 = "youtube_data_api_v3"  # Official Google API
    MANUAL_UPLOAD = "manual_upload"  # User-provided
    UNKNOWN = "unknown"


class TranscriptSnippet(BaseModel):
    """Individual transcript snippet with timing information."""

    text: str = Field(..., min_length=1, description="Transcript text content")
    start: float = Field(..., ge=0.0, description="Start time in seconds")
    duration: float = Field(..., gt=0.0, description="Duration in seconds")

    @property
    def end(self) -> float:
        """Calculate end time from start + duration."""
        return self.start + self.duration

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Validate text is not empty after stripping."""
        if not v or not v.strip():
            raise ValueError("Snippet text cannot be empty")
        return v.strip()

    model_config = ConfigDict(
        validate_assignment=True,
    )


class RawTranscriptData(BaseModel):
    """Raw transcript data from external APIs before processing."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    language_code: LanguageCode = Field(..., description="BCP-47 language code")
    language_name: Optional[str] = Field(
        None, description="Human-readable language name"
    )
    snippets: List[TranscriptSnippet] = Field(..., min_length=1)
    is_generated: bool = Field(..., description="Whether transcript is auto-generated")
    is_translatable: Optional[bool] = Field(
        None, description="Whether can be translated"
    )
    source: TranscriptSource = Field(..., description="Source of transcript data")
    source_metadata: Optional[dict] = Field(
        None, description="Additional source-specific data"
    )
    retrieved_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    @property
    def total_duration(self) -> float:
        """Calculate total duration of transcript."""
        if not self.snippets:
            return 0.0
        last_snippet = self.snippets[-1]
        return last_snippet.start + last_snippet.duration

    @property
    def plain_text(self) -> str:
        """Get transcript as plain text without timestamps."""
        return " ".join(snippet.text for snippet in self.snippets)

    @property
    def snippet_count(self) -> int:
        """Get number of transcript snippets."""
        return len(self.snippets)

    def get_text_at_time(self, time_seconds: float) -> Optional[str]:
        """Get transcript text at specific time."""
        for snippet in self.snippets:
            if snippet.start <= time_seconds <= snippet.end:
                return snippet.text
        return None

    model_config = ConfigDict(
        validate_assignment=True,
    )


class YouTubeTranscriptApiResponse(BaseModel):
    """Model for youtube-transcript-api library responses."""

    video_id: VideoId
    language: str
    language_code: str  # Will be converted to LanguageCode enum
    is_generated: bool
    snippets: List[
        dict
    ]  # Raw format: [{'text': str, 'start': float, 'duration': float}]

    def to_raw_transcript_data(self) -> RawTranscriptData:
        """Convert to unified RawTranscriptData format."""
        # Convert language code string to enum
        try:
            lang_code = LanguageCode(self.language_code.lower())
        except ValueError:
            # Fallback to English if language code not supported
            lang_code = LanguageCode.ENGLISH

        # Convert snippet dictionaries to TranscriptSnippet objects
        transcript_snippets = [
            TranscriptSnippet(
                text=snippet["text"],
                start=snippet["start"],
                duration=snippet["duration"],
            )
            for snippet in self.snippets
        ]

        return RawTranscriptData(
            video_id=self.video_id,
            language_code=lang_code,
            language_name=self.language,
            snippets=transcript_snippets,
            is_generated=self.is_generated,
            is_translatable=None,  # Not provided by this API
            source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
            source_metadata={
                "original_language": self.language,
                "original_language_code": self.language_code,
            },
        )


class YouTubeDataApiCaptionMetadata(BaseModel):
    """Model for YouTube Data API v3 caption metadata."""

    id: CaptionId = Field(..., description="Caption track ID (validated)")
    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    language: str = Field(..., description="Language code from API")
    name: str = Field(default="", description="Caption track name")
    track_kind: str = Field(..., description="Caption track kind")
    is_cc: bool = Field(default=False, description="Whether closed captions")
    is_large: bool = Field(default=False)
    is_easy_reader: bool = Field(default=False)
    is_draft: bool = Field(default=False)
    is_auto_synced: bool = Field(default=False, description="Whether auto-generated")
    status: str = Field(..., description="Caption status")
    last_updated: Optional[datetime] = Field(None)

    @property
    def is_generated(self) -> bool:
        """Determine if caption is auto-generated."""
        return self.track_kind == "asr" or self.is_auto_synced


class YouTubeDataApiCaptionFile(BaseModel):
    """Model for parsed YouTube Data API v3 caption file content."""

    caption_id: CaptionId = Field(..., description="Caption track ID (validated)")
    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    file_format: str = Field(..., description="Original file format (srt, vtt, etc.)")
    raw_content: str = Field(..., description="Raw file content")
    parsed_snippets: List[TranscriptSnippet] = Field(..., min_length=1)
    metadata: YouTubeDataApiCaptionMetadata

    def to_raw_transcript_data(self) -> RawTranscriptData:
        """Convert to unified RawTranscriptData format."""
        # Convert language code to enum
        try:
            lang_code = LanguageCode(self.metadata.language.lower())
        except ValueError:
            lang_code = LanguageCode.ENGLISH

        return RawTranscriptData(
            video_id=self.video_id,
            language_code=lang_code,
            language_name=self.metadata.language,
            snippets=self.parsed_snippets,
            is_generated=self.metadata.is_generated,
            is_translatable=None,  # Would need additional API call to determine
            source=TranscriptSource.YOUTUBE_DATA_API_V3,
            source_metadata={
                "caption_id": self.caption_id,
                "file_format": self.file_format,
                "track_kind": self.metadata.track_kind,
                "is_cc": self.metadata.is_cc,
                "last_updated": (
                    self.metadata.last_updated.isoformat()
                    if self.metadata.last_updated
                    else None
                ),
            },
        )


class TranscriptComparison(BaseModel):
    """Model for comparing transcripts from different sources."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    language_code: LanguageCode
    primary_transcript: RawTranscriptData
    secondary_transcript: RawTranscriptData
    comparison_metrics: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    @property
    def text_similarity_score(self) -> Optional[float]:
        """Get text similarity score if calculated."""
        return self.comparison_metrics.get("text_similarity")

    @property
    def timing_difference_avg(self) -> Optional[float]:
        """Get average timing difference if calculated."""
        return self.comparison_metrics.get("timing_difference_avg")

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TranscriptSearchFilters(BaseModel):
    """Filters for searching transcript data."""

    video_ids: Optional[List[VideoId]] = Field(None, description="Filter by video IDs")
    language_codes: Optional[List[LanguageCode]] = Field(
        None, description="Filter by languages"
    )
    sources: Optional[List[TranscriptSource]] = Field(
        None, description="Filter by sources"
    )
    is_generated_only: Optional[bool] = Field(
        None, description="Filter by generation type"
    )
    min_duration: Optional[float] = Field(None, ge=0.0, description="Minimum duration")
    text_search: Optional[str] = Field(None, description="Search in transcript text")
    retrieved_after: Optional[datetime] = Field(
        None, description="Retrieved after date"
    )
    retrieved_before: Optional[datetime] = Field(
        None, description="Retrieved before date"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
