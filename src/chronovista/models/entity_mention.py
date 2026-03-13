"""
Entity mention models for tracking named entity occurrences in transcript segments.

Defines Pydantic models for entity mentions detected in transcript text,
supporting detection method tracking, confidence scoring, and segment linkage.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import DetectionMethod
from .youtube_types import VideoId


class EntityMentionBase(BaseModel):
    """Base model for entity mention data."""

    entity_id: uuid.UUID = Field(
        ..., description="UUID of the named entity being mentioned"
    )
    segment_id: int = Field(
        ..., description="ID of the transcript segment containing the mention"
    )
    video_id: VideoId = Field(
        ..., description="YouTube video ID where the mention occurs"
    )
    language_code: str = Field(
        ...,
        min_length=2,
        max_length=10,
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
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
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
    def validate_confidence_range(cls, v: float) -> float:
        """Validate confidence is within valid range.

        Parameters
        ----------
        v : float
            The confidence value to validate.

        Returns
        -------
        float
            The validated confidence value.

        Raises
        ------
        ValueError
            If confidence is outside the [0.0, 1.0] range.
        """
        if v < 0.0 or v > 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EntityMentionCreate(EntityMentionBase):
    """Model for creating entity mentions. No extra fields beyond the base."""

    pass


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
