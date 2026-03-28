"""
Canonical tag models for tag normalization.

Defines Pydantic models for canonical tags that represent the normalized,
deduplicated form of video tags with lifecycle management and merge tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import EntityType, TagStatus


class CanonicalTagBase(BaseModel):
    """Base model for canonical tag data."""

    canonical_form: str = Field(
        ..., min_length=1, max_length=500, description="Display form of the tag"
    )
    normalized_form: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Machine key (lowercased, accent-folded)",
    )
    entity_type: EntityType | None = Field(
        default=None, description="Entity type classification (nullable)"
    )
    status: TagStatus = Field(
        default=TagStatus.ACTIVE, description="Lifecycle status of the canonical tag"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class CanonicalTagCreate(CanonicalTagBase):
    """Model for creating canonical tags."""

    alias_count: int = Field(default=1, ge=0, description="Number of known aliases")
    video_count: int = Field(
        default=0, ge=0, description="Number of videos using this tag"
    )
    entity_id: uuid.UUID | None = Field(
        default=None, description="Link to named entity"
    )
    merged_into_id: uuid.UUID | None = Field(
        default=None, description="Target tag ID if merged"
    )

    @model_validator(mode="after")
    def merged_status_requires_target(self) -> CanonicalTagCreate:
        """Validate that merged status has a merge target (FR-027)."""
        if self.status == TagStatus.MERGED and self.merged_into_id is None:
            raise ValueError(
                "merged_into_id is required when status is 'merged'"
            )
        return self


class CanonicalTagUpdate(BaseModel):
    """Model for updating canonical tags (PATCH-style, all fields optional)."""

    canonical_form: str | None = Field(
        default=None, min_length=1, max_length=500
    )
    normalized_form: str | None = Field(
        default=None, min_length=1, max_length=500
    )
    entity_type: EntityType | None = None
    status: TagStatus | None = None
    alias_count: int | None = Field(default=None, ge=0)
    video_count: int | None = Field(default=None, ge=0)
    entity_id: uuid.UUID | None = None
    merged_into_id: uuid.UUID | None = None

    model_config = ConfigDict(
        validate_assignment=True,
    )


class CanonicalTag(CanonicalTagBase):
    """Full canonical tag model with timestamps and identifiers."""

    id: uuid.UUID = Field(..., description="Canonical tag UUID (UUIDv7)")
    alias_count: int = Field(..., ge=0, description="Number of known aliases")
    video_count: int = Field(
        ..., ge=0, description="Number of videos using this tag"
    )
    entity_id: uuid.UUID | None = Field(
        default=None, description="Link to named entity"
    )
    merged_into_id: uuid.UUID | None = Field(
        default=None, description="Target tag ID if merged"
    )
    created_at: datetime = Field(..., description="When the record was created")
    updated_at: datetime = Field(..., description="When the record was last updated")

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )

    @model_validator(mode="after")
    def merged_status_requires_target(self) -> CanonicalTag:
        """Validate that merged status has a merge target (FR-027)."""
        if self.status == TagStatus.MERGED and self.merged_into_id is None:
            raise ValueError(
                "merged_into_id is required when status is 'merged'"
            )
        return self

    @model_validator(mode="after")
    def no_self_merge(self) -> CanonicalTag:
        """Validate that a tag cannot be merged into itself (FR-028)."""
        if self.merged_into_id is not None and self.merged_into_id == self.id:
            raise ValueError("A canonical tag cannot be merged into itself")
        return self
