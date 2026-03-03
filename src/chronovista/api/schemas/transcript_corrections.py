"""Transcript correction API request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from chronovista.models.enums import CorrectionType


class CorrectionSubmitRequest(BaseModel):
    """Request body for submitting a transcript correction."""

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    corrected_text: str = Field(
        ..., min_length=1, description="The corrected segment text"
    )
    correction_type: CorrectionType = Field(
        ..., strict=False, description="Category of correction"
    )
    correction_note: str | None = Field(
        default=None, description="Optional explanation"
    )
    corrected_by_user_id: str | None = Field(
        default=None, max_length=100, description="Optional user identifier"
    )

    @field_validator("correction_type")
    @classmethod
    def reject_revert_type(cls, v: CorrectionType) -> CorrectionType:
        """Prevent use of REVERT correction type in submit requests.

        Parameters
        ----------
        v : CorrectionType
            The correction type to validate.

        Returns
        -------
        CorrectionType
            The validated correction type.

        Raises
        ------
        ValueError
            If the correction type is REVERT.
        """
        if v == CorrectionType.REVERT:
            raise ValueError(
                "The 'revert' correction type cannot be used in submit requests. "
                "Use the dedicated revert endpoint instead."
            )
        return v


class CorrectionAuditRecord(BaseModel):
    """Response schema for a single correction audit record."""

    model_config = ConfigDict(strict=True, from_attributes=True)

    id: uuid.UUID
    video_id: str
    language_code: str
    segment_id: int | None
    correction_type: CorrectionType = Field(strict=False)
    original_text: str
    corrected_text: str
    correction_note: str | None
    corrected_by_user_id: str | None
    corrected_at: datetime
    version_number: int


class SegmentCorrectionState(BaseModel):
    """Current segment state after a correction mutation."""

    model_config = ConfigDict(strict=True)

    has_correction: bool
    effective_text: str


class CorrectionSubmitResponse(BaseModel):
    """Response wrapping the audit record and resulting segment state."""

    model_config = ConfigDict(strict=True)

    correction: CorrectionAuditRecord
    segment_state: SegmentCorrectionState


CorrectionRevertResponse = CorrectionSubmitResponse
"""Type alias for revert responses (identical structure to submit responses)."""
