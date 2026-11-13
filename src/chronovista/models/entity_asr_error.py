"""Entity ASR-error models (Feature 110).

Pydantic models for confirmed ASR mis-transcriptions of entity names, stored in
their own dedicated table (``entity_asr_errors``) rather than mixed among names in
``entity_aliases``. These strings are discovery input for the transcript-corrections
flow and must never be used as name-match patterns — a separation the schema enforces
(the table has no ``alias_type``).

Unlike :mod:`chronovista.models.entity_alias`, there is no ``alias_type`` (the table
is the type) and no ``occurrence_count`` (a derived, unread counter on the old store;
dropped by the Feature 110 decision rather than carried as recompute-to-zero garbage).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EntityAsrErrorBase(BaseModel):
    """Base model for entity ASR-error data."""

    alias_name: str = Field(
        ..., min_length=1, max_length=500, description="The garbled (ASR-error) string"
    )
    alias_name_normalized: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Normalized form of the garbled string for duplicate detection",
    )
    case_sensitive: bool = Field(
        default=False,
        description=(
            "When true, this form matches only the exact casing stored in "
            "alias_name. Defaults to false (case-insensitive), mirroring the "
            "name store's historical behaviour."
        ),
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EntityAsrErrorCreate(EntityAsrErrorBase):
    """Model for creating entity ASR-error rows."""

    entity_id: uuid.UUID = Field(
        ..., description="FK to the named_entity this ASR-error form belongs to"
    )


class EntityAsrErrorUpdate(BaseModel):
    """Model for updating entity ASR-error rows (PATCH-style, all fields optional)."""

    alias_name: str | None = Field(default=None, min_length=1, max_length=500)
    alias_name_normalized: str | None = Field(
        default=None, min_length=1, max_length=500
    )
    entity_id: uuid.UUID | None = None
    case_sensitive: bool | None = None

    model_config = ConfigDict(
        validate_assignment=True,
    )


class EntityAsrError(EntityAsrErrorBase):
    """Full entity ASR-error model with timestamps and identifiers."""

    id: uuid.UUID = Field(..., description="Entity ASR-error UUID (UUIDv7)")
    entity_id: uuid.UUID = Field(
        ..., description="FK to the named_entity this ASR-error form belongs to"
    )
    first_seen_at: datetime = Field(
        ..., description="When this form was first encountered"
    )
    last_seen_at: datetime = Field(
        ..., description="When this form was last encountered"
    )

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
