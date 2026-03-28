"""
Video transcript models.

Defines Pydantic models for video transcripts with multi-language support,
quality indicators, and validation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import DownloadReason, LanguageCode, TrackKind, TranscriptType
from .transcript_source import RawTranscriptData, TranscriptSource
from .youtube_types import VideoId


class VideoTranscriptBase(BaseModel):
    """Base model for video transcripts."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    language_code: LanguageCode | str = Field(
        ...,
        description="BCP-47 language code (e.g., 'en-US', 'it-IT'). Can be enum or string for regional variants.",
    )
    transcript_text: str = Field(
        ..., min_length=1, description="Full transcript text content"
    )
    transcript_type: TranscriptType = Field(..., description="Type of transcript")
    download_reason: DownloadReason = Field(
        ..., description="Reason for transcript download"
    )
    confidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Transcript confidence/quality score (0.0-1.0)",
    )
    is_cc: bool = Field(
        default=False, description="Whether this is closed captions (higher quality)"
    )
    is_auto_synced: bool = Field(
        default=True, description="Whether transcript is auto-generated/synced"
    )
    track_kind: TrackKind = Field(
        default=TrackKind.STANDARD, description="Caption track type"
    )
    caption_name: str | None = Field(
        default=None, max_length=255, description="Caption track name or description"
    )

    @field_validator("language_code", mode="before")
    @classmethod
    def validate_language_code(cls, v: Any) -> Any:
        """Validate and normalize BCP-47 language code format.

        This validator runs before enum coercion to handle various input formats
        including lowercase strings from external APIs.
        """
        from .transcript_source import resolve_language_code

        if v is None or v == "":
            raise ValueError("Language code cannot be empty")

        # If already a LanguageCode enum, return as-is
        if isinstance(v, LanguageCode):
            return v

        # Convert string to proper LanguageCode enum
        if isinstance(v, str):
            # Basic BCP-47 validation
            parts = v.split("-")
            if len(parts) < 1 or len(parts) > 3:
                raise ValueError("Invalid BCP-47 language code format")

            # Language code should be 2-3 letters (not numbers)
            language = parts[0]
            if len(language) < 2 or len(language) > 3:
                raise ValueError("Language code must be 2-3 characters")
            if not language.isalpha():
                raise ValueError("Language code must contain only letters")

            # Use resolve_language_code to handle casing normalization
            # and map to valid LanguageCode enum values
            return resolve_language_code(v)

        # For any other type, return as-is and let enum validation handle it
        return v

    # Note: video_id validation is now handled by VideoId type

    @field_validator("transcript_text")
    @classmethod
    def validate_transcript_text(cls, v: str) -> str:
        """Validate transcript text is not empty."""
        if not v or not v.strip():
            raise ValueError("Transcript text cannot be empty")
        return v.strip()

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )


class VideoTranscriptCreate(VideoTranscriptBase):
    """Model for creating video transcripts."""

    pass


class VideoTranscriptUpdate(BaseModel):
    """Model for updating video transcripts."""

    transcript_text: str | None = Field(None, min_length=1)
    transcript_type: TranscriptType | None = None
    download_reason: DownloadReason | None = None
    confidence_score: float | None = Field(None, ge=0.0, le=1.0)
    is_cc: bool | None = None
    is_auto_synced: bool | None = None
    track_kind: TrackKind | None = None
    caption_name: str | None = Field(None, max_length=255)

    @field_validator("transcript_text")
    @classmethod
    def validate_transcript_text(cls, v: str | None) -> str | None:
        """Validate transcript text if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Transcript text cannot be empty")
        return v.strip() if v else v

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )


class VideoTranscript(VideoTranscriptBase):
    """Full video transcript model with timestamps."""

    downloaded_at: datetime = Field(
        ..., description="When the transcript was downloaded"
    )

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        use_enum_values=True,
        validate_assignment=True,
    )


class VideoTranscriptWithQuality(VideoTranscript):
    """Video transcript with computed quality metrics."""

    quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Computed quality score"
    )
    is_high_quality: bool = Field(
        ..., description="Whether transcript is considered high quality"
    )
    language_match_user_prefs: bool = Field(
        default=False, description="Whether language matches user preferences"
    )

    @field_validator("quality_score")
    @classmethod
    def validate_quality_score(cls, v: float) -> float:
        """Ensure quality score is within valid range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Quality score must be between 0.0 and 1.0")
        return v


class TranscriptSearchFilters(BaseModel):
    """Filters for searching transcripts."""

    video_ids: list[VideoId] | None = Field(
        default=None, description="Filter by video IDs"
    )
    language_codes: list[str] | None = Field(
        default=None, description="Filter by language codes"
    )
    transcript_types: list[TranscriptType] | None = Field(
        default=None, description="Filter by transcript types"
    )
    download_reasons: list[DownloadReason] | None = Field(
        default=None, description="Filter by download reasons"
    )
    track_kinds: list[TrackKind] | None = Field(
        default=None, description="Filter by track kinds"
    )
    min_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Minimum confidence score"
    )
    is_cc_only: bool | None = Field(
        default=None, description="Filter for closed captions only"
    )
    is_manual_only: bool | None = Field(
        default=None, description="Filter for manual transcripts only"
    )
    downloaded_after: datetime | None = Field(
        default=None, description="Filter by download date"
    )
    downloaded_before: datetime | None = Field(
        default=None, description="Filter by download date"
    )

    model_config = ConfigDict(use_enum_values=True)


class EnhancedVideoTranscriptBase(VideoTranscriptBase):
    """Enhanced video transcript model supporting multiple sources."""

    # New fields for hybrid approach
    source: TranscriptSource = Field(..., description="Source of transcript data")
    source_metadata: dict[str, Any] | None = Field(
        default=None, description="Additional source-specific metadata"
    )
    raw_transcript_data: dict[str, Any] | None = Field(
        default=None, description="Original raw data from source API"
    )
    plain_text_only: str = Field(
        ..., min_length=1, description="Transcript text without timestamps"
    )
    has_timestamps: bool = Field(
        default=True, description="Whether original data included timing information"
    )
    snippet_count: int | None = Field(
        default=None, ge=0, description="Number of transcript snippets"
    )
    total_duration: float | None = Field(
        default=None, ge=0.0, description="Total duration in seconds"
    )

    @classmethod
    def from_raw_transcript_data(
        cls, raw_data: RawTranscriptData, **additional_fields: Any
    ) -> EnhancedVideoTranscriptBase:
        """Create from RawTranscriptData object."""
        # Map transcript source to our existing enums
        transcript_type_mapping = {
            TranscriptSource.YOUTUBE_TRANSCRIPT_API: (
                TranscriptType.AUTO if raw_data.is_generated else TranscriptType.MANUAL
            ),
            TranscriptSource.YOUTUBE_DATA_API_V3: TranscriptType.MANUAL,  # Usually higher quality
            TranscriptSource.MANUAL_UPLOAD: TranscriptType.MANUAL,
            TranscriptSource.UNKNOWN: TranscriptType.AUTO,
        }

        # Define valid field names for this model (from both base classes)
        valid_fields = {
            # From VideoTranscriptBase
            "video_id",
            "language_code",
            "transcript_text",
            "transcript_type",
            "download_reason",
            "confidence_score",
            "is_cc",
            "is_auto_synced",
            "track_kind",
            "caption_name",
            # From EnhancedVideoTranscriptBase
            "source",
            "source_metadata",
            "raw_transcript_data",
            "plain_text_only",
            "has_timestamps",
            "snippet_count",
            "total_duration",
        }

        # Fields that we're setting explicitly in the constructor
        explicitly_set_fields = {
            "video_id",
            "language_code",
            "transcript_text",
            "plain_text_only",
            "transcript_type",
            "download_reason",
            "confidence_score",
            "is_cc",
            "is_auto_synced",
            "track_kind",
            "caption_name",
            "source",
            "source_metadata",
            "raw_transcript_data",
            "has_timestamps",
            "snippet_count",
            "total_duration",
        }

        # Filter additional_fields to only include valid field names
        # and exclude fields we're already setting explicitly
        filtered_additional_fields = {
            k: v
            for k, v in additional_fields.items()
            if k in valid_fields and k not in explicitly_set_fields
        }

        # Build the constructor arguments
        constructor_args = {
            "video_id": raw_data.video_id,
            "language_code": raw_data.language_code,
            "transcript_text": raw_data.plain_text,  # Use plain text version
            "plain_text_only": raw_data.plain_text,  # Store plain text separately
            "transcript_type": transcript_type_mapping.get(
                raw_data.source, TranscriptType.AUTO
            ),
            "download_reason": additional_fields.get(
                "download_reason", DownloadReason.USER_REQUEST
            ),
            "confidence_score": 0.95 if not raw_data.is_generated else 0.80,
            "is_cc": not raw_data.is_generated,
            "is_auto_synced": raw_data.is_generated,
            "track_kind": TrackKind.STANDARD,
            "caption_name": f"Transcript from {raw_data.source.value}",
            "source": raw_data.source,
            "source_metadata": raw_data.source_metadata,
            "raw_transcript_data": raw_data.model_dump(mode='json'),
            "has_timestamps": len(raw_data.snippets) > 0,
            "snippet_count": raw_data.snippet_count,
            "total_duration": raw_data.total_duration,
        }

        # Add any additional fields that aren't already set
        constructor_args.update(filtered_additional_fields)

        return cls(**constructor_args)


class EnhancedVideoTranscriptCreate(EnhancedVideoTranscriptBase):
    """Model for creating enhanced video transcripts."""

    pass


class EnhancedVideoTranscript(EnhancedVideoTranscriptBase):
    """Full enhanced video transcript model with timestamps."""

    downloaded_at: datetime = Field(
        ..., description="When the transcript was downloaded"
    )

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        validate_assignment=True,
    )


class TranscriptSourceComparison(BaseModel):
    """Model for comparing transcripts from different sources for the same video."""

    video_id: VideoId = Field(..., description="YouTube video ID (validated)")
    language_code: LanguageCode | str
    primary_source: TranscriptSource = Field(
        ..., description="Primary transcript source"
    )
    secondary_source: TranscriptSource = Field(
        ..., description="Secondary transcript source"
    )
    primary_transcript: EnhancedVideoTranscript
    secondary_transcript: EnhancedVideoTranscript

    # Comparison metrics
    text_similarity_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Text similarity score (0.0-1.0)"
    )
    length_difference_ratio: float | None = Field(
        None, description="Ratio of length difference"
    )
    timing_precision_comparison: dict[str, float | int | str] | None = Field(
        None, description="Comparison of timing precision"
    )
    quality_difference_score: float | None = Field(
        None, description="Quality difference assessment"
    )

    comparison_notes: str | None = Field(
        None, description="Additional notes about the comparison"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def recommended_source(self) -> TranscriptSource:
        """Determine which source is recommended based on comparison."""
        # Simple logic: prefer official API if available, otherwise third-party
        if self.secondary_source == TranscriptSource.YOUTUBE_DATA_API_V3:
            return self.secondary_source
        return self.primary_source

    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True,
    )
