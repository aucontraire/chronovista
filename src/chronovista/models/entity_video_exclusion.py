"""Pydantic V2 models for manual entity↔video exclusions (Feature 091).

An exclusion is an explicit **negative association** — "this video is NOT this entity" —
the stored negative that the shared association definition subtracts. Per-(entity, video)
pair; it suppresses the video regardless of how it would otherwise match (mention, tag
link, or alias-tag name match).
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class EntityVideoExclusionCreate(BaseModel):
    """Input to create an exclusion. ``entity_id`` is supplied by the request path."""

    model_config = ConfigDict(strict=True)

    video_id: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="YouTube video ID to exclude from this entity",
    )
    reason: str | None = Field(
        default=None, description="Optional free-text note explaining the exclusion"
    )


class EntityVideoExclusion(BaseModel):
    """A stored exclusion record (one per entity-video pair)."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: uuid.UUID = Field(..., description="Named entity UUID")
    video_id: str = Field(..., description="YouTube video ID")
    excluded_by: str = Field(..., description="Actor who created the exclusion")
    excluded_at: datetime.datetime = Field(
        ..., description="When the exclusion was created"
    )
    reason: str | None = Field(default=None, description="Optional free-text note")
