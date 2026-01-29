"""
Pydantic models for transcript segments.

This module provides Pydantic V2 models for transcript segment management,
following the Base/Create/Full model hierarchy per the project Constitution.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo

from chronovista.models.youtube_types import VideoId

if TYPE_CHECKING:
    pass


class TranscriptSegmentBase(BaseModel):
    """Base model for transcript segments with validation.

    Contains common fields and validators for all transcript segment operations.
    Follows the Base/Create/Full model hierarchy per the project Constitution.
    """

    video_id: VideoId = Field(..., description="YouTube video ID")
    language_code: str = Field(
        ...,
        min_length=2,
        max_length=10,
        description="BCP-47 language code",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Segment text content",
    )
    start_time: float = Field(
        ...,
        ge=0.0,
        description="Start time in seconds",
    )
    duration: float = Field(
        ...,
        ge=0.0,
        description="Duration in seconds (zero allowed per FR-EDGE-07)",
    )
    end_time: float = Field(
        ...,
        ge=0.0,
        description="End time in seconds (start + duration)",
    )
    sequence_number: int = Field(
        ...,
        ge=0,
        description="Order within transcript (0-indexed)",
    )

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: float, info: ValidationInfo) -> float:
        """Ensure end_time equals start_time + duration.

        Parameters
        ----------
        v : float
            The end_time value to validate.
        info : ValidationInfo
            Validation context containing other field values.

        Returns
        -------
        float
            The validated end_time value.

        Raises
        ------
        ValueError
            If end_time does not equal start_time + duration within tolerance.
        """
        start = info.data.get("start_time")
        duration = info.data.get("duration")
        if start is not None and duration is not None:
            expected = start + duration
            if abs(v - expected) > 0.001:  # Float tolerance
                raise ValueError(
                    f"end_time ({v}) must equal start_time + duration ({expected})"
                )
        return v

    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class TranscriptSegmentCreate(TranscriptSegmentBase):
    """Model for creating transcript segments (used in migration).

    Extends TranscriptSegmentBase with a factory method for creating
    segments from raw JSONB snippet data.
    """

    @classmethod
    def from_snippet(
        cls,
        video_id: VideoId,
        language_code: str,
        snippet: Dict[str, Any],
        sequence_number: int,
    ) -> "TranscriptSegmentCreate":
        """Create segment from raw JSONB snippet.

        Parameters
        ----------
        video_id : VideoId
            YouTube video identifier.
        language_code : str
            BCP-47 language code.
        snippet : Dict[str, Any]
            Raw snippet from raw_transcript_data.snippets.
            Expected format: {"text": str, "start": float, "duration": float}
        sequence_number : int
            Order within transcript.

        Returns
        -------
        TranscriptSegmentCreate
            Validated segment ready for database insertion.
        """
        start_time = float(snippet["start"])
        duration = float(snippet["duration"])
        return cls(
            video_id=video_id,
            language_code=language_code,
            text=snippet["text"],
            start_time=start_time,
            duration=duration,
            end_time=start_time + duration,
            sequence_number=sequence_number,
        )


class TranscriptSegment(TranscriptSegmentBase):
    """Full transcript segment model with database fields.

    Extends TranscriptSegmentBase with database-specific fields like
    id, has_correction, corrected_text, and created_at.
    """

    id: int = Field(..., description="Database segment ID")
    has_correction: bool = Field(
        default=False,
        description="Whether this segment has been corrected",
    )
    corrected_text: Optional[str] = Field(
        default=None,
        description="User-corrected text (Phase 3)",
    )
    created_at: datetime = Field(
        ...,
        description="When segment was created",
    )

    @property
    def display_text(self) -> str:
        """Return corrected text if available, otherwise original.

        Returns
        -------
        str
            The corrected_text if has_correction is True and corrected_text
            is not None, otherwise the original text.
        """
        if self.has_correction and self.corrected_text is not None:
            return self.corrected_text
        return self.text

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )


class TranscriptSegmentResponse(BaseModel):
    """Response model for CLI/API output.

    Provides a simplified representation of transcript segments
    suitable for display in CLI or API responses.
    """

    segment_id: int = Field(..., description="Database segment ID")
    text: str = Field(..., description="Segment text (corrected if available)")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    start_formatted: str = Field(..., description="Formatted start time (e.g., '0:01:30')")
    end_formatted: str = Field(..., description="Formatted end time (e.g., '0:01:32')")

    @classmethod
    def from_segment(cls, segment: TranscriptSegment) -> "TranscriptSegmentResponse":
        """Create response from segment model.

        Parameters
        ----------
        segment : TranscriptSegment
            The full segment model to convert.

        Returns
        -------
        TranscriptSegmentResponse
            A response model suitable for CLI/API output.
        """
        from chronovista.services.segment_service import format_timestamp

        return cls(
            segment_id=segment.id,
            text=segment.display_text,
            start_time=segment.start_time,
            end_time=segment.end_time,
            duration=segment.duration,
            start_formatted=format_timestamp(segment.start_time),
            end_formatted=format_timestamp(segment.end_time),
        )

    model_config = ConfigDict(
        frozen=True,
    )


__all__ = [
    "TranscriptSegmentBase",
    "TranscriptSegmentCreate",
    "TranscriptSegment",
    "TranscriptSegmentResponse",
]
