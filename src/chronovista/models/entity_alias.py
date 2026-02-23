"""
Entity alias models for named entity resolution.

Defines Pydantic models for entity aliases that map alternative names
(variants, abbreviations, nicknames, etc.) to their canonical named entities.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import EntityAliasType


class EntityAliasBase(BaseModel):
    """Base model for entity alias data."""

    alias_name: str = Field(
        ..., min_length=1, max_length=500, description="Alternative name text"
    )
    alias_name_normalized: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized alias name for matching",
    )
    alias_type: EntityAliasType = Field(
        default=EntityAliasType.NAME_VARIANT,
        description="Type of alias relationship",
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EntityAliasCreate(EntityAliasBase):
    """Model for creating entity aliases."""

    entity_id: uuid.UUID = Field(
        ..., description="FK to named_entity this alias belongs to"
    )
    occurrence_count: int = Field(
        default=0, ge=0, description="How many times this alias was seen"
    )


class EntityAliasUpdate(BaseModel):
    """Model for updating entity aliases (PATCH-style, all fields optional)."""

    alias_name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    alias_name_normalized: Optional[str] = Field(
        default=None, min_length=1, max_length=500
    )
    alias_type: Optional[EntityAliasType] = None
    entity_id: Optional[uuid.UUID] = None
    occurrence_count: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EntityAlias(EntityAliasBase):
    """Full entity alias model with timestamps and identifiers."""

    id: uuid.UUID = Field(..., description="Entity alias UUID (UUIDv7)")
    entity_id: uuid.UUID = Field(
        ..., description="FK to named_entity this alias belongs to"
    )
    occurrence_count: int = Field(
        ..., ge=0, description="How many times this alias was seen"
    )
    first_seen_at: datetime = Field(
        ..., description="When this alias was first encountered"
    )
    last_seen_at: datetime = Field(
        ..., description="When this alias was last encountered"
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
