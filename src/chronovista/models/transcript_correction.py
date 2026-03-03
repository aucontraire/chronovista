"""
Pydantic models for transcript corrections.

This module provides Pydantic V2 models for transcript correction management,
following the Base/Create/Full model hierarchy per the project Constitution.

Transcript corrections are append-only (FR-018): no update model is provided.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationInfo

from chronovista.models.enums import CorrectionType


class TranscriptCorrectionBase(BaseModel):
    """Base model for transcript corrections with validation.

    Contains common fields and validators for all transcript correction
    operations. Follows the Base/Create/Full model hierarchy per the
    project Constitution.

    Notes
    -----
    Corrections are append-only (FR-018). No update operations are
    supported on this entity.
    """

    video_id: str = Field(
        ...,
        max_length=20,
        description="YouTube video ID",
    )
    language_code: str = Field(
        ...,
        max_length=10,
        description="BCP-47 language code for the transcript being corrected",
    )
    segment_id: int | None = Field(
        default=None,
        description="Optional reference to the transcript segment being corrected",
    )
    correction_type: CorrectionType = Field(
        ...,
        description="Category of correction applied",
    )
    original_text: str = Field(
        ...,
        description="Original transcript text before correction",
    )
    corrected_text: str = Field(
        ...,
        description="Corrected transcript text after applying the correction",
    )
    correction_note: str | None = Field(
        default=None,
        description="Optional human-readable explanation for the correction",
    )
    corrected_by_user_id: str | None = Field(
        default=None,
        max_length=100,
        description="Identifier of the user who made the correction",
    )
    version_number: int = Field(
        ...,
        ge=1,
        description="Version number of this correction (must be >= 1)",
    )

    @field_validator("version_number")
    @classmethod
    def validate_version_number(cls, v: int) -> int:
        """Ensure version_number is at least 1.

        Parameters
        ----------
        v : int
            The version_number value to validate.

        Returns
        -------
        int
            The validated version_number value.

        Raises
        ------
        ValueError
            If version_number is less than 1.
        """
        if v < 1:
            raise ValueError(
                f"version_number must be >= 1, got {v}"
            )
        return v

    @field_validator("corrected_text")
    @classmethod
    def validate_corrected_text_differs(
        cls, v: str, info: ValidationInfo
    ) -> str:
        """Ensure corrected_text is different from original_text (no-op prevention).

        Parameters
        ----------
        v : str
            The corrected_text value to validate.
        info : ValidationInfo
            Validation context containing other field values.

        Returns
        -------
        str
            The validated corrected_text value.

        Raises
        ------
        ValueError
            If corrected_text is identical to original_text.
        """
        original = info.data.get("original_text")
        if original is not None and v == original:
            raise ValueError(
                "corrected_text must differ from original_text; "
                "no-op corrections are not permitted"
            )
        return v

    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class TranscriptCorrectionCreate(TranscriptCorrectionBase):
    """Model for creating transcript corrections (used as creation input).

    Extends TranscriptCorrectionBase with no additional fields. This model
    is used as the input payload when recording a new correction. Updates
    are not supported (FR-018 — append-only entity).
    """


class TranscriptCorrectionRead(TranscriptCorrectionBase):
    """Full transcript correction model with database fields.

    Extends TranscriptCorrectionBase with database-specific fields such as
    the surrogate primary key and the timestamp recorded at insertion time.
    Used when reading corrections back from the database.
    """

    id: uuid.UUID = Field(
        ...,
        description="Surrogate primary key (UUIDv7)",
    )
    corrected_at: datetime = Field(
        ...,
        description="Timestamp when the correction was recorded",
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )


__all__ = [
    "TranscriptCorrectionBase",
    "TranscriptCorrectionCreate",
    "TranscriptCorrectionRead",
]
