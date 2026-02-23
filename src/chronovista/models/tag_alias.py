"""
Tag alias models for tag normalization.

Defines Pydantic models for tag aliases that map raw tag forms (as they appear
in YouTube data) to their canonical normalized representations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import CreationMethod


class TagAliasBase(BaseModel):
    """Base model for tag alias data."""

    raw_form: str = Field(
        ..., min_length=1, max_length=500, description="Original tag text as seen"
    )
    normalized_form: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized form for matching",
    )
    creation_method: CreationMethod = Field(
        default=CreationMethod.AUTO_NORMALIZE,
        description="How this alias was created",
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TagAliasCreate(TagAliasBase):
    """Model for creating tag aliases."""

    canonical_tag_id: uuid.UUID = Field(
        ..., description="FK to canonical_tag this alias resolves to"
    )
    normalization_version: int = Field(
        default=1, ge=1, description="Version of the normalization algorithm"
    )
    occurrence_count: int = Field(
        default=1, ge=0, description="How many times this raw form was seen"
    )


class TagAliasUpdate(BaseModel):
    """Model for updating tag aliases (PATCH-style, all fields optional)."""

    raw_form: Optional[str] = Field(default=None, min_length=1, max_length=500)
    normalized_form: Optional[str] = Field(
        default=None, min_length=1, max_length=500
    )
    canonical_tag_id: Optional[uuid.UUID] = None
    creation_method: Optional[CreationMethod] = None
    normalization_version: Optional[int] = Field(default=None, ge=1)
    occurrence_count: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TagAlias(TagAliasBase):
    """Full tag alias model with timestamps and identifiers."""

    id: uuid.UUID = Field(..., description="Tag alias UUID (UUIDv7)")
    canonical_tag_id: uuid.UUID = Field(
        ..., description="FK to canonical_tag this alias resolves to"
    )
    normalization_version: int = Field(
        ..., ge=1, description="Version of the normalization algorithm"
    )
    occurrence_count: int = Field(
        ..., ge=0, description="How many times this raw form was seen"
    )
    first_seen_at: datetime = Field(
        ..., description="When this raw form was first encountered"
    )
    last_seen_at: datetime = Field(
        ..., description="When this raw form was last encountered"
    )
    created_at: datetime = Field(..., description="When the record was created")

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
