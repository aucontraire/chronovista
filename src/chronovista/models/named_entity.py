"""
Named entity models for entity extraction and management.

Defines Pydantic models for named entities discovered from tags and transcripts,
supporting entity resolution, merge tracking, and confidence scoring.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import DiscoveryMethod, EntityType, TagStatus


class NamedEntityBase(BaseModel):
    """Base model for named entity data."""

    canonical_name: str = Field(
        ..., min_length=1, max_length=500, description="Display name of the entity"
    )
    canonical_name_normalized: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized name for matching",
    )
    entity_type: EntityType = Field(
        ..., description="Entity type classification (required, not nullable)"
    )
    discovery_method: DiscoveryMethod = Field(
        default=DiscoveryMethod.MANUAL,
        description="How this entity was discovered",
    )
    status: TagStatus = Field(
        default=TagStatus.ACTIVE, description="Lifecycle status of the entity"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class NamedEntityCreate(NamedEntityBase):
    """Model for creating named entities."""

    entity_subtype: Optional[str] = Field(
        default=None, max_length=255, description="Finer-grained subtype"
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable description"
    )
    external_ids: Dict[str, Any] = Field(
        default_factory=dict,
        description="External identifiers (Wikidata QID, MusicBrainz, etc.)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    merged_into_id: Optional[uuid.UUID] = Field(
        default=None, description="Target entity ID if merged"
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        """Validate confidence is within valid range."""
        if v < 0.0 or v > 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v

    @model_validator(mode="after")
    def merged_status_requires_target(self) -> NamedEntityCreate:
        """Validate that merged status has a merge target (FR-027)."""
        if self.status == TagStatus.MERGED and self.merged_into_id is None:
            raise ValueError(
                "merged_into_id is required when status is 'merged'"
            )
        return self


class NamedEntityUpdate(BaseModel):
    """Model for updating named entities (PATCH-style, all fields optional)."""

    canonical_name: Optional[str] = Field(
        default=None, min_length=1, max_length=500
    )
    canonical_name_normalized: Optional[str] = Field(
        default=None, min_length=1, max_length=500
    )
    entity_type: Optional[EntityType] = None
    discovery_method: Optional[DiscoveryMethod] = None
    status: Optional[TagStatus] = None
    entity_subtype: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    external_ids: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    merged_into_id: Optional[uuid.UUID] = None
    mention_count: Optional[int] = Field(default=None, ge=0)
    video_count: Optional[int] = Field(default=None, ge=0)
    channel_count: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(
        validate_assignment=True,
    )


class NamedEntity(NamedEntityBase):
    """Full named entity model with timestamps and identifiers."""

    id: uuid.UUID = Field(..., description="Named entity UUID (UUIDv7)")
    entity_subtype: Optional[str] = Field(
        default=None, max_length=255, description="Finer-grained subtype"
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable description"
    )
    external_ids: Dict[str, Any] = Field(
        default_factory=dict,
        description="External identifiers (Wikidata QID, MusicBrainz, etc.)",
    )
    mention_count: int = Field(
        ..., ge=0, description="Total mentions across all sources"
    )
    video_count: int = Field(
        ..., ge=0, description="Number of videos referencing this entity"
    )
    channel_count: int = Field(
        ..., ge=0, description="Number of channels referencing this entity"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    merged_into_id: Optional[uuid.UUID] = Field(
        default=None, description="Target entity ID if merged"
    )
    created_at: datetime = Field(..., description="When the record was created")
    updated_at: datetime = Field(..., description="When the record was last updated")

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        """Validate confidence is within valid range."""
        if v < 0.0 or v > 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v

    @model_validator(mode="after")
    def merged_status_requires_target(self) -> NamedEntity:
        """Validate that merged status has a merge target (FR-027)."""
        if self.status == TagStatus.MERGED and self.merged_into_id is None:
            raise ValueError(
                "merged_into_id is required when status is 'merged'"
            )
        return self

    @model_validator(mode="after")
    def no_self_merge(self) -> NamedEntity:
        """Validate that an entity cannot be merged into itself (FR-028)."""
        if self.merged_into_id is not None and self.merged_into_id == self.id:
            raise ValueError("A named entity cannot be merged into itself")
        return self
