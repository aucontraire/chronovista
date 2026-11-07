"""API schemas for the novel-relationship candidate queue (Feature 107, read-only).

The queue asserts nothing about a pair beyond "candidate": ``status`` is a literal
``"candidate"`` and no verdict is ever exposed by the API in this MVP. Each item
carries its interpretability provenance (channel + N) so a lift is never shown bare.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EntitySummary(BaseModel):
    """Minimal entity identity for display + navigation to the entity detail page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_name: str
    entity_type: str


class RelationshipCandidateItem(BaseModel):
    """One ranked candidate row with the evidence needed to judge it in place."""

    id: uuid.UUID
    entity_a: EntitySummary
    entity_b: EntitySummary
    shared_video_count: int
    lift: float
    both_typed_eligible: bool
    kb_corroboration_count: int
    kb_corroboration_detail: list[str] = Field(
        default_factory=list,
        description="Captured fields on which the pair shares a referent",
    )
    channel: str
    channel_video_universe: int = Field(
        ...,
        description="N — the denominator the lift was computed against (provenance)",
    )
    status: Literal["candidate"] = Field(
        default="candidate",
        description="Always 'candidate' — the MVP exposes no verdict",
    )


class RelationshipCandidateListResponse(BaseModel):
    """A lift-ranked page of candidates plus pagination + generation freshness."""

    items: list[RelationshipCandidateItem]
    total: int = Field(
        ..., description="Total qualifying candidates matching the filters"
    )
    limit: int
    offset: int
    generated_at: datetime | None = Field(
        default=None,
        description="When the set was last generated, so the viewer knows its age",
    )
