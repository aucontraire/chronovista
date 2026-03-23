"""
Entity mention models for tracking named entity occurrences in transcript segments.

Defines Pydantic models for entity mentions detected in transcript text,
supporting detection method tracking, confidence scoring, and segment linkage.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import DetectionMethod
from .youtube_types import VideoId


class EntityMentionBase(BaseModel):
    """Base model for entity mention data."""

    entity_id: uuid.UUID = Field(
        ..., description="UUID of the named entity being mentioned"
    )
    segment_id: int | None = Field(
        default=None,
        description="ID of the transcript segment containing the mention",
    )
    video_id: VideoId = Field(
        ..., description="YouTube video ID where the mention occurs"
    )
    language_code: str | None = Field(
        default=None,
        description="BCP-47 language code of the transcript segment",
    )
    mention_text: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Exact text span that triggered the mention",
    )
    detection_method: DetectionMethod = Field(
        default=DetectionMethod.RULE_MATCH,
        description="Method used to detect this mention",
    )
    confidence: float | None = Field(
        default=None,
        description="Confidence score of the detection (0.0 to 1.0)",
    )
    match_start: Optional[int] = Field(
        default=None,
        description="Character offset where the mention starts in segment text",
    )
    match_end: Optional[int] = Field(
        default=None,
        description="Character offset where the mention ends in segment text",
    )
    correction_id: Optional[uuid.UUID] = Field(
        default=None,
        description="UUID of the correction that created or updated this mention",
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float | None) -> float | None:
        """Validate confidence is within valid range.

        Parameters
        ----------
        v : float | None
            The confidence value to validate.

        Returns
        -------
        float | None
            The validated confidence value, or None for manual mentions.

        Raises
        ------
        ValueError
            If confidence is outside the [0.0, 1.0] range.
        """
        if v is None:
            return None
        if v < 0.0 or v > 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EntityMentionCreate(EntityMentionBase):
    """Model for creating entity mentions with manual vs automated validation."""

    @model_validator(mode="after")
    def validate_manual_fields(self) -> EntityMentionCreate:
        """Validate field constraints based on detection method.

        Manual mentions must have NULL segment_id, match_start, match_end,
        confidence, and language_code. Automated mentions must have a
        non-NULL segment_id.

        Returns
        -------
        EntityMentionCreate
            The validated instance.

        Raises
        ------
        ValueError
            If field constraints are violated for the detection method.
        """
        if self.detection_method == DetectionMethod.MANUAL:
            if self.segment_id is not None:
                raise ValueError(
                    "segment_id must be None for manual mentions"
                )
            if self.match_start is not None:
                raise ValueError(
                    "match_start must be None for manual mentions"
                )
            if self.match_end is not None:
                raise ValueError(
                    "match_end must be None for manual mentions"
                )
            if self.confidence is not None:
                raise ValueError(
                    "confidence must be None for manual mentions"
                )
            if self.language_code is not None:
                raise ValueError(
                    "language_code must be None for manual mentions"
                )
        else:
            if self.segment_id is None:
                raise ValueError(
                    "segment_id is required for non-manual mentions"
                )
        return self


class EntityMention(EntityMentionBase):
    """Full entity mention model with database-assigned fields."""

    id: uuid.UUID = Field(..., description="Entity mention UUID (UUIDv7)")
    created_at: datetime = Field(
        ..., description="Timestamp when the mention record was created"
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )


__all__ = [
    "EntityMentionBase",
    "EntityMentionCreate",
    "EntityMention",
]
